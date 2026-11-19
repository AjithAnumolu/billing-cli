# AWS Billing CSV Summarizer

[![CI](https://github.com/AjithAnumolu/billing-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/AjithAnumolu/billing-cli/actions/workflows/ci.yml)

A CLI and a FastAPI service that read a CSV of AWS service costs, aggregate spend by service, and return services from highest to lowest spend with the grand total.

The input CSV must include these columns:
```csv
service,cost
```

The application:

- Strips leading and trailing whitespace from service names.
- Requires `service` to be non-empty after trimming whitespace.
- Parses `cost` as a number.
- Requires `cost` to be greater than or equal to zero.
- Combines repeated service names.
- Sorts services by descending total cost.
- Uses alphabetical service-name ordering to break equal-cost ties.
- Prints the overall total and count of distinct services, even when `--top` limits the displayed services.

## Quickstart

```bash
git clone https://github.com/AjithAnumolu/billing-cli
cd billing-cli
uv sync
uv run pytest                                   # 44 tests
uv run uvicorn api.main:app --port 8000         # API on http://localhost:8000
```

## Setup

From the repository root, install the project environment and dependencies:

```bash
uv sync
```

Run the application with:

```bash
uv run billing <csv-path>
```

Create a sample file named `billing.csv`:

```csv
service,cost
Amazon EC2,12.50
Amazon S3,3.25
Amazon EC2,7.50
AWS Lambda,1.20
```

## Commands

### Show all services

```bash
uv run billing billing.csv
```

Expected output:

```text
{'Amazon EC2': 20.0, 'Amazon S3': 3.25, 'AWS Lambda': 1.2}
Total: $24.45 across 3 services
```

The command writes the summary to stdout and exits with code `0`.

### Show only the top services

Use `--top N` to limit the displayed service dictionary:

```bash
uv run billing billing.csv --top 2
```

For example, given this input:

```csv
service,cost
Amazon EC2,12.50
Amazon S3,3.25
AWS Lambda,0.75
Amazon EC2,1.75
Amazon RDS,8.40
Amazon S3,0.60
AWS CloudWatch,2.15
Amazon EC2,1.20
Amazon S3,3.00
  Amazon S3  ,9.00
```

The output is:

```text
{'Amazon S3': 15.85, 'Amazon EC2': 15.45}
Total: $42.60 across 5 services
```

Whitespace around a service name is removed before aggregation, so `Amazon S3` and `  Amazon S3  ` are treated as the same service.

`--top N` affects only the displayed dictionary. The grand total and service count always include all valid rows.

The command exits with code `0` on success.

## Validation and errors

Expected input and validation errors are written to stderr with an `Error:` prefix and exit with code `1`.

### Missing file

```bash
uv run billing does-not-exist.csv
```

The error begins with the operating-system file error, for example:

```text
Error: [Errno 2] No such file or directory: 'does-not-exist.csv'
```

### Missing required column

A CSV missing either `service` or `cost` is rejected.

For example:

```csv
service
Amazon EC2
Amazon S3
```

Produces an error equivalent to:

```text
Error: Missing columns: expected ['cost', 'service'], found ['service']
```

### Invalid numeric cost

```csv
service,cost
Amazon EC2,not-a-number
```

Produces:

```text
Error: CSV line 2: cost: Input should be a valid number, unable to parse string as a number
```

### Missing cost value

```csv
service,cost
Amazon EC2
```

Produces an error beginning with:

```text
Error: CSV line 2: cost: Input should be a valid number
```

### Empty service name

A service containing only whitespace is invalid:

```csv
service,cost
   ,3.25
```

The error includes:

```text
Error: CSV line 2: service: Value error, service must be non-empty
```

If the same row has multiple invalid fields, the application reports each validation failure. For example:

```csv
service,cost
   ,-3.25
```

Produces:

```text
Error: CSV line 2: service: Value error, service must be non-empty; cost: Value error, cost must be >= 0
```

### Negative cost

```csv
service,cost
Amazon S3,-3.25
```

Produces:

```text
Error: CSV line 2: cost: Value error, cost must be >= 0
```

### CSV with headers but no data rows

```csv
service,cost
```

Produces:

```text
Error: No data rows in billing.csv
```

### Invalid `--top` value

`--top` must be a positive integer.

A value of zero or less is handled as an application error:

```bash
uv run billing billing.csv --top 0
```

```text
Error: --top must be a positive integer; received 0
```

This exits with code `1`.

A non-integer value is rejected by the command-line argument parser:

```bash
uv run billing billing.csv --top abc
```

The exact usage text varies with the executable name used to launch the program, but it follows this form:

```text
usage: billing [-h] [--top N] csv_path
billing: error: argument --top: invalid int value: 'abc'
```

This exits with code `2`.

## API

### `GET /healthz`

```json
{ "status": "ok", "request_id": "3f6b2a1e-9c4d-4e8a-b5f1-2d7c0a9e6f31" }
```

The same request ID is returned in the `X-Request-ID` response header.

### `POST /v1/billing/summarize`

Upload the CSV as `multipart/form-data` with field `file`. Optional query param `top` limits the displayed rows.

```bash
curl -X POST "http://localhost:8000/v1/billing/summarize?top=2" \
  -F "file=@billing.csv"
```

```json
{
  "services": [
    { "service": "Amazon EC2", "cost": 17.0 },
    { "service": "Amazon S3", "cost": 3.25 }
  ],
  "grand_total": 20.25,
  "service_count": 2,
  "source_filename": "billing.csv"
}
```

Errors use one envelope, `{"error": {"code", "message", "details"}}`, with the request ID in `details`. Codes: `missing_required_columns`, `empty_csv`, `malformed_csv`, `invalid_text_encoding` (400); `file_too_large` (413, 10 MiB limit); `invalid_csv_row` and `request_validation_error` (422); `internal_error` (500, traceback in the server log only). An invalid row fails the whole request — never a partial summary.

Note: unlike the CLI, the API's `grand_total` and `service_count` are scoped to the `top` rows displayed, not the whole file.

## Docker

```bash
docker build -t billing-api:local .
docker run -d --name billing --restart unless-stopped -p 8000:8000 billing-api:local
```

Image: 290 MB on disk, 73.5 MB of content (the rest is the shared `python:3.12-slim` base). Multi-stage build with uv layer caching, non-root `appuser`, and a urllib-based `HEALTHCHECK` on `/healthz` (the slim image has no curl). Restart policy is `--restart unless-stopped`; the drill is killing the process inside the container (`docker exec billing sh -c 'kill -9 1'`) — `docker kill` is treated as an explicit stop and never triggers a restart.

## Exit codes

| Situation | Output stream | Exit code |
|---|---:|---:|
| Successful summary | stdout | `0` |
| Missing file, invalid CSV columns, invalid row values, empty input data, or `--top < 1` | stderr | `1` |
| Invalid command-line syntax, including a non-integer `--top` value | stderr | `2` |

On validation failures, the application does not write a partial summary to stdout.

## Design decisions

### Validate rows at the CSV boundary

Each CSV row is converted to a validated `SpendRow` model as it is read. This keeps invalid input from entering aggregation code and gives the rest of the application a clear contract:

- `service` is a trimmed, non-empty string.
- `cost` is a parsed numeric value.
- `cost` is non-negative.

The model can report multiple invalid fields from a single CSV row. For example, an empty service and negative cost are returned together in the line-specific error message rather than failing one field at a time.

### Preserve source line numbers

CSV data begins on line 2 because line 1 contains the header. Validation errors include that source line number, making malformed billing records easy to find and correct.

### Aggregate normalized service names

Service names are normalized by trimming surrounding whitespace before aggregation. This prevents accidental duplicate totals when a source CSV contains values such as `Amazon S3` and `  Amazon S3  `.

### Keep totals independent of `--top`

The program aggregates all valid billing rows before applying `--top`. Therefore, limiting displayed services does not change the grand total or the number of distinct services.

## Tests and CI

```bash
uv run pytest                  # 44 tests
uv run ruff check . && uv run ruff format --check .
```

GitHub Actions runs lint, tests (`--cov=billing --cov-fail-under=100`), and a Docker build on every push and pull request.
