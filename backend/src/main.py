import asyncio

from fastapi import FastAPI, HTTPException

from config import get_settings
from llm import compare_products, extract_image_facts
from products import Product
from schemas import CompareRequest, CompareResponse, ImageFacts
from scraper.router import router as scraper_router

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.include_router(scraper_router)


@app.get("/health")
def health():
    return {"status": "ok"}


def _analyzed(product: Product, facts: ImageFacts) -> Product:
    # Narrow images to what was actually analyzed, so the UI gallery matches.
    kept = [finding.image for finding in facts.per_image]
    return product.model_copy(update={"images": kept}) if kept else product


@app.post("/api/compare")
async def compare(request: CompareRequest) -> CompareResponse:
    a, b = request.a, request.b
    if a.id == b.id:
        raise HTTPException(400, "Izaberi dva različita proizvoda")

    facts_a, facts_b = await asyncio.gather(
        extract_image_facts(a), extract_image_facts(b)
    )
    return CompareResponse(
        a=_analyzed(a, facts_a),
        b=_analyzed(b, facts_b),
        image_facts_a=facts_a,
        image_facts_b=facts_b,
        comparison=await compare_products(a, b, facts_a, facts_b),
    )
