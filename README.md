# JobCheck

A screening aid for fraudulent job postings.
Paste the text of a job posting and JobCheck lists the common red flags it finds, with the matching phrases highlighted.

## Setup

Requires Python 3.9 or later.

```bash
./scripts/setup.sh
source .venv/bin/activate
flask --app app run --debug
```

Open http://127.0.0.1:5000. The SQLite database is created at `instance/jobcheck.db` on first run, and the app log is written to `logs/app.log`.

Set the `SECRET_KEY` environment variable for anything beyond local development; without it a random key is generated at each start, which invalidates open forms.

## JSON API

```bash
curl -X POST http://127.0.0.1:5000/api/check \
  -H "Content-Type: application/json" \
  -d '{"text": "Pay the registration fee of Rs 500 and message us on WhatsApp to start today."}'
```

Returns `201` with the check's `id`, `score`, `indicator`, `label` and `hits` (each with `rule_id`, `explanation`, `matched_text`, `start`, `end`), or `400` with `errors`. The text must be 50 to 10,000 characters after whitespace clean-up.

## Bulk Excel mode and URL input

`/bulk` takes an `.xlsx` file with a header row and one posting per row (up to 500) and returns the same workbook with result, score and red-flag columns, flagged rows highlighted, and a summary sheet.
The home page also accepts a link to a public posting; if the site blocks automated access or needs JavaScript, paste the text instead.

## Data and automation scripts

Run from the project root.

```bash
python scrape_pages.py                          # scrape permitted pages in scrapers/sources.txt
scripts/prototype_rules.sh [csv]                # candidate pattern hit rates, fraud vs genuine
python scripts/freeze_indian_split.py           # data/indian_labelled.csv -> data/processed/indian_{dev,test}.csv
scripts/backup.sh [keep]                        # timestamped database backup in backups/
scripts/rotate_logs.sh [max_kb] [keep]          # rotate logs/*.log above a size limit
.venv/bin/python -m scripts.monthly_report      # reports/report_YYYY-MM.xlsx for the previous month
scripts/nightly.sh                              # scrape, back up, rotate logs; monthly report on the 1st
```

Schedule the nightly job with `crontab -e`:

```
0 2 * * * /full/path/to/job_check/scripts/nightly.sh >> /full/path/to/job_check/logs/nightly.log 2>&1
```

## Tests

```bash
pytest
```

## Layout

```
app/        Flask app: routes, forms, models, templates
detector/   rule engine (rules.py)
scripts/    setup and automation shell scripts
tests/      pytest tests
data/       datasets (data/raw is not committed)
notebooks/  exploratory analysis and evaluation
reports/    generated charts and Excel reports
```
