"""Groq chat client with the failure handling the open models need.

gpt-oss-120b is fast but occasionally rejects a request (json_validate_failed,
tool/format errors, rate limits). We retry once, then fall back to a second model.
"""

from __future__ import annotations

import logging
import time

from groq import Groq

log = logging.getLogger(__name__)


class GroqLLM:
    def __init__(self, api_key: str, model: str, fallback_model: str | None = None):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.fallback_model = fallback_model

    def complete(self, system: str, user: str) -> str:
        models = [self.model, self.model] + ([self.fallback_model] if self.fallback_model else [])
        last_err: Exception | None = None
        for attempt, model in enumerate(models):
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.2,
                    max_completion_tokens=2048,
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # groq raises several error types; all are retryable here
                last_err = e
                log.warning("Groq call failed (model=%s, attempt=%d): %s", model, attempt + 1, e)
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"LLM unavailable after retries: {last_err}")
