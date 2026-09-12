import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from config import get_settings
from llm import compare_products, extract_image_facts
from products import BY_ID, PRODUCTS, Product
from schemas import CompareRequest, CompareResponse
from scraper.router import router as scraper_router

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount(
    "/images",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "data" / "images"),
    name="images",
)
app.include_router(scraper_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/products")
def list_products() -> list[Product]:
    return PRODUCTS


def _resolve(ref: str | Product) -> Product:
    """`ref` is either a demo product id or a full Product (e.g. converted
    client-side from a live search result on the scraper)."""
    if isinstance(ref, Product):
        return ref
    product = BY_ID.get(ref)
    if product is None:
        raise HTTPException(404, f"Nepoznat proizvod: {ref}")
    return product


@app.post("/api/compare")
async def compare(request: CompareRequest) -> CompareResponse:
    a, b = _resolve(request.a), _resolve(request.b)
    if a.id == b.id:
        raise HTTPException(400, "Izaberi dva različita proizvoda")

    facts_a, facts_b = await asyncio.gather(
        extract_image_facts(a), extract_image_facts(b)
    )
    return CompareResponse(
        a=a,
        b=b,
        image_facts_a=facts_a,
        image_facts_b=facts_b,
        comparison=await compare_products(a, b, facts_a, facts_b),
    )
