"""Unit tests for Action-Value Foundation and Data Sufficiency Gates (Phase 3.1I/J/K)."""
import uuid
from dataclasses import dataclass
from app.action_value.action_impact import ActionImpactModel
from app.action_value.spatial_threat import SpatialThreatModel


@dataclass
class MockAction:
    action_type: str
    action_subtype: str
    action_quantity: int = 1
    minute: int = 45
    outcome: str = "SUCCESS"
    x: float | None = None
    y: float | None = None


def test_spatial_threat_model_data_sufficiency_gate():
    model = SpatialThreatModel()
    p_id = uuid.uuid4()

    # Actions lacking coordinates
    actions_without_coords = [
        MockAction(action_type="PASSING", action_subtype="PASS_COMPLETED"),
        MockAction(action_type="SHOOTING", action_subtype="GOAL"),
    ]

    result = model.evaluate(p_id, actions_without_coords, minutes=900)

    # Strictly verifies that lack of coordinates triggers INSUFFICIENT_DATA
    assert result.status == "INSUFFICIENT_DATA"
    assert result.spatial_data_sufficient is False
    assert result.net_action_value is None
    assert result.action_value_per_90 is None
    assert "Granular (x, y) pitch coordinates are required" in (result.data_limitation_reason or "")
    assert len(result.licensing_requirements) > 0
    assert any("StatsBomb" in req or "Opta" in req for req in result.licensing_requirements)


def test_action_impact_model_insufficient_sample():
    model = ActionImpactModel()
    p_id = uuid.uuid4()

    actions = [MockAction(action_type="SHOOTING", action_subtype="GOAL")]
    # Only 90 minutes -> below 270 min threshold
    result = model.evaluate(p_id, actions, minutes=90)

    assert result.status == "INSUFFICIENT_SAMPLE"
    assert result.net_action_value is None
    assert result.action_value_per_90 is None


def test_action_impact_model_evaluated():
    model = ActionImpactModel()
    p_id = uuid.uuid4()

    actions = [
        MockAction(action_type="SHOOTING", action_subtype="GOAL", action_quantity=1),
        MockAction(action_type="CREATION", action_subtype="KEY_PASS", action_quantity=3),
        MockAction(action_type="DEFENDING", action_subtype="TACKLE", action_quantity=4),
        MockAction(action_type="PASSING", action_subtype="PASS_COMPLETED", action_quantity=50),
    ]

    # 450 minutes -> LOW/EVALUATED sample
    result = model.evaluate(p_id, actions, minutes=450)

    assert result.status == "EVALUATED"
    assert result.net_action_value is not None
    assert result.net_action_value > 0.0
    assert result.action_value_per_90 is not None
    assert result.total_actions_evaluated == 4
