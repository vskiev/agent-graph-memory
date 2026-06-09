#!/usr/bin/env python3
"""
Spec Status Sync
Compares PROJ files (source of truth) with graph database.
Updates graph where statuses differ.

Usage:
  docker exec agent-graph-mcp python3 /app/sync_specs.py
  docker exec agent-graph-mcp python3 /app/sync_specs.py --dry-run
"""
import asyncio
import os
import re
import sys
from pathlib import Path

REPO        = Path(os.getenv("REPO_PATH", "/repo"))
DB_URL      = os.getenv("SURREALDB_URL",  "ws://surrealdb:8000/rpc")
DB_USER     = os.getenv("SURREALDB_USER", "root")
DB_PASS     = os.getenv("SURREALDB_PASS", "root_password")
DB_NS       = os.getenv("SURREALDB_NS",   "project")
DB_DB       = os.getenv("SURREALDB_DB",   "main")

DRY_RUN = "--dry-run" in sys.argv

VALID_STATUSES = {"draft", "ready", "in-progress", "done", "rejected", "unknown"}


def load_proj_files(repo: Path) -> dict[str, str]:
    """Read all PROJ-*.md files → {ticket: status}."""
    proj_dir = repo / "specs" / "proj"
    if not proj_dir.exists():
        print(f"⚠  specs/proj not found at {proj_dir}")
        return {}

    statuses = {}
    for f in sorted(proj_dir.glob("PROJ-*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r'\|\s*Status\s*\|\s*(\S+)\s*\|', text)
        ticket = f.stem.replace("PROJ-", "")
        statuses[ticket] = m.group(1) if m else "unknown"
    return statuses


async def main():
    from surrealdb import AsyncSurreal

    print(f"🔍 Reading PROJ files from {REPO / 'specs' / 'proj'}")
    file_statuses = load_proj_files(REPO)
    if not file_statuses:
        print("No PROJ files found.")
        return

    print(f"   Found {len(file_statuses)} PROJ files\n")

    async with AsyncSurreal(DB_URL) as db:
        await db.signin({"username": DB_USER, "password": DB_PASS})
        await db.use(DB_NS, DB_DB)

        rows = await db.query("SELECT ticket, status FROM spec ORDER BY ticket")
        graph_statuses = {r["ticket"]: r["status"] for r in rows}

    all_tickets = sorted(set(file_statuses) | set(graph_statuses))

    mismatches  = []
    only_file   = []
    only_graph  = []
    in_sync     = []

    for t in all_tickets:
        fs = file_statuses.get(t)
        gs = graph_statuses.get(t)
        if fs and not gs:
            only_file.append((t, fs))
        elif gs and not fs:
            only_graph.append((t, gs))
        elif fs != gs:
            mismatches.append((t, fs, gs))
        else:
            in_sync.append(t)

    print(f"✅ In sync:  {len(in_sync)} specs")

    if only_file:
        print(f"\n⚠  In files but missing from graph ({len(only_file)}):")
        for t, fs in only_file:
            print(f"   {t:<35} file={fs}")

    if only_graph:
        print(f"\n⚠  In graph but no PROJ file ({len(only_graph)}):")
        for t, gs in only_graph:
            print(f"   {t:<35} graph={gs}")

    if mismatches:
        print(f"\n❌ Status mismatches ({len(mismatches)}):")
        for t, fs, gs in mismatches:
            print(f"   {t:<35} file={fs:<15} graph={gs}")

    needs_update = mismatches or only_file
    if not needs_update:
        print("\n🎉 Graph is fully in sync with PROJ files.")
        return

    if DRY_RUN:
        print(f"\n[DRY RUN] Would update {len(mismatches)} mismatches + insert {len(only_file)} missing specs.")
        return

    print(f"\n🔄 Updating graph...")

    async with AsyncSurreal(DB_URL) as db:
        await db.signin({"username": DB_USER, "password": DB_PASS})
        await db.use(DB_NS, DB_DB)

        updated = 0
        inserted = 0

        for t, fs, gs in mismatches:
            await db.query(
                "UPDATE spec SET status = $s, updated_by = 'sync_specs', updated_at = time::now() WHERE ticket = $t",
                {"t": t, "s": fs}
            )
            print(f"   ✓ Updated  {t}: {gs} → {fs}")
            updated += 1

        for t, fs in only_file:
            await db.query(
                "CREATE spec CONTENT $data",
                {"data": {"ticket": t, "status": fs, "branch": "", "spec_path": "", "key_files": [], "ac": []}}
            )
            print(f"   ✓ Inserted {t}: {fs}")
            inserted += 1

    print(f"\n✅ Done — {updated} updated, {inserted} inserted.")


if __name__ == "__main__":
    asyncio.run(main())
