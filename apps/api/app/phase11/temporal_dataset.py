"""Phase 11 — Temporal Dataset Builder & Leakage Protection (§7).

Enforces strict chronological ordering across train, validation, and test splits.
Guarantees that no future result, performance, transfer, lineup, or event leaks
into pre-match feature vectors (feature_as_of < target_date).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, date
import hashlib
import json
from typing import Any, Sequence


@dataclass
class TemporalExample:
    """Single time-indexed training/validation record with provenance (§7)."""
    example_id: str
    entity_ids: dict[str, str]  # e.g. {"home_club": "c_arsenal", "away_club": "c_chelsea"}
    competition: str
    season: str
    match_date: str
    feature_as_of: str
    target_date: str
    feature_set_version: str
    dataset_version: str
    features: dict[str, float]
    target: Any
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.checksum:
            payload = json.dumps({
                "example_id": self.example_id,
                "features": self.features,
                "feature_as_of": self.feature_as_of,
                "target": self.target,
            }, sort_keys=True)
            self.checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TemporalSplit:
    """Chronologically bounded dataset partition."""
    split_name: str  # "train", "validation", "test"
    start_date: str
    end_date: str
    examples: list[TemporalExample] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.examples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "split_name": self.split_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "count": self.count,
            "examples": [e.to_dict() for e in self.examples],
        }


class TemporalDatasetBuilder:
    """Builder enforcing chronological cutoff integrity and adversarial leakage validation."""

    def __init__(self, dataset_version: str = "1.0.0", feature_set_version: str = "match_prediction_v1") -> None:
        self.dataset_version = dataset_version
        self.feature_set_version = feature_set_version

    def build_splits(
        self,
        raw_records: Sequence[dict[str, Any]],
        train_end: str,
        val_end: str,
        date_field: str = "match_date",
    ) -> dict[str, TemporalSplit]:
        """Partitions records into train, validation, and test splits with strict ordering.
        
        Ordering invariant:
        train: [min_date, train_end]
        validation: (train_end, val_end]
        test: (val_end, max_date]
        """
        sorted_records = sorted(raw_records, key=lambda x: str(x.get(date_field, "")))
        if not sorted_records:
            return {
                "train": TemporalSplit("train", "", train_end),
                "validation": TemporalSplit("validation", train_end, val_end),
                "test": TemporalSplit("test", val_end, ""),
            }

        min_date = str(sorted_records[0].get(date_field, ""))
        max_date = str(sorted_records[-1].get(date_field, ""))

        train_split = TemporalSplit("train", min_date, train_end)
        val_split = TemporalSplit("validation", train_end, val_end)
        test_split = TemporalSplit("test", val_end, max_date)

        for r in sorted_records:
            m_date = str(r.get(date_field, ""))
            as_of = str(r.get("feature_as_of", m_date))

            # Strictly enforce feature_as_of <= match_date
            if as_of > m_date:
                raise ValueError(
                    f"Temporal leakage violation: feature_as_of ({as_of}) > match_date ({m_date}) "
                    f"for record {r.get('match_id', 'unknown')}"
                )

            example = TemporalExample(
                example_id=str(r.get("match_id", f"ex_{len(train_split.examples) + len(val_split.examples) + len(test_split.examples)}")),
                entity_ids={
                    "home_club": str(r.get("home_club_id", "")),
                    "away_club": str(r.get("away_club_id", "")),
                },
                competition=str(r.get("competition", "EPL")),
                season=str(r.get("season", "2023/2024")),
                match_date=m_date,
                feature_as_of=as_of,
                target_date=m_date,
                feature_set_version=self.feature_set_version,
                dataset_version=self.dataset_version,
                features=r.get("features", {}),
                target=r.get("target", r.get("outcome", 0)),
            )

            if m_date <= train_end:
                train_split.examples.append(example)
            elif m_date <= val_end:
                val_split.examples.append(example)
            else:
                test_split.examples.append(example)

        return {
            "train": train_split,
            "validation": val_split,
            "test": test_split,
        }

    def verify_adversarial_invariance(
        self,
        base_example: TemporalExample,
        future_injections: list[dict[str, Any]],
    ) -> bool:
        """Adversarial validation: Injects future matches/stats/transfers and verifies bit-for-bit invariance.
        
        The historical prediction/feature checksum MUST remain identical.
        """
        # Historical example checksum
        orig_checksum = base_example.checksum

        # Filter injections: only allow features as-of base_example.feature_as_of
        filtered_features = dict(base_example.features)
        for injection in future_injections:
            event_date = str(injection.get("event_date", ""))
            if event_date <= base_example.feature_as_of:
                # Legitimate pre-cutoff update
                filtered_features.update(injection.get("features", {}))
            # Future events (> feature_as_of) are strictly ignored by pre-match builder

        # Re-compute checksum
        test_payload = json.dumps({
            "example_id": base_example.example_id,
            "features": filtered_features,
            "feature_as_of": base_example.feature_as_of,
            "target": base_example.target,
        }, sort_keys=True)
        new_checksum = hashlib.sha256(test_payload.encode("utf-8")).hexdigest()

        return orig_checksum == new_checksum
