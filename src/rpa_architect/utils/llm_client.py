"""Unified LLM client with provider abstraction and retry logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from rpa_architect.config import AppConfig, LLMProvider

logger = logging.getLogger("rpa_architect.utils.llm_client")

T = TypeVar("T", bound=BaseModel)

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0


class LLMClient:
    """Provider-agnostic LLM client with retry and structured output support.

    Attributes:
        provider: The active :class:`LLMProvider` enum value.
        model: Model identifier string.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._base_url = base_url
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._anthropic_client: Any = None
        self._openai_client: Any = None

    # ------------------------------------------------------------------
    # Lazy client initialisation
    # ------------------------------------------------------------------

    def _get_anthropic(self) -> Any:
        if self._anthropic_client is None:
            import anthropic

            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=self._api_key,
                **({"base_url": self._base_url} if self._base_url else {}),
            )
        return self._anthropic_client

    def _get_openai(self) -> Any:
        if self._openai_client is None:
            import openai

            self._openai_client = openai.AsyncOpenAI(
                api_key=self._api_key,
                **({"base_url": self._base_url} if self._base_url else {}),
            )
        return self._openai_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a plain-text completion.

        Args:
            prompt: User prompt.
            system: Optional system prompt.
            **kwargs: Extra provider-specific parameters.

        Returns:
            The model's text response.
        """
        return await self._with_retries(self._do_complete, prompt, system, **kwargs)

    async def complete_structured(
        self,
        prompt: str,
        response_model: type[T],
        **kwargs: Any,
    ) -> T:
        """Generate a completion and parse it into a Pydantic model.

        The model is instructed to reply with JSON matching the schema of
        *response_model*.  The raw response is parsed via
        ``response_model.model_validate_json``.

        Args:
            prompt: User prompt describing the task.
            response_model: Pydantic model class for the expected output.
            **kwargs: Extra provider-specific parameters.

        Returns:
            An instance of *response_model*.
        """
        schema_json = response_model.model_json_schema()
        system = (
            "You are a structured-data assistant. Respond ONLY with valid JSON "
            f"matching this JSON Schema:\n{schema_json}"
        )
        raw = await self.complete(prompt, system=system, **kwargs)
        # Strip markdown fences if present.
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: -3]
        return response_model.model_validate_json(text.strip())

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------

    async def _do_complete(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        if self.provider == LLMProvider.ANTHROPIC:
            return await self._complete_anthropic(prompt, system, **kwargs)
        if self.provider == LLMProvider.OPENAI:
            return await self._complete_openai(prompt, system, **kwargs)
        if self.provider == LLMProvider.UIPATH_GATEWAY:
            return await self._complete_openai(prompt, system, **kwargs)
        msg = f"Unsupported provider: {self.provider}"
        raise ValueError(msg)

    async def _complete_anthropic(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._get_anthropic()
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": kwargs.pop("max_tokens", self._max_tokens),
            "temperature": kwargs.pop("temperature", self._temperature),
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            params["system"] = system
        response = await client.messages.create(**params, **kwargs)
        return response.content[0].text  # type: ignore[union-attr]

    async def _complete_openai(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._get_openai()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            temperature=kwargs.pop("temperature", self._temperature),
            **kwargs,
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    async def _with_retries(self, fn: Any, *args: Any, **kwargs: Any) -> str:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                wait = _INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
        raise RuntimeError(
            f"LLM call failed after {_MAX_RETRIES} retries"
        ) from last_exc


def create_llm_client(config: AppConfig) -> LLMClient:
    """Factory: build an :class:`LLMClient` from application configuration.

    Args:
        config: Resolved :class:`AppConfig`.

    Returns:
        A ready-to-use LLM client.
    """
    api_key: str | None = None
    if config.llm.api_key is not None:
        api_key = config.llm.api_key.get_secret_value()

    return LLMClient(
        provider=config.llm.provider,
        model=config.llm.model_name,
        api_key=api_key,
        base_url=config.llm.base_url,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
    )
