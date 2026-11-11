"""Optional rolling history of cell voltages + statistics over a time window.

Stored as a small JSON file: a list of ``[unix_timestamp, [cell mV, ...]]`` samples.
Nothing here talks to the battery; feed it the ``cells_mv`` list from an analog read.
"""

import json
import os
import tempfile

DEFAULT_WINDOW_S = 7 * 86400


def load(path):
    """Load samples; a missing or corrupt file gives an empty history."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [s for s in data if isinstance(s, list) and len(s) == 2 and isinstance(s[1], list)]


def save(path, samples):
    """Atomic write (temp file + rename) so a crash never leaves a half-written file."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".history-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(samples, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add(samples, timestamp, cells_mv, window_s=DEFAULT_WINDOW_S):
    """Append a sample and drop everything older than the window. Returns the new list."""
    keep = [s for s in samples if s[0] > timestamp - window_s and s[0] < timestamp]
    return keep + [[int(timestamp), list(cells_mv)]]


def stats(samples):
    """Per-cell and pack statistics over all samples (of the current cell count).

    Per cell: now, min, max, avg (mV) and deviation from the pack mean of the same
    sample, now ("dev_now_mv"), averaged over the window ("dev_avg_mv") and the largest
    one in the window ("dev_max_mv", signed: the deviation with the biggest magnitude;
    "dev_max_ts" = when it happened). The averages hide short peaks, the max shows them.
    Pack: spread (max - min cell) now / avg / min / max over the window.
    Returns None for an empty history.
    """
    if not samples:
        return None
    n = len(samples[-1][1])
    use = [s for s in samples if len(s[1]) == n]
    now = use[-1][1]
    means = [sum(s[1]) / float(n) for s in use]
    cells = []
    for i in range(n):
        vals = [s[1][i] for s in use]
        devs = [v - m for v, m in zip(vals, means)]
        k = max(range(len(devs)), key=lambda j: abs(devs[j]))
        cells.append({
            "cell": i + 1,
            "now_mv": now[i],
            "min_mv": min(vals),
            "max_mv": max(vals),
            "avg_mv": round(sum(vals) / len(vals), 1),
            "dev_now_mv": round(now[i] - means[-1], 1),
            "dev_avg_mv": round(sum(devs) / len(devs), 1),
            "dev_max_mv": round(devs[k], 1),
            "dev_max_ts": use[k][0],
        })
    spreads = [max(s[1]) - min(s[1]) for s in use]
    return {
        "samples": len(use),
        "first_timestamp": use[0][0],
        "last_timestamp": use[-1][0],
        "span_days": round((use[-1][0] - use[0][0]) / 86400.0, 2),
        "spread_now_mv": spreads[-1],
        "spread_avg_mv": round(sum(spreads) / len(spreads), 1),
        "spread_min_mv": min(spreads),
        "spread_max_mv": max(spreads),
        "cells": cells,
    }
