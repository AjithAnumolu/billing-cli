import csv
from collections.abc import Iterable

from .summarize import summarize_spend
from .models import SpendRow


def read_billing_rows(file_path: str) -> Iterable[SpendRow]:

    with open(file_path, "r", newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        expected = {"service", "cost"}
        found = set(reader.fieldnames or [])
        if not expected.issubset(found):
            raise ValueError(f"Missing columns: expected {sorted(expected)}, found {sorted(found)}")

        for line_number, row in enumerate(reader, start=2):
            service = str.strip(row["service"])
            raw_cost = row["cost"]

            try:
                cost = float(raw_cost)
                yield SpendRow(service, cost)
            except ValueError:
                raise ValueError(
                    f"Row {line_number}: invalid cost value {raw_cost!r}"
                ) from None

import sys

def main():
    try:
        rows = read_billing_rows(sys.argv[1])
        totals = summarize_spend(rows)
        print(totals)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)

if __name__ == "__main__":
    main()