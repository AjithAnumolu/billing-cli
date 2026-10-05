from pydantic import BaseModel, Field


class ServiceSpend(BaseModel):
    service: str
    cost: float = Field(ge=0)


class BillingSummaryResponse(BaseModel):
    services: list[ServiceSpend]
    grand_total: float = Field(ge=0)
    service_count: int = Field(ge=0)
