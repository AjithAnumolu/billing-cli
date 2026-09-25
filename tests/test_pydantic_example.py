import pytest

from billing.pydantic_example import SpendRow


def test_spend_row_rejects_empty_service():
    with pytest.raises(ValueError, match="service must be non-empty"):
        SpendRow(service="", cost=8.00)


def test_spend_row_rejects_negative_cost():
    with pytest.raises(ValueError, match="cost must be >= 0"):
        SpendRow(service="Amazon EC2", cost=-8.00)
