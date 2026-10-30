"""API latency, p50 and p95 per route (roadmap #5). Usage, from backend/: python bench_api.py <base-url> [n]

Locally, use http://127.0.0.1:8001, not localhost: on Windows, localhost tries IPv6 first and uvicorn listens
on IPv4 only, which adds about 2 s to every request (measured 30 Oct: 2059 ms vs 3 ms).

GET routes only, so nothing is written (no events, no profile changes). The plan route can call the novelty
model if a learner has notes with unchecked terms; demo learners' verdicts are cached, so it shouldn't.
Requests run one at a time: this is one user's wait, not throughput under load. The first request to each
route is reported apart as "first" (on a sleeping free host it includes the wake-up) and kept out of p50/p95.
"""

import json
import statistics
import sys
import time
from urllib.request import urlopen


def get(url: str) -> tuple[float, bytes]:
    """Fetch url; return (seconds taken, body). Any non-2xx raises, so a broken route can't pass as fast."""
    started = time.perf_counter()
    with urlopen(url, timeout=120) as resp:
        body = resp.read()
    return time.perf_counter() - started, body


def routes(base: str) -> list[str]:
    """The read routes a learner and the dashboard hit, using the demo learners and the first video."""
    learners = {
        item["name"]: item["id"] for item in json.loads(get(f"{base}/api/learners")[1])
    }
    video = json.loads(get(f"{base}/api/videos")[1])[0]["id"]
    return [
        "/api/config",
        "/api/learners",
        "/api/videos",
        f"/api/learners/{learners['Learner A']}/videos/{video}/plan",
        f"/api/learners/{learners['Learner B']}/videos/{video}/plan",
        f"/api/videos/{video}/quiz",
        f"/api/dashboard/videos/{video}",
        "/api/usage",
    ]


def main(base: str, n: int) -> None:
    """Time each route n times after one first request, and print a table in milliseconds."""
    first_overall, _ = get(
        f"{base}/health"
    )  # the very first request: wakes a sleeping host
    print(f"{base}  n={n} per route  first /health: {first_overall * 1000:.0f} ms\n")
    print(f"{'route':45} {'first':>7} {'p50':>7} {'p95':>7} {'max':>7}")
    for route in routes(base):
        first, _ = get(base + route)
        times = sorted(get(base + route)[0] * 1000 for _ in range(n))
        cuts = statistics.quantiles(
            times, n=20, method="inclusive"
        )  # cuts[9] = p50, cuts[18] = p95
        print(
            f"{route:45} {first * 1000:7.0f} {cuts[9]:7.0f} {cuts[18]:7.0f} {times[-1]:7.0f}"
        )


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"), int(sys.argv[2]) if len(sys.argv) > 2 else 50)
