"""LLM Provider Registry and Management.

Manages provider lifecycle, health checks, fallback logic, and status reporting.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.llm.base import LLMProvider
from app.llm import GroqProvider, HuggingFaceProvider, OpenAIProvider
from app.llm.anthropic import AnthropicProvider
from app.llm.gemini import GeminiProvider

logger = logging.getLogger(__name__)


@dataclass
class ProviderStatus:
    """Current status of an LLM provider."""
    provider: str
    model: str
    configured: bool = False
    status: str = "NOT_CONFIGURED"  # NOT_CONFIGURED | CONFIGURED_UNVERIFIED | AVAILABLE | DEGRADED | RATE_LIMITED | AUTHENTICATION_FAILED | UNAVAILABLE | DISABLED
    last_check: datetime | None = None
    last_error: str | None = None
    latency_ms: int | None = None
    streaming_verified: bool = False
    fallback_used: bool = False
    # Measured on a real completion (not on the health probe), so a displayed
    # "last successful inference" can never be inferred from configuration.
    last_success_at: datetime | None = None
    last_success_latency_ms: int | None = None
    last_success_finish_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "configured": self.configured,
            "status": self.status,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_error": self.last_error,
            "latency_ms": self.latency_ms,
            "streaming_verified": self.streaming_verified,
            "fallback_used": self.fallback_used,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_success_latency_ms": self.last_success_latency_ms,
            "last_success_finish_reason": self.last_success_finish_reason,
        }


class LLMRegistry:
    """Registry managing LLM provider instances and health."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._statuses: dict[str, ProviderStatus] = {}
        self._primary: Optional[LLMProvider] = None
        self._fallback: Optional[LLMProvider] = None
        self._primary_key: Optional[str] = None
        self._fallback_key: Optional[str] = None
        self._settings = get_settings()
        self._initialized = False

    def _create_provider(self, provider_name: str, model: str | None) -> Optional[LLMProvider]:
        """Create a provider instance from configuration."""
        if provider_name == "groq":
            api_key = self._settings.groq_api_key
            if not api_key:
                return None
            return GroqProvider(
                api_key=api_key,
                model=model or "openai/gpt-oss-120b",
                base_url=self._settings.groq_base_url,
                timeout_seconds=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
                max_output_tokens=self._settings.llm_max_output_tokens,
                enable_streaming=self._settings.llm_enable_streaming,
            )
        elif provider_name == "huggingface":
            api_key = self._settings.hf_token
            if not api_key:
                return None
            return HuggingFaceProvider(
                api_key=api_key,
                model=model or "openai/gpt-oss-120b",
                base_url=self._settings.hf_base_url,
                timeout_seconds=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
                max_output_tokens=self._settings.llm_max_output_tokens,
                enable_streaming=self._settings.llm_enable_streaming,
            )
        elif provider_name == "openai":
            api_key = self._settings.openai_api_key
            if not api_key:
                return None
            return OpenAIProvider(
                api_key=api_key,
                model=model or "gpt-4o-mini",
                base_url=self._settings.openai_base_url,
                timeout_seconds=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
                max_output_tokens=self._settings.llm_max_output_tokens,
                enable_streaming=self._settings.llm_enable_streaming,
            )
        elif provider_name == "anthropic":
            api_key = self._settings.anthropic_api_key
            if not api_key:
                return None
            return AnthropicProvider(
                api_key=api_key,
                model=model or "claude-3-5-sonnet-20241022",
                base_url=self._settings.anthropic_base_url,
                timeout_seconds=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
                max_output_tokens=self._settings.llm_max_output_tokens,
                enable_streaming=self._settings.llm_enable_streaming,
            )
        elif provider_name == "gemini":
            api_key = self._settings.gemini_api_key
            if not api_key:
                return None
            return GeminiProvider(
                api_key=api_key,
                model=model or "gemini-1.5-flash",
                base_url=self._settings.gemini_base_url,
                timeout_seconds=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
                max_output_tokens=self._settings.llm_max_output_tokens,
                enable_streaming=self._settings.llm_enable_streaming,
            )
        return None

    def initialize(self) -> None:
        """Initialize providers from configuration."""
        if self._initialized:
            return

        primary_provider = self._settings.llm_provider
        primary_model = self._settings.llm_model

        fallback_provider = self._settings.llm_fallback_provider
        fallback_model = self._settings.llm_fallback_model

        # Create primary provider
        if primary_provider != "none" and primary_model:
            provider = self._create_provider(primary_provider, primary_model)
            if provider:
                self._providers[primary_provider] = provider
                self._primary = provider
                self._primary_key = primary_provider
                self._statuses[primary_provider] = ProviderStatus(
                    provider=provider.provider_name,
                    model=primary_model,
                    configured=True,
                    status="CONFIGURED_UNVERIFIED",
                )
                logger.info(f"Initialized primary LLM provider: {primary_provider} ({primary_model})")

        # Create fallback provider
        if (
            fallback_provider
            and fallback_provider != "none"
            and fallback_model
            and fallback_provider.strip().lower() != primary_provider.strip().lower()
            and self._settings.llm_allow_paid_fallback
        ):
            provider = self._create_provider(fallback_provider, fallback_model)
            if provider:
                self._providers[fallback_provider] = provider
                self._fallback = provider
                self._fallback_key = fallback_provider
                self._statuses[fallback_provider] = ProviderStatus(
                    provider=provider.provider_name,
                    model=fallback_model,
                    configured=True,
                    status="CONFIGURED_UNVERIFIED",
                )
                logger.info(f"Initialized fallback LLM provider: {fallback_provider} ({fallback_model})")

        self._initialized = True

    def get_primary(self) -> Optional[LLMProvider]:
        return self._primary

    def get_fallback(self) -> Optional[LLMProvider]:
        return self._fallback

    def get_provider(self, name: str) -> Optional[LLMProvider]:
        return self._providers.get(name)

    def get_status(self, provider_name: str) -> ProviderStatus | None:
        return self._statuses.get(provider_name)

    def get_all_statuses(self) -> list[dict]:
        return [s.to_dict() for s in self._statuses.values()]

    async def verify_all(self) -> list[dict]:
        """Verify health of all configured providers."""
        results = []
        for name, provider in self._providers.items():
            try:
                status = await provider.verify_health()
                self._statuses[name].status = status.get("status", "ERROR")
                self._statuses[name].last_check = datetime.now(timezone.utc)
                self._statuses[name].last_error = status.get("error")
                self._statuses[name].latency_ms = status.get("latency_ms")
                self._statuses[name].streaming_verified = status.get("streaming_verified", False)
                self._statuses[name].model = status.get("model", self._statuses[name].model)
                results.append(status)
            except Exception as e:
                self._statuses[name].status = "ERROR"
                self._statuses[name].last_check = datetime.now(timezone.utc)
                self._statuses[name].last_error = str(e)
                results.append({
                    "status": "ERROR",
                    "provider": name,
                    "error": str(e),
                })
                logger.exception(f"Health check failed for {name}: {e}")
        return results

    def _to_llm_messages(self, messages: list) -> list:
        """Convert dict messages to LLMMessage objects."""
        from app.llm.base import LLMMessage
        result = []
        for msg in messages:
            if isinstance(msg, dict):
                result.append(LLMMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    tool_calls=msg.get("tool_calls"),
                    tool_call_id=msg.get("tool_call_id"),
                    name=msg.get("name"),
                ))
            elif hasattr(msg, 'role'):  # Already an LLMMessage
                result.append(msg)
            else:
                raise ValueError(f"Unsupported message type: {type(msg)}")
        return result

    async def complete_with_fallback(
        self,
        messages: list,
        stream: bool = False,
        **kwargs,
    ):
        """Complete with primary, fallback to secondary if enabled and primary fails."""
        if not self._primary:
            raise RuntimeError("No primary LLM provider configured")

        llm_messages = self._to_llm_messages(messages)

        try:
            result = await self._primary.complete(llm_messages, stream=stream, **kwargs)
            self._record_success(self._primary_key, result)
            return result
        except Exception as e:
            logger.warning(f"Primary provider {self._primary.provider_name} failed: {e}")
            if self._primary_key and self._primary_key in self._statuses:
                self._statuses[self._primary_key].last_error = f"{type(e).__name__}: {e}"
                self._statuses[self._primary_key].last_check = datetime.now(timezone.utc)

            # Try fallback if enabled
            if (
                self._settings.llm_allow_paid_fallback
                and self._fallback
                and self._fallback != self._primary
            ):
                logger.info(f"Falling back to {self._fallback.provider_name}")
                if self._fallback_key:
                    self._statuses[self._fallback_key].fallback_used = True
                result = await self._fallback.complete(llm_messages, stream=stream, **kwargs)
                self._record_success(self._fallback_key, result)
                return result

            # No fallback available or disabled
            raise

    def _record_success(self, provider_key: str | None, result) -> None:
        """Record a measured completion. Streaming results are generators and
        are deliberately not recorded here (no completion has been observed)."""
        if not provider_key or provider_key not in self._statuses:
            return
        status = self._statuses[provider_key]
        latency = getattr(result, "latency_ms", None)
        finish = getattr(result, "finish_reason", None)
        if latency is None and finish is None:
            return
        status.status = "AVAILABLE"
        status.last_success_at = datetime.now(timezone.utc)
        status.last_success_latency_ms = latency
        status.last_success_finish_reason = finish
        status.last_error = None

    def get_active_status(self) -> dict:
        """Get status of the active (primary) provider."""
        if not self._primary:
            return {
                "provider": "none",
                "model": "none",
                "status": "NOT_CONFIGURED",
                "configured": False,
            }

        status = self._statuses.get(self._primary_key) if self._primary_key else None
        if status:
            return status.to_dict()

        return {
            "provider": self._primary.provider_name,
            "model": self._primary.model,
            "status": "CONFIGURED_UNVERIFIED",
            "configured": True,
        }

    async def close_all(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing provider: {e}")


# Global registry instance
_llm_registry: Optional[LLMRegistry] = None


def get_llm_registry() -> LLMRegistry:
    """Get or create the global LLM registry."""
    global _llm_registry
    if _llm_registry is None:
        _llm_registry = LLMRegistry()
    return _llm_registry


def initialize_llm_registry() -> LLMRegistry:
    """Initialize the global LLM registry."""
    global _llm_registry
    _llm_registry = LLMRegistry()
    _llm_registry.initialize()
    return _llm_registry