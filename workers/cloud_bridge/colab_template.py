"""
Google Colab Template — CineOS Cloud GPU Worker

Run this script in a Google Colab GPU runtime cell. It installs ComfyUI
with FLUX + ControlNet + IP Adapter + LoRA + Face Detailer, RealESRGAN
for super-resolution, sets up an ngrok tunnel, and exposes a REST API
that the Cloud Worker Bridge can dispatch jobs to.

Usage:
  1. Open this in Colab
  2. Set your ngrok auth token and cineos_api_key below
  3. Run all cells
  4. Copy the printed ngrok URL into your .env as COLAB_COMFYUI_ENDPOINT
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 1 — Configuration
# ═══════════════════════════════════════════════════════════════════════════════

NGROK_AUTH_TOKEN = ""  # Get free token at https://ngrok.com
CINEOS_API_KEY = ""    # Must match COLAB_API_KEY in your .env
INACTIVITY_TIMEOUT_MINUTES = 15
PORT = 8188
API_PORT = 8199

print("Cell 1: Configuration set")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 2 — Install Dependencies
# ═══════════════════════════════════════════════════════════════════════════════

import subprocess
import sys
import os

def run_cmd(cmd, desc=""):
    if desc:
        print(f"Installing {desc}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Warning: {result.stderr[:200]}")
    return result.returncode == 0

# System dependencies
run_cmd("apt-get update -qq", "system packages")
run_cmd("apt-get install -y -qq aria2 libgl1-mesa-glx libglib2.0-0", "system libs")

# Python packages for the REST API
run_cmd(f"{sys.executable} -m pip install -q flask flask-cors pyngrok requests", "Flask + ngrok")

# RealESRGAN
if not os.path.exists("/content/Real-ESRGAN"):
    run_cmd("git clone --depth 1 https://github.com/xinntao/Real-ESRGAN.git /content/Real-ESRGAN", "RealESRGAN")
    run_cmd(f"{sys.executable} -m pip install -q basicsr facexlib gfpgan", "RealESRGAN deps")
    run_cmd(f"{sys.executable} -m pip install -q -e /content/Real-ESRGAN", "RealESRGAN install")

# ComfyUI
if not os.path.exists("/content/ComfyUI"):
    run_cmd("git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /content/ComfyUI", "ComfyUI")
    run_cmd(f"{sys.executable} -m pip install -q -r /content/ComfyUI/requirements.txt", "ComfyUI deps")

# ComfyUI Manager (for easy node installation)
if not os.path.exists("/content/ComfyUI/custom_nodes/ComfyUI-Manager"):
    run_cmd(
        "git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git "
        "/content/ComfyUI/custom_nodes/ComfyUI-Manager",
        "ComfyUI Manager",
    )

print("\nCell 2: Core dependencies installed")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 3 — Install Custom Nodes (FLUX, ControlNet, IP-Adapter, LoRA, Face Detailer)
# ═══════════════════════════════════════════════════════════════════════════════

CUSTOM_NODES_DIR = "/content/ComfyUI/custom_nodes"

custom_nodes = {
    "ComfyUI-IPAdapter-Plus": "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git",
    "ComfyUI-FaceDetailer": "https://github.com/dsdish/comfyui-FaceDetailer.git",
    "comfyui_controlnet_aux": "https://github.com/Fannovel16/comfyui_controlnet_aux.git",
}

for name, url in custom_nodes.items():
    target = f"{CUSTOM_NODES_DIR}/{name}"
    if not os.path.exists(target):
        run_cmd(f"git clone --depth 1 {url} {target}", f"Custom node: {name}")

# Install custom node deps
for name in custom_nodes:
    req = f"{CUSTOM_NODES_DIR}/{name}/requirements.txt"
    if os.path.exists(req):
        run_cmd(f"{sys.executable} -m pip install -q -r {req}", f"{name} deps")

print("\nCell 3: Custom nodes installed")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 4 — Download Models
# ═══════════════════════════════════════════════════════════════════════════════

COMFYUI_DIR = "/content/ComfyUI"
MODELS_DIR = f"{COMFYUI_DIR}/models"

model_downloads = [
    # Checkpoints
    {
        "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors",
        "dest": f"{MODELS_DIR}/checkpoints/sd_xl_base_1.0.safetensors",
        "desc": "SDXL Base 1.0",
    },
    # VAE
    {
        "url": "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors",
        "dest": f"{MODELS_DIR}/vae/sdxl_vae.safetensors",
        "desc": "SDXL VAE",
    },
    # CLIP
    {
        "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors",
        "dest": f"{MODELS_DIR}/clip/clip_l.safetensors",
        "desc": "CLIP-L encoder",
    },
    {
        "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors",
        "dest": f"{MODELS_DIR}/clip/t5xxl_fp16.safetensors",
        "desc": "T5-XXL encoder",
    },
    # ControlNet
    {
        "url": "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_canny.pth",
        "dest": f"{MODELS_DIR}/controlnet/control_v11p_sd15_canny.pth",
        "desc": "ControlNet Canny",
    },
    {
        "url": "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_openpose.pth",
        "dest": f"{MODELS_DIR}/controlnet/control_v11p_sd15_openpose.pth",
        "desc": "ControlNet OpenPose",
    },
    # IP-Adapter
    {
        "url": "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sdxl_vit-h.safetensors",
        "dest": f"{MODELS_DIR}/ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors",
        "desc": "IP-Adapter Plus SDXL",
    },
    # CLIP Vision for IP-Adapter
    {
        "url": "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors",
        "dest": f"{MODELS_DIR}/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        "desc": "CLIP Vision for IP-Adapter",
    },
    # Upscale models
    {
        "url": "https://huggingface.co/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x4plus.pth",
        "dest": f"{MODELS_DIR}/upscale_models/RealESRGAN_x4plus.pth",
        "desc": "RealESRGAN x4",
    },
    {
        "url": "https://huggingface.co/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x4plus_anime_6B.pth",
        "dest": f"{MODELS_DIR}/upscale_models/RealESRGAN_x4plus_anime_6B.pth",
        "desc": "RealESRGAN x4 anime",
    },
    # LoRA (example: detail enhancer)
    {
        "url": "https://huggingface.co/InstantX/FLUX.1-dev-LoRA-Add-details/resolve/main/add_details.safetensors",
        "dest": f"{MODELS_DIR}/loras/add_details.safetensors",
        "desc": "FLUX add details LoRA",
    },
]

for model in model_downloads:
    dest = model["dest"]
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if not os.path.exists(dest):
        print(f"Downloading {model['desc']}...")
        run_cmd(f'aria2c -x 16 -s 16 -k 1M -d "{os.path.dirname(dest)}" -o "{os.path.basename(dest)}" "{model["url"]}"', "")
    else:
        print(f"  {model['desc']} already exists, skipping")

print("\nCell 4: Models downloaded")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 5 — RealESRGAN Standalone Setup
# ═══════════════════════════════════════════════════════════════════════════════

REALESRGAN_DIR = "/content/Real-ESRGAN"
if not os.path.exists(REALESRGAN_DIR):
    run_cmd("git clone --depth 1 https://github.com/xinntao/Real-ESRGAN.git /content/Real-ESRGAN", "RealESRGAN")

# Download pretrained model for standalone RealESRGAN
realesrgan_weights = f"{REALESRGAN_DIR}/weights/RealESRGAN_x4plus.pth"
if not os.path.exists(realesrgan_weights):
    os.makedirs(f"{REALESRGAN_DIR}/weights", exist_ok=True)
    run_cmd(
        f'aria2c -x 16 -s 16 -k 1M -d "{REALESRGAN_DIR}/weights" '
        f'-o "RealESRGAN_x4plus.pth" '
        f'"https://huggingface.co/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x4plus.pth"',
        "RealESRGAN weights",
    )

print("\nCell 5: RealESRGAN standalone setup complete")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 6 — Start ComfyUI
# ═══════════════════════════════════════════════════════════════════════════════

import threading

def start_comfyui():
    proc = subprocess.Popen(
        [sys.executable, "main.py", "--listen", "0.0.0.0", "--port", str(PORT), "--dont-print-server"],
        cwd=COMFYUI_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc

comfyui_proc = start_comfyui()
print(f"Cell 6: ComfyUI started on port {PORT} (PID: {comfyui_proc.pid})")

# Wait for ComfyUI to be ready
import time
import requests

print("Waiting for ComfyUI to start...")
for i in range(60):
    try:
        r = requests.get(f"http://127.0.0.1:{PORT}/system_stats", timeout=2)
        if r.status_code == 200:
            print(f"ComfyUI ready after {i+1} seconds")
            break
    except Exception:
        pass
    time.sleep(1)
else:
    print("WARNING: ComfyUI may not be fully ready yet")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 7 — REST API + ngrok Tunnel
# ═══════════════════════════════════════════════════════════════════════════════

import threading
import uuid
import hashlib
import base64
import json
import signal
import atexit
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# ── Inactivity Timer ────────────────────────────────────────────────────────

_last_activity = time.monotonic()
_inactivity_timeout = INACTIVITY_TIMEOUT_MINUTES * 60
_shutting_down = False

def _check_inactivity():
    global _shutting_down
    while not _shutting_down:
        elapsed = time.monotonic() - _last_activity
        if elapsed > _inactivity_timeout:
            print(f"\n[INACTIVITY] No requests for {INACTIVITY_TIMEOUT_MINUTES} min — shutting down")
            _shutting_down = True
            try:
                import google.colab
                google.colab.auth.authenticate_user()
            except Exception:
                pass
            os.kill(os.getpid(), signal.SIGTERM)
            break
        time.sleep(30)

_inactivity_thread = threading.Thread(target=_check_inactivity, daemon=True)
_inactivity_thread.start()

# ── Flask API ──────────────────────────────────────────────────────────────

api = Flask(__name__)
CORS(api)

_jobs: Dict[str, Dict[str, Any]] = {}

def _auth_check():
    if CINEOS_API_KEY:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        else:
            token = request.headers.get("X-Api-Key", "")
        if token != CINEOS_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
    return None


@api.route("/health", methods=["GET"])
def health():
    try:
        r = requests.get(f"http://127.0.0.1:{PORT}/system_stats", timeout=5)
        comfyui_ok = r.status_code == 200
    except Exception:
        comfyui_ok = False

    return jsonify({
        "status": "healthy" if comfyui_ok else "degraded",
        "comfyui_running": comfyui_ok,
        "port": PORT,
        "uptime_seconds": round(time.monotonic() - _start_time, 2),
        "jobs_processed": _jobs_count,
    })


@api.route("/warmup", methods=["POST"])
def warmup():
    global _last_activity
    _last_activity = time.monotonic()
    return jsonify({"status": "ok", "message": "Warmup received"})


@api.route("/job", methods=["POST"])
def submit_job():
    global _last_activity, _jobs_count
    _last_activity = time.monotonic()

    auth_err = _auth_check()
    if auth_err:
        return auth_err

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    task_id = data.get("task_id", str(uuid.uuid4()))
    job_type = data.get("job_type", "image_generation")
    payload = data.get("payload", {})

    _jobs_count += 1

    if job_type == "image_generation":
        return _handle_image_generation(task_id, payload)
    elif job_type == "super_resolution":
        return _handle_super_resolution(task_id, payload)
    elif job_type == "image_animation":
        return _handle_animation(task_id, payload)
    else:
        return jsonify({"error": f"Unknown job type: {job_type}"}), 400


@api.route("/status/<task_id>", methods=["GET"])
def task_status(task_id):
    auth_err = _auth_check()
    if auth_err:
        return auth_err

    job = _jobs.get(task_id)
    if job is None:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(job)


def _handle_image_generation(task_id: str, payload: dict) -> tuple:
    prompt = payload.get("prompt", "")
    negative_prompt = payload.get("negative_prompt", "")
    width = payload.get("width", 1024)
    height = payload.get("height", 1024)
    steps = payload.get("steps", 30)
    cfg_scale = payload.get("cfg_scale", 7.0)
    seed = payload.get("seed")
    if seed is None:
        seed = int.from_bytes(os.urandom(4), "big")

    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed, "steps": steps, "cfg": cfg_scale,
                "sampler_name": "euler_ancestral", "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0], "positive": ["6", 0],
                "negative": ["7", 0], "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": payload.get("model", "sd_xl_base_1.0.safetensors")},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": f"cineos_{task_id[:8]}", "images": ["8", 0]},
        },
    }

    _jobs[task_id] = {"status": "processing", "task_id": task_id}
    thread = threading.Thread(
        target=_execute_comfyui_job,
        args=(task_id, workflow),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id, "status": "processing"})


def _handle_super_resolution(task_id: str, payload: dict) -> tuple:
    image_path = payload.get("image_path", "")
    scale = payload.get("scale", 4)
    model_name = payload.get("model", "realesrgan-x4plus")

    if not os.path.exists(image_path):
        return jsonify({"error": f"Image not found: {image_path}"}), 404

    _jobs[task_id] = {"status": "processing", "task_id": task_id}
    thread = threading.Thread(
        target=_execute_realesrgan,
        args=(task_id, image_path, scale, model_name),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id, "status": "processing"})


def _handle_animation(task_id: str, payload: dict) -> tuple:
    image_path = payload.get("image_path", "")
    duration = payload.get("duration", 5.0)
    fps = payload.get("fps", 24)
    effect = payload.get("effect", "zoom_in")

    if not os.path.exists(image_path):
        return jsonify({"error": f"Image not found: {image_path}"}), 404

    _jobs[task_id] = {"status": "processing", "task_id": task_id}
    thread = threading.Thread(
        target=_execute_ken_burns,
        args=(task_id, image_path, duration, fps, effect),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id, "status": "processing"})


def _execute_comfyui_job(task_id: str, workflow: dict):
    try:
        resp = requests.post(
            f"http://127.0.0.1:{PORT}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        resp.raise_for_status()
        prompt_data = resp.json()
        prompt_id = prompt_data.get("prompt_id")
        if not prompt_id:
            _jobs[task_id] = {"status": "failed", "error": "No prompt_id returned"}
            return

        for _ in range(300):
            time.sleep(1)
            hist_resp = requests.get(
                f"http://127.0.0.1:{PORT}/history/{prompt_id}", timeout=10
            )
            if hist_resp.status_code != 200:
                continue
            history = hist_resp.json()
            if prompt_id not in history:
                continue

            outputs = history[prompt_id].get("outputs", {})
            for node_id, node_output in outputs.items():
                images = node_output.get("images", [])
                if images:
                    img_info = images[0]
                    img_resp = requests.get(
                        f"http://127.0.0.1:{PORT}/view",
                        params={
                            "filename": img_info["filename"],
                            "subfolder": img_info.get("subfolder", ""),
                            "type": img_info.get("type", "output"),
                        },
                        timeout=30,
                    )
                    img_resp.raise_for_status()
                    img_bytes = img_resp.content

                    output_path = f"/content/output/{task_id}.png"
                    os.makedirs("/content/output", exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(img_bytes)

                    checksum = hashlib.sha256(img_bytes).hexdigest()
                    _jobs[task_id] = {
                        "status": "completed",
                        "result": {
                            "image_path": output_path,
                            "image_base64": base64.b64encode(img_bytes).decode(),
                            "checksum": checksum,
                            "file_size_bytes": len(img_bytes),
                            "source": "comfyui_colab",
                        },
                    }
                    return

        _jobs[task_id] = {"status": "failed", "error": "ComfyUI timeout after 300s"}

    except Exception as exc:
        _jobs[task_id] = {"status": "failed", "error": str(exc)}


def _execute_realesrgan(task_id: str, image_path: str, scale: int, model_name: str):
    try:
        output_path = f"/content/output/{task_id}_sr.png"
        os.makedirs("/content/output", exist_ok=True)

        model_map = {
            "realesrgan-x4plus": "realesrgan-x4plus",
            "realesrgan-x4plus-anime": "realesrgan-x4plus-anime-6b",
            "realesrnet-x4plus": "realesrnet-x4plus",
        }
        model_name_param = model_map.get(model_name, "realesrgan-x4plus")

        proc = subprocess.run(
            [
                sys.executable, "-m", "realesrgan.inference_realesrgan",
                "-i", image_path,
                "-o", output_path,
                "-s", str(scale),
                "-n", model_name_param,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if proc.returncode != 0:
            raise RuntimeError(f"RealESRGAN failed: {proc.stderr[:500]}")

        with open(output_path, "rb") as f:
            img_bytes = f.read()

        checksum = hashlib.sha256(img_bytes).hexdigest()
        _jobs[task_id] = {
            "status": "completed",
            "result": {
                "image_path": output_path,
                "image_base64": base64.b64encode(img_bytes).decode(),
                "checksum": checksum,
                "file_size_bytes": len(img_bytes),
                "scale": scale,
                "source": "realesrgan_colab",
            },
        }
    except Exception as exc:
        _jobs[task_id] = {"status": "failed", "error": str(exc)}


def _execute_ken_burns(task_id: str, image_path: str, duration: float, fps: int, effect: str):
    try:
        output_path = f"/content/output/{task_id}_anim.mp4"
        os.makedirs("/content/output", exist_ok=True)

        total_frames = int(duration * fps)

        effects = {
            "zoom_in": {"scale_start": 1.0, "scale_end": 1.3, "x_start": 0, "x_end": 0, "y_start": 0, "y_end": 0},
            "zoom_out": {"scale_start": 1.3, "scale_end": 1.0, "x_start": 0, "x_end": 0, "y_start": 0, "y_end": 0},
            "pan_left": {"scale_start": 1.0, "scale_end": 1.0, "x_start": 0, "x_end": -0.15, "y_start": 0, "y_end": 0},
            "pan_right": {"scale_start": 1.0, "scale_end": 1.0, "x_start": 0, "x_end": 0.15, "y_start": 0, "y_end": 0},
        }
        params = effects.get(effect, effects["zoom_in"])

        zoom_expr = f"if(eq(on,0),{params['scale_start']},{params['scale_start']}+({params['scale_end']}-{params['scale_start']})*on/{total_frames})"
        x_expr = f"if(eq(on,0),{params['x_start']},{params['x_start']}+({params['x_end']}-{params['x_start']})*on/{total_frames})"
        y_expr = f"if(eq(on,0),{params['y_start']},{params['y_start']}+({params['y_end']}-{params['y_start']})*on/{total_frames})"

        zoompan = (
            f"zoompan=z='{zoom_expr}'"
            f":x='iw*({x_expr})'"
            f":y='ih*({y_expr})'"
            f":d={total_frames}:s=1920x1080:fps={fps}"
        )

        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", image_path,
                "-vf", f"{zoompan},format=yuv420p",
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {proc.stderr[:500]}")

        with open(output_path, "rb") as f:
            video_bytes = f.read()

        checksum = hashlib.sha256(video_bytes).hexdigest()
        _jobs[task_id] = {
            "status": "completed",
            "result": {
                "video_path": output_path,
                "video_base64": base64.b64encode(video_bytes).decode(),
                "checksum": checksum,
                "file_size_bytes": len(video_bytes),
                "duration_seconds": duration,
                "fps": fps,
                "effect": effect,
                "source": "colab_ken_burns",
            },
        }
    except Exception as exc:
        _jobs[task_id] = {"status": "failed", "error": str(exc)}


# ── API Server Thread ────────────────────────────────────────────────────────

_start_time = time.monotonic()
_jobs_count = 0

def run_api_server():
    api.run(host="0.0.0.0", port=API_PORT, debug=False, use_reloader=False)

api_thread = threading.Thread(target=run_api_server, daemon=True)
api_thread.start()
print(f"Cell 7: REST API running on port {API_PORT}")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 8 — Start ngrok Tunnel
# ═══════════════════════════════════════════════════════════════════════════════

from pyngrok import ngrok

if NGROK_AUTH_TOKEN:
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)

tunnel = ngrok.connect(API_PORT, "http")
public_url = tunnel.public_url

print(f"\n{'='*60}")
print(f"CineOS Colab Worker is LIVE!")
print(f"{'='*60}")
print(f"Public URL: {public_url}")
print(f"Health:     {public_url}/health")
print(f"Submit:     {public_url}/job")
print(f"Warmup:     {public_url}/warmup")
print(f"{'='*60}")
print(f"\nAdd to your .env:")
print(f"  COLAB_COMFYUI_ENDPOINT={public_url}")
print(f"\nAuto-shutdown in {INACTIVITY_TIMEOUT_MINUTES} minutes of inactivity")
print(f"{'='*60}\n")

# ═══════════════════════════════════════════════════════════════════════════════
# CELL 9 — Keep Alive (run this cell to keep Colab alive)
# ═══════════════════════════════════════════════════════════════════════════════

import signal

def _signal_handler(sig, frame):
    print("\nShutting down...")
    try:
        ngrok.kill()
    except Exception:
        pass
    if comfyui_proc and comfyui_proc.poll() is None:
        comfyui_proc.terminate()
    os._exit(0)

signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

print(f"Worker running at {public_url}")
print("Press Ctrl+K then Ctrl+C in Colab to stop")
print(f"Auto-shutdown after {INACTIVITY_TIMEOUT_MINUTES} min inactivity")

while not _shutting_down:
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        break

ngrok.kill()
if comfyui_proc and comfyui_proc.poll() is None:
    comfyui_proc.terminate()
print("Worker stopped")
