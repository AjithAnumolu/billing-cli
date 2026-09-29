import re
import sys

import pytest

from billing.cli import main, read_billing_rows


def test_main_prints_spend_summary(
    valid_billing_csv,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["billing-summary", str(valid_billing_csv)],
    )

    main()

    captured = capsys.readouterr()

    assert captured.out == (
        "{'Amazon EC2': 14.0, 'Amazon S3': 3.25}\nTotal: $17.25 across 2 services\n"
    )
    assert captured.err == ""


def test_main_prints_file_error_and_exits_one(
    tmp_path,
    monkeypatch,
    capsys,
):
    missing_file = tmp_path / "does-not-exist.csv"

    monkeypatch.setattr(
        sys,
        "argv",
        ["billing-summary", str(missing_file)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err.startswith("Error: [Errno 2]")
    assert str(missing_file) in captured.err


def test_main_prints_validation_error_and_exits_one(
    invalid_cost_csv,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["billing-summary", str(invalid_cost_csv)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        "Error: CSV line 2: cost: Input should be a valid number, "
        "unable to parse string as a number\n"
    )


def test_main_prints_top_n_list(
    top_n_billing_csv,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["billing-summary", str(top_n_billing_csv), "--top", "2"],
    )

    main()

    captured = capsys.readouterr()

    assert captured.out == (
        "{'Amazon S3': 15.85, 'Amazon EC2': 15.45}\nTotal: $42.60 across 5 services\n"
    )
    assert captured.err == ""


def test_main_prints_top_n_not_greater_than_zero(
    top_n_billing_csv,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["billing-summary", str(top_n_billing_csv), "--top", "0"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ("Error: --top must be a positive integer; received 0\n")


def test_main_prints_top_n_must_be_an_integer(
    top_n_billing_csv,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["cli", str(top_n_billing_csv), "--top", "abc"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        "usage: cli [-h] [--top N] csv_path\n"
        "cli: error: argument --top: invalid int value: 'abc'\n"
    )


def test_main_empty_rows_validation_error(
    header_only_billing_csv,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["cli", str(header_only_billing_csv), "--top", "2"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (f"Error: No data rows in {header_only_billing_csv}\n")


def test_read_billing_rows_missing_column(missing_cost_column_csv):
    expected = {"service", "cost"}
    found = {"service"}
    expected_message = (
        f"Missing columns: expected {sorted(expected)}, found {sorted(found)}"
    )

    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(missing_cost_column_csv))


def test_read_billing_rows_bad_cost(invalid_cost_csv):
    expected_message = (
        "CSV line 2: cost: Input should be a valid number, "
        "unable to parse string as a number"
    )

    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(invalid_cost_csv))


def test_read_billing_rows_wraps_negative_cost_validation_error(
    negative_cost_csv,
):
    expected_message = "CSV line 2: cost: Value error, cost must be >= 0"

    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(negative_cost_csv))


def test_read_billing_rows_wraps_empty_service_validation_error(
    blank_service_and_negative_cost_csv,
):
    expected_message = (
        "CSV line 2: service: Value error, service must be non-empty; "
        "cost: Value error, cost must be >= 0"
    )

    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(blank_service_and_negative_cost_csv))


def test_read_billing_rows_missing_cost_value_validation_error(
    missing_cost_value_csv,
):
    expected_message = "CSV line 2: cost: Input should be a valid number"

    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(missing_cost_value_csv))
