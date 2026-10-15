"""Speech to text on CPU with word timestamps (faster-whisper), cached per video."""

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

WHISPER_MODEL = "small.en"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    words: list[Word]


def transcribe(video: Path) -> tuple[list[Segment], float, int]:
    """Return segments with word timestamps, the duration in seconds, and the real transcription time in ms.

    The time comes from the run that filled the cache, so a cached re-run still reports the true CPU cost.
    """
    # ponytail: cache keyed by file name + model; renaming the video re-transcribes
    cache = CACHE_DIR / f"{video.stem}.{WHISPER_MODEL}.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if (
            "transcribe_ms" in data
        ):  # older caches lack it: re-transcribe once to measure
            return (
                [_from_dict(s) for s in data["segments"]],
                data["duration"],
                data["transcribe_ms"],
            )

    from faster_whisper import (
        WhisperModel,
    )  # heavy import; tests and cached runs skip it

    t0 = time.monotonic()
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    raw, info = model.transcribe(str(video), word_timestamps=True, vad_filter=True)
    segments = [
        Segment(
            s.start,
            s.end,
            s.text.strip(),
            [Word(w.start, w.end, w.word.strip()) for w in s.words],
        )
        for s in raw  # the generator does the work here, not in transcribe()
    ]
    transcribe_ms = int(
        (time.monotonic() - t0) * 1000
    )  # includes model load: part of the real cost
    cache.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "duration": info.duration,
        "transcribe_ms": transcribe_ms,
        "segments": [asdict(s) for s in segments],
    }
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return segments, info.duration, transcribe_ms


def _from_dict(d: dict) -> Segment:
    return Segment(d["start"], d["end"], d["text"], [Word(**w) for w in d["words"]])


def to_vtt(rows: list[tuple[float, float, str]]) -> str:
    """WebVTT captions from (start_s, end_s, text) segment rows."""

    def stamp(s: float) -> str:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{int(h):02}:{int(m):02}:{sec:06.3f}"

    cues = (f"{stamp(a)} --> {stamp(b)}\n{t.strip()}" for a, b, t in rows)
    return "WEBVTT\n\n" + "\n\n".join(cues) + "\n"
