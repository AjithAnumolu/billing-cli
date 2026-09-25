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

## Setup

From the repository root, install the project environment and dependencies:

```bash
uv sync
```

Run the command-line application with:

```bash
uv run billing <csv-path>
```

Create a sample input file named `billing.csv`:

```csv
service,cost
Amazon EC2,12.50
Amazon S3,3.25
Amazon EC2,7.50
AWS Lambda,1.20
```

## Commands

### 1. Happy path: show every service

```bash
uv run billing billing.csv
```

Expected stdout:

```text
{'Amazon EC2': 20.0, 'Amazon S3': 3.25, 'AWS Lambda': 1.2}
Total: $24.45 across 3 services
```

Expected exit code: `0`.

### 2. Show only the top 2 services

```bash
uv run billing billing.csv --top 2
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
uv run billing bad-billing.csv
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