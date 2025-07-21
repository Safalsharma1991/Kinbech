from pydantic import BaseModel
from typing import List


class ProductOut(BaseModel):
    id: int
    name: str
    description: str
    price: str
    delivery_range_km: int
    image_urls: List[str]
    likes: int | None = 0

    model_config = {"from_attributes": True}
