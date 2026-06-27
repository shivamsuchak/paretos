"""Claude LLM client wrapper for agent system."""

from __future__ import annotations

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)


def get_client() -> anthropic.Anthropic:
    """Get an authenticated Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment or .env")
    return anthropic.Anthropic(api_key=api_key, timeout=120.0)


def call_claude(
    prompt: str,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.1,
) -> str:
    """Call Claude and return the text response.

    Args:
        prompt: User message content.
        system: System prompt (role definition).
        model: Model name (defaults to PRIMARY_LLM_MODEL from env).
        max_tokens: Max response tokens.
        temperature: Sampling temperature.

    Returns:
        Response text string.
    """
    client = get_client()
    model = model or os.getenv("PRIMARY_LLM_MODEL", "claude-sonnet-4-6")

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text
