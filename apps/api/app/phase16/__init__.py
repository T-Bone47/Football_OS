"""Phase 16: Production Football Intelligence Platform.

Architectural Doctrine:
- Reliable, continuously refreshed, observable, secure, scalable production intelligence platform.
- Zero fabrication: Missing data must be explicitly reported as UNVERIFIED, UNAVAILABLE, or NOT_TESTED.
- Epistemic segregation preserved: OBSERVED, MODELLED, COUNTERFACTUAL, SCENARIO, ASSUMPTION, ANALYSIS, HYPOTHESIS.
- Discovery != Validation != Production Adoption.
- Governed failover, idempotent ingestion, deterministic caching, rate-limited provider calls, and immutable audit logs.
"""

from enum import Enum


class Phase16ReleaseState(str, Enum):
    PHASE_16_IN_PROGRESS = "PHASE_16_IN_PROGRESS"
    PLATFORM_FOUNDATION_VALIDATED = "PLATFORM_FOUNDATION_VALIDATED"
    PRODUCTION_DATA_PIPELINE_VALIDATED = "PRODUCTION_DATA_PIPELINE_VALIDATED"
    MODEL_SERVING_VALIDATED = "MODEL_SERVING_VALIDATED"
    OBSERVABILITY_VALIDATED = "OBSERVABILITY_VALIDATED"
    SECURITY_VALIDATED = "SECURITY_VALIDATED"
    PRODUCTION_READINESS_VALIDATED = "PRODUCTION_READINESS_VALIDATED"
    PRODUCTION_FOOTBALL_INTELLIGENCE = "PRODUCTION_FOOTBALL_INTELLIGENCE"
    PHASE_16_RELEASE_BLOCKED = "PHASE_16_RELEASE_BLOCKED"


class DeploymentState(str, Enum):
    REGISTERED = "REGISTERED"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class FreshnessState(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"
    ACCEPTED_RISK = "ACCEPTED_RISK"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    SCOUT = "SCOUT"
    RESEARCHER = "RESEARCHER"
    VIEWER = "VIEWER"


class SystemHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ModelHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    MONITOR = "MONITOR"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ProviderCapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DEPRECATED = "DEPRECATED"
    # Phase 17: the default for a capability no live request has confirmed.
    UNVERIFIED = "UNVERIFIED"
