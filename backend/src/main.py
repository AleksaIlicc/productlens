from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from config import get_settings
from lab.router import router as lab_router
from llm import compare_products, extract_image_facts
from products import BY_ID, PRODUCTS, Product
from schemas import CompareRequest, CompareResponse

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount(
    "/images",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "data" / "images"),
    name="images",
)
app.include_router(lab_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/products")
def list_products() -> list[Product]:
    return PRODUCTS


def _get(product_id: str) -> Product:
    product = BY_ID.get(product_id)
    if product is None:
        raise HTTPException(404, f"Nepoznat proizvod: {product_id}")
    return product


@app.post("/api/compare")
def compare(request: CompareRequest) -> CompareResponse:
    if request.a == request.b:
        raise HTTPException(400, "Izaberi dva različita proizvoda")

    a, b = _get(request.a), _get(request.b)
    facts_a = extract_image_facts(a)
    facts_b = extract_image_facts(b)
    return CompareResponse(
        a=a,
        b=b,
        image_facts_a=facts_a,
        image_facts_b=facts_b,
        comparison=compare_products(a, b, facts_a, facts_b),
    )
