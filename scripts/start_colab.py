"""
start_colab.py — Helper script to launch and manage Colab GPU workers for CineOS.

Detects if Colab endpoints are configured, provides instructions for starting
Colab, tests connectivity, and warns if Colab is offline.

Usage:
    python scripts/start_colab.py                    # Show status
    python scripts/start_colab.py --check            # Test all endpoints
    python scripts/start_colab.py --test             # Test + dispatch a probe job
    python scripts/start_colab.py --setup            # Show setup instructions
    python scripts/start_colab.py --print-template   # Print the Colab notebook code
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

# ─── Configuration ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

COLAB_ENDPOINTS = {
    "COLAB_COMFYUI_ENDPOINT": {
        "name": "ComfyUI (Image Generation + Super-Res)",
        "capabilities": ["image_generation", "super_resolution"],
        "health_path": "/health",
        "warmup_path": "/warmup",
        "job_path": "/job",
    },
    "COLAB_ESRGAN_ENDPOINT": {
        "name": "RealESRGAN (Super Resolution Only)",
        "capabilities": ["super_resolution"],
        "health_path": "/health",
        "warmup_path": "/warmup",
        "job_path": "/job",
    },
    "COLAB_LIVEPORTRAIT_ENDPOINT": {
        "name": "LivePortrait (Animation)",
        "capabilities": ["image_animation"],
        "health_path": "/health",
        "warmup_path": "/warmup",
        "job_path": "/job",
    },
    "COLAB_KOKORO_ENDPOINT": {
        "name": "Kokoro TTS (Voice)",
        "capabilities": ["text_to_speech"],
        "health_path": "/health",
        "warmup_path": "/warmup",
        "job_path": "/job",
    },
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    for key in COLAB_ENDPOINTS:
        val = os.environ.get(key, "")
        if val:
            env[key] = val
    return env


def _check_endpoint(url: str, api_key: str = "", timeout: int = 10) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "url": url,
        "reachable": False,
        "status_code": None,
        "latency_ms": None,
        "error": None,
        "details": None,
    }

    try:
        import httpx
    except ImportError:
        try:
            import requests as req_lib
            headers: Dict[str, str] = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            start = time.monotonic()
            resp = req_lib.get(
                f"{url.rstrip('/')}/health",
                headers=headers,
                timeout=timeout,
            )
            elapsed = (time.monotonic() - start) * 1000
            result["status_code"] = resp.status_code
            result["latency_ms"] = round(elapsed, 2)
            result["reachable"] = resp.status_code == 200
            if resp.status_code == 200:
                try:
                    result["details"] = resp.json()
                except Exception:
                    pass
            else:
                result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return result
        except ImportError:
            result["error"] = "No HTTP library available (install httpx or requests)"
            return result

    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=timeout) as client:
            start = time.monotonic()
            resp = client.get(
                f"{url.rstrip('/')}/health",
                headers=headers,
            )
            elapsed = (time.monotonic() - start) * 1000
            result["status_code"] = resp.status_code
            result["latency_ms"] = round(elapsed, 2)
            result["reachable"] = resp.status_code == 200
            if resp.status_code == 200:
                try:
                    result["details"] = resp.json()
                except Exception:
                    pass
            else:
                result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except ImportError:
        result["error"] = "httpx not installed"
    except Exception as exc:
        result["error"] = str(exc)

    return result


def _send_warmup(url: str, api_key: str = "", timeout: int = 10) -> bool:
    try:
        import httpx
    except ImportError:
        try:
            import requests as req_lib
            headers: Dict[str, str] = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = req_lib.post(f"{url.rstrip('/')}/warmup", headers=headers, timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{url.rstrip('/')}/warmup", headers=headers)
            return resp.status_code == 200
    except Exception:
        return False


# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_status(env: Dict[str, str]):
    print("\n" + "=" * 60)
    print("  CineOS Colab Worker Status")
    print("=" * 60)

    configured = []
    unconfigured = []

    for key, info in COLAB_ENDPOINTS.items():
        url = env.get(key, "")
        if url:
            configured.append((key, url, info))
        else:
            unconfigured.append((key, info))

    if configured:
        print(f"\n  Configured Endpoints ({len(configured)}):")
        print("  " + "-" * 56)
        for key, url, info in configured:
            api_key = env.get("COLAB_API_KEY", "")
            result = _check_endpoint(url, api_key)
            status = "\033[32mONLINE\033[0m" if result["reachable"] else "\033[31mOFFLINE\033[0m"
            latency = f"{result['latency_ms']:.0f}ms" if result["latency_ms"] else "N/A"
            print(f"  [{status}] {info['name']}")
            print(f"    URL:     {url}")
            print(f"    Latency: {latency}")
            if result.get("details"):
                details = result["details"]
                if isinstance(details, dict):
                    jobs = details.get("jobs_processed", details.get("jobs_completed", "?"))
                    print(f"    Jobs:    {jobs} processed")
            if result.get("error"):
                print(f"    Error:   {result['error'][:80]}")
            print()
    else:
        print("\n  No Colab endpoints configured.")
        print("  All heavy AI workloads will use free cloud APIs (Pollinations, HF).")

    if unconfigured:
        print(f"\n  Optional Endpoints (not configured):")
        print("  " + "-" * 56)
        for key, info in unconfigured:
            print(f"    - {info['name']}: Set {key} in .env")
        print()

    print("=" * 60)


def cmd_check(env: Dict[str, str]):
    print("\n" + "=" * 60)
    print("  CineOS Colab Connectivity Check")
    print("=" * 60)

    all_ok = True
    for key, info in COLAB_ENDPOINTS.items():
        url = env.get(key, "")
        if not url:
            continue

        api_key = env.get("COLAB_API_KEY", "")
        result = _check_endpoint(url, api_key)

        if result["reachable"]:
            print(f"  [OK]     {info['name']}")
            print(f"         URL: {url}")
            if result["latency_ms"]:
                print(f"         Latency: {result['latency_ms']:.0f}ms")
            if result.get("details"):
                d = result["details"]
                if isinstance(d, dict):
                    comfyui = d.get("comfyui_running")
                    if comfyui is not None:
                        print(f"         ComfyUI: {'running' if comfyui else 'not running'}")
                    uptime = d.get("uptime_seconds")
                    if uptime:
                        print(f"         Uptime: {uptime:.0f}s")
        else:
            all_ok = False
            print(f"  [FAIL]  {info['name']}")
            print(f"         URL: {url}")
            print(f"         Error: {result.get('error', 'Unknown')}")

        print()

    if all_ok:
        print("  All configured endpoints are online.")
    else:
        print("  Some endpoints are offline. Start your Colab notebook.")

    print("=" * 60)


def cmd_test(env: Dict[str, str]):
    print("\n" + "=" * 60)
    print("  CineOS Colab Probe Test")
    print("=" * 60)

    url = env.get("COLAB_COMFYUI_ENDPOINT", "")
    if not url:
        print("\n  No COLAB_COMFYUI_ENDPOINT configured. Nothing to test.")
        print("=" * 60)
        return

    api_key = env.get("COLAB_API_KEY", "")
    print(f"\n  Testing: {url}")

    result = _check_endpoint(url, api_key)
    if not result["reachable"]:
        print(f"  Endpoint offline: {result.get('error', 'Unknown')}")
        print("  Start your Colab notebook first.")
        print("=" * 60)
        return

    print(f"  Health check passed ({result['latency_ms']:.0f}ms)")

    print("\n  Sending warmup...")
    warmup_ok = _send_warmup(url, api_key)
    if warmup_ok:
        print("  Warmup OK")
    else:
        print("  Warmup failed (endpoint may not support it)")

    print("\n  Dispatching probe job (1x1 test image)...")

    test_payload = {
        "task_id": f"probe_{int(time.time())}",
        "job_type": "image_generation",
        "payload": {
            "prompt": "a tiny red dot on white background",
            "width": 64,
            "height": 64,
            "steps": 4,
            "cfg_scale": 7.0,
            "seed": 42,
        },
    }

    try:
        import httpx as httpx_lib
    except ImportError:
        import requests as httpx_lib

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        start = time.monotonic()
        resp = httpx_lib.post(
            f"{url.rstrip('/')}/job",
            json=test_payload,
            headers=headers,
            timeout=30,
        )
        elapsed = (time.monotonic() - start) * 1000

        if resp.status_code == 200:
            data = resp.json()
            task_id = data.get("task_id", test_payload["task_id"])
            status = data.get("status", "unknown")
            print(f"  Job submitted: task_id={task_id}, status={status} ({elapsed:.0f}ms)")

            if status == "processing":
                print("  Polling for result...")
                for i in range(60):
                    time.sleep(2)
                    try:
                        if hasattr(httpx_lib, "get"):
                            sr = httpx_lib.get(
                                f"{url.rstrip('/')}/status/{task_id}",
                                headers=headers,
                                timeout=10,
                            )
                        else:
                            sr = httpx_lib.get(
                                f"{url.rstrip('/')}/status/{task_id}",
                                headers=headers,
                                timeout=10,
                            )
                        if sr.status_code == 200:
                            sdata = sr.json()
                            s = sdata.get("status", "")
                            if s == "completed":
                                print(f"  Probe job completed in {i*2}s")
                                break
                            elif s == "failed":
                                print(f"  Probe job failed: {sdata.get('error', 'Unknown')}")
                                break
                    except Exception:
                        pass
                else:
                    print("  Probe job timed out (60s) — this may be normal for first run")
        else:
            print(f"  Job submission failed: HTTP {resp.status_code}")
            print(f"  {resp.text[:200]}")
    except Exception as exc:
        print(f"  Test failed: {exc}")

    print("=" * 60)


def cmd_setup():
    template_path = PROJECT_ROOT / "workers" / "cloud_bridge" / "colab_template.py"

    print("\n" + "=" * 60)
    print("  CineOS Colab Setup Instructions")
    print("=" * 60)

    print("""
  1. OPEN GOOGLE COLAB
     Go to https://colab.research.google.com

  2. CREATE A NEW NOTEBOOK
     File > New notebook

  3. SET GPU ACCELERATION
     Runtime > Change runtime type > T4 GPU (free tier)

  4. COPY THE TEMPLATE CODE
     The template is at:
     """)

    if template_path.exists():
        print(f"     {template_path}")
    else:
        print("     workers/cloud_bridge/colab_template.py")

    print("""
  5. CONFIGURE (at the top of the notebook)
     Set NGROK_AUTH_TOKEN:
       - Sign up free at https://ngrok.com
       - Copy your auth token
       - Paste it in the NGROK_AUTH_TOKEN variable

     Set CINEOS_API_KEY:
       - Must match COLAB_API_KEY in your .env

  6. RUN ALL CELLS
     Runtime > Run all

  7. COPY THE NGROK URL
     The last cell prints a public URL like:
       https://abc123.ngrok-free.app

  8. SET IT IN YOUR .env
     Add to your .env file:
       COLAB_COMFYUI_ENDPOINT=<paste the ngrok URL>

  9. RESTART THE CLOUD BRIDGE
     docker compose restart cloud_bridge

  The Colab notebook will auto-shutdown after 15 minutes of inactivity.
  Start it again whenever you need GPU processing.
