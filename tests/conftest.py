import csv
import sys
from collections.abc import Iterable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from billing.models import SpendRow

# Make src/ importable when pytest is run from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_csv_bytes() -> bytes:
    return b"service,cost\nAmazon S3,3.25\nAmazon EC2,10.00\nAmazon EC2,2.50\n"


def _write_csv(tmp_path: Path, filename: str, rows: list[list[object]]) -> Path:
    """Internal helper used only by fixtures."""
    path = tmp_path / filename

    with path.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(rows)

    return path


# ---------------------------------------------------------------------
# CSV fixtures for test_cli.py
# ---------------------------------------------------------------------


@pytest.fixture
def valid_billing_csv(tmp_path) -> Path:
    """A valid CSV for the basic CLI summary test."""
    return _write_csv(
        tmp_path,
        "billing.csv",
        [
            ["service", "cost"],
            ["Amazon EC2", "12.00"],
            ["Amazon S3", "3.25"],
            ["Amazon EC2", "2.00"],
        ],
    )


@pytest.fixture
def top_n_billing_csv(tmp_path) -> Path:
    """A valid CSV whose totals support the top-N CLI tests."""
    return _write_csv(
        tmp_path,
        "top_n.csv",
        [
            ["service", "cost"],
            ["Amazon EC2", "12.50"],
            ["Amazon S3", "3.25"],
            ["AWS Lambda", "0.75"],
            ["Amazon EC2", "1.75"],
            ["Amazon RDS", "8.40"],
            ["Amazon S3", "0.60"],
            ["AWS CloudWatch", "2.15"],
            ["Amazon EC2", "1.20"],
            ["Amazon S3", "3.00"],
            [" Amazon S3 ", "9.00"],
        ],
    )


@pytest.fixture
def invalid_cost_csv(tmp_path) -> Path:
    """A CSV where the second row contains a nonnumeric cost."""
    return _write_csv(
        tmp_path,
        "invalid_cost.csv",
        [
            ["service", "cost"],
            ["Amazon EC2", "not-a-number"],
            ["Amazon S3", "3.25"],
        ],
    )


@pytest.fixture
def header_only_billing_csv(tmp_path) -> Path:
    """A syntactically valid CSV with required headers but zero data rows."""
    return _write_csv(
        tmp_path,
        "header_only.csv",
        [
            ["service", "cost"],
        ],
    )


@pytest.fixture
def missing_cost_column_csv(tmp_path) -> Path:
    """A CSV whose header lacks the required cost column."""
    return _write_csv(
        tmp_path,
        "missing_cost_column.csv",
        [
            ["service"],
            ["Amazon EC2"],
            ["Amazon S3"],
        ],
    )


@pytest.fixture
def negative_cost_csv(tmp_path) -> Path:
    """A CSV rejected because a cost is negative."""
    return _write_csv(
        tmp_path,
        "negative_cost.csv",
        [
            ["service", "cost"],
            ["Amazon S3", "-3.25"],
        ],
    )


@pytest.fixture
def blank_service_and_negative_cost_csv(tmp_path) -> Path:
    """A CSV which triggers both service and cost validation errors."""
    return _write_csv(
        tmp_path,
        "blank_service_and_negative_cost.csv",
        [
            ["service", "cost"],
            [" ", "-3.25"],
        ],
    )


@pytest.fixture
def missing_cost_value_csv(tmp_path) -> Path:
    """A CSV whose row has service but omits cost."""
    return _write_csv(
        tmp_path,
        "missing_cost_value.csv",
        [
            ["service", "cost"],
            ["Amazon EC2"],
        ],
    )


# ---------------------------------------------------------------------
# SpendRow fixtures for test_summarize.py
# ---------------------------------------------------------------------


@pytest.fixture
def empty_spend_rows() -> Iterable[SpendRow]:
    """An empty iterable for summarize_spend."""
    return ()


@pytest.fixture
def spend_rows_with_distinct_totals() -> list[SpendRow]:
    """
    Service totals:
    AWS Lambda: 12.75
    Amazon EC2: 11.50
    Amazon RDS: 10.50
    Amazon S3: 8.25
    AWS CloudWatch: 3.15
    """
    return [
        SpendRow(service="Amazon EC2", cost=8.00),
        SpendRow(service="Amazon S3", cost=8.25),
        SpendRow(service="AWS Lambda", cost=12.75),
        SpendRow(service="Amazon EC2", cost=3.50),
        SpendRow(service="Amazon RDS", cost=4.25),
        SpendRow(service="AWS CloudWatch", cost=3.15),
        SpendRow(service="Amazon RDS", cost=6.25),
    ]


@pytest.fixture
def spend_rows_with_equal_totals() -> list[SpendRow]:
    """Five services each totaling 8.00, for alphabetical tie-breaking."""
    return [
        SpendRow(service="Amazon EC2", cost=8.00),
        SpendRow(service="Amazon S3", cost=8.00),
        SpendRow(service="AWS Lambda", cost=8.00),
        SpendRow(service="Amazon RDS", cost=8.00),
        SpendRow(service="AWS CloudWatch", cost=8.00),
    ]
