# `data/raw` folder

This folder is intended for **raw data** related to the company: dumps, exports, sample files, event samples, or untransformed datasets.

- **Main purpose**: serve as a landing zone or reference for original data before pipelines process it.
- **Recommendation**: document each dataset’s origin, format, expected size, privacy/PII considerations, and how it is versioned (ideally avoiding sensitive data in the repository).

> _Spanish version: [README.es.md](./README.es.md)._

## Generated contents (git-ignored)

- `prefect-results/` — cached results of the weekly pipeline's `transform-weekly-kpis` task (1-day expiration; safe
  to delete).
- `telemetry_YYYY-MM-DD.csv` — daily copy of `telemetry_events` (that UTC day's events) written by the nightly process
  [`scripts/nightly_export.py`](../../scripts/nightly_export.py). Audit/recovery backup only: no pipeline reads it.
  Never overwritten; contains user and session pseudonyms (not committed).
