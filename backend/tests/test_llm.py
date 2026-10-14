"""Tests for the Token Factory client, using a fake HTTP server (no real model)."""

import json

import httpx
import openai
import pydantic
import pytest
from pipeline import llm
from pipeline.llm import EmptyReplyError, Settings, TokenFactory
from pydantic import BaseModel, ConfigDict

SETTINGS = Settings(
    base_url="http://fake/v1",
    api_key="test",
    llm_model="fake-llm",
    vision_model="fake-vision",
)
MESSAGES = [{"role": "user", "content": "hi"}]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str


def completion(
    content: str, prompt_tokens: int = 10, completion_tokens: int = 5
) -> httpx.Response:
    """A fake OpenAI-style chat completion response."""
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "fake-llm",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )


def error(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"message": "fake error"}}, headers=headers
    )


def make_client(*responses: httpx.Response):
    """Client whose fake server returns `responses` in order. Also returns cost rows and seen requests."""
    queue, costs, seen = list(responses), [], []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TokenFactory(SETTINGS, cost_sink=costs.append, http_client=http), costs, seen


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Skip real waiting (rate-limit gap and backoff) so tests run instantly."""
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)


def test_valid_json_is_parsed_and_request_follows_rules():
    tf, _, seen = make_client(completion('{"answer": "hi"}'))
    assert tf.chat_json("t", Out, MESSAGES) == Out(answer="hi")
    body = json.loads(seen[0].content)
    assert body["reasoning_effort"] == "none"
    assert body["response_format"] == {"type": "json_object"}
    assert (
        '"answer"' in body["messages"][0]["content"]
    )  # schema is in the system prompt
    assert body["model"] == "fake-llm"


def test_429_is_retried_and_counted():
    tf, costs, seen = make_client(
        error(429, {"retry-after": "0"}), completion('{"answer": "hi"}')
    )
    tf.chat_json("t", Out, MESSAGES)
    assert len(seen) == 2
    assert costs[0].retries_429 == 1 and costs[0].requests == 2


def test_500_is_not_retried():
    tf, _, seen = make_client(error(500))
    with pytest.raises(openai.InternalServerError):
        tf.chat_json("t", Out, MESSAGES)
    assert len(seen) == 1


def test_gives_up_after_max_tries():
    tf, _, seen = make_client(*[error(429) for _ in range(llm.MAX_TRIES)])
    with pytest.raises(openai.RateLimitError):
        tf.chat_json("t", Out, MESSAGES)
    assert len(seen) == llm.MAX_TRIES


def test_empty_reply_raises():
    tf, _, _ = make_client(completion(""))
    with pytest.raises(EmptyReplyError):
        tf.chat_json("t", Out, MESSAGES)


def test_reply_not_matching_schema_raises():
    tf, _, _ = make_client(completion('{"wrong": 1}'))
    with pytest.raises(pydantic.ValidationError):
        tf.chat_json("t", Out, MESSAGES)


def test_cost_row_has_tokens_and_ids():
    tf, costs, _ = make_client(
        completion('{"answer": "hi"}', prompt_tokens=120, completion_tokens=30)
    )
    tf.chat_json("terms", Out, MESSAGES, video_id=7)
    c = costs[0]
    assert (c.stage, c.input_tokens, c.output_tokens, c.video_id) == (
        "terms",
        120,
        30,
        7,
    )


def test_check_models_fails_when_model_missing():
    models = httpx.Response(
        200,
        json={
            "object": "list",
            "data": [
                {"id": "fake-llm", "object": "model", "created": 0, "owned_by": "amd"}
            ],
        },
    )
    tf, _, _ = make_client(models)
    with pytest.raises(RuntimeError, match="fake-vision"):
        tf.check_models()
