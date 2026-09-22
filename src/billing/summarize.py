from collections.abc import Iterable
from .models import SpendRow

def summarize_spend(rows: Iterable[SpendRow]) -> dict[str, float]:
    totals: dict[str, float] = {}

    for row in rows:
        totals[row.service] = totals.get(row.service, 0.0) + row.cost

    return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))