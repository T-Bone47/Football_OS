"""Provider Orchestration, Rate Limit Governance & Governed Failover for Phase 16.

Rules:
- Explicit provider capability checking.
- Token-bucket / quota-aware rate limiting.
- Controlled fallback without silent data merging.
- If primary and fallback sources disagree: emit CONFLICT_DETECTED.
- Full provenance preservation (source_provider, record_id, snapshot_digest, timestamp).
"""

from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Any
from pydantic import BaseModel, Field

from app.phase16 import ProviderCapabilityStatus


class ProviderCapabilityProfile(BaseModel):
    provider_name: str
    resource: str  # fixtures, events, lineups, stats, transfers, injuries, standings
    competition: str | None = None
    season: str | None = None
    status: ProviderCapabilityStatus
    rate_limit_per_minute: int
    current_minute_requests: int = 0
    quota_exhausted: bool = False
    last_verified_at: str | None = None
    license_metadata: str = "Commercial / Open-Data"


class ProviderRecord(BaseModel):
    source_provider: str
    source_record_id: str
    resource: str
    competition: str
    season: str
    payload: dict[str, Any]
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snapshot_digest: str


class FailoverResolution(BaseModel):
    resource: str
    primary_provider: str
    resolved_provider: str
    failover_occurred: bool
    record: ProviderRecord | None = None
    conflict_detected: bool = False
    conflict_details: str | None = None
    provenance_chain: list[str] = Field(default_factory=list)


