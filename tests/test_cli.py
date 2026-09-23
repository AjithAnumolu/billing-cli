import csv
import re
import sys

import pytest

from billing.cli import main, read_billing_rows


def test_main_prints_spend_summary(tmp_path, monkeypatch, capsys):
    test_file = tmp_path / "billing.csv"

    with test_file.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(
            [
                ["service", "cost"],
                ["Amazon EC2", "12.00"],
                ["Amazon S3", "3.25"],
                ["Amazon EC2", "2.00"],
            ]
        )

    monkeypatch.setattr(
        sys,
        "argv",
        ["billing-summary", str(test_file)],
    )

    main()

    captured = capsys.readouterr()

    assert captured.out == ("{'Amazon EC2': 14.0, 'Amazon S3': 3.25}\n")
    assert captured.err == ""


def test_main_prints_file_error_and_exits_one(tmp_path, monkeypatch, capsys):
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
    tmp_path,
    monkeypatch,
    capsys,
):
    test_file = tmp_path / "bad_billing.csv"
    test_file.write_text(
        "service,cost\nAmazon EC2,not-a-number\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["billing-summary", str(test_file)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ("Error: Row 2: invalid cost value 'not-a-number'\n")


def test_read_billing_rows_missing_column(tmp_path):
    test_file = tmp_path / "test.csv"
    data = [["service"], ["Amazon EC2", 8.00], ["Amazon S3", 3.25]]

    with open(test_file, mode="w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(data)

    assert test_file.exists()
    expected = {"service", "cost"}
    found = {"service"}
    expected_message = (
        f"Missing columns: expected {sorted(expected)}, found {sorted(found)}"
    )
    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(test_file))


def test_read_billing_rows_bad_cost(tmp_path):
    test_file = tmp_path / "test.csv"
    data = [["service", "cost"], ["Amazon EC2", "not-a-number"], ["Amazon S3", 3.25]]

    with open(test_file, mode="w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(data)

    assert test_file.exists()
    expected_message = "Row 2: invalid cost value 'not-a-number'"
    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(test_file))


def test_read_billing_rows_wraps_negative_cost_validation_error(tmp_path):
    test_file = tmp_path / "negative_cost.csv"
    data = [["service", "cost"], ["Amazon S3", -3.25]]

    with open(test_file, mode="w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(data)

    assert test_file.exists()
    expected_message = "Row 2: cost must be >= 0"
    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(test_file))


def test_read_billing_rows_wraps_empty_service_validation_error(tmp_path):
    test_file = tmp_path / "blank_service.csv"
    data = [["service", "cost"], ["  ", -3.25]]

    with open(test_file, mode="w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(data)

    assert test_file.exists()
    expected_message = "Row 2: service must be non-empty"
    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(test_file))


def test_read_billing_rows_missing_cost_value_validation_error(tmp_path):
    test_file = tmp_path / "none_cost.csv"
    data = [["service", "cost"], ["Amazon EC2"]]

    with open(test_file, mode="w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(data)

    assert test_file.exists()
    expected_message = "CSV line 2: missing 'cost' field"
    with pytest.raises(ValueError, match=re.escape(expected_message)):
        list(read_billing_rows(test_file))
