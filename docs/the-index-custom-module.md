# The Index (Custom Module)

The Index is a private ForgeMarketing extension for ingesting external JSON form submissions, running AI-assisted analysis, and exposing report endpoints.

## Scope and isolation

- Module code is isolated under `custom_modules/the_index/`.
- Runtime activation is controlled by `ENABLE_THE_INDEX_MODULE` (default: `true`).
- API prefixes are `/api/the-index` (internal module tooling) and `/api/index-submissions` (public intake/reporting contract).

## Data model

- `the_index_submissions`: raw payload, normalized payload, AI analysis, flags, status.
- `the_index_report_snapshots`: optional persisted snapshots of generated reports.
- `the_index_survey_submissions`: firstcityfoundry.com survey submissions with answers/reporting/request metadata.

## Endpoints

- `GET /api/the-index/health`
- `POST /api/the-index/submissions`
- `POST /api/the-index/submissions/bulk`
- `GET /api/the-index/submissions`
- `GET /api/the-index/submissions/<id>`
- `POST /api/the-index/submissions/<id>/analyze`
- `POST /api/the-index/submissions/<id>/status`
- `GET /api/the-index/reports/overview`
- `GET /api/the-index/reports/daily-volume`
- `POST /api/the-index/reports/snapshots`
- `GET /api/the-index/reports/snapshots`

Public intake/reporting endpoints:

- `POST /api/index-submissions`
- `GET /api/index-submissions`
- `GET /api/index-submissions/summary`

Public endpoint behavior:

- CORS allowlist: `https://www.firstcityfoundry.com`, `https://firstcityfoundry.com`, and local preview origins.
- Payload max size: 512KB.
- String sanitization and JSON shape controls for `answers` and `reporting`.
- Basic POST rate limiting (per-client IP, in-memory).
- Request metadata stored with `client_ip` and `request_id`.
- Server logs include `request_id`, status, method/path, and latency.

Field-level contract and validation:

- For `source=first_city_foundry_index`, server enforces required fields, enum values, and conditional `other` companion fields.
- Deterministic scoring metadata is generated and stored under `request_meta.index_scoring`.
- Validation failures return HTTP 400 with `validation_errors` array.

JSON Schema reference:

- `docs/the-index-submission-schema.json`

## Quick test

```bash
curl -X POST "http://localhost:5000/api/the-index/submissions?analyze=true" \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "IDX-1001",
    "submission_type": "partner-intake",
    "name": "Alex Founder",
    "email": "alex@example.com",
    "company": "Example Labs",
    "title": "Looking for campaign support",
    "message": "Urgent launch support needed. Budget approved for partnership pilot.",
    "tags": ["launch", "partner", "budget"]
  }'
```

## AI analysis behavior

- Always runs a deterministic heuristic analysis.
- Optional Ollama enhancement can be enabled with:
  - `THE_INDEX_USE_OLLAMA=true`
  - `OLLAMA_HOST=http://localhost:11434`
  - `THE_INDEX_OLLAMA_MODEL=llama3.2:1b`

## Next integration step

Once your final form schema is available, update field mapping in:

- `custom_modules/the_index/service.py` function `normalize_submission_payload`

and add schema-level validation rules in:

- `custom_modules/the_index/index_submissions_api.py` endpoint `create_index_submission`
