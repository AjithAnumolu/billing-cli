from pydantic import BaseModel, field_validator


class SpendRow(BaseModel):
    service: str
    cost: float

    @field_validator("service")
    @classmethod
    def service_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("service must be non-empty")
        return value

    @field_validator("cost")
    @classmethod
    def cost_should_be_greater_than_zero(cls, value: float) -> float:
        if value < 0.00:
            raise ValueError("cost must be >= 0")
        return value
