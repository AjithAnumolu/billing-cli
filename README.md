# AWS Billing CSV Summarizer

A small command-line program that reads a CSV of AWS service costs, adds together the cost for each service, sorts services from highest to lowest spend, and prints the result plus a grand total.

It expects these CSV columns:

```csv
service,cost
```

- `service` must be non-empty.
- `cost` must be a number greater than or equal to zero.
- Repeated services are combined.
- Ties are ordered alphabetically by service name.

## Prerequisites

- Python 3.10 or later.
- [`uv`](https://docs.astral.sh/uv/) installed.

This project has no third-party runtime dependencies, but `uv` provides a repeatable way to create and run inside a virtual environment.

## Setup

From the directory that contains the package directory (the directory holding `cli.py`, `summarize.py`, and `models.py`):

```bash
uv venv
```

Activate the environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Create a sample input file named `billing.csv`:

```csv
service,cost
Amazon EC2,12.50
Amazon S3,3.25
Amazon EC2,7.50
AWS Lambda,1.20
```

> Replace `your_package` in the commands below with the package directory name that contains `cli.py`. For example, if the files are in `billing_summary/cli.py`, use `python -m billing_summary.cli`.

## Commands

### 1. Happy path: show every service

```bash
uv run python -m your_package.cli billing.csv
```

Expected stdout:

```text
{'Amazon EC2': 20.0, 'Amazon S3': 3.25, 'AWS Lambda': 1.2}
Total: $24.45 across 3 services
```

Expected exit code: `0`.

### 2. Show only the top 2 services

```bash
uv run python -m your_package.cli billing.csv --top 2
```

Expected stdout:

```text
{'Amazon EC2': 20.0, 'Amazon S3': 3.25}
Total: $24.45 across 3 services
```

`--top N` changes only the displayed service dictionary. The total still covers every valid row in the file.

Expected exit code: `0`.

### 3. Bad file: clean error on stderr

Create `bad-billing.csv` with a non-numeric cost:

```csv
service,cost
Amazon EC2,12.50
Amazon S3,not-a-number
```

Run:

```bash
uv run python -m your_package.cli bad-billing.csv
```

Expected stderr:

```text
Error: Row 3: invalid cost value 'not-a-number'
```

Expected stdout: no output.

Expected exit code: `1`.

You can verify the exit code immediately after running the command:

```bash
# macOS/Linux
 echo $?

# Windows PowerShell
$LASTEXITCODE
```

## Error behavior

The program writes expected input errors to stderr with an `Error:` prefix and exits with code `1`. This includes:

- A missing input file.
- Missing required `service` or `cost` CSV columns.
- A blank `cost` value.
- A non-numeric cost.
- An empty service name.
- A negative cost.
- A CSV with headers but no data rows.
- `--top` values less than 1.

Successful runs write the summary to stdout and exit with code `0`.

# Design Decisions

## Use a frozen, validated `SpendRow` instead of dictionaries

Each CSV row is converted into a frozen `SpendRow` at the program boundary rather than being passed around as a plain dictionary. This gives the summarization code a small, explicit contract: every row has a non-empty service name and a non-negative numeric cost. Making the dataclass frozen also prevents accidental changes after validation, so aggregation can operate on trustworthy, stable values. A dictionary would be more flexible, but it would allow missing keys, misspellings, and invalid values to survive further into the program, where failures are harder to diagnose.