#!/usr/bin/env python3
"""
Migration script: Move jobs.json + user_names.json data into SQLite.

- user_names.json -> users table (api_key + display_name)
- jobs.json (NDJSON) -> jobs table + quota_charges table

Leaderboard starts empty in the new DB (leaderboard.json not migrated by design).

Usage:
    python scripts/migrate_to_sqlite.py [--dry-run] [--force]

After migration, restart the server. The old .json files are backed up.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# Make the slacathon package importable when run from anywhere
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from slacathon.db import (
    init_db,
    upsert_user,
    insert_job,
    load_jobs as db_load_jobs,
)
from slacathon.settings import settings


def backup_file(src: Path, timestamp: int) -> Path:
    """Create a timestamped backup of a file."""
    if not src.exists():
        return None
    backup = src.with_suffix(f".json.bak.{timestamp}")
    shutil.copy2(src, backup)
    return backup


def _migrate_insert_quota_charge(db_path: Path, user_id: str, charged_at: float, job_id: str | None, kind: str) -> None:
    """Migration-only insert (bypasses app-level atomic charge logic)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO quota_charges (user_id, charged_at, job_id, kind) VALUES (?, ?, ?, ?)",
            (user_id, charged_at, job_id, kind),
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_get_all_user_charge_counts(db_path: Path) -> dict[str, int]:
    """Migration-only count for guard check."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT user_id, COUNT(*) as c FROM quota_charges GROUP BY user_id"
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def migrate_users(dry_run: bool, data_dir: Path, timestamp: int) -> int:
    user_file = data_dir / "user_names.json"
    if not user_file.exists():
        print(f"[users] No {user_file} found, skipping.")
        return 0

    with open(user_file) as f:
        users = json.load(f)

    print(f"[users] Found {len(users)} entries in {user_file}")

    if not dry_run:
        for api_key, display_name in users.items():
            upsert_user(api_key, display_name)
        backup = backup_file(user_file, timestamp)
        if backup:
            print(f"[users] Backed up original to {backup}")

    return len(users)


def migrate_jobs_and_charges(dry_run: bool, data_dir: Path, timestamp: int) -> tuple[int, int]:
    jobs_file = data_dir / "jobs.json"
    if not jobs_file.exists():
        print(f"[jobs] No {jobs_file} found, skipping.")
        return 0, 0

    print(f"[jobs] Processing NDJSON file {jobs_file} (this may take a moment for large files)...")

    job_map: dict[str, dict] = {}          # job_id -> best record (prefer completed)
    charges: list[dict] = []
    seen_charge_keys: set[tuple] = set()

    line_count = 0
    with open(jobs_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line_count += 1
            try:
                rec = json.loads(line)
            except Exception:
                continue

            user_id = rec.get("user_id")
            if not user_id:
                continue

            job_id = rec.get("job_id")
            kind = rec.get("kind", "validate" if job_id else "submit")
            created_at = rec.get("created_at", time.time())

            # Dedup charges: one per (user_id, job_id) for jobs, or (user_id, created_at) for submits
            charge_key = (user_id, job_id) if job_id else (user_id, round(created_at, 3))
            if charge_key not in seen_charge_keys:
                seen_charge_keys.add(charge_key)
                charges.append({
                    "user_id": user_id,
                    "charged_at": created_at,
                    "job_id": job_id,
                    "kind": kind,
                })

            # Collect best job record
            if job_id:
                current = job_map.get(job_id)
                # Prefer completed records
                if (not current) or (rec.get("status") == "completed" and current.get("status") != "completed"):
                    job_map[job_id] = rec

    print(f"[jobs] Parsed {line_count} lines → {len(job_map)} unique jobs, {len(charges)} charges")

    if not dry_run:
        # Insert jobs (prefer completed data)
        for job_id, rec in job_map.items():
            insert_job({
                "job_id": job_id,
                "user_id": rec["user_id"],
                "input": rec.get("input", {}),
                "status": rec.get("status", "completed"),
                "result": rec.get("result"),
                "created_at": rec.get("created_at"),
                "completed_at": rec.get("completed_at"),
            })

        # Insert charges
        for ch in charges:
            _migrate_insert_quota_charge(
                settings.db_file,
                ch["user_id"],
                ch["charged_at"],
                ch["job_id"],
                ch["kind"],
            )

        backup = backup_file(jobs_file, timestamp)
        if backup:
            print(f"[jobs] Backed up original to {backup}")

    return len(job_map), len(charges)



def main():
    parser = argparse.ArgumentParser(description="Migrate JSON data to SQLite (jobs + users + leaderboard).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done, do not modify DB or files.")
    parser.add_argument("--force", action="store_true", help="Proceed even if DB already contains data.")
    args = parser.parse_args()

    data_dir = Path(settings.db_file).parent
    print(f"Data directory: {data_dir}")
    print(f"Database:       {settings.db_file}")
    print(f"Mode:           {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    init_db()

    # Simple guard: if users or jobs already exist, require --force
    if not args.force and not args.dry_run:
        from slacathon.db import load_users as _load_users
        existing_users = len(_load_users() or {})
        existing_jobs = len(db_load_jobs() or {})
        existing_charges = sum(_migrate_get_all_user_charge_counts(settings.db_file).values())
        if existing_users or existing_jobs or existing_charges:
            print("Database already contains data.")
            print(f"  users: {existing_users}, jobs: {existing_jobs}, charges: {existing_charges}")
            print("Use --force to overwrite / add anyway, or --dry-run to inspect.")
            sys.exit(1)

    timestamp = int(time.time())

    # 1. Users
    n_users = migrate_users(args.dry_run, data_dir, timestamp)

    # 2. Jobs + Quota charges
    n_jobs, n_charges = migrate_jobs_and_charges(args.dry_run, data_dir, timestamp)

    print()
    print("=== Migration summary ===")
    print(f"Users migrated:   {n_users}")
    print(f"Jobs migrated:    {n_jobs}")
    print(f"Charges created:  {n_charges}")
    print()
    if not args.dry_run:
        print("Migration finished. You can now restart the server.")
        print("The old JSON files have been backed up with .bak.<timestamp> suffix.")
    else:
        print("Dry run complete. No changes were made.")


if __name__ == "__main__":
    main()