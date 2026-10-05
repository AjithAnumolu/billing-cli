import pytest

from api.main import MAX_UPLOAD_BYTES


@pytest.mark.parametrize("top", ["0", "-1", "1.5", "not-a-number"])
def test_invalid_top_is_fastapi_422(client, valid_csv_bytes, top):
    response = client.post(
        f"/v1/billing/summarize?top={top}",
        files={"file": ("billing.csv", valid_csv_bytes, "text/csv")},
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["query", "top"]


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
