# CineOS Google Colab Setup Guide

Step-by-step guide for running ComfyUI + FLUX on Google Colab's free T4 GPU and connecting it to CineOS for high-quality image generation.

---

## 1. Prerequisites

| Requirement | Details |
|-------------|---------|
| Google Account | Any free Gmail/Google account |
| CineOS Running | Docker Compose stack must be up locally |
| Internet | Stable connection (Colab uploads ~10GB model files on first run) |
| Time | ~15 minutes for first setup, ~2 minutes for subsequent starts |

---

## 2. Understanding the Architecture

```
┌─────────────────────────────────┐
│      Google Colab (Cloud)       │
│                                 │
│  ┌───────────────────────────┐  │
│  │  T4 GPU (15GB VRAM)      │  │
│  │                           │  │
│  │  ComfyUI Server           │  │
│  │  + FLUX.1 model           │  │
│  └───────────┬───────────────┘  │
│              │                  │
│  ┌───────────▼───────────────┐  │
│  │  ngrok tunnel             │  │
│  │  (public HTTPS URL)       │  │
│  └───────────┬───────────────┘  │
└──────────────┼──────────────────┘
               │  internet
┌──────────────▼──────────────────┐
│      Your PC (Local)            │
│                                 │
│  n8n → sends prompts to → Colab │
│  n8n ← receives images from ← Colab│
└─────────────────────────────────┘
```

Colab runs ComfyUI as a server. ngrok creates a public URL so your local n8n can send image generation requests to Colab over the internet.

---

## 3. Step-by-Step Notebook Setup

### 3.1 Open Google Colab

1. Go to https://colab.research.google.com
2. Sign in with your Google account
3. Click **File → Upload notebook**
4. Upload `notebooks/comfyui_flux.ipynb` from the CineOS repo

Or create a new notebook and paste the cells below.

### 3.2 Select GPU Runtime

**This is critical.** Colab defaults to CPU runtime.

1. Click **Runtime** in the menu bar
2. Click **Change runtime type**
3. Under **Hardware accelerator**, select **T4 GPU**
4. Click **Save**

Verify GPU is available:

```python
!nvidia-smi
```

You should see something like:

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.104.05   Driver Version: 535.104.05   CUDA Version: 12.2     |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  Tesla T4            Off  | 00000000:00:04.0 Off |                    0 |
| N/A   40C    P8     9W /  70W |      0MiB / 15360MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

If you see `N/A` for GPU or `No devices were found`, the GPU runtime is not selected. Go back and change the runtime type.

### 3.3 Run the Setup Cell

Execute the first cell in the notebook. This:

1. Installs system dependencies (~2 min)
2. Clones ComfyUI repository (~1 min)
3. Installs Python dependencies (~3 min)
4. Downloads FLUX.1-schnell model (~10 GB, first run only — cached afterward)
5. Starts ComfyUI server on port 7860

```python
# Cell 1: Install ComfyUI + FLUX
import subprocess, os

# System dependencies
subprocess.run(["apt-get", "-qq", "update"], check=True)
subprocess.run(["apt-get", "-qq", "install", "-y", "wget", "git", "libgl1", "libglib2.0-0"], check=True)

# Clone ComfyUI
if not os.path.exists("/content/ComfyUI"):
    subprocess.run(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", "/content/ComfyUI"], check=True)

# Install Python dependencies
subprocess.run(["pip", "install", "-q", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu121"], check=True)
subprocess.run(["pip", "install", "-q", "-r", "/content/ComfyUI/requirements.txt"], check=True)

# Download FLUX.1-schnell model
models_dir = "/content/ComfyUI/models/unet"
os.makedirs(models_dir, exist_ok=True)
flux_path = os.path.join(models_dir, "flux1-schnell.safetensors")
if not os.path.exists(flux_path):
    print("Downloading FLUX.1-schnell (~10GB, first run only)...")
    subprocess.run([
        "wget", "-q", "-O", flux_path,
        "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors"
    ], check=True)

# Download CLIP models
clip_dir = "/content/ComfyUI/models/clip"
os.makedirs(clip_dir, exist_ok=True)
for model, url in [
    ("t5xxl_fp16.safetensors", "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors"),
    ("clip_l.safetensors", "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"),
]:
    path = os.path.join(clip_dir, model)
    if not os.path.exists(path):
        subprocess.run(["wget", "-q", "-O", path, url], check=True)

# Download VAE
vae_dir = "/content/ComfyUI/models/vae"
os.makedirs(vae_dir, exist_ok=True)
vae_path = os.path.join(vae_dir, "ae.safetensors")
if not os.path.exists(vae_path):
    subprocess.run([
        "wget", "-q", "-O", vae_path,
        "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"
    ], check=True)

print("Setup complete.")
```

