"""Phase 17 disaster-recovery drill (§37): backup -> restore -> verify.

- PostgreSQL: pg_dump (custom format) of the live database, pg_restore into
  a new database, then table-by-table row counts, the audit hash chain,
  decision content hashes and the immutability triggers are compared.
- Bronze: tar of the snapshot store, extracted elsewhere; every file must
  hash to its own name (content addressing makes this a full check).
- Configuration: templates and migrations hashed (never .env).
- Model registry: rows compared after restore.
Timings are measured; nothing is estimated.

Usage:  python tools/phase17/dr_drill.py
Writes: docs/evidence/phase17/dr_drill.json
"""
from __future__ import annotations

import asyncio
import hashlib
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from common import PG_ADMIN, ROOT, now, write_evidence
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.phase17.audit import verify_chain

SRC = "fios_p17_live"
DST = "fios_p17_restore"
BASE = "postgresql://fios:fios@localhost:5432"


async def snapshot_db(name: str) -> dict:
    engine = create_async_engine(f"postgresql+asyncpg://fios:fios@localhost:5432/{name}")
    async with async_sessionmaker(engine)() as s:
        tables = (await s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"))).scalars().all()
        counts = {t: (await s.execute(text(f'SELECT count(*) FROM "{t}"'))).scalar_one() for t in tables}
        chain = await verify_chain(s)
        decisions = (await s.execute(text("SELECT id::text, content_sha256 FROM ops_decisions ORDER BY 1"))).all()
        registry = (await s.execute(text("SELECT model_id, model_version, artifact_sha256, deployment_state, "
                                         "supported_competitions::text FROM ops_model_registry ORDER BY 1"))).all()
        triggers = (await s.execute(text("SELECT trigger_name FROM information_schema.triggers "
                                         "WHERE trigger_name LIKE 'ops_%_immutable' ORDER BY 1"))).scalars().all()
        head = (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    await engine.dispose()
    return {"row_counts": counts, "audit_chain": chain, "decision_hashes": [list(r) for r in decisions],
            "model_registry": [list(map(str, r)) for r in registry], "immutability_triggers": triggers,
            "migration_head": head}


def main() -> None:
    ev: dict = {"started_at": now(), "source_database": SRC, "restore_database": DST}
    work = Path(tempfile.mkdtemp(prefix="fios-dr-"))
    dump = work / f"{SRC}.dump"

    t0 = time.perf_counter()
    subprocess.run(["pg_dump", "-Fc", "-f", str(dump), f"{BASE}/{SRC}"], check=True)
    ev["postgres_backup"] = {"seconds": round(time.perf_counter() - t0, 2), "bytes": dump.stat().st_size,
                             "sha256": hashlib.sha256(dump.read_bytes()).hexdigest()}
    before = asyncio.run(snapshot_db(SRC))

    t0 = time.perf_counter()
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"DROP DATABASE IF EXISTS {DST} WITH (FORCE);"], check=True)
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"CREATE DATABASE {DST} OWNER fios;"], check=True)
    restore = subprocess.run(["pg_restore", "--no-owner", "-d", f"{BASE}/{DST}", str(dump)], capture_output=True, text=True)
    ev["postgres_restore"] = {"seconds": round(time.perf_counter() - t0, 2), "exit_code": restore.returncode,
                              "stderr_tail": restore.stderr[-500:]}
    t0 = time.perf_counter()
    after = asyncio.run(snapshot_db(DST))
    mismatched = {t: (before["row_counts"][t], after["row_counts"].get(t)) for t in before["row_counts"]
                  if before["row_counts"][t] != after["row_counts"].get(t)}
    ev["postgres_verification"] = {
        "seconds": round(time.perf_counter() - t0, 2),
        "tables": len(before["row_counts"]), "rows_total": sum(before["row_counts"].values()),
        "row_count_mismatches": mismatched,
        "audit_chain_source": before["audit_chain"], "audit_chain_restored": after["audit_chain"],
        "decision_hashes_equal": before["decision_hashes"] == after["decision_hashes"],
        "model_registry_equal": before["model_registry"] == after["model_registry"],
        "immutability_triggers_restored": sorted(set(after["immutability_triggers"])),
        "migration_head_restored": after["migration_head"],
        "passed": not mismatched and after["audit_chain"]["valid"] and before["audit_chain"]["head_hash"] == after["audit_chain"].get("head_hash")
                  and before["decision_hashes"] == after["decision_hashes"] and before["model_registry"] == after["model_registry"]
                  and len(set(after["immutability_triggers"])) == 3,
    }

    bronze = ROOT / "data" / "bronze"
    archive = work / "bronze.tar.gz"
    t0 = time.perf_counter()
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(bronze, arcname="bronze")
    backup_s = round(time.perf_counter() - t0, 2)
    t0 = time.perf_counter()
    out = work / "restored"
    with tarfile.open(archive) as tar:
        tar.extractall(out, filter="data")
    restore_s = round(time.perf_counter() - t0, 2)
    files = [p for p in (out / "bronze").rglob("*.json")]
    bad = [str(p.relative_to(out)) for p in files if hashlib.sha256(p.read_bytes()).hexdigest() != p.stem]
    ev["bronze"] = {"files": len(files), "archive_bytes": archive.stat().st_size, "backup_seconds": backup_s,
                    "restore_seconds": restore_s, "hash_mismatches": bad, "passed": not bad and bool(files)}

    config_files = sorted([*(ROOT / "deploy" / "env").glob("*.env.example"), ROOT / ".env.example", ROOT / "alembic.ini",
                           *(ROOT / "database" / "migrations" / "versions").glob("*.py")])
    ev["configuration"] = {"files": len(config_files),
                           "manifest_sha256": hashlib.sha256(b"".join(hashlib.sha256(p.read_bytes()).digest()
                                                                    for p in config_files)).hexdigest(),
                           "secrets_backed_up": False,
                           "note": ".env is excluded; production secrets belong to the secret manager's own backup"}
    total = ev["postgres_backup"]["seconds"] + ev["postgres_restore"]["seconds"] + ev["postgres_verification"]["seconds"] + \
        ev["bronze"]["restore_seconds"]
    ev["measured_recovery_time_seconds"] = round(total, 2)
    ev["scope_note"] = ("Measured on a single local PostgreSQL 16 instance and local disk in the sandbox. "
                        "Object storage (S3/MinIO) restore is NOT_TESTED: no object store is reachable here.")
    ev["finished_at"] = now()
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"DROP DATABASE IF EXISTS {DST} WITH (FORCE);"])
    print("wrote", write_evidence("dr_drill", ev))


if __name__ == "__main__":
    main()
