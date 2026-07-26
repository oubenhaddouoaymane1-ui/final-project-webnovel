#!/usr/bin/env python3
"""One-shot n8n setup: import workflows, create credentials, activate everything."""

import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("setup_n8n")

N8N_HOST = os.getenv("N8N_HOST", "n8n")
N8N_PORT = int(os.getenv("N8N_PORT", "5678"))
N8N_BASE = f"http://{N8N_HOST}:{N8N_PORT}"
N8N_USER = os.getenv("N8N_BASIC_AUTH_USER", "admin")
N8N_PASS = os.getenv("N8N_BASIC_AUTH_PASSWORD", "cineos_admin")
WORKFLOWS_DIR = Path(os.getenv("WORKFLOWS_DIR", "/workflows"))

POSTGRES_HOST = os.getenv("CINEOS_DB_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("CINEOS_DB_PORT", "5432"))
POSTGRES_DB = os.getenv("CINEOS_DB_NAME", "cineos")
POSTGRES_USER = os.getenv("CINEOS_DB_USER", "cineos")
POSTGRES_PASS = os.getenv("CINEOS_DB_PASSWORD", "cineos_secret")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

HEALTH_POLL_INTERVAL = 3
HEALTH_POLL_TIMEOUT = 120
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30


def auth_headers() -> dict:
    import base64

    creds = base64.b64encode(f"{N8N_USER}:{N8N_PASS}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


def wait_for_n8n() -> bool:
    url = f"{N8N_BASE}/healthz"
    log.info("Waiting for n8n at %s ...", url)
    deadline = time.time() + HEALTH_POLL_TIMEOUT
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=5)
            if r.status_code == 200:
                log.info("n8n is ready.")
                return True
        except httpx.ConnectError:
            pass
        except Exception as exc:
            log.debug("Health probe error: %s", exc)
        time.sleep(HEALTH_POLL_INTERVAL)
    log.error("n8n did not become ready within %ds", HEALTH_POLL_TIMEOUT)
    return False


def import_workflows(client: httpx.Client) -> list[dict]:
    if not WORKFLOWS_DIR.is_dir():
        log.warning("Workflows directory %s does not exist", WORKFLOWS_DIR)
        return []

    json_files = sorted(WORKFLOWS_DIR.glob("*.json"))
    if not json_files:
        log.info("No workflow JSON files found in %s", WORKFLOWS_DIR)
        return []

    log.info("Found %d workflow files", len(json_files))
    imported = []

    for path in json_files:
        try:
            raw = path.read_text(encoding="utf-8")
            workflow_data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to read %s: %s", path.name, exc)
            continue

        payload = {"nodes": [], "connections": {}, "settings": {}}
        if "nodes" in workflow_data:
            payload["nodes"] = workflow_data["nodes"]
        if "connections" in workflow_data:
            payload["connections"] = workflow_data["connections"]
        if "settings" in workflow_data:
            payload["settings"] = workflow_data["settings"]
        if "name" in workflow_data:
            payload["name"] = workflow_data["name"]
        elif "meta" in workflow_data and "instanceId" in workflow_data.get("meta", {}):
            payload["name"] = path.stem

        resp = client.post(f"{N8N_BASE}/api/v1/workflows", json=payload)
        if resp.status_code in (200, 201):
            wf = resp.json()
            wf_id = wf.get("id")
            wf_name = wf.get("name", path.stem)
            log.info("  Imported: %s (id=%s)", wf_name, wf_id)
            imported.append({"id": wf_id, "name": wf_name, "file": path.name})
        elif resp.status_code == 409:
            log.info("  Already exists, updating: %s", path.name)
            existing = _find_workflow_by_name(client, payload.get("name", path.stem))
            if existing:
                wf_id = existing["id"]
                client.put(f"{N8N_BASE}/api/v1/workflows/{wf_id}", json=payload)
                imported.append({"id": wf_id, "name": payload.get("name", path.stem), "file": path.name})
        else:
            log.error("  Failed to import %s: HTTP %d — %s", path.name, resp.status_code, resp.text[:300])

    return imported


def _find_workflow_by_name(client: httpx.Client, name: str) -> dict | None:
    resp = client.get(f"{N8N_BASE}/api/v1/workflows")
    if resp.status_code != 200:
        return None
    for wf in resp.json().get("data", []):
        if wf.get("name") == name:
            return wf
    return None


def activate_workflows(client: httpx.Client, workflows: list[dict]):
    log.info("Activating %d workflows ...", len(workflows))
    for wf in workflows:
        wf_id = wf["id"]
        resp = client.patch(
            f"{N8N_BASE}/api/v1/workflows/{wf_id}",
            json={"active": True},
        )
        if resp.status_code in (200, 201):
            log.info("  Activated: %s", wf["name"])
        else:
            log.warning("  Could not activate %s: HTTP %d", wf["name"], resp.status_code)


def create_postgres_credential(client: httpx.Client) -> str | None:
    payload = {
        "name": "CineOS PostgreSQL",
        "type": "postgresDb",
        "data": {
            "host": POSTGRES_HOST,
            "port": POSTGRES_PORT,
            "database": POSTGRES_DB,
            "user": POSTGRES_USER,
            "password": POSTGRES_PASS,
            "ssl": "allow",
        },
    }
    resp = client.post(f"{N8N_BASE}/api/v1/credentials", json=payload)
    if resp.status_code in (200, 201):
        cred_id = resp.json().get("id")
        log.info("Created PostgreSQL credential (id=%s)", cred_id)
        return cred_id
    if resp.status_code == 409:
        log.info("PostgreSQL credential already exists")
        existing = _find_credential_by_name(client, "CineOS PostgreSQL")
        return existing.get("id") if existing else None
    log.error("Failed to create PostgreSQL credential: HTTP %d — %s", resp.status_code, resp.text[:300])
    return None


def create_telegram_credential(client: httpx.Client) -> str | None:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set — skipping Telegram credential")
        return None

    payload = {
        "name": "CineOS Telegram",
        "type": "telegramApi",
        "data": {
            "accessToken": TELEGRAM_BOT_TOKEN,
        },
    }
    resp = client.post(f"{N8N_BASE}/api/v1/credentials", json=payload)
    if resp.status_code in (200, 201):
        cred_id = resp.json().get("id")
        log.info("Created Telegram credential (id=%s)", cred_id)
        return cred_id
    if resp.status_code == 409:
        log.info("Telegram credential already exists")
        existing = _find_credential_by_name(client, "CineOS Telegram")
        return existing.get("id") if existing else None
    log.error("Failed to create Telegram credential: HTTP %d — %s", resp.status_code, resp.text[:300])
    return None


def _find_credential_by_name(client: httpx.Client, name: str) -> dict | None:
    resp = client.get(f"{N8N_BASE}/api/v1/credentials")
    if resp.status_code != 200:
        return None
    for cred in resp.json().get("data", []):
        if cred.get("name") == name:
            return cred
    return None


def main():
    log.info("=== CineOS n8n Setup ===")

    if not wait_for_n8n():
        sys.exit(1)

    with httpx.Client(timeout=REQUEST_TIMEOUT, headers=auth_headers()) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                create_postgres_credential(client)
                break
            except Exception as exc:
                log.warning("Postgres credential attempt %d failed: %s", attempt, exc)
                if attempt == MAX_RETRIES:
                    log.error("Giving up on Postgres credential after %d attempts", MAX_RETRIES)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                create_telegram_credential(client)
                break
            except Exception as exc:
                log.warning("Telegram credential attempt %d failed: %s", attempt, exc)
                if attempt == MAX_RETRIES:
                    log.error("Giving up on Telegram credential after %d attempts", MAX_RETRIES)

        imported = []
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                imported = import_workflows(client)
                break
            except Exception as exc:
                log.warning("Workflow import attempt %d failed: %s", attempt, exc)
                if attempt == MAX_RETRIES:
                    log.error("Giving up on workflow import after %d attempts", MAX_RETRIES)

        if imported:
            activate_workflows(client, imported)

    log.info("=== n8n setup complete ===")
    log.info(
        "Summary: %d workflows imported, credentials created",
        len(imported),
    )


if __name__ == "__main__":
    main()
