import json
from pathlib import Path

from pydantic import BaseModel

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"


class Product(BaseModel):
    id: str
    source: str
    url: str
    title: str
    brand: str
    price: str
    availability: str
    specs: dict[str, str]
    sections: dict[str, str]
    images: list[str]


PRODUCTS: list[Product] = [
    Product.model_validate(item) for item in json.loads(DATA_FILE.read_text())
]
BY_ID: dict[str, Product] = {p.id: p for p in PRODUCTS}
