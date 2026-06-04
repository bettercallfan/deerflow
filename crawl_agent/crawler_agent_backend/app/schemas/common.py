from datetime import datetime
from pydantic import BaseModel


class APIMessage(BaseModel):
    message: str


class Pagination(BaseModel):
    total: int
    page: int
    page_size: int


class PaginatedResponse(BaseModel):
    items: list
    pagination: Pagination


class HealthResponse(BaseModel):
    status: str
    time: datetime
