from pydantic import BaseModel


# One channel's listing, built from a live scraper result
# (see frontend/src/search.ts). The comparison step reads shade, volume,
# ingredients etc. straight out of raw_text.
class Product(BaseModel):
    id: str
    source: str
    url: str
    title: str
    raw_text: str
    images: list[str]