""")

    print("=" * 60)


def cmd_print_template():
    template_path = PROJECT_ROOT / "workers" / "cloud_bridge" / "colab_template.py"
    if template_path.exists():
        content = template_path.read_text()
        print("\n" + "=" * 60)
        print("  Colab Template — copy each cell into Colab")
        print("=" * 60 + "\n")

        in_cell = False
        cell_num = 0
        for line in content.splitlines():
            if line.startswith("# CELL ") or line.startswith("# ══"):
                pass
            print(line)
    else:
        print(f"Template not found at: {template_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CineOS Colab Worker Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/start_colab.py                    # Show status
  python scripts/start_colab.py --check            # Test connectivity
  python scripts/start_colab.py --test             # Test + dispatch probe
  python scripts/start_colab.py --setup            # Show setup instructions
  python scripts/start_colab.py --print-template   # Print notebook code
        """,
    )
    parser.add_argument("--check", action="store_true", help="Test connectivity to all Colab endpoints")
    parser.add_argument("--test", action="store_true", help="Test connectivity and dispatch a probe job")
    parser.add_argument("--setup", action="store_true", help="Show setup instructions")
    parser.add_argument("--print-template", action="store_true", help="Print the Colab notebook template")

    args = parser.parse_args()
    env = load_env()

    if args.setup:
        cmd_setup()
    elif args.check:
        cmd_check(env)
    elif args.test:
        cmd_test(env)
    elif args.print_template:
        cmd_print_template()
    else:
        cmd_status(env)


if __name__ == "__main__":
    main()
