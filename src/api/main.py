from __future__ import annotations

import codecs
import csv
import io
from collections.abc import AsyncIterator
from pathlib import Path, PureWindowsPath
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError

from api.schemas import BillingSummaryResponse, ServiceSpend
from billing.models import SpendRow
from billing.summarize import summarize_spend

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024

app = FastAPI(title="Billing Summary API", version="0.1.0")


class BillingCsvError(Exception):
    def __init__(
        self, code: str, message: str, details: dict[str, object] | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


async def iter_upload_bytes(file: UploadFile) -> AsyncIterator[bytes]:
    total = 0
    while chunk := await file.read(READ_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise BillingCsvError(
                "file_too_large",
                "Uploaded CSV must not exceed 10 MiB.",
                {"limit_bytes": MAX_UPLOAD_BYTES},
            )
        yield chunk


async def read_utf8_csv(file: UploadFile) -> str:
    decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
    parts: list[str] = []
    bytes_seen = 0

    try:
        async for chunk in iter_upload_bytes(file):
            try:
                parts.append(decoder.decode(chunk))
            except UnicodeDecodeError as exc:
                raise BillingCsvError(
                    "invalid_text_encoding",
                    "CSV must be UTF-8 encoded.",
                    {
                        "expected_encoding": "utf-8",
                        "byte_offset": bytes_seen + exc.start,
                    },
                ) from exc
            bytes_seen += len(chunk)
        parts.append(decoder.decode(b"", final=True))
    except UnicodeDecodeError as exc:
        raise BillingCsvError(
            "invalid_text_encoding",
            "CSV must be UTF-8 encoded.",
            {"expected_encoding": "utf-8", "byte_offset": bytes_seen + exc.start},
        ) from exc

    return "".join(parts)


async def parse_billing_csv(file: UploadFile) -> list[SpendRow]:
    text = await read_utf8_csv(file)

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        expected = {"service", "cost"}
        found = set(reader.fieldnames or [])
        if not expected.issubset(found):
            raise BillingCsvError(
                "missing_required_columns",
                "CSV must contain service and cost columns.",
                {"expected_columns": sorted(expected), "found_columns": sorted(found)},
            )

        rows: list[SpendRow] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                rows.append(
                    SpendRow.model_validate(
                        {"service": row.get("service"), "cost": row.get("cost")}
                    )
                )
            except ValidationError as exc:
                errors = [
                    {
                        "field": ".".join(str(part) for part in error["loc"]),
                        "message": error["msg"],
                    }
                    for error in exc.errors()
                ]
                raise BillingCsvError(
                    "invalid_csv_row",
                    "CSV validation failed.",
                    {"line": line_number, "errors": errors},
                ) from exc
    except csv.Error as exc:
        raise BillingCsvError("malformed_csv", "CSV could not be parsed.") from exc

    if not rows:
        raise BillingCsvError("empty_csv", "CSV must contain at least one data row.")

    return rows


def as_http_error(error: BillingCsvError) -> HTTPException:
    status_code = {
        "file_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
        "invalid_csv_row": status.HTTP_422_UNPROCESSABLE_CONTENT,
    }.get(error.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        },
    )


def sanitize_filename(filename: str | None) -> str | None:
    if filename is None:
        return None
    return Path(PureWindowsPath(filename).name).name


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/billing/summarize", response_model=BillingSummaryResponse)
async def summarize_billing_csv(
    file: Annotated[
        UploadFile,
        File(description="UTF-8 billing CSV with service and cost columns"),
    ],
    top: Annotated[
        int | None,
        Query(gt=0, description="Return only the top N services"),
    ] = None,
) -> BillingSummaryResponse:
    if file.filename is None:  # pragma: no cover
        source_filename = None
    else:
        source_filename = sanitize_filename(file.filename)

    try:
        rows = await parse_billing_csv(file)
    except BillingCsvError as exc:
        raise as_http_error(exc) from exc
    finally:
        await file.close()

    totals = summarize_spend(iter(rows))
    displayed = list(totals.items())[:top] if top is not None else list(totals.items())
    services = [ServiceSpend(service=service, cost=cost) for service, cost in displayed]

    return BillingSummaryResponse(
        services=services,
        grand_total=sum(item.cost for item in services),
        service_count=len(services),
        source_filename=source_filename,
    )
