"""TEMPORARY router for the scraping side of ProductLens.

Everything lives under /api/lab and is owned by the search+scraping work; it does
no LLM processing. Once the two halves are joined, `payload.offers` from
/api/lab/discover becomes the input of the comparison step and this router goes away.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, HTTPException, Query, Response

from lab import cache, pipeline
from lab.models import (
    DiscoverRequest,
    DiscoverResponse,
    LabHealth,
    RunSummary,
    ScrapedPage,
    ScrapeOneRequest,
)
from lab.providers import exa, firecrawl
from lab.settings import CACHE_DIR, get_lab_settings

router = APIRouter(prefix="/api/lab", tags=["lab"])

ALLOWED_IMAGE_PORTS = (80, 443)


@router.get("/health")
async def health(
    ping: bool = Query(default=False, description="Pozovi provajdere (troši kredite)"),
) -> LabHealth:
    settings = get_lab_settings()
    firecrawl_ping = "ključ postavljen" if settings.firecrawl_api_key else "nema ključa"
    exa_ping = "ključ postavljen" if settings.exa_api_key else "nema ključa"

    if ping:
        fc_task = firecrawl.search_web("test", limit=1, use_cache=True)
        exa_task = exa.search("test", num_results=1, use_cache=True)
        (_fc_hits, fc_call), (_exa_hits, exa_call) = await asyncio.gather(
            fc_task, exa_task
        )
        firecrawl_ping = "ok" if fc_call.ok else f"greška: {fc_call.error}"[:120]
        exa_ping = "ok" if exa_call.ok else f"greška: {exa_call.error}"[:120]

    return LabHealth(
        firecrawl_key=bool(settings.firecrawl_api_key),
        exa_key=bool(settings.exa_api_key),
        cache_enabled=settings.lab_cache_enabled,
        cache_dir=str(CACHE_DIR),
        runs=cache.runs_count(),
        firecrawl_ping=firecrawl_ping,
        exa_ping=exa_ping,
    )


@router.post("/discover")
async def discover(request: DiscoverRequest) -> DiscoverResponse:
    if not request.query.strip():
        raise HTTPException(400, "Unesi naziv proizvoda")
    if not request.providers:
        raise HTTPException(400, "Izaberi najmanje jedan provajder")
    return await pipeline.discover(request)


@router.post("/scrape")
async def scrape(request: ScrapeOneRequest) -> ScrapedPage:
    url = request.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL mora počinjati sa http:// ili https://")
    return await pipeline.scrape_one(request.model_copy(update={"url": url}))


@router.get("/runs")
def runs(limit: int = Query(default=50, ge=1, le=200)) -> list[RunSummary]:
    return [RunSummary.model_validate(item) for item in cache.list_runs(limit)]


@router.get("/runs/{run_id}")
def run(run_id: str) -> DiscoverResponse:
    data = cache.load_run(run_id)
    if data is None:
        raise HTTPException(404, f"Nepoznat run: {run_id}")
    return DiscoverResponse.model_validate(data)


async def _image_url_problem(url: str) -> str:
    """SSRF guard: public http(s) hosts on standard ports only, per redirect hop."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return "dozvoljeni su samo http i https"
    host = parts.hostname
    if not host:
        return "nedostaje host"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_IMAGE_PORTS:
        return f"port {port} nije dozvoljen"
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, port, proto=socket.IPPROTO_TCP
        )
    except OSError:
        return "host se ne može razrešiti"
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            return "neispravna IP adresa"
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return "privatne i lokalne adrese nisu dozvoljene"
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None and (
            mapped.is_private or mapped.is_loopback or mapped.is_link_local
        ):
            return "privatne i lokalne adrese nisu dozvoljene"
    return ""


@router.get("/image")
async def image(url: str = Query(..., min_length=8, max_length=2048)) -> Response:
    """Proxy product images so hotlink protection cannot blank out the lab gallery."""
    from lab.http import get_bytes  # local import keeps the module graph flat

    target = unquote(url).strip()
    problem = await _image_url_problem(target)
    if problem:
        raise HTTPException(400, f"Slika nije dozvoljena: {problem}")

    settings = get_lab_settings()
    status, body, content_type, error = await get_bytes(
        target,
        timeout=30.0,
        max_bytes=settings.lab_max_image_bytes,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ProductLensLab/0.1)",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": f"{urlsplit(target).scheme}://{urlsplit(target).netloc}/",
        },
        validate=_image_url_problem,
    )
    if error:
        raise HTTPException(502, f"Slika nije preuzeta: {error}")
    if status is None or status >= 400 or not body:
        raise HTTPException(502, f"Slika nije preuzeta (HTTP {status})")
    if not content_type.startswith("image/"):
        raise HTTPException(
            415, f"Sadržaj nije slika ({content_type or 'nepoznat tip'})"
        )

    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
