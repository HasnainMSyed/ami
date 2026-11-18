"""A tiny chat client for the companion: Ollama's native API or any OpenAI-compatible API.

Gemini (generativelanguage.googleapis.com/v1beta/openai) and DeepSeek (api.deepseek.com)
both speak the OpenAI format, so switching provider is a config change.
"""
from __future__ import annotations

import json
import re

import aiohttp


class LLMError(Exception):
    pass


class ChatLLM:
    def __init__(self, provider: str, base_url: str, model: str, api_key: str | None = None, timeout_s: float = 45.0):
        if provider not in ("ollama", "openai"):
            raise ValueError(f"unknown provider {provider!r}")
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self.http: aiohttp.ClientSession | None = None

    def attach(self, http: aiohttp.ClientSession) -> None:
        self.http = http

    def __repr__(self) -> str:  # never show the key
        return f"ChatLLM({self.provider}, {self.base_url}, {self.model})"

    async def chat(self, messages: list[dict], max_tokens: int = 300, temperature: float = 0.6, json_mode: bool = True) -> str:
        if self.http is None:
            raise LLMError("no HTTP session attached")
        try:
            if self.provider == "ollama":
                return await self._ollama(messages, max_tokens, temperature, json_mode)
            return await self._openai(messages, max_tokens, temperature, json_mode)
        except (aiohttp.ClientError, TimeoutError) as e:
            raise LLMError(f"{self.provider} request failed: {e}") from e

    async def _ollama(self, messages, max_tokens, temperature, json_mode) -> str:
        body = {"model": self.model, "messages": messages, "stream": False, "think": False,
                "options": {"temperature": temperature, "num_predict": max_tokens}}
        if json_mode:
            body["format"] = "json"
        async with self.http.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout) as r:
            if r.status != 200:
                raise LLMError(f"ollama HTTP {r.status}: {(await r.text())[:200]}")
            return (await r.json())["message"]["content"]

    async def _openai(self, messages, max_tokens, temperature, json_mode) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        url = f"{self.base_url}/chat/completions"
        async with self.http.post(url, json=body, headers=headers, timeout=self.timeout) as r:
            if r.status == 400 and json_mode:
                # Some providers reject response_format; the prompt still asks for JSON.
                body.pop("response_format")
                async with self.http.post(url, json=body, headers=headers, timeout=self.timeout) as r2:
                    return await self._openai_text(r2)
            return await self._openai_text(r)

    @staticmethod
    async def _openai_text(r: aiohttp.ClientResponse) -> str:
        if r.status != 200:
            raise LLMError(f"HTTP {r.status}: {(await r.text())[:200]}")
        data = await r.json()
        return data["choices"][0]["message"]["content"] or ""


def parse_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and chatter around it."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise LLMError(f"no JSON in model output: {text[:120]!r}")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"bad JSON in model output: {e}") from e
    if not isinstance(obj, dict):
        raise LLMError("model output is not a JSON object")
    return obj
