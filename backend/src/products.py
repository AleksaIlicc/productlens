import json
from pathlib import Path

from pydantic import BaseModel

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"


class Product(BaseModel):
    """One channel's listing for a product: scraped text plus photo filenames.

    Shaped to match what a scraper hands over — a title, a brand, a blob of
    scraped page text, and a list of images. No pre-parsed specs/sections:
    the comparison step reads shade, volume, ingredients etc. straight out
    of raw_text instead of relying on us bucketing it by hand.
    """

    id: str
    source: str
    url: str
    title: str
    brand: str
    raw_text: str
    images: list[str]


PRODUCTS: list[Product] = [
    Product.model_validate(item) for item in json.loads(DATA_FILE.read_text())
]
BY_ID: dict[str, Product] = {p.id: p for p in PRODUCTS}
