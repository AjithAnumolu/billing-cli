from billing.summarize import summarize_spend


def test_summarize_spend_returns_empty_dict_for_no_rows(empty_spend_rows):
    result = summarize_spend(iter(empty_spend_rows))

    assert result == {}


def test_summarize_spend_orders_totals_and_descending(
    spend_rows_with_distinct_totals,
):
    result = summarize_spend(iter(spend_rows_with_distinct_totals))

    assert list(result.items()) == [
        ("AWS Lambda", 12.75),
        ("Amazon EC2", 11.50),
        ("Amazon RDS", 10.50),
        ("Amazon S3", 8.25),
        ("AWS CloudWatch", 3.15),
    ]


def test_summarize_spend_orders_totals_and_alphabetical_ties(
    spend_rows_with_equal_totals,
):
    result = summarize_spend(iter(spend_rows_with_equal_totals))

    assert list(result.items()) == [
        ("AWS CloudWatch", 8.00),
        ("AWS Lambda", 8.00),
        ("Amazon EC2", 8.00),
        ("Amazon RDS", 8.00),
        ("Amazon S3", 8.00),
    ]
