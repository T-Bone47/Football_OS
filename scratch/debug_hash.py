import asyncio
import sys
sys.path.append("apps/api")
sys.path.append(".")

from datetime import datetime, timezone
from app.decisions.recruitment import RecruitmentTargetEngine
from app.decisions.schemas import RecruitmentTargetRequest
from tests.unit.test_phase8_reproducibility import _make_candidate

async def main():
    engine = RecruitmentTargetEngine(session=None)
    t0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    req = RecruitmentTargetRequest(
        target_position='MF',
        target_role='Playmaker',
        tactical_context_id='possession_dominant_433',
        budget_eur=30_000_000.0,
        as_of=t0,
    )
    c1 = _make_candidate('00000000-0000-0000-0000-000000000001', 'Player One', 20_000_000.0, 85.0)
    res1 = await engine.evaluate_recruitment(req, candidates_override=[c1])
    res2 = await engine.evaluate_recruitment(req, candidates_override=[c1])
    print('res1 hash:', res1.decision.evidence_hash)
    print('res2 hash:', res2.decision.evidence_hash)
    for i, (n1, n2) in enumerate(zip(res1.decision.evidence_graph.nodes, res2.decision.evidence_graph.nodes)):
        if n1 != n2:
            print(f'Diff node {i}:', n1, 'VS', n2)

asyncio.run(main())
