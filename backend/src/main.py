from fastapi import FastAPI, HTTPException

from analyze import router as analyze_router
from analyze import run_comparison
from config import get_settings
from schemas import CompareRequest, CompareResponse
from scraper.router import router as scraper_router

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(scraper_router)
app.include_router(analyze_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/compare")
async def compare(request: CompareRequest) -> CompareResponse:
    # The UI runs this through /api/analyze/compare so it can show progress;
    # this route is the same work in one blocking call.
    if len(request.listings) < 2:
        raise HTTPException(400, "Pick at least two listings to compare")
    if len({listing.id for listing in request.listings}) != len(request.listings):
        raise HTTPException(400, "The same listing was picked twice")
    return await run_comparison(request.listings)
