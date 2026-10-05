import pytest


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
