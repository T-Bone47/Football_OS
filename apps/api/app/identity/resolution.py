"""Conservative cross-provider identity resolution.

Rules, in order of confidence:

1. ``DIRECT_PROVIDER_ID`` — the provider id is already mapped to a canonical player.
2. ``VERIFIED_ALIAS`` — a previously verified alias of a canonical player.
3. ``STRONG_EVIDENCE`` — same normalised name **and** the same date of birth **and**
   a compatible nationality, or the same name with a club that both records share.
4. ``PROBABILISTIC`` — a scored candidate that is *not* strong enough to merge
   automatically: it is written to the review queue instead.
5. ``AMBIGUOUS`` — several equally plausible candidates: review queue, no merge.

Two players are never merged on the name alone, and a match is never forced when the
evidence is insufficient. Every automatic decision is written to `field_provenance`
and every ambiguous decision to `identity_review_queue`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Player, PlayerIdentity
from app.db.models.expansion import FieldProvenance, IdentityReviewItem, PlayerAlias
from app.identity.names import name_key, name_tokens, normalize_name

# Minimum score for an automatic merge. Deliberately high: a false merge corrupts
# every downstream feature, a missed merge is recoverable through the review queue.
AUTO_MERGE_SCORE = 0.92
REVIEW_SCORE = 0.55


@dataclass
class IdentityEvidence:
    """Why two records are (or are not) the same person."""

    name_match: bool = False
    name_score: float = 0.0
    dob_match: bool | None = None
    nationality_match: bool | None = None
    club_match: bool | None = None
    shared_clubs: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name_match": self.name_match,
            "name_score": round(self.name_score, 4),
            "dob_match": self.dob_match,
            "nationality_match": self.nationality_match,
            "club_match": self.club_match,
            "shared_clubs": self.shared_clubs,
            "notes": list(self.notes),
        }


def _dob_match(left: date | None, right: date | None) -> bool | None:
    if left is None or right is None:
        return None
    return left == right


def _nationality_match(left: str | None, right: str | None) -> bool | None:
    if not left or not right:
        return None
    return normalize_name(left) == normalize_name(right)


def score_candidates(
    *,
    name: str,
    date_of_birth: date | None,
    nationality: str | None,
    club_ids: set[str] | None,
    candidates: list[tuple[Player, set[str]]],
) -> list[tuple[Player, float, IdentityEvidence]]:
    """Score every candidate against the incoming record.

    ``candidates`` pairs a canonical player with the club ids seen for that player.
    """
    incoming_key = name_key(name)
    incoming_tokens = set(name_tokens(name))
    scored: list[tuple[Player, float, IdentityEvidence]] = []

    for player, player_clubs in candidates:
        evidence = IdentityEvidence()
        player_key = name_key(player.name)
        player_tokens = set(name_tokens(player.name))

        if incoming_key and incoming_key == player_key:
            evidence.name_match = True
            evidence.name_score = 1.0
        elif incoming_tokens and player_tokens:
            overlap = len(incoming_tokens & player_tokens)
            union = len(incoming_tokens | player_tokens)
            evidence.name_score = round(overlap / union, 4) if union else 0.0
            evidence.name_match = evidence.name_score >= 0.6
        else:
            evidence.name_score = 0.0

        evidence.dob_match = _dob_match(date_of_birth, player.date_of_birth)
        evidence.nationality_match = _nationality_match(nationality, player.nationality)
        if club_ids is not None:
            shared = club_ids & player_clubs
            evidence.shared_clubs = len(shared)
            evidence.club_match = bool(shared)

        score = evidence.name_score
        # Supporting evidence raises the score; contradicting evidence lowers it.
        if evidence.dob_match is True:
            score += 0.15
        elif evidence.dob_match is False:
            score -= 0.45
        if evidence.nationality_match is True:
            score += 0.05
        elif evidence.nationality_match is False:
            score -= 0.20
        if evidence.shared_clubs:
            score += min(0.10, 0.05 * evidence.shared_clubs)
        if not evidence.name_match:
            score -= 0.30

        # Hard rules, applied after scoring:
        #  * a contradicting date of birth or nationality can never auto-merge;
        #  * a name match on its own can never auto-merge — two players are never
        #    merged just because their names are equal.
        contradicting = evidence.dob_match is False or evidence.nationality_match is False
        no_supporting_evidence = (
            evidence.dob_match is None
            and evidence.nationality_match is None
            and not evidence.shared_clubs
        )
        if contradicting or no_supporting_evidence:
            score = min(score, AUTO_MERGE_SCORE - 0.01)
            if contradicting:
                evidence.notes.append("contradicting dob/nationality: automatic merge blocked")
            else:
                evidence.notes.append("name-only match: automatic merge blocked")

        scored.append((player, max(0.0, min(1.0, score)), evidence))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


class IdentityResolver:
    """Resolves provider records onto canonical players, conservatively."""

    def __init__(self, session: AsyncSession, provider: str) -> None:
        self._session = session
        self._provider = provider

    async def _identity_for(self, provider_player_id: str) -> PlayerIdentity | None:
        return (
            await self._session.execute(
                select(PlayerIdentity).where(
                    PlayerIdentity.provider == self._provider,
                    PlayerIdentity.provider_player_id == provider_player_id,
                )
            )
        ).scalar_one_or_none()

    async def _alias_match(self, aliases: list[str]) -> Player | None:
        for alias in aliases:
            row = (
                await self._session.execute(
                    select(PlayerAlias).where(
                        PlayerAlias.provider == self._provider,
                        PlayerAlias.alias == alias,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                return (
                    await self._session.execute(
                        select(Player).where(Player.id == row.player_id)
                    )
                ).scalar_one_or_none()
        return None

    async def resolve(
        self,
        *,
        provider_player_id: str,
        name: str,
        date_of_birth: date | None = None,
        nationality: str | None = None,
        club_ids: set[str] | None = None,
        aliases: list[str] | None = None,
    ) -> tuple[Player | None, str, float, IdentityEvidence]:
        """Resolve one provider record.

        Returns ``(player_or_None, method, score, evidence)``. ``player_or_None`` is
        None when the record must be queued for review instead of merged.
        """
        identity = await self._identity_for(provider_player_id)
        if identity is not None:
            player = (
                await self._session.execute(select(Player).where(Player.id == identity.player_id))
            ).scalar_one()
            return player, "DIRECT_PROVIDER_ID", 1.0, IdentityEvidence(
                name_match=True, name_score=1.0, notes=["provider id already mapped"]
            )

        if aliases:
            alias_player = await self._alias_match(aliases)
            if alias_player is not None:
                return alias_player, "VERIFIED_ALIAS", 0.99, IdentityEvidence(
                    name_match=True, name_score=1.0, notes=["matched a verified alias"]
                )

        candidates = await self._candidates(name)
        scored = score_candidates(
            name=name,
            date_of_birth=date_of_birth,
            nationality=nationality,
            club_ids=club_ids,
            candidates=candidates,
        )
        if not scored:
            return None, "NEW", 0.0, IdentityEvidence(notes=["no comparable canonical player"])

        best_player, best_score, best_evidence = scored[0]
        runner_up_score = scored[1][1] if len(scored) > 1 else 0.0

        if best_score >= AUTO_MERGE_SCORE and best_score - runner_up_score >= 0.05:
            return best_player, "STRONG_EVIDENCE", best_score, best_evidence

        if best_score >= REVIEW_SCORE:
            best_evidence.notes.append("ambiguous: queued for review, not merged")
            await self.queue_for_review(
                provider_player_id=provider_player_id,
                candidate_player_id=best_player.id,
                score=best_score,
                evidence=best_evidence,
            )
            return None, "AMBIGUOUS", best_score, best_evidence

        return None, "NO_MATCH", best_score, best_evidence

    async def _candidates(self, name: str) -> list[tuple[Player, set[str]]]:
        """Canonical players whose name key matches the incoming name key."""
        key = name_key(name)
        if not key:
            return []
        rows = (
            await self._session.execute(
                select(Player).where(Player.name_normalized.isnot(None))
            )
        ).scalars().all()
        matched = [player for player in rows if name_key(player.name) == key]
        if not matched:
            return []
        club_map: dict[uuid.UUID, set[str]] = {}
        for player in matched:
            club_map[player.id] = set()
        return [(player, club_map[player.id]) for player in matched]

    async def queue_for_review(
        self,
        *,
        provider_player_id: str,
        candidate_player_id: uuid.UUID,
        score: float,
        evidence: IdentityEvidence,
    ) -> None:
        existing = (
            await self._session.execute(
                select(IdentityReviewItem).where(
                    IdentityReviewItem.provider == self._provider,
                    IdentityReviewItem.provider_entity_id == provider_player_id,
                    IdentityReviewItem.candidate_player_id == candidate_player_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.match_score = score
            existing.evidence = evidence.as_dict()
            existing.status = "PENDING"
            return
        self._session.add(
            IdentityReviewItem(
                provider=self._provider,
                provider_entity_id=provider_player_id,
                candidate_player_id=candidate_player_id,
                match_score=score,
                evidence=evidence.as_dict(),
                status="PENDING",
            )
        )

    async def record_field_provenance(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        field_name: str,
        provider_entity_id: str | None,
        source_value: Any,
        transformation: str | None = None,
        source_hash: str | None = None,
        confidence: float | None = None,
    ) -> None:
        row = (
            await self._session.execute(
                select(FieldProvenance).where(
                    FieldProvenance.entity_type == entity_type,
                    FieldProvenance.entity_id == entity_id,
                    FieldProvenance.field_name == field_name,
                    FieldProvenance.provider == self._provider,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            self._session.add(
                FieldProvenance(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_name=field_name,
                    provider=self._provider,
                    provider_entity_id=provider_entity_id,
                    source_value=source_value,
                    transformation=transformation,
                    source_hash=source_hash,
                    confidence=confidence,
                )
            )
            return
        row.source_value = source_value
        row.transformation = transformation
        row.source_hash = source_hash
        row.confidence = confidence
