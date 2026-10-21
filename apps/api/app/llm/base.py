"""Base classes and protocols for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal, TypedDict
import json


@dataclass
class LLMMessage:
    """A message in a conversation."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class LLMStreamChunk:
    """A single chunk from a streaming response."""
    delta: str
    finish_reason: str | None = None
    usage: dict | None = None
    model: str | None = None


@dataclass
class LLMResponse:
    """Complete non-streaming response from an LLM."""
    content: str
    model: str
    provider: str
    usage: dict | None = None
    finish_reason: str | None = None
    latency_ms: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: dict | None = None
    tool_calls: list[dict] | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 45,
        max_retries: int = 2,
        max_output_tokens: int = 1200,
        enable_streaming: bool = True,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.enable_streaming = enable_streaming
        self._client = None

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming."""

    @abstractmethod
    async def _make_request(
        self,
        messages: list[LLMMessage],
        stream: bool,
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse | AsyncGenerator[LLMStreamChunk, None]:
        """Make a request to the provider. Returns response or async generator for streaming.

        ``tools`` carries the OpenAI-compatible function schema. A provider that does not
        implement tool calling must ignore it and answer without tools - the caller then
        sees a tool-free answer instead of a fabricated tool result.
        """

    @abstractmethod
    async def verify_health(self) -> dict:
        """Verify provider connectivity and return health status."""

    @property
    def supports_tool_calling(self) -> bool:
        """Whether this provider can execute tool calls. Verified per provider, not assumed."""
        return False

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int | None = None,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse | AsyncGenerator[LLMStreamChunk, None]:
        """Complete a chat request, with optional streaming."""
        if stream and not self.supports_streaming:
            # Fall back to non-streaming if streaming not supported
            return await self._make_request(messages, False, temperature, top_p, max_tokens)

        return await self._make_request(
            messages, stream, temperature, top_p, max_tokens, tools, tool_choice
        )

    async def verify_config(self) -> dict:
        """Verify that the provider is properly configured."""
        if not self.api_key:
            return {"configured": False, "error": "No API key provided"}
        return {"configured": True}

    async def close(self) -> None:
        """Close any open connections."""
        pass


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(self, message: str, provider: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class LLMAuthenticationError(LLMProviderError):
    """Authentication failed (401)."""

    def __init__(self, message: str, provider: str) -> None:
        super().__init__(message, provider, 401)


class LLMRateLimitError(LLMProviderError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str, provider: str, retry_after: int | None = None) -> None:
        super().__init__(message, provider, 429)
        self.retry_after = retry_after


class LLMProviderUnavailableError(LLMProviderError):
    """Provider unavailable (5xx or network error)."""

    def __init__(self, message: str, provider: str, status_code: int | None = None) -> None:
        super().__init__(message, provider, status_code)


class LLMBadRequestError(LLMProviderError):
    """Bad request (400)."""

    def __init__(self, message: str, provider: str) -> None:
        super().__init__(message, provider, 400)