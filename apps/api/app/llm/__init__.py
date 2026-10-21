"""LLM Provider abstraction layer for Football Intelligence OS.

Provides a unified interface for multiple LLM providers with:
- OpenAI-compatible API providers (Groq, Hugging Face, OpenAI)
- Anthropic API
- Google Gemini
- Streaming support
- Usage tracking and latency measurement
- Health verification
"""
from __future__ import annotations

from app.llm.base import LLMProvider, LLMResponse, LLMStreamChunk, LLMMessage
from app.llm.openai_compatible import GroqProvider, HuggingFaceProvider, OpenAIProvider, OpenAICompatibleProvider
from app.llm.anthropic import AnthropicProvider
from app.llm.gemini import GeminiProvider
from app.llm.registry import LLMRegistry, get_llm_registry

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "LLMStreamChunk",
    "LLMMessage",
    "GroqProvider",
    "HuggingFaceProvider",
    "OpenAIProvider",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "LLMRegistry",
    "get_llm_registry",
]