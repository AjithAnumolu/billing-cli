from billing.models import SpendRow
from billing.summarize import summarize_spend


def test_summarize_spend_returns_empty_dict_for_no_rows():
    result = summarize_spend(iter([]))
    assert result == {}


def test_summarize_spend_orders_totals_and_descending():
    rows = iter(
        [
            SpendRow(service="Amazon EC2", cost=8.00),
            SpendRow(service="Amazon S3", cost=8.25),
            SpendRow(service="AWS Lambda", cost=12.75),
            SpendRow(service="Amazon EC2", cost=3.50),
            SpendRow(service="Amazon RDS", cost=4.25),
            SpendRow(service="AWS CloudWatch", cost=3.15),
            SpendRow(service="Amazon RDS", cost=6.25),
        ]
    )

    assert list(summarize_spend(rows).items()) == [
        ("AWS Lambda", 12.75),
        ("Amazon EC2", 11.50),
        ("Amazon RDS", 10.50),
        ("Amazon S3", 8.25),
        ("AWS CloudWatch", 3.15),
    ]


def test_summarize_spend_orders_totals_and_alphabetical_ties():
    rows = iter(
        [
            SpendRow(service="Amazon EC2", cost=8.00),
            SpendRow(service="Amazon S3", cost=8.00),
            SpendRow(service="AWS Lambda", cost=8.00),
            SpendRow(service="Amazon RDS", cost=8.00),
            SpendRow(service="AWS CloudWatch", cost=8.00),
        ]
    )

    assert list(summarize_spend(rows).items()) == [
        ("AWS CloudWatch", 8.00),
        ("AWS Lambda", 8.00),
        ("Amazon EC2", 8.00),
        ("Amazon RDS", 8.00),
        ("Amazon S3", 8.00),
    ]
