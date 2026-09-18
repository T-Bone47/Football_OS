import json

from app.db.models.provenance import ValidationStatus
from app.validation.validate import validate_snapshot


def test_rejects_non_json():
    status, error = validate_snapshot("statsbomb", "competitions", b"not json{{{")
    assert status == ValidationStatus.INVALID
    assert "JSON" in error


def test_statsbomb_competitions_valid_row_passes():
    payload = [
        {
            "competition_id": 11,
            "season_id": 90,
            "country_name": "Spain",
            "competition_name": "La Liga",
            "competition_gender": "male",
        }
    ]
    status, error = validate_snapshot("statsbomb", "competitions", json.dumps(payload).encode())
    assert status == ValidationStatus.VALID
    assert error is None


def test_statsbomb_competitions_missing_field_is_invalid():
    payload = [{"competition_id": 11, "season_id": 90}]  # missing required fields
    status, error = validate_snapshot("statsbomb", "competitions", json.dumps(payload).encode())
    assert status == ValidationStatus.INVALID
    assert error


def test_api_football_envelope_shape():
    payload = {"get": "leagues", "parameters": {}, "errors": [], "results": 0, "paging": {}, "response": []}
    status, error = validate_snapshot("api-football", "leagues", json.dumps(payload).encode())
    assert status == ValidationStatus.VALID


def test_unknown_provider_resource_is_pending_not_fabricated_valid():
    status, error = validate_snapshot("some-future-provider", "whatever", b'{"a": 1}')
    assert status == ValidationStatus.PENDING
    assert "no schema" in error
