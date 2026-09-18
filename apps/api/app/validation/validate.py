"""Validation dispatcher (architecture doc §21/§27/§28): raw bytes in,
(ValidationStatus, errors) out. The raw snapshot is already saved by the
time this runs — validation never gates whether we keep the bytes, only
what we record about them.
"""
from __future__ import annotations

import json

import pandas as pd
import pandera.errors
from pydantic import ValidationError

from app.db.models.provenance import ValidationStatus
from app.validation.envelopes import ApiFootballEnvelope, FootballDataOrgEnvelope
from app.validation.statsbomb_schemas import StatsBombCompetitionSchema


def validate_snapshot(provider: str, resource: str, content: bytes) -> tuple[ValidationStatus, str | None]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return ValidationStatus.INVALID, f"not valid JSON: {exc}"

    try:
        if provider == "statsbomb" and resource == "competitions":
            StatsBombCompetitionSchema.validate(pd.DataFrame(payload))
        elif provider == "api-football":
            ApiFootballEnvelope.model_validate(payload)
        elif provider == "football-data-org":
            FootballDataOrgEnvelope.model_validate(payload)
        else:
            # No schema defined yet for this provider/resource pair — valid
            # JSON is all we can honestly claim, not "conforms to a shape".
            return ValidationStatus.PENDING, "no schema registered for this provider/resource yet"
    except pandera.errors.SchemaError as exc:
        return ValidationStatus.INVALID, str(exc)
    except ValidationError as exc:
        return ValidationStatus.INVALID, str(exc)

    return ValidationStatus.VALID, None