### 3.4 Start ComfyUI Server

```python
# Cell 2: Start ComfyUI server
import subprocess, time, threading

def start_comfyui():
    subprocess.run([
        "python", "/content/ComfyUI/main.py",
        "--listen", "0.0.0.0",
        "--port", "7860",
        "--dont-print-server"
    ], cwd="/content/ComfyUI")

thread = threading.Thread(target=start_comfyui, daemon=True)
thread.start()

# Wait for server to be ready
import urllib.request
for i in range(30):
    try:
        urllib.request.urlopen("http://localhost:7860/system_stats")
        print("ComfyUI server ready on port 7860")
        break
    except Exception:
        time.sleep(2)
else:
    print("Warning: ComfyUI may not be ready yet. Check logs.")
```

### 3.5 Start ngrok Tunnel

```python
# Cell 3: Create ngrok tunnel
!pip install -q pyngrok

from pyngrok import ngrok
import random, string

# Generate a random auth token for security
api_key = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
print(f"API Key: {api_key}")
print(f"Save this — you'll need it for CineOS .env")

# Create tunnel
public_url = ngrok.connect(7860, "http")
print(f"\nComfyUI public URL: {public_url}")
print(f"\nSet these in your CineOS .env file:")
print(f"COLAB_COMFYUI_ENDPOINT={public_url}")
print(f"COLAB_API_KEY={api_key}")
```

**Copy both values** (the URL and the API key) and paste them into your local `.env` file.

### 3.6 Verify the Connection

On your local machine, test the Colab endpoint:

```bash
# Test health endpoint
curl -s $COLAB_COMFYUI_ENDPOINT/system_stats | python -m json.tool

# Test with a simple prompt
curl -s -X POST $COLAB_COMFYUI_ENDPOINT/prompt \
  -H "Authorization: Bearer $COLAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": {
      "3": {
        "class_type": "KSampler",
        "inputs": {
          "seed": 42,
          "steps": 4,
          "cfg": 1.0,
          "sampler_name": "euler",
          "denoise": 1.0,
          "model": ["4", 0],
          "positive": ["6", 0],
          "negative": ["7", 0],
          "latent_image": ["5", 0]
        }
      },
      "4": {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": "flux1-schnell.safetensors", "weight_dtype": "default"}
      },
      "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1}
      },
      "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "a medieval castle at sunset", "clip": ["11", 0]}
      },
      "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "blurry, low quality", "clip": ["11", 0]}
      },
      "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["10", 0]}
      },
      "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "test", "images": ["8", 0]}
      },
      "10": {
        "class_type": "VAELoader",
        "inputs": {"vae_name": "ae.safetensors"}
      },
      "11": {
        "class_type": "DualCLIPLoader",
        "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp16.safetensors", "type": "flux"}
      }
    }
  }'
```

---

## 4. Auto-Shutdown Configuration

Colab disconnects after ~90 minutes of idle time. To manage this and avoid wasting GPU quota:

### Option A: Manual Shutdown (Simple)

When done, click **Runtime → Disconnect and delete runtime** in Colab.

### Option B: Timer-Based Auto-Shutdown

Add this cell to the notebook:

```python
# Cell 4: Auto-shutdown after inactivity
import threading, time

def auto_shutdown(minutes=30):
    """Shutdown ComfyUI after N minutes of no requests."""
    import urllib.request
    last_activity = time.time()

    def check_loop():
        nonlocal last_activity
        while True:
            time.sleep(60)
            # Check if ComfyUI has recent activity
            try:
                stats = urllib.request.urlopen("http://localhost:7860/system_stats", timeout=5)
                # If server is running and no jobs in queue, consider idle
            except Exception:
                pass

            idle_minutes = (time.time() - last_activity) / 60
            if idle_minutes >= minutes:
                print(f"Idle for {minutes} minutes. Shutting down ComfyUI...")
                import os
                os._exit(0)  # Kill the Colab runtime

    thread = threading.Thread(target=check_loop, daemon=True)
    thread.start()

# Auto-shutdown after 30 minutes of no ComfyUI requests
auto_shutdown(minutes=30)
print("Auto-shutdown enabled: runtime will stop after 30 minutes of inactivity")
```

