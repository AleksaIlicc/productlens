"""Thin async HTTP helper. Uses httpx2 (already in the venv via openai) and never
raises for network/HTTP problems: callers get a result object and keep going.
"""

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx2

RETRY_STATUSES = (408, 425, 429, 500, 502, 503, 504)


@dataclass
class HttpResult:
    ok: bool
    status: int | None = None
    json: Any | None = None
    text: str = ""
    elapsed_ms: int = 0
    error: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def _retry_after_seconds(headers: dict[str, str], attempt: int) -> float:
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw:
        try:
            return min(float(raw), 20.0)
        except ValueError:
            pass
    return min(2.0**attempt, 12.0) + random.uniform(0, 0.4)


async def post_json(
    url: str,
    body: dict,
    headers: dict[str, str],
    *,
    timeout: float,
    attempts: int = 3,
) -> HttpResult:
    loop = asyncio.get_running_loop()
    started = loop.time()
    last = HttpResult(ok=False, error="no attempt made")

    for attempt in range(max(1, attempts)):
        try:
            async with httpx2.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                res = await c.post(url, json=body, headers=headers)
            payload: Any | None
            try:
                payload = res.json()
            except Exception:
                payload = None
            elapsed = int((loop.time() - started) * 1000)
            hdrs = {k.lower(): v for k, v in res.headers.items()}
            if res.status_code < 400:
                return HttpResult(
                    ok=True,
                    status=res.status_code,
                    json=payload,
                    text="" if payload is not None else res.text[:4000],
                    elapsed_ms=elapsed,
                    headers=hdrs,
                )
            detail = ""
            if isinstance(payload, dict):
                detail = str(payload.get("error") or payload.get("detail") or payload)[
                    :300
                ]
            else:
                detail = res.text[:300]
            last = HttpResult(
                ok=False,
                status=res.status_code,
                json=payload,
                text=res.text[:2000],
                elapsed_ms=elapsed,
                error=f"HTTP {res.status_code}: {detail}",
                headers=hdrs,
            )
            if res.status_code not in RETRY_STATUSES or attempt == attempts - 1:
                return last
            await asyncio.sleep(_retry_after_seconds(hdrs, attempt))
        except Exception as exc:  # transport, timeout, DNS, TLS...
            last = HttpResult(
                ok=False,
                elapsed_ms=int((loop.time() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}"[:300],
            )
            if attempt == attempts - 1:
                return last
            await asyncio.sleep(min(2.0**attempt, 8.0) + random.uniform(0, 0.4))

    return last


async def get_bytes(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    validate: Callable[[str], Awaitable[str]] | None = None,
    max_redirects: int = 3,
) -> tuple[int | None, bytes, str, str]:
    """Fetch bytes with a hard size cap, following redirects manually so that
    `validate` (the SSRF guard) runs again for every hop. Returns
    (status, body, content_type, error).
    """
    current = url
    for _ in range(max_redirects + 1):
        if validate is not None:
            problem = await validate(current)
            if problem:
                return None, b"", "", problem
        try:
            async with httpx2.AsyncClient(timeout=timeout, follow_redirects=False) as c:
                async with c.stream("GET", current, headers=headers or {}) as res:
                    if res.status_code in (301, 302, 303, 307, 308):
                        location = res.headers.get("location", "")
                        await res.aclose()
                        if not location:
                            return res.status_code, b"", "", "redirect without location"
                        current = str(httpx2.URL(current).join(location))
                        continue
                    content_type = (
                        res.headers.get("content-type", "").split(";")[0].strip()
                    )
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in res.aiter_bytes(64 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            return res.status_code, b"", content_type, "file too large"
                        chunks.append(chunk)
                    return res.status_code, b"".join(chunks), content_type, ""
        except Exception as exc:
            return None, b"", "", f"{type(exc).__name__}: {exc}"[:200]
    return None, b"", "", "too many redirects"
