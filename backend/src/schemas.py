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
    "shade",
    "volume",
    "ingredients",
    "warnings",
    "images_vs_text",
]


class ListingValue(BaseModel):
    """What one listing states for one dimension.

    `listing` is the short label ("A", "B", ...) the audit prompt was given,
    not a domain — two pages can come from the same shop.
    """

    listing: str
    value: str


class FieldComparison(BaseModel):
    field: ComparisonField
    origin: Literal["web", "image", "both"]
    values: list[ListingValue]
    # Labels carrying the problem this row describes — the listings that would
    # need fixing. Empty when nothing is wrong.
    flagged: list[str]
    status: Literal["match", "minor", "mismatch", "missing"]
    severity: Literal["info", "low", "medium", "high"]
    explanation: str


class Comparison(BaseModel):
    same_product: bool
    verdict: str
    fields: list[FieldComparison]


class AnalysedListing(BaseModel):
    label: str
    product: Product
    facts: ImageFacts


class CompareRequest(BaseModel):
    listings: list[Product]


class CompareResponse(BaseModel):
    listings: list[AnalysedListing]
    comparison: Comparison