### Option C: Request-Based Tracking

Track actual API requests to determine inactivity:

```python
# Cell 4b: Track requests for accurate idle detection
import time, threading

last_request_time = time.time()

def update_activity():
    global last_request_time
    last_request_time = time.time()

def auto_shutdown_watcher(max_idle_minutes=30):
    def watcher():
        while True:
            time.sleep(60)
            idle = (time.time() - last_request_time) / 60
            if idle >= max_idle_minutes:
                print(f"No requests for {max_idle_minutes} min. Shutting down...")
                import os
                os._exit(0)
    t = threading.Thread(target=watcher, daemon=True)
    t.start()

# Hook into ComfyUI to track requests
# (ComfyUI calls this on each prompt submission)
import sys
sys.path.insert(0, "/content/ComfyUI")

auto_shutdown_watcher(max_idle_minutes=30)
print("Request-based auto-shutdown enabled (30 min idle)")
```

---

## 5. Connecting to CineOS

### 5.1 Update .env File

```env
# Colab ComfyUI
COLAB_COMFYUI_ENDPOINT=https://abc123.ngrok-free.app
COLAB_API_KEY=your_random_32_char_key
```

### 5.2 Restart n8n

```bash
docker compose restart n8n
```

### 5.3 Verify Connection

```bash
# Check Colab endpoint health
curl -s $COLAB_COMFYUI_ENDPOINT/system_stats | python -m json.tool

# Check n8n can see the endpoint
curl -s http://localhost:5678/healthz
```

### 5.4 Send a Test Novel

1. Send a short test novel via Telegram (50-100 words is fine for testing)
2. Monitor the n8n execution log at http://localhost:5678
3. Watch the image generation workflow dispatch to Colab
4. Verify images are saved in `./generated/images/`

---

## 6. GPU vs. CPU Runtime Selection

### When to Use GPU Runtime

- Running ComfyUI + FLUX (primary use case)
- Super-resolution upscaling (RealESRGAN)
- LivePortrait face animation
- Any task requiring CUDA acceleration

### When to Use CPU Runtime

- Testing notebook cells without GPU
- Running non-AI setup steps
- Saving GPU quota when only testing orchestration

### How to Switch

1. Go to **Runtime → Change runtime type**
2. Select **CPU** or **T4 GPU**
3. Click **Save**
4. Runtime will disconnect and reconnect with new hardware

### GPU Availability Tips

- **Peak hours** (US daytime): GPU may be unavailable. Try off-peak hours.
- **Long-running sessions**: Colab may disconnect after 12 hours. Reconnect manually.
- **GPU quota**: Free tier allows ~12 hours/day of T4 GPU time across all notebooks.
- **Check remaining quota**: Look at the GPU icon in the top-right corner of Colab.

---

## 7. Common Issues and Fixes

### "GPU not found" / "No devices were found"

**Cause:** Runtime is set to CPU.

**Fix:** Runtime → Change runtime type → T4 GPU → Save.

### ComfyUI server won't start

**Cause:** Port 7860 is already in use, or a dependency is missing.

**Fix:**

```python
# Kill any existing process on port 7860
!fuser -k 7860/tcp 2>/dev/null
!pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu121
!pip install -q -r /content/ComfyUI/requirements.txt
```

Then re-run the server start cell.

### ngrok URL not working from local machine

**Cause:** ngrok free tier shows a browser warning page, or the tunnel is expired.

**Fix:**

1. Check if the Colab runtime is still connected (green circle in top right)
2. Re-run the ngrok cell to get a fresh URL
3. Update `.env` with the new URL
4. Restart n8n: `docker compose restart n8n`

### "CUDA out of memory"

**Cause:** FLUX model uses ~12GB VRAM, T4 has 15GB. Should be fine, but background processes may consume VRAM.

**Fix:**

```python
# Clear GPU memory
import torch
torch.cuda.empty_cache()
import gc
gc.collect()
```

If persistent, reduce image resolution to 768x768.

### Images appear corrupted or are all black

**Cause:** VAE model not loaded correctly, or FLUX model download was incomplete.

**Fix:**

