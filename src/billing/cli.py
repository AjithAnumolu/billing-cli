import argparse
import csv
import sys
from collections.abc import Iterator

from pydantic import ValidationError

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
            try:
                yield SpendRow.model_validate(
                    {
                        "service": row.get("service"),
                        "cost": row.get("cost"),
                    }
                )
            except ValidationError as exc:
                errors = "; ".join(
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors()
                )
                raise ValueError(f"CSV line {line_number}: {errors}") from None


def main():
    try:
        parser = argparse.ArgumentParser(
            description="Summarize AWS billing CSV by service"
        )
        parser.add_argument("csv_path")
        parser.add_argument(
            "--top",
            type=int,
            default=None,
            metavar="N",
            help="Show only the top N services by spend",
        )

        args = parser.parse_args()

        if args.top is not None and args.top <= 0:
            raise ValueError(f"--top must be a positive integer; received {args.top}")

        rows = read_billing_rows(args.csv_path)
        totals = summarize_spend(rows)

        if not totals:
            raise ValueError(f"No data rows in {args.csv_path}")

        if args.top is None:
            print(totals)
        else:
            print(dict(list(totals.items())[: args.top]))

        grand_total = sum(totals.values())
        service_count = len(totals)

        print(f"Total: ${grand_total:.2f} across {service_count} services")

    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
