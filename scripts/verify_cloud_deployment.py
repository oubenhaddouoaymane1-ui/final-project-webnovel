#!/usr/bin/env python3
"""
CineOS — Cloud Deployment Pre-flight Verification

Checks that all required files, environment variables, and service
endpoints are ready before deploying to any cloud provider.

Usage:
    python scripts/verify_cloud_deployment.py
    python scripts/verify_cloud_deployment.py --provider gcp
    python scripts/verify_cloud_deployment.py --provider flyio
    python scripts/verify_cloud_deployment.py --provider railway
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {Colors.GREEN}✓{Colors.END} {msg}")


def fail(msg: str) -> None:
    print(f"  {Colors.RED}✗{Colors.END} {msg}")


def warn(msg: str) -> None:
    print(f"  {Colors.YELLOW}⚠{Colors.END} {msg}")


def section(title: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.CYAN}{title}{Colors.END}")


def check_file_exists(path: str, description: str) -> bool:
    full = Path(path)
    if full.exists():
        ok(f"{description} ({path})")
        return True
    else:
        fail(f"{description} — MISSING: {path}")
        return False


def check_env(var: str, required: bool = True) -> bool:
    val = os.environ.get(var, "")
    if val:
        ok(f"{var} is set")
        return True
    elif required:
        fail(f"{var} is NOT set (required)")
        return False
    else:
        warn(f"{var} is not set (optional)")
        return True


def check_url_reachable(url: str, description: str, timeout: int = 5) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status < 500:
                ok(f"{description} — reachable (HTTP {resp.status})")
                return True
            else:
                warn(f"{description} — returned HTTP {resp.status}")
                return False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            ok(f"{description} — reachable (404 is expected for non-root)")
            return True
        warn(f"{description} — HTTP error {e.code}")
        return False
    except Exception:
        warn(f"{description} — unreachable (may not be deployed yet)")
        return False


def load_dotenv(path: str = ".env") -> None:
    """Load .env file into os.environ (simple parser, no dependency)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description="CineOS cloud deployment verification")
    parser.add_argument("--provider", choices=["gcp", "flyio", "railway", "all"], default="all")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    args = parser.parse_args()

    load_dotenv(args.env_file)

    print(f"\n{Colors.BOLD}{'═' * 60}")
    print(" CineOS — Cloud Deployment Pre-flight Check")
    print(f"{'═' * 60}{Colors.END}")

    passed = 0
    failed = 0
    warned = 0

    # ── Phase 1: Core Files ────────────────────────────────────────────────
    section("Phase 1: Core Files")
    core_files = [
        ("docker-compose.yml", "Docker Compose (base)"),
        ("docker-compose.cloud.yml", "Docker Compose (cloud override)"),
        ("Dockerfile", "Telegram Bot Dockerfile"),
        ("docker/cloud_bridge/Dockerfile", "Cloud Bridge Dockerfile"),
        ("docker/cloud_bridge/requirements.txt", "Cloud Bridge requirements"),
        ("docker/voice/Dockerfile", "Voice Worker Dockerfile"),
        ("docker/ffmpeg/Dockerfile", "Render Worker Dockerfile"),
        ("requirements.txt", "Root requirements"),
        (".env.example", "Environment template"),
        ("deploy/env.cloud.example", "Cloud env template"),
        ("run.sh", "Startup script"),
        ("Makefile", "Makefile"),
    ]
    for path, desc in core_files:
        if check_file_exists(path, desc):
            passed += 1
        else:
            failed += 1

    # ── Phase 2: Source Code (zero local GPU) ──────────────────────────────
    section("Phase 2: Zero Local GPU/LLM Verification")
    gpu_remnants = []
    source_dirs = ["src/", "workers/"]
    gpu_patterns = ["import torch", "import ollama", "from diffusers", "import numpy"]
    for sd in source_dirs:
        p = Path(sd)
        if not p.exists():
            continue
        for py_file in p.rglob("*.py"):
            try:
                content = py_file.read_text()
                for pat in gpu_patterns:
                    if pat in content:
                        gpu_remnants.append(f"{py_file}: contains '{pat}'")
            except Exception:
                pass
    if not gpu_remnants:
        ok("No torch/ollama/diffusers/numpy imports found in src/ or workers/")
        passed += 1
    else:
        for r in gpu_remnants:
            fail(r)
        failed += 1

    # ── Phase 3: Configuration Integrity ───────────────────────────────────
    section("Phase 3: Configuration Files")
    config_files = [
        ("config/models.yaml", "Model config"),
        ("config/workers.yaml", "Workers config"),
        ("config/config.yaml", "System config"),
    ]
    for path, desc in config_files:
        if check_file_exists(path, desc):
            passed += 1
        else:
            failed += 1

    # Check models.yaml has no torch/ollama references
    models_yaml = Path("config/models.yaml")
    if models_yaml.exists():
        content = models_yaml.read_text()
        if "torch" not in content and "ollama" not in content:
            ok("models.yaml has no torch/ollama references")
            passed += 1
        else:
            fail("models.yaml still references torch or ollama")
            failed += 1

    # ── Phase 4: Workflow Files ────────────────────────────────────────────
    section("Phase 4: n8n Workflows")
    wf_dir = Path("workflows")
    if wf_dir.exists():
        wf_files = list(wf_dir.glob("*.json"))
        ok(f"Found {len(wf_files)} workflow files")
        passed += 1
        valid = 0
        for wf in wf_files:
            try:
                data = json.loads(wf.read_text())
                if "nodes" in data and "connections" in data:
                    valid += 1
                else:
                    warn(f"  {wf.name}: missing nodes or connections")
            except json.JSONDecodeError:
                warn(f"  {wf.name}: invalid JSON")
        if valid == len(wf_files):
            ok(f"All {valid} workflows have valid nodes+connections")
            passed += 1
        else:
            warn(f"{valid}/{len(wf_files)} workflows are valid")
    else:
        fail("workflows/ directory not found")
        failed += 1

    # ── Phase 5: Environment Variables ─────────────────────────────────────
    section("Phase 5: Environment Variables")
    env_required = [
        ("POSTGRES_HOST", True),
        ("POSTGRES_DB", True),
        ("POSTGRES_USER", True),
        ("POSTGRES_PASSWORD", True),
        ("REDIS_HOST", True),
        ("REDIS_PORT", True),
        ("N8N_PORT", True),
        ("N8N_BASIC_AUTH_PASSWORD", True),
        ("N8N_ENCRYPTION_KEY", True),
    ]
    env_optional = [
        ("TELEGRAM_BOT_TOKEN", False),
        ("OPENROUTER_API_KEY", False),
        ("OPENROUTER_KEY", False),
        ("HF_API_KEY", False),
        ("POLLINATIONS_ENABLED", False),
        ("COLAB_COMFYUI_ENDPOINT", False),
        ("COLAB_API_KEY", False),
        ("WEBHOOK_URL", False),
    ]
    for var, req in env_required:
        if check_env(var, req):
            passed += 1
        else:
            failed += 1
    for var, req in env_optional:
        if check_env(var, req):
            passed += 1

    # ── Phase 6: Colab Notebooks ───────────────────────────────────────────
    section("Phase 6: Colab Notebooks")
    notebooks = [
        ("notebooks/comfyui_flux.ipynb", "ComfyUI + FLUX notebook"),
        ("notebooks/realesrgan_upscaler.ipynb", "RealESRGAN upscaler notebook"),
        ("notebooks/liveportrait_animator.ipynb", "LivePortrait animation notebook"),
    ]
    for path, desc in notebooks:
        if check_file_exists(path, desc):
            passed += 1
        else:
            failed += 1

    # ── Phase 7: SQL Schema ────────────────────────────────────────────────
    section("Phase 7: Database Schema")
    sql_files = [
        ("sql/init.sql", "Init SQL"),
        ("database/schema.sql", "Schema SQL"),
        ("database/seed/config_defaults.sql", "Seed config"),
    ]
    for path, desc in sql_files:
        if check_file_exists(path, desc):
            passed += 1
        else:
            failed += 1

    # ── Phase 8: Provider-Specific ─────────────────────────────────────────
    section(f"Phase 8: Provider Config ({args.provider.upper()})")
    provider_configs = {
        "gcp": [
            ("deploy/gcp/cloudbuild.yaml", "GCP Cloud Build config"),
            ("deploy/gcp/deploy.sh", "GCP deploy script"),
        ],
        "flyio": [
            ("deploy/flyio/fly.toml", "Fly.io config"),
            ("deploy/flyio/deploy.sh", "Fly.io deploy script"),
        ],
        "railway": [
            ("deploy/railway/railway.json", "Railway config"),
            ("deploy/railway/deploy.sh", "Railway deploy script"),
        ],
    }
    if args.provider == "all":
        for prov, files in provider_configs.items():
            for path, desc in files:
                if check_file_exists(path, desc):
                    passed += 1
                else:
                    failed += 1
    else:
        for path, desc in provider_configs.get(args.provider, []):
            if check_file_exists(path, desc):
                passed += 1
            else:
                failed += 1

    # ── Phase 9: Cloud Service Reachability ────────────────────────────────
    section("Phase 9: Cloud Service Reachability")
    services = [
        ("https://openrouter.ai/api/v1/models", "OpenRouter API"),
        ("https://image.pollinations.ai/prompt/test", "Pollinations Image API"),
        ("https://api-inference.huggingface.co", "HuggingFace Inference API"),
    ]
    for url, desc in services:
        if check_url_reachable(url, desc):
            passed += 1
        else:
            warned += 1

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    total = passed + failed + warned
    if failed == 0:
        print(f"{Colors.GREEN}{Colors.BOLD} ✓ ALL CHECKS PASSED ({passed}/{total}){Colors.END}")
    else:
        print(f"{Colors.RED}{Colors.BOLD} ✗ {failed} CHECK(S) FAILED ({passed}/{total} passed){Colors.END}")
    if warned > 0:
        print(f"{Colors.YELLOW} ⚠ {warned} warning(s) (non-blocking){Colors.END}")
    print(f"{'═' * 60}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
