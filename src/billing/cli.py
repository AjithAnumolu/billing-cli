import argparse
import csv
import sys
from collections.abc import Iterator

from .models import SpendRow
from .summarize import summarize_spend


def read_billing_rows(file_path: str) -> Iterator[SpendRow]:

    with open(file_path, "r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        expected = {"service", "cost"}
        found = set(reader.fieldnames or [])
        if not expected.issubset(found):
            raise ValueError(
                f"Missing columns: expected {sorted(expected)}, found {sorted(found)}"
            )

        for line_number, row in enumerate(reader, start=2):
            raw_service = row["service"]
            raw_cost = row["cost"]

            if raw_cost is None or not raw_cost.strip():
                raise ValueError(f"CSV line {line_number}: missing 'cost' field")

            service = raw_service.strip()

            try:
                cost = float(raw_cost)
            except ValueError:
                raise ValueError(
                    f"Row {line_number}: invalid cost value {raw_cost!r}"
                ) from None
            try:
                yield SpendRow(service, cost)
            except ValueError as e:
                raise ValueError(f"Row {line_number}: {e}") from None


def main():
    try:
        parser = argparse.ArgumentParser(
            description="Summarize AWS billing CSV by service"
        )
        parser.add_argument("csv_path")
        args = parser.parse_args()
        rows = read_billing_rows(args.csv_path)
        totals = summarize_spend(rows)
        print(totals)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__": # pragma: no cover
    main()
