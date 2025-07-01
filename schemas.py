from pydantic import BaseModel
from typing import List


class ProductOut(BaseModel):
    id: int
    name: str
    description: str
    price: float
    delivery_range_km: int
    expiry_datetime: str  # or datetime if you’re using datetime
    image_urls: List[str]

    model_config = {
        "from_attributes": True
    }
