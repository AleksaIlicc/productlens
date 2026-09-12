# On-disk JSON cache for raw provider responses plus persisted runs, so
# re-running a query is free and past runs stay inspectable.

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from scraper.settings import CACHE_DIR, RUNS_DIR

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def cache_key(kind: str, payload: dict) -> str:
    blob = (
        kind
        + "|"
        + json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _path(kind: str, key: str) -> Path:
    return CACHE_DIR / kind / f"{key}.json"


def _write_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load(kind: str, payload: dict, ttl_hours: int) -> dict | None:
    path = _path(kind, cache_key(kind, payload))
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(entry.get("cached_at", 0)) > ttl_hours * 3600:
            return None
        value = entry.get("value")
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        path.unlink(missing_ok=True)  # corrupt or half-written entry
        return None


def store(kind: str, payload: dict, value: dict) -> None:
    try:
        _write_atomic(
            _path(kind, cache_key(kind, payload)),
            {"cached_at": time.time(), "kind": kind, "value": value},
        )
    except OSError:
        pass  # a cache that cannot be written must not break a run


def save_run(response: dict) -> None:
    run_id = str(response.get("run_id", ""))
    if not RUN_ID_RE.match(run_id):
        return
    try:
        _write_atomic(RUNS_DIR / f"{run_id}.json", response)
    except OSError:
        pass


def list_runs(limit: int = 50) -> list[dict]:
    if not RUNS_DIR.is_dir():
        return []
    files = sorted(
        RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    out: list[dict] = []
    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        totals = data.get("totals") or {}
        out.append(
            {
                "run_id": data.get("run_id", path.stem),
                "query": data.get("query", ""),
                "scope": data.get("scope", "both"),
                "started_at": data.get("started_at", ""),
                "elapsed_ms": data.get("elapsed_ms", 0),
                "candidates": totals.get("candidates", 0),
                "scraped_ok": totals.get("scraped_ok", 0),
                "images": totals.get("images", 0),
            }
        )
    return out


def load_run(run_id: str) -> dict | None:
    if not RUN_ID_RE.match(run_id or ""):
        return None
    path = RUNS_DIR / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def runs_count() -> int:
    return len(list(RUNS_DIR.glob("*.json"))) if RUNS_DIR.is_dir() else 0
