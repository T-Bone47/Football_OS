"""Final Silver DataQualityReport per pilot competition season, run after
all lineups and events are loaded (§10).

Usage:  python tools/phase17/assess_quality.py
Writes: docs/evidence/phase17/quality_final.json
"""
from __future__ import annotations

import asyncio

from common import now, write_evidence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.canonical import Competition, CompetitionSeason, Season
from app.phase17.data_quality import assess_silver

URL = "postgresql+asyncpg://fios:fios@localhost:5432/fios_p17_live"


async def main() -> None:
    engine = create_async_engine(URL)
    out = {}
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        rows = (await s.execute(select(CompetitionSeason.id, Competition.name, Season.name)
                                .join(Competition).join(Season))).all()
        for cs_id, comp, season in rows:
            report = await assess_silver(s, "statsbomb", cs_id)
            await report.persist(s)
            out[f"{comp} {season}"] = report.to_dict()
        await s.commit()
    await engine.dispose()
    print("wrote", write_evidence("quality_final", {"reports": out, "finished_at": now()}))


if __name__ == "__main__":
    asyncio.run(main())
