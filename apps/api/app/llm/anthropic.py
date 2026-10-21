"""Anthropic (Claude) LLM provider implementation."""
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


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        model: str = "claude-3-5-sonnet-20241022",
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
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
        )

    @property
    def provider_name(self) -> str:
        return "Anthropic"

    @property
    def supports_streaming(self) -> bool:
        return True

    def _format_messages(self, messages: list[LLMMessage]) -> tuple[str | None, list[dict]]:
        """Convert messages to Anthropic format. Returns (system_prompt, messages)."""
        system = None
        formatted = []

        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                formatted.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        return system, formatted

    async def _make_request(
        self,
        messages: list[LLMMessage],
        stream: bool,
        temperature: float = 0.3,
        top_p: float = 0.9,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ):
        import time
        start_time = time.perf_counter()

        system, formatted_messages = self._format_messages(messages)

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens or self.max_output_tokens,
            "stream": stream,
        }

        if system:
            payload["system"] = system

        headers = {}
        if stream:
            headers["Accept"] = "text/event-stream"

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(
                    "/messages",
                    json=payload,
                    headers=headers,
                )
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code == 401:
                    raise LLMAuthenticationError("Invalid API key", self.provider_name)
                elif response.status_code == 429:
                    retry_after = None
                    if "retry-after" in response.headers:
                        try:
                            retry_after = int(response.headers["retry-after"])
                        except ValueError:
                            pass
                    raise LLMRateLimitError("Rate limit exceeded", self.provider_name, retry_after)
                elif response.status_code >= 500:
                    raise LLMProviderUnavailableError(
                        f"Provider error: {response.text}", self.provider_name, response.status_code
                    )
                elif response.status_code >= 400:
                    raise LLMBadRequestError(
                        f"Bad request: {response.text}", self.provider_name
                    )

                if stream:
                    return self._stream_response(response, latency_ms)
                else:
                    data = response.json()
                    return self._parse_response(data, latency_ms)

            except (LLMAuthenticationError, LLMBadRequestError):
                raise
            except LLMRateLimitError as e:
                if attempt < self.max_retries and e.retry_after:
                    import asyncio
                    await asyncio.sleep(min(e.retry_after, 10))
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
                raise LLMProviderUnavailableError("Request timed out", self.provider_name)
            except httpx.TransportError as e:
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                raise LLMProviderUnavailableError(f"Network error: {e}", self.provider_name)

        raise LLMProviderUnavailableError("Max retries exceeded", self.provider_name)

    def _parse_response(self, data: dict, latency_ms: int) -> LLMResponse:
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            provider=self.provider_name,
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
            finish_reason=data.get("stop_reason"),
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def _stream_response(
        self, response: httpx.Response, latency_ms: int
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """Parse Anthropic streaming response (Server-Sent Events)."""
        async for line in response.aiter_lines():
            if not line or line.startswith(":"):
                continue

            if line.startswith("data: "):
                data_str = line[6:].strip()
                if not data_str:
                    continue

                try:
                    chunk_data = json.loads(data_str)
                    chunk_type = chunk_data.get("type")

                    if chunk_type == "content_block_delta":
                        delta = chunk_data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield LLMStreamChunk(
                                delta=delta.get("text", ""),
                                model=self.model,
                            )
                    elif chunk_type == "message_delta":
                        # Handle stop reason
                        delta = chunk_data.get("delta", {})
                        if delta.get("stop_reason"):
                            yield LLMStreamChunk(
                                delta="",
                                finish_reason=delta.get("stop_reason"),
                                model=self.model,
                            )
                    elif chunk_type == "message_stop":
                        break

                except json.JSONDecodeError:
                    continue

    async def verify_health(self) -> dict:
        """Verify Anthropic connectivity."""
        try:
            response = await self._client.post(
                "/messages",
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
                return {
                    "status": "AVAILABLE",
                    "provider": self.provider_name,
                    "model": self.model,
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