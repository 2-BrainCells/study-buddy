"""Token Factory client: the only way this app talks to an LLM."""

from __future__ import annotations

import json
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TypeVar

import httpx
import openai
import psycopg
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

RETRYABLE = {429, 502, 503}
MAX_TRIES = 5
MAX_CONCURRENT = 8
MIN_GAP_S = 3.0  # 60 s / 20 requests


@dataclass(frozen=True)
class Settings:
    """Endpoint and model names, always from env vars."""

    base_url: str
    api_key: str
    llm_model: str
    vision_model: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            base_url=os.environ["LLM_BASE_URL"],
            api_key=os.environ["RADEON_API_KEY"],
            llm_model=os.environ["LLM_MODEL"],
            vision_model=os.environ["VISION_MODEL"],
        )


@dataclass(frozen=True)
class StageCost:
    """One row of stage_costs."""

    stage: str
    model: str
    requests: int
    input_tokens: int
    output_tokens: int
    retries_429: int
    latency_ms: int
    video_id: int | None = None
    learner_id: int | None = None


class EmptyReplyError(RuntimeError):
    """The model returned no content (ux_tokens)."""


def _backoff(attempt: int, retry_after: str | None) -> float:
    """Seconds to wait before the next se 2**attempt, plus jitter."""
    try:
        base = float(retry_after) if retry_after else 2.0**attempt
    except ValueError:  # Retry-After may also be an HTTP date
        base = 2.0**attempt
    return base + random.uniform(0, 1)


def db_cost_sink(database_url: str) -> Callable[[StageCost], None]:
    """Return a sink that inserts each StageCost into stage_costs."""

    def write(cost: StageCost) -> None:
        row = asdict(cost)
        cols = ", ".join(row)
        params = ", ".join(f"%({c})s" for c in row)
        with psycopg.connect(database_url) as conn:  # commits on exit
            conn.execute(f"INSERT INTO stage_costs ({cols}) VALUES ({params})", row)

    return write


class TokenFactory:
    """Rate-limited, retrying, cost-logctory API."""

    def __init__(
        self,
        settings: Settings,
        cost_sink: Callable[[StageCost], None],
        http_client: httpx.Client | None = None,
        max_tokens: int = 2000,
    ) -> None:
        self.settings = settings
        self.cost_sink = cost_sink
        self.max_tokens = max_tokens
        self._client = openai.OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            max_retries=0,
            http_client=http_client,
        )
        self._slots = threading.Semaphore(MAX_CONCURRENT)
        self._gap_lock = threading.Lock()
        self._next_start = 0.0

    def _wait_turn(self) -> None:
        # ponytail: process-local limiter; needs a shared one (Postgres/Redis) if we run >1 worker
        with self._gap_lock:
            now = time.monotonic()
            start = max(now, self._next_start)
            self._next_start = start + MIN_GAP_S
        time.sleep(start - now)

    def check_models(self) -> list[str]:
        """Return served model ids; raise if LLM_MODEL or VISION_MODEL is missing."""
        ids = [m.id for m in self._client.models.list().data]
        missing = {self.settings.llm_model, self.settings.vision_model} - set(ids)
        if missing:
            raise RuntimeError(
                f"Token Factory does not serve {sorted(missing)}; available: {ids}"
            )
        return ids

    def chat_json(
        self,
        stage: str,
        out_model: type[T],
        messages: list[dict[str, str]],
        *,
        video_id: int | None = None,
        learner_id: int | None = None,
    ) -> T:
        """Call the LLM in JSON mode (schema in the prompt) and return the Pydantic-validated reply."""
        # ponytail: Token Factory has JSON mode only (structured_outputs: false, probed 14 Oct), so the
        # schema goes in the prompt and Pydantic is the real check. Add one repair retry if real chunks fail.
        system = {
            "role": "system",
            "content": "Reply with only a JSON object that matches this JSON Schema:\n"
            + json.dumps(out_model.model_json_schema()),
        }
        retries_429 = 0
        started = time.monotonic()
        for attempt in range(MAX_TRIES):
            self._wait_turn()
            try:
                with self._slots:
                    completion = self._client.chat.completions.create(
                        model=self.settings.llm_model,
                        messages=[system, *messages],
                        response_format={"type": "json_object"},
                        reasoning_effort="none",
                        max_tokens=self.max_tokens,
                    )
                break
            except openai.APIStatusError as e:
                if e.status_code == 429:
                    retries_429 += 1
                if e.status_code not in RETRYABLE or attempt == MAX_TRIES - 1:
                    # ponytail: failed calls aren't logged; log them too if the Saturday 429 panel needs it
                    raise
                time.sleep(_backoff(attempt, e.response.headers.get("retry-after")))

        usage = completion.usage
        self.cost_sink(
            StageCost(
                stage=stage,
                model=self.settings.llm_model,
                requests=attempt + 1,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                retries_429=retries_429,
                latency_ms=int((time.monotonic() - started) * 1000),
                video_id=video_id,
                learner_id=learner_id,
            )
        )
        content = completion.choices[0].message.content
        if not content:
            raise EmptyReplyError(
                f"{stage}: empty reply (finish_reason={completion.choices[0].finish_reason})"
            )
        return out_model.model_validate_json(content)
