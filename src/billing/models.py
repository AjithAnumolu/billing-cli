from dataclasses import dataclass

@dataclass(frozen=True)
class SpendRow:
    service: str
    cost: float

    def __post_init__(self):
        if not self.service.strip():
            raise ValueError("service must be non-empty")
        if self.cost < 0:
            raise ValueError("cost must be >= 0")
