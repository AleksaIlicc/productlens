from typing import Literal

from pydantic import BaseModel

from products import Product


class ImageFinding(BaseModel):
    image: str
    role: str
    visible_text: list[str]
    notes: str


class ImageFacts(BaseModel):
    per_image: list[ImageFinding]
    product_name: str
    brand: str
    shade: str
    volume: str
    ingredients: list[str]
    warnings: list[str]
    claims: list[str]


# The exact set of dimensions this tool audits. Fixed on purpose: price,
# availability, SKU, category etc. don't belong to brand-content consistency
# and a closed enum keeps the model from flagging noise outside this scope.
ComparisonField = Literal[
    "product_identity",
    "brand",
    "shade",
    "volume",
    "ingredients",
    "warnings",
    "images_vs_text",
]


class FieldComparison(BaseModel):
    field: ComparisonField
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
    a: Product
    b: Product


class CompareResponse(BaseModel):
    a: Product
    b: Product
    image_facts_a: ImageFacts
    image_facts_b: ImageFacts
    comparison: Comparison