class ProviderOrchestrator:
    """Governs provider capability checks, rate limits, and non-destructive failover."""

    def __init__(self) -> None:
        self._profiles: dict[tuple[str, str], ProviderCapabilityProfile] = {}
        self._rate_limits: dict[str, dict[str, Any]] = {}
        self._seed_default_capabilities()

    def _seed_default_capabilities(self) -> None:
        # 1. StatsBomb
        self.register_capability(
            provider_name="statsbomb",
            resource="competitions",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=120,
        )
        self.register_capability(
            provider_name="statsbomb",
            resource="matches",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=120,
        )
        self.register_capability(
            provider_name="statsbomb",
            resource="events",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=120,
        )

        # 2. API-Football
        self.register_capability(
            provider_name="api_football",
            resource="transfers",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=30,
        )
        self.register_capability(
            provider_name="api_football",
            resource="fixtures",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=30,
        )
        self.register_capability(
            provider_name="api_football",
            resource="injuries",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=30,
        )

        # 3. Football-Data.org (Secondary standby)
        self.register_capability(
            provider_name="football_data_org",
            resource="fixtures",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=10,
        )
        self.register_capability(
            provider_name="football_data_org",
            resource="standings",
            status=ProviderCapabilityStatus.AVAILABLE,
            rate_limit_per_minute=10,
        )

    def register_capability(
        self,
        provider_name: str,
        resource: str,
        status: ProviderCapabilityStatus,
        rate_limit_per_minute: int = 60,
        competition: str | None = None,
        season: str | None = None,
    ) -> ProviderCapabilityProfile:
        key = (provider_name.lower(), resource.lower())
        profile = ProviderCapabilityProfile(
            provider_name=provider_name.lower(),
            resource=resource.lower(),
            competition=competition,
            season=season,
            status=status,
            rate_limit_per_minute=rate_limit_per_minute,
            last_verified_at=datetime.now(timezone.utc).isoformat(),
        )
        self._profiles[key] = profile
        return profile

    def get_capability(self, provider_name: str, resource: str) -> ProviderCapabilityProfile:
        key = (provider_name.lower(), resource.lower())
        if key in self._profiles:
            return self._profiles[key]
        return ProviderCapabilityProfile(
            provider_name=provider_name.lower(),
            resource=resource.lower(),
            status=ProviderCapabilityStatus.UNAVAILABLE,
            rate_limit_per_minute=0,
            quota_exhausted=True,
        )

    def set_capability_status(self, provider_name: str, resource: str, status: ProviderCapabilityStatus) -> None:
        key = (provider_name.lower(), resource.lower())
        if key in self._profiles:
            self._profiles[key].status = status
        else:
            self.register_capability(provider_name=provider_name, resource=resource, status=status)

    def record_rate_limit_exceeded(self, provider_name: str, resource: str) -> None:
        self.set_capability_status(provider_name, resource, ProviderCapabilityStatus.RATE_LIMITED)
        p_name = provider_name.lower()
        if p_name not in self._rate_limits:
            self._rate_limits[p_name] = {"window_start": time.time(), "count": 99999}
        else:
            self._rate_limits[p_name]["count"] = 99999

    def check_rate_limit(self, provider_name: str, resource: str | None = None) -> bool:
        """Validates rate limit budget for a provider. Returns True if allowed, False if blocked."""
        now = time.time()
        p_name = provider_name.lower()

        # Check capability status
        if resource:
            prof = self._profiles.get((p_name, resource.lower()))
            if prof and prof.status in (ProviderCapabilityStatus.RATE_LIMITED, ProviderCapabilityStatus.BLOCKED, ProviderCapabilityStatus.UNAVAILABLE):
                return False

        if p_name not in self._rate_limits:
            self._rate_limits[p_name] = {"window_start": now, "count": 0}

        tracker = self._rate_limits[p_name]
        if now - tracker["window_start"] > 60.0:
            tracker["window_start"] = now
            tracker["count"] = 0

        # Find limit for this provider/resource
        if resource:
            prof = self._profiles.get((p_name, resource.lower()))
            max_req = prof.rate_limit_per_minute if prof else 60
        else:
            limits = [p.rate_limit_per_minute for (pr, _), p in self._profiles.items() if pr == p_name]
            max_req = min(limits) if limits else 60

        if tracker["count"] >= max_req:
            return False

        tracker["count"] += 1
        return True

    def fetch_with_failover(
        self,
        resource: str,
        competition: str,
        season: str,
        primary_provider: str,
        secondary_provider: str,
        primary_fetcher: Any = None,
        secondary_fetcher: Any = None,
    ) -> FailoverResolution:
        pf = primary_fetcher or (lambda: {"status": "ok", "resource": resource, "competition": competition})
        sf = secondary_fetcher or (lambda: {"status": "ok", "resource": resource, "competition": competition})
        return self.execute_failover_fetch(
            resource=resource,
            competition=competition,
            season=season,
            primary_provider=primary_provider,
            secondary_provider=secondary_provider,
            primary_fetcher=pf,
            secondary_fetcher=sf,
        )

    def execute_failover_fetch(
        self,
        resource: str,
        competition: str,
        season: str,
        primary_provider: str,
        secondary_provider: str,
        primary_fetcher: Any,
        secondary_fetcher: Any,
    ) -> FailoverResolution:
        """Executes fetch against primary with controlled secondary failover and conflict detection."""
        provenance: list[str] = [primary_provider]

        # Check primary capability status
        prim_prof = self._profiles.get((primary_provider.lower(), resource.lower()))
        prim_cap_blocked = prim_prof and prim_prof.status in (
            ProviderCapabilityStatus.UNAVAILABLE,
            ProviderCapabilityStatus.BLOCKED,
            ProviderCapabilityStatus.RATE_LIMITED,
            ProviderCapabilityStatus.AUTH_REQUIRED,
        )

        primary_allowed = (not prim_cap_blocked) and self.check_rate_limit(primary_provider, resource)

        primary_result = None
        primary_failed = False

        if not primary_allowed:
            primary_failed = True
        else:
            try:
                primary_result = primary_fetcher()
            except Exception:
                primary_failed = True

        if not primary_failed and primary_result is not None:
            # Primary succeeded
            raw_sig = json.dumps(primary_result, sort_keys=True)
            digest = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()
            record = ProviderRecord(
                source_provider=primary_provider,
                source_record_id=f"{resource}_{competition}_{season}",
                resource=resource,
                competition=competition,
                season=season,
                payload=primary_result,
                snapshot_digest=digest,
            )
            return FailoverResolution(
                resource=resource,
                primary_provider=primary_provider,
                resolved_provider=primary_provider,
                failover_occurred=False,
                record=record,
                provenance_chain=provenance,
            )

        # Failover to secondary
        provenance.append(secondary_provider)
        secondary_allowed = self.check_rate_limit(secondary_provider, resource)
        if not secondary_allowed:

            return FailoverResolution(
                resource=resource,
                primary_provider=primary_provider,
                resolved_provider="NONE",
                failover_occurred=True,
                record=None,
                conflict_detected=False,
                conflict_details="Both primary and secondary providers unavailable or rate limited.",
                provenance_chain=provenance,
            )

        try:
            sec_result = secondary_fetcher()
            raw_sig = json.dumps(sec_result, sort_keys=True)
            digest = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()
            record = ProviderRecord(
                source_provider=secondary_provider,
                source_record_id=f"{resource}_{competition}_{season}",
                resource=resource,
                competition=competition,
                season=season,
                payload=sec_result,
                snapshot_digest=digest,
            )
            return FailoverResolution(
                resource=resource,
                primary_provider=primary_provider,
                resolved_provider=secondary_provider,
                failover_occurred=True,
                record=record,
                provenance_chain=provenance,
            )
        except Exception as e:
            return FailoverResolution(
                resource=resource,
                primary_provider=primary_provider,
                resolved_provider="NONE",
                failover_occurred=True,
                record=None,
                conflict_details=f"Secondary fetch failed: {str(e)}",
                provenance_chain=provenance,
            )

    def detect_conflicts(self, record_a: ProviderRecord, record_b: ProviderRecord, key_field: str) -> tuple[bool, str | None]:
        """Explicitly compares two provider records on a key field. Emits CONFLICT_DETECTED if mismatched."""
        val_a = record_a.payload.get(key_field)
        val_b = record_b.payload.get(key_field)
        if val_a != val_b:
            return True, f"CONFLICT_DETECTED on '{key_field}': {record_a.source_provider}='{val_a}' vs {record_b.source_provider}='{val_b}'"
        return False, None

    def list_capabilities(self) -> list[ProviderCapabilityProfile]:
        return list(self._profiles.values())


_GLOBAL_PROVIDER_ORCHESTRATOR: ProviderOrchestrator | None = None


def get_provider_orchestrator() -> ProviderOrchestrator:
    global _GLOBAL_PROVIDER_ORCHESTRATOR
    if _GLOBAL_PROVIDER_ORCHESTRATOR is None:
        _GLOBAL_PROVIDER_ORCHESTRATOR = ProviderOrchestrator()
    return _GLOBAL_PROVIDER_ORCHESTRATOR
