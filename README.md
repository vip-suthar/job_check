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
