import json
import logging
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api.main import MAX_UPLOAD_BYTES, app


def assert_uuid4(value: str) -> None:
    parsed = UUID(value)
    assert parsed.version == 4
    assert str(parsed) == value


def test_healthz_has_request_id(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "request_id": response.headers["X-Request-ID"],
    }
    assert_uuid4(response.headers["X-Request-ID"])


def test_each_request_gets_a_new_id(client):
    first = client.get("/healthz")
    second = client.get("/healthz")

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_validation_error_has_request_id(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize?top=0",
        files={
            "file": ("billing.csv", valid_csv_bytes, "text/csv"),
        },
    )

    assert response.status_code == 422
    assert_uuid4(response.headers["X-Request-ID"])


def test_internal_error_correlates_response_and_traceback(
    monkeypatch,
    caplog,
    valid_csv_bytes,
):
    def fail_aggregation(rows):
        raise RuntimeError("simulated aggregation failure")

    monkeypatch.setattr(
        "api.main.summarize_spend",
        fail_aggregation,
    )

    with (
        caplog.at_level(logging.ERROR, logger="api.main"),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post(
            "/v1/billing/summarize",
            files={
                "file": (
                    "billing.csv",
                    valid_csv_bytes,
                    "text/csv",
                )
            },
        )

    assert response.status_code == 500

    request_id = response.headers["X-Request-ID"]
    assert_uuid4(request_id)

    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "details": {
                "request_id": request_id,
            },
        }
    }

    matching_records = [
        record
        for record in caplog.records
        if getattr(record, "request_fields", {}).get("request_id") == request_id
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert record.levelno == logging.ERROR
    assert record.request_fields["status_code"] == 500
    assert record.request_fields["error_code"] == "internal_error"
    assert record.exc_info is not None
    assert "simulated aggregation failure" in caplog.text


@pytest.mark.parametrize("top", ["0", "-1", "1.5", "not-a-number"])
def test_invalid_top_returns_validation_envelope(
    client,
    valid_csv_bytes,
    top,
):
    response = client.post(
        f"/v1/billing/summarize?top={top}",
        files={
            "file": ("billing.csv", valid_csv_bytes, "text/csv"),
        },
    )

    assert response.status_code == 422

    error = response.json()["error"]
    assert error["code"] == "request_validation_error"
    assert error["message"] == "Request validation failed."

    details = error["details"]
    assert details["request_id"] == response.headers["X-Request-ID"]
    assert_uuid4(details["request_id"])
    assert details["errors"][0]["loc"] == ["query", "top"]


def test_missing_file_returns_validation_envelope(client, caplog):
    with caplog.at_level(logging.WARNING, logger="api.main"):
        response = client.post("/v1/billing/summarize")

    assert response.status_code == 422

    error = response.json()["error"]
    assert error["code"] == "request_validation_error"

    details = error["details"]
    assert details["request_id"] == response.headers["X-Request-ID"]
    assert_uuid4(details["request_id"])
    assert any(
        item["loc"] == ["body", "file"] and item["type"] == "missing"
        for item in details["errors"]
    )

    record = request_record(caplog, response)
    assert record.levelno == logging.WARNING
    assert record.request_fields["status_code"] == 422
    assert record.request_fields["error_code"] == "request_validation_error"
    assert record.request_fields["rows_parsed"] == 0
    assert record.request_fields["source_filename"] is None


def test_top_is_optional_and_limits_ranked_results(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize?top=1",
        files={"file": ("billing.csv", valid_csv_bytes, "text/csv")},
    )

    assert response.status_code == 200
    assert len(response.json()["services"]) == 1


def test_summarize_csv(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "billing.csv",
                valid_csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "services": [
            {"service": "Amazon EC2", "cost": 12.5},
            {"service": "Amazon S3", "cost": 3.25},
        ],
        "grand_total": 15.75,
        "service_count": 2,
        "source_filename": "billing.csv",
    }


def test_source_filename_is_sanitized(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "../../sensitive-path/billing.csv",
                valid_csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["source_filename"] == "billing.csv"


def test_source_filename_strips_windows_path(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                r"C:\Users\ajith\Downloads\billing.csv",
                valid_csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["source_filename"] == "billing.csv"


def test_rejects_upload_larger_than_10_mib(client):
    csv_bytes = b"a" * (MAX_UPLOAD_BYTES + 1)

    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "too-large.csv",
                csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 413

    body = response.json()
    assert body["detail"]["error"]["code"] == "file_too_large"
    assert body["detail"]["error"]["details"]["limit_bytes"] == MAX_UPLOAD_BYTES


def test_rejects_non_utf8_csv(client):
    # \x96 is invalid as an independent UTF-8 byte.
    csv_bytes = b"service,cost\nAmazon\x96S3,3.25\n"

    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "invalid-encoding.csv",
                csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 400

    body = response.json()
    assert body["detail"]["error"]["code"] == "invalid_text_encoding"
    assert body["detail"]["error"]["details"]["expected_encoding"] == "utf-8"
    assert isinstance(body["detail"]["error"]["details"]["byte_offset"], int)


def test_accepts_utf8_bom(client):
    csv_bytes = b"\xef\xbb\xbfservice,cost\nAmazon S3,3.25\n"

    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "bom.csv",
                csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["services"] == [{"service": "Amazon S3", "cost": 3.25}]


def test_rejects_csv_missing_cost_column(client):
    csv_bytes = b"service\nAmazon S3\n"

    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "missing-cost.csv",
                csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 400

    body = response.json()
    assert body["detail"]["error"] == {
        "code": "missing_required_columns",
        "message": "CSV must contain service and cost columns.",
        "details": {
            "expected_columns": ["cost", "service"],
            "found_columns": ["service"],
            "request_id": response.headers["X-Request-ID"],
        },
    }


def test_rejects_negative_cost_row(client):
    csv_bytes = b"service,cost\nAmazon S3,-1.00\n"

    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "negative-cost.csv",
                csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 422

    body = response.json()
    error = body["detail"]["error"]

    assert error["code"] == "invalid_csv_row"
    assert error["message"] == "CSV validation failed."
    assert error["details"]["line"] == 2
    assert error["details"]["errors"][0]["field"] == "cost"


def test_rejects_header_only_csv(client):
    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "empty.csv",
                b"service,cost\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "empty_csv"


def test_rejects_malformed_csv(client):
    csv_bytes = b'service,cost\n"Amazon S3,3.25\n'

    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "malformed.csv",
                csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "invalid_csv_row"


def test_returns_source_filename(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "billing.csv",
                valid_csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["source_filename"] == "billing.csv"


def test_sanitizes_source_filename(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                "../../private/billing.csv",
                valid_csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["source_filename"] == "billing.csv"


def test_sanitizes_windows_source_filename(client, valid_csv_bytes):
    response = client.post(
        "/v1/billing/summarize",
        files={
            "file": (
                r"C:\Users\ajith\Downloads\billing.csv",
                valid_csv_bytes,
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["source_filename"] == "billing.csv"


def request_record(caplog, response):
    request_id = response.headers["X-Request-ID"]
    records = [
        record
        for record in caplog.records
        if getattr(record, "request_fields", {}).get("request_id") == request_id
    ]
    assert len(records) == 1
    return records[0]


def test_success_logs_request_metadata(client, valid_csv_bytes, caplog):
    with caplog.at_level(logging.INFO, logger="api.main"):
        response = client.post(
            "/v1/billing/summarize?top=1",
            files={"file": ("../../private/billing.csv", valid_csv_bytes, "text/csv")},
        )
    assert response.status_code == 200
    record = request_record(caplog, response)
    fields = record.request_fields
    assert record.levelno == logging.INFO
    assert fields["method"] == "POST"
    assert fields["path"] == "/v1/billing/summarize"
    assert fields["source_filename"] == "billing.csv"
    assert fields["rows_parsed"] == 3
    assert fields["status_code"] == 200
    assert fields["duration_ms"] >= 0
    assert "error_code" not in fields


def test_validation_error_logs_warning(client, valid_csv_bytes, caplog):
    with caplog.at_level(logging.WARNING, logger="api.main"):
        response = client.post(
            "/v1/billing/summarize?top=0",
            files={"file": ("billing.csv", valid_csv_bytes, "text/csv")},
        )
    assert response.status_code == 422
    record = request_record(caplog, response)
    assert record.levelno == logging.WARNING
    assert record.request_fields["error_code"] == "request_validation_error"
    assert record.request_fields["source_filename"] is None
    assert record.request_fields["rows_parsed"] == 0


def test_csv_error_logs_warning_and_correlates_id(client, caplog):
    with caplog.at_level(logging.WARNING, logger="api.main"):
        response = client.post(
            "/v1/billing/summarize",
            files={
                "file": ("billing.csv", b"service,cost\nAmazon S3,-1\n", "text/csv")
            },
        )
    assert response.status_code == 422
    record = request_record(caplog, response)
    assert record.levelno == logging.WARNING
    assert record.request_fields["error_code"] == "invalid_csv_row"
    assert (
        response.json()["detail"]["error"]["details"]["request_id"]
        == record.request_fields["request_id"]
    )


def test_json_formatter_outputs_one_line_with_traceback():
    from api.logging_config import JsonFormatter

    try:
        raise RuntimeError("simulated failure")
    except RuntimeError as exc:
        record = logging.LogRecord(
            "api.main",
            logging.ERROR,
            __file__,
            1,
            "request_completed",
            (),
            (type(exc), exc, exc.__traceback__),
        )
    record.request_fields = {"request_id": "test-id", "status_code": 500}
    output = JsonFormatter().format(record)
    assert len(output.splitlines()) == 1
    payload = json.loads(output)
    assert payload["request_id"] == "test-id"
    assert payload["status_code"] == 500
    assert "RuntimeError: simulated failure" in payload["traceback"]
