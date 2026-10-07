from __future__ import annotations

import codecs
import csv
import io
import logging
from collections.abc import AsyncIterator
from pathlib import Path, PureWindowsPath
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api.schemas import BillingSummaryResponse, ServiceSpend
from billing.models import SpendRow
from billing.summarize import summarize_spend

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024

logger = logging.getLogger(__name__)

app = FastAPI(title="Billing Summary API", version="0.1.0")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    request.state.source_filename = None
    request.state.rows_parsed = 0
    request.state.error_code = None

    started = perf_counter()
    status_code = 500
    exception_info = None

    try:
        response = await call_next(request)
        status_code = response.status_code

        if status_code == 422 and request.state.error_code is None:
            request.state.error_code = "request_validation_error"

        response.headers["X-Request-ID"] = request.state.request_id
        return response

    except Exception as exc:
        request.state.error_code = "internal_error"
        exception_info = (type(exc), exc, exc.__traceback__)
        raise

    finally:
        level = (
            logging.ERROR
            if status_code >= 500
            else logging.WARNING
            if status_code >= 400
            else logging.INFO
        )

        fields = {
            "request_id": request.state.request_id,
            "method": request.method,
            "path": request.url.path,
            "source_filename": request.state.source_filename,
            "rows_parsed": request.state.rows_parsed,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "status_code": status_code,
        }

        if request.state.error_code is not None:
            fields["error_code"] = request.state.error_code

        logger.log(
            level,
            "request_completed",
            extra={"request_fields": fields},
            exc_info=exception_info,
        )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    request_id = request.state.request_id
    request.state.error_code = "request_validation_error"

    errors = [
        {
            "type": error["type"],
            "loc": list(error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "request_validation_error",
                "message": "Request validation failed.",
                "details": {
                    "request_id": request_id,
                    "errors": errors,
                },
            }
        },
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def handle_internal_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    request_id = request.state.request_id

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": {"request_id": request_id},
            }
        },
        headers={"X-Request-ID": request_id},
    )


class BillingCsvError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
        request_id: str | None = None,
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


async def parse_billing_csv(file: UploadFile, *, request: Request) -> list[SpendRow]:
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
                request.state.rows_parsed = len(rows)
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


def as_http_error(error: BillingCsvError, *, request_id: str) -> HTTPException:
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
                "details": {
                    **error.details,
                    "request_id": request_id,
                },
            }
        },
    )


def sanitize_filename(filename: str | None) -> str | None:
    if filename is None:
        return None
    return Path(PureWindowsPath(filename).name).name


@app.get("/healthz")
async def healthz(request: Request) -> dict[str, str]:
    return {"status": "ok", "request_id": request.state.request_id}


@app.post("/v1/billing/summarize", response_model=BillingSummaryResponse)
async def summarize_billing_csv(
    request: Request,
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

    request.state.source_filename = source_filename

    try:
        rows = await parse_billing_csv(file, request=request)
    except BillingCsvError as exc:
        request.state.error_code = exc.code
        raise as_http_error(exc, request_id=request.state.request_id) from exc
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
