from pydantic import BaseModel


class Product(BaseModel):
    """One channel's listing for a product: scraped text plus image URLs.

    Always built from a live scraper result (see frontend/src/search.ts) —
    there's no local/demo data source; the comparison step reads shade,
    volume, ingredients etc. straight out of raw_text.
    """

    id: str
    source: str
    url: str
    title: str
    brand: str
    raw_text: str
    images: list[str]
