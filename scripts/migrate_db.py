#!/usr/bin/env python3
"""Database migration runner for CineOS PostgreSQL schemas."""

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("migrate_db")

DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "cineos")
DB_USER = os.getenv("POSTGRES_USER", "cineos")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "cineos_secret")

DATABASE_DIR = Path(os.getenv("DATABASE_DIR", "/database"))

MIGRATION_ORDER = [
    ("schema.sql", "Create types, schemas, and tables"),
    ("indexes.sql", "Create performance indexes"),
    ("constraints.sql", "Add foreign key and check constraints"),
    ("functions.sql", "Create PL/pgSQL functions"),
    ("triggers.sql", "Create database triggers"),
    ("views.sql", "Create analytic views"),
]

SEED_DIR = DATABASE_DIR / "seed"
MIGRATIONS_TABLE = "cineos_core.schema_migrations"


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def ensure_migrations_table(conn):
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            migration_id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL UNIQUE,
            file_hash TEXT NOT NULL,
            description TEXT,
            executed_at TIMESTAMPTZ DEFAULT NOW(),
            execution_ms INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT
        )
    """)
    conn.commit()
    cur.close()


def get_executed_migrations(conn) -> dict[str, dict]:
    cur = conn.cursor()
    cur.execute(f"SELECT filename, file_hash, description, executed_at, success FROM {MIGRATIONS_TABLE} ORDER BY migration_id")
    rows = cur.fetchall()
    cur.close()
    return {
        row[0]: {
            "file_hash": row[1],
            "description": row[2],
            "executed_at": row[3],
            "success": row[4],
        }
        for row in rows
    }


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_sql_file(conn, path: Path, dry_run: bool = False) -> tuple[bool, int, str]:
    sql = path.read_text(encoding="utf-8")
    if dry_run:
        log.info("  [DRY RUN] Would execute %s (%d bytes)", path.name, len(sql))
        return True, 0, ""

    cur = conn.cursor()
    import time
    start = time.monotonic()
    try:
        cur.execute(sql)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        conn.commit()
        log.info("  Executed %s (%d bytes, %dms)", path.name, len(sql), elapsed_ms)
        return True, elapsed_ms, ""
    except Exception as exc:
        conn.rollback()
        elapsed_ms = int((time.monotonic() - start) * 1000)
        log.error("  Failed on %s: %s", path.name, exc)
        return False, elapsed_ms, str(exc)
    finally:
        cur.close()


def record_migration(conn, filename: str, fhash: str, desc: str, ms: int, success: bool, error: str):
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO {MIGRATIONS_TABLE} (filename, file_hash, description, execution_ms, success, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (filename, fhash, desc, ms, success, error or None),
    )
    conn.commit()
    cur.close()


def run_seed_files(conn, dry_run: bool = False):
    if not SEED_DIR.is_dir():
        return

    seed_files = sorted(SEED_DIR.glob("*.sql"))
    if not seed_files:
        return

    log.info("Running %d seed files ...", len(seed_files))
    for path in seed_files:
        success, ms, err = run_sql_file(conn, path, dry_run)
        if not success:
            log.warning("  Seed file %s had errors (may contain IF NOT EXISTS)", path.name)


def run_migrations(force: bool = False, dry_run: bool = False):
    log.info("=== CineOS Database Migration ===")
    log.info("Database dir: %s", DATABASE_DIR)
    log.info("Host: %s:%d  DB: %s  User: %s", DB_HOST, DB_PORT, DB_NAME, DB_USER)

    conn = get_connection()
    ensure_migrations_table(conn)
    executed = get_executed_migrations(conn)

    files_to_run: list[tuple[Path, str, str]] = []
    for filename, description in MIGRATION_ORDER:
        path = DATABASE_DIR / filename
        if not path.exists():
            log.warning("Migration file not found: %s (skipping)", path)
            continue

        fhash = file_hash(path)
        prev = executed.get(filename)

        if prev and not force:
            if prev["file_hash"] == fhash and prev["success"]:
                log.info("  [OK] %s — already applied", filename)
                continue
            elif prev["file_hash"] != fhash:
                log.warning("  [CHANGED] %s — file modified since last run", filename)
            elif not prev["success"]:
                log.warning("  [PREV FAIL] %s — re-running", filename)

        files_to_run.append((path, fhash, description))

    if force:
        log.info("--force: re-running all %d migration files", len(files_to_run))

    if not files_to_run:
        log.info("No pending migrations.")
    else:
        log.info("Running %d migration(s) ...", len(files_to_run))
        for path, fhash, desc in files_to_run:
            log.info("Applying: %s — %s", path.name, desc)
            success, ms, error = run_sql_file(conn, path, dry_run)
            if not dry_run:
                record_migration(conn, path.name, fhash, desc, ms, success, error)
            if not success and path.name == "schema.sql":
                log.error("Schema failed — aborting remaining migrations")
                break

    run_seed_files(conn, dry_run)

    cur = conn.cursor()
    cur.execute("SELECT current_state, COUNT(*) FROM cineos_core.projects GROUP BY current_state LIMIT 5")
    rows = cur.fetchall()
    if rows:
        log.info("Project state distribution:")
        for state, count in rows:
            log.info("  %s: %d", state, count)
    cur.close()

    conn.close()
    log.info("=== Migration complete ===")


def main():
    parser = argparse.ArgumentParser(description="CineOS database migration runner")
    parser.add_argument("--force", action="store_true", help="Re-run all migrations regardless of prior state")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be executed without making changes")
    args = parser.parse_args()

    for attempt in range(5):
        try:
            run_migrations(force=args.force, dry_run=args.dry_run)
            return
        except psycopg2.OperationalError as exc:
            log.warning("Connection failed (attempt %d/5): %s", attempt + 1, exc)
            if attempt < 4:
                import time
                time.sleep(3)
            else:
                log.error("Could not connect to database after 5 attempts")
                sys.exit(1)


if __name__ == "__main__":
    main()