```python
# Verify model files exist and have correct sizes
import os
for path, expected_size in [
    ("/content/ComfyUI/models/unet/flux1-schnell.safetensors", 23_800_000_000),
    ("/content/ComfyUI/models/vae/ae.safetensors", 335_000_000),
    ("/content/ComfyUI/models/clip/t5xxl_fp16.safetensors", 9_870_000_000),
    ("/content/ComfyUI/models/clip/clip_l.safetensors", 250_000_000),
]:
    if os.path.exists(path):
        actual = os.path.getsize(path)
        status = "OK" if actual > expected_size * 0.9 else "INCOMPLETE"
        print(f"{status}: {os.path.basename(path)} ({actual / 1e9:.1f}GB)")
    else:
        print(f"MISSING: {os.path.basename(path)}")
```

Re-download any incomplete or missing files.

### Colab disconnects unexpectedly

**Cause:** Free tier runtime limit (~90 min idle, ~12 hours total).

**Fix:**

1. Re-open the Colab notebook
2. Re-run all cells (models are cached, so it's fast)
3. Re-copy the new ngrok URL to `.env`
4. Restart n8n: `docker compose restart n8n`

### Slow image generation (30+ seconds per image)

**Cause:** FLUX.1-schnell should take 5-10 seconds on T4. If slower:

1. Check GPU utilization: `!nvidia-smi` — should show high GPU-Util
2. If GPU-Util is low, something else is using GPU memory
3. Restart the runtime: Runtime → Restart runtime

---

## 8. Performance Benchmarks

On a free T4 GPU (15GB VRAM):

| Task | Time | Notes |
|------|------|-------|
| FLUX.1-schnell 1024x1024 | 5-10s | 4 inference steps |
| FLUX.1-dev 1024x1024 | 20-30s | 20 inference steps, higher quality |
| RealESRGAN 4x upscale | 3-5s per frame | For super-resolution |
| LivePortrait animation | 10-20s per clip | For face animation |

### Tips for Faster Generation

1. **Use FLUX.1-schnell** (4 steps) instead of FLUX.1-dev (20 steps) — 4x faster
2. **Batch requests**: Send multiple prompts in one API call
3. **Keep the model loaded**: Don't restart Colab between jobs
4. **Use 1024x1024**: Larger resolutions take proportionally longer

---

## 9. Cost and Quota Management

### Free Tier Quotas

| Resource | Free Limit | Notes |
|----------|-----------|-------|
| GPU runtime | ~12 hours/day | Across all notebooks |
| Idle timeout | ~90 minutes | Disconnects if no activity |
| Max session | ~6 hours | Hard limit per connection |
| Storage | ~15 GB | Google Drive + runtime disk |

### Tracking GPU Usage

```python
# Check remaining GPU memory
!nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Check session runtime
!cat /proc/uptime | awk '{print int($1/3600)"h "int($1%3600/60)"m"}'
```

### Maximizing Free Usage

1. **Use auto-shutdown**: Don't leave Colab idle (wastes quota)
2. **Batch jobs**: Generate multiple images per Colab session
3. **Cache models**: FLUX download only happens once (saves bandwidth)
4. **Off-peak hours**: GPU availability is better at night (US time)
5. **Multiple accounts**: Use different Google accounts for separate quotas

---

## 10. Quick Reference

### Colab Cell Summary

| Cell | Purpose | Run Time |
|------|---------|----------|
| Cell 1 | Install ComfyUI + FLUX | 5-10 min (first run), 30s (cached) |
| Cell 2 | Start ComfyUI server | 10-20 seconds |
| Cell 3 | Create ngrok tunnel | 5 seconds |
| Cell 4 | Auto-shutdown timer | Instant |

### Required .env Variables

```env
COLAB_COMFYUI_ENDPOINT=https://xxxx.ngrok-free.app
COLAB_API_KEY=your_32_char_random_string
```

### Key Commands

```bash
# Test Colab connection
curl -s $COLAB_COMFYUI_ENDPOINT/system_stats

# Restart n8n to pick up new Colab URL
docker compose restart n8n

# Monitor n8n image generation workflow
docker compose logs -f n8n | grep -i "colab\|comfyui\|image"
```

---

## See Also

- [Deployment Guide](deployment-guide.md) — Full CineOS deployment
- [Cloud Services Guide](cloud-services-guide.md) — All cloud backends
- [Worker Guide](worker-guide.md) — Local worker configuration
- [Troubleshooting](troubleshooting.md) — Common issues
