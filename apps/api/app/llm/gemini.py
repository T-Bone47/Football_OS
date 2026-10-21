"""Google Gemini LLM provider implementation."""
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


class GeminiProvider(LLMProvider):
    """Provider for Google Gemini API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model: str = "gemini-1.5-flash",
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
            params={"key": self.api_key},
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
        )

    @property
    def provider_name(self) -> str:
        return "Google Gemini"

    @property
    def supports_streaming(self) -> bool:
        return True

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

        # Extract system message if present
        system_text = None
        formatted_messages = []
        for msg in messages:
            if msg.role == "system":
                system_text = msg.content
            else:
                role = "model" if msg.role == "assistant" else "user"
                formatted_messages.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })

        # If system message exists, prepend to first user message
        if system_text and formatted_messages:
            first_user_idx = next(
                (i for i, m in enumerate(formatted_messages) if m["role"] == "user"),
                None
            )
            if first_user_idx is not None:
                formatted_messages[first_user_idx]["parts"][0]["text"] = (
                    f"{system_text}\n\n{formatted_messages[first_user_idx]['parts'][0]['text']}"
                )
            elif not any(m["role"] == "user" for m in formatted_messages):
                # No user message, add system as user message
                formatted_messages.insert(0, {
                    "role": "user",
                    "parts": [{"text": system_text}],
                })

        payload = {
            "contents": formatted_messages,
            "generationConfig": {
                "temperature": temperature,
                "topP": top_p,
                "maxOutputTokens": max_tokens or self.max_output_tokens,
            },
        }

        endpoint = f"/models/{self.model}:{'streamGenerateContent' if stream else 'generateContent'}"

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(
                    endpoint,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code == 401:
                    raise LLMAuthenticationError("Invalid API key", self.provider_name)
                elif response.status_code == 429:
                    raise LLMRateLimitError("Rate limit exceeded", self.provider_name)
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
            except LLMRateLimitError:
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(10)
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
        candidates = data.get("candidates", [])
        if candidates:
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    content += part["text"]

        usage = data.get("usageMetadata", {})

        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.provider_name,
            usage={
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
            finish_reason=candidates[0].get("finishReason") if candidates else None,
            latency_ms=latency_ms,
            raw_response=data,
        )

    async def _stream_response(
        self, response: httpx.Response, latency_ms: int
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """Parse Gemini streaming response."""
        buffer = ""
        async for line in response.aiter_lines():
            if not line or line.startswith(":"):
                continue

            try:
                chunk_data = json.loads(line)
                candidates = chunk_data.get("candidates", [])
                if candidates:
                    for part in candidates[0].get("content", {}).get("parts", []):
                        if "text" in part:
                            yield LLMStreamChunk(
                                delta=part["text"],
                                model=self.model,
                            )
            except json.JSONDecodeError:
                continue

    async def verify_health(self) -> dict:
        """Verify Gemini connectivity."""
        try:
            response = await self._client.post(
                f"/models/{self.model}:generateContent",
                json={
                    "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 1, "temperature": 0},
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