"""UiPath LLM Gateway client for hosted model access."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("rpa_architect.platform.llm_gateway")

_DEFAULT_TIMEOUT = 120.0


class UiPathLLMClient:
    """Client for the UiPath LLM Gateway.

    Falls back to direct API calls (via the same HTTP interface) if the gateway
    is unavailable.

    Args:
        gateway_url: Base URL for the LLM Gateway endpoint.
        api_key: Authentication key for the gateway.
        default_model: Model identifier to use when none is specified.
    """

    def __init__(
        self,
        gateway_url: str = "https://llm-gateway.uipath.com",
        api_key: str | None = None,
        default_model: str = "gpt-4o",
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a text completion via the LLM Gateway.

        Args:
            prompt: User prompt.
            system: Optional system prompt.
            model: Model identifier (falls back to ``default_model``).
            **kwargs: Additional parameters forwarded to the gateway.

        Returns:
            The model's text response.
        """
        model = model or self._default_model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            **kwargs,
        }

        try:
            return await self._call_gateway(payload)
        except (httpx.HTTPError, httpx.ConnectError) as exc:
            logger.warning("Gateway unavailable (%s), falling back to direct API", exc)
            return await self._call_direct(payload)

    async def complete_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Generate a completion constrained to a JSON schema.

        Args:
            prompt: User prompt describing the task.
            schema: JSON Schema the response must conform to.
            model: Model identifier.

        Returns:
            Parsed JSON dictionary.
        """
        system = (
            "You are a structured-data assistant. Respond ONLY with valid JSON "
            f"matching this JSON Schema:\n{json.dumps(schema)}"
        )
        raw = await self.complete(prompt, system=system, model=model)
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())  # type: ignore[no-any-return]

    async def _call_gateway(self, payload: dict[str, Any]) -> str:
        """Send a request to the UiPath LLM Gateway."""
        url = f"{self._gateway_url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]  # type: ignore[no-any-return]

    async def _call_direct(self, payload: dict[str, Any]) -> str:
        """Fallback: call an OpenAI-compatible endpoint directly."""
        url = "https://api.openai.com/v1/chat/completions"
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]  # type: ignore[no-any-return]
