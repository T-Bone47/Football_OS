"""Phase 17: Live Football Intelligence Operations.

Phase 17 adds no new intelligence layer. It makes the existing system
observable against real providers, real infrastructure and real state, and
it reports what it cannot observe instead of filling the gap.

Rules every module in this package follows:
- A state is derived from a recorded observation (a probe row, an ingestion
  run, a snapshot, an inference log row), never from a default.
- Missing evidence is reported as UNKNOWN / UNVERIFIED / NOT_TESTED /
  UNAVAILABLE, never as success.
- Historical predictions, decisions and audit events are immutable; the
  database enforces it with triggers (migration 0014).
"""

from enum import Enum


class Phase17ReleaseState(str, Enum):
    PHASE_17_IN_PROGRESS = "PHASE_17_IN_PROGRESS"
    LIVE_PROVIDER_VALIDATED = "LIVE_PROVIDER_VALIDATED"
    LIVE_DATA_PIPELINE_VALIDATED = "LIVE_DATA_PIPELINE_VALIDATED"
    LIVE_MODEL_OPERATIONS_VALIDATED = "LIVE_MODEL_OPERATIONS_VALIDATED"
    LIVE_FIELD_WORKFLOW_VALIDATED = "LIVE_FIELD_WORKFLOW_VALIDATED"
    LIVE_OUTCOME_VALIDATED = "LIVE_OUTCOME_VALIDATED"
    PRODUCTION_OPERATIONAL = "PRODUCTION_OPERATIONAL"
    PHASE_17_RELEASE_BLOCKED = "PHASE_17_RELEASE_BLOCKED"
    LIVE_FOOTBALL_INTELLIGENCE_OPERATIONAL = "LIVE_FOOTBALL_INTELLIGENCE_OPERATIONAL"


class EvidenceLevel(str, Enum):
    """Certification vocabulary (§63). Ordered loosely from weakest claim."""

    NOT_TESTED = "NOT_TESTED"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    IMPLEMENTED = "IMPLEMENTED"
    SIMULATED = "SIMULATED"
    VERIFIED = "VERIFIED"
    VALIDATED = "VALIDATED"
    STAGING_ONLY = "STAGING_ONLY"
    SHADOW_ONLY = "SHADOW_ONLY"
    LIVE_VERIFIED = "LIVE_VERIFIED"
    PRODUCTION_READY = "PRODUCTION_READY"


class ProviderConnectivityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class CapabilityState(str, Enum):
    LIVE_AVAILABLE = "LIVE_AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"


class ScheduleClass(str, Enum):
    LIVE = "LIVE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    SEASONAL = "SEASONAL"
    ON_DEMAND = "ON_DEMAND"


class QualityStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class FeatureRefreshState(str, Enum):
    REFRESHED = "REFRESHED"
    UNCHANGED = "UNCHANGED"
    STALE = "STALE"
    FAILED = "FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class InferenceStatus(str, Enum):
    SERVED = "SERVED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    STALE_DATA = "STALE_DATA"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    # A pre-match prediction requested with a cutoff at/after kickoff, or a
    # feature input dated at/after the cutoff (§15, adversarial 20).
    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"


class PredictionType(str, Enum):
    PRE_MATCH = "PRE_MATCH"
    LIVE_STATE = "LIVE_STATE"
    POST_MATCH_OBSERVATION = "POST_MATCH_OBSERVATION"


class MatchState(str, Enum):
    SCHEDULED = "SCHEDULED"
    PRE_MATCH = "PRE_MATCH"
    LIVE = "LIVE"
    HALFTIME = "HALFTIME"
    POST_MATCH = "POST_MATCH"
    FINAL = "FINAL"
    DATA_DELAYED = "DATA_DELAYED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class CompetitionOperationalState(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_AVAILABLE = "DATA_AVAILABLE"
    MODEL_VALIDATED = "MODEL_VALIDATED"
    SHADOW = "SHADOW"
    PRODUCTION_READY = "PRODUCTION_READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class DriftClass(str, Enum):
    STABLE = "STABLE"
    MONITOR = "MONITOR"
    DRIFT = "DRIFT"
    CRITICAL_DRIFT = "CRITICAL_DRIFT"
    NOT_ENOUGH_OBSERVATIONS = "NOT_ENOUGH_OBSERVATIONS"


class AlertState(str, Enum):
    TRIGGERED = "TRIGGERED"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"
    RESOLVED = "RESOLVED"


class NotificationChannel(str, Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    WEBHOOK = "WEBHOOK"


class NotificationState(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class ComponentHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNKNOWN = "UNKNOWN"


class OpsRole(str, Enum):
    ADMIN = "ADMIN"
    DATA_ENGINEER = "DATA_ENGINEER"
    ANALYST = "ANALYST"
    SCOUT = "SCOUT"
    RESEARCHER = "RESEARCHER"
    VIEWER = "VIEWER"
