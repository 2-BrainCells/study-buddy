"""Tests for the dashboard and usage aggregates and the quota collector (no database, no real API)."""

import httpx
import pytest
from app.insights import cost_usd, per_hour, struggle_rows
from pipeline.llm import Settings, quota_summary, rate_limits

SETTINGS = Settings(base_url="https://tf.test/v1", api_key="k", llm_model="m", vision_model="v")


def test_cost_uses_list_price_and_unknown_models_have_none():
    assert cost_usd("MiMo-V2.6-Flash", 1_000_000, 1_000_000) == pytest.approx(0.42)
    assert cost_usd("faster-whisper-small.en", 0, 0) is None


def test_per_hour_scales_a_16_minute_clip():
    assert per_hour(1.0, 900) == 4.0
    assert per_hour(1.0, None) is None


def test_struggle_rows_rank_hardest_first_and_count_new_learners():
    rows = [(1, "easy", 10.0, 2, 0, 1, 2, 0), (2, "hard", 20.0, 0, 2, 0, 2, 2)]
    out = struggle_rows(rows, learners=2)
    assert [r["term"] for r in out] == ["hard", "easy"]
    assert out[0]["new_for"] == 2 and out[0]["score"] == 4 and out[1]["new_for"] == 0


def test_rate_limits_never_raises_and_reports_why():
    def boom(request):
        raise httpx.ConnectError("down")

    q = rate_limits(SETTINGS, httpx.Client(transport=httpx.MockTransport(boom)))
    assert q["available"] is False and "ConnectError" in q["reason"]


def test_quota_summary_keeps_panel_fields_and_drops_ids():
    usage = {"daily_cost_limit_usd": 1, "daily_cost_remaining_usd": 0.9, "rpm_limit": 20,
             "organization_id": "org", "project_id": "p", "today": {"requests": 3, "cost": 0.1, "secret": 1}}

    def ok(request):
        return httpx.Response(200, json=usage)

    q = quota_summary(rate_limits(SETTINGS, httpx.Client(transport=httpx.MockTransport(ok))))
    assert q["available"] and q["daily_limit_usd"] == 1 and q["rpm_limit"] == 20
    assert "organization_id" not in str(q) and q["today"]["requests"] == 3 and "secret" not in q["today"]
