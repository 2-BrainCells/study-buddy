"""Tests for caption formatting."""

from pipeline.transcribe import to_vtt


def test_to_vtt_formats_hours_minutes_seconds():
    assert to_vtt([(3725.5, 3727.0, " Hello. ")]) == "WEBVTT\n\n01:02:05.500 --> 01:02:07.000\nHello.\n"
