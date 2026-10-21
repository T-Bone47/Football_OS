"""OpenAI-compatible LLM provider implementation.

Works with: Groq, Hugging Face Inference Providers, OpenAI, and any OpenAI-compatible API.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator
import httpx

from app.llm.base import (
    LLMProvider,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMProviderUnavailableError,
    LLMBadRequestError,
)


class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs (Groq, Hugging Face, OpenAI, etc.)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str = "OpenAI-Compatible",
        timeout_seconds: int = 45,
        max_retries: int = 2,
        max_output_tokens: int = 1200,
        enable_streaming: bool = True,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_output_tokens=max_output_tokens,
            enable_streaming=enable_streaming,
        )
        self._provider_name = provider_name
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
        )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_tool_calling(self) -> bool:
        """OpenAI-compatible endpoints accept the ``tools`` function schema.

        Verified live against Groq with ``openai/gpt-oss-120b`` (the model returned a
        well-formed ``tool_calls`` entry). Other OpenAI-compatible servers may differ;
        the provider error surfaces as a provider error, never as a fabricated result.
        """
        return True

    def _format_messages(self, messages: list) -> list[dict]:
        """Convert LLMMessage objects to provider format."""
        return [
            {
                "role": msg.role,
                "content": msg.content,
                **(
                    {"tool_calls": msg.tool_calls}
                    if msg.tool_calls
                    else {}
                ),
                **(
                    {"tool_call_id": msg.tool_call_id}
                    if msg.tool_call_id
                    else {}
                ),
                **(
                    {"name": msg.name}
                    if msg.name
                    else {}
                ),
            }
            for msg in messages
        ]

    async def _make_request(
        self,
        messages: list,
        stream: bool,
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ):
        import time
        start_time = time.perf_counter()

        payload = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            "max_tokens": max_tokens or self.max_output_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=payload)
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code == 401:
                    raise LLMAuthenticationError(
                        "Invalid API key", self.provider_name
                    )
                elif response.status_code == 429:
                    retry_after = None
                    if "retry-after" in response.headers:
                        try:
                            retry_after = int(response.headers["retry-after"])
                        except ValueError:
                            pass
                    # The provider body says which limit was hit (per minute or per
                    # day); the message is kept so the operator sees the real budget.
                    detail = response.text[:300]
                    raise LLMRateLimitError(
                        f"Rate limit exceeded: {detail}", self.provider_name, retry_after
                    )
                elif response.status_code >= 500:
                    raise LLMProviderUnavailableError(
                        f"Provider error: {response.text}", self.provider_name, response.status_code
                    )
                elif response.status_code == 404:
                    # A retired/unknown model id and a wrong base URL both land
                    # here; the provider body is preserved so the two can be told
                    # apart instead of being reported as a generic bad request.
                    raise LLMBadRequestError(
                        f"Model or endpoint not found (404): {response.text}",
                        self.provider_name,
                    )
                elif response.status_code >= 400:
                    raise LLMBadRequestError(
                        f"Bad request ({response.status_code}): {response.text}",
                        self.provider_name,
                    )

                if stream:
                    return self._stream_response(response, latency_ms)
                else:
                    data = response.json()
                    return self._parse_response(data, latency_ms)

            except (LLMAuthenticationError, LLMBadRequestError):
                raise
            except LLMRateLimitError as e:
                # A daily token budget cannot be retried inside the turn: the
                # provider says when it resets. Fail fast and report it.
                if "per day" in str(e).lower() or "tpd" in str(e).lower():
                    raise
                # Retry a rate-limited request even when the provider sends no
                # Retry-After header. The Free tier enforces 10 requests/minute
                # and 8 000 tokens/minute, so the wait has to be long enough for
                # the window to roll over.
                if attempt < self.max_retries:
                    import asyncio
                    wait = e.retry_after if e.retry_after else 20 * (attempt + 1)
                    await asyncio.sleep(min(wait, 60))
                    continue
                raise
            except LLMProviderUnavailableError:
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise LLMProviderUnavailableError(
                    "Request timed out", self.provider_name
                )
            except httpx.TransportError as e:
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise LLMProviderUnavailableError(
                    f"Network error: {e}", self.provider_name
                )

        raise LLMProviderUnavailableError(
            f"Max retries exceeded", self.provider_name
        )

    def _parse_response(self, data: dict, latency_ms: int) -> LLMResponse:
        """Parse non-streaming response."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return LLMResponse(
            content=message.get("content", ""),
            model=data.get("model", self.model),
            provider=self.provider_name,
            usage=usage,
            finish_reason=choice.get("finish_reason"),
            latency_ms=latency_ms,
            raw_response=data,
            tool_calls=message.get("tool_calls") or None,
        )

    async def _stream_response(
        self, response: httpx.Response, latency_ms: int
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """Parse streaming response (Server-Sent Events)."""
        buffer = ""
        first_token_latency = None
        import time
        start_time = time.perf_counter()

        async for line in response.aiter_lines():
            if not line or line.startswith(":"):
                continue

            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break

                try:
                    chunk_data = json.loads(data_str)
                    choice = chunk_data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = choice.get("finish_reason")

                    if content and first_token_latency is None:
                        first_token_latency = int((time.perf_counter() - start_time) * 1000)

                    if content:
                        yield LLMStreamChunk(
                            delta=content,
                            finish_reason=finish_reason,
                            model=chunk_data.get("model", self.model),
                        )

                    if finish_reason:
                        break

                except json.JSONDecodeError:
                    continue

    async def verify_health(self) -> dict:
        """Verify provider connectivity with a minimal request."""
        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "temperature": 0,
                },
                timeout=10.0,
            )

            if response.status_code == 401:
                return {
                    "status": "AUTHENTICATION_FAILED",
                    "provider": self.provider_name,
                    "model": self.model,
                    "error": "Invalid API key",
                }
            elif response.status_code == 429:
                return {
                    "status": "RATE_LIMITED",
                    "provider": self.provider_name,
                    "model": self.model,
                }
            elif response.status_code >= 500:
                return {
                    "status": "UNAVAILABLE",
                    "provider": self.provider_name,
                    "model": self.model,
                    "error": f"HTTP {response.status_code}",
                }
            elif response.status_code >= 400:
                return {
                    "status": "DEGRADED",
                    "provider": self.provider_name,
                    "model": self.model,
                    "error": f"HTTP {response.status_code}: {response.text}",
                }
            else:
                data = response.json()
                return {
                    "status": "AVAILABLE",
                    "provider": self.provider_name,
                    "model": data.get("model", self.model),
                    "streaming_verified": True,
                }

        except httpx.TimeoutException:
            return {
                "status": "UNAVAILABLE",
                "provider": self.provider_name,
                "model": self.model,
                "error": "Timeout",
            }
        except httpx.TransportError as e:
            return {
                "status": "UNAVAILABLE",
                "provider": self.provider_name,
                "model": self.model,
                "error": f"Network error: {e}",
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "provider": self.provider_name,
                "model": self.model,
                "error": str(e),
            }

    async def close(self) -> None:
        await self._client.aclose()


class GroqProvider(OpenAICompatibleProvider):
    """Groq provider - ultra-fast inference for open models."""

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
        **kwargs,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name="Groq",
            **kwargs,
        )


class HuggingFaceProvider(OpenAICompatibleProvider):
    """Hugging Face Inference Providers - routes to various inference providers."""

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://router.huggingface.co/v1",
        **kwargs,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name="Hugging Face",
            **kwargs,
        )


class OpenAIProvider(OpenAICompatibleProvider):
    """Official OpenAI API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        **kwargs,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name="OpenAI",
            **kwargs,
        )