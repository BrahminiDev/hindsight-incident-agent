"""Groq chat client with the failure handling the open models need.

gpt-oss-120b is fast but occasionally rejects a request (json_validate_failed,
tool/format errors). We retry once, then fall back to a second model.

Rate limits (429) are different: retrying the same model immediately is pointless,
so we switch to the fallback model (it has its own quota), and if that is limited
too, wait as long as Groq asks (capped) and try the primary one last time.
"""

from __future__ import annotations

import logging
import time

from groq import Groq, RateLimitError

log = logging.getLogger(__name__)

MAX_RATE_LIMIT_WAIT_S = 20.0


def _retry_after(err: RateLimitError) -> float:
    try:
        return float(err.response.headers.get("retry-after", "10"))
    except (AttributeError, TypeError, ValueError):
        return 10.0


class GroqLLM:
    def __init__(self, api_key: str, model: str, fallback_model: str | None = None, timeout: float = 45.0):
        # Retries are handled below (with a model fallback), so the SDK's own retries are off.
        self.client = Groq(api_key=api_key, timeout=timeout, max_retries=0)
        self.model = model
        self.fallback_model = fallback_model

    def ping(self) -> None:
        """Authenticated metadata call; raises if the key or model is not usable."""
        # models.retrieve() URL-encodes the "/" in ids like openai/gpt-oss-120b and 404s, so list instead.
        available = {m.id for m in self.client.models.list(timeout=10).data}
        if self.model not in available:
            raise RuntimeError(f"model {self.model} is not available to this Groq key")

    def _call(self, model: str, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_completion_tokens=2048,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

    def complete(self, system: str, user: str) -> str:
        plan = [self.model, self.model] + ([self.fallback_model] if self.fallback_model else [])
        last_err: Exception | None = None
        rate_wait = 0.0
        i = 0
        while i < len(plan):
            model = plan[i]
            try:
                return self._call(model, system, user)
            except RateLimitError as e:
                last_err, rate_wait = e, max(rate_wait, _retry_after(e))
                log.warning("Groq rate limit (model=%s), retry-after %.0fs", model, _retry_after(e))
                while i < len(plan) and plan[i] == model:  # same model will still be limited
                    i += 1
            except Exception as e:  # groq raises several error types; the rest are retryable here
                last_err = e
                log.warning("Groq call failed (model=%s, attempt=%d): %s", model, i + 1, e)
                i += 1
                time.sleep(0.5 * i)
        if rate_wait:
            time.sleep(min(rate_wait, MAX_RATE_LIMIT_WAIT_S))
            try:
                return self._call(self.model, system, user)
            except Exception as e:
                last_err = e
        raise RuntimeError(f"LLM unavailable after retries: {last_err}")
