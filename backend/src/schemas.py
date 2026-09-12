from typing import Literal

from pydantic import BaseModel

from products import Product


class ImageFinding(BaseModel):
    image: str
    role: str
    visible_text: list[str]
    claims: list[str]
    notes: str


class ImageFacts(BaseModel):
    per_image: list[ImageFinding]
    product_name: str
    brand: str
    shade: str
    volume: str
    spf: str
    claims: list[str]


class FieldComparison(BaseModel):
    field: str
    origin: Literal["web", "image", "both"]
    value_a: str
    value_b: str
    status: Literal["match", "minor", "mismatch", "missing"]
    severity: Literal["info", "low", "medium", "high"]
    explanation: str


class Comparison(BaseModel):
    same_product: bool
    verdict: str
    fields: list[FieldComparison]


class CompareRequest(BaseModel):
    a: str
    b: str


class CompareResponse(BaseModel):
    a: Product
    b: Product
    image_facts_a: ImageFacts
    image_facts_b: ImageFacts
    comparison: Comparison
