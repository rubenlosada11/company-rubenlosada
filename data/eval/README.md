# `data/eval` folder

This folder is for **evaluation and validation**: evaluation datasets, golden sets, experiment results, metrics, and artifacts used to measure quality for models, RAG, agents, or pipelines.

- **Main purpose**: centralize evaluation inputs and outputs so improvements stay measurable across project milestones.
- **Recommendation**: document each evaluation set (what it measures, how it was built, success criteria) and avoid sensitive data; use synthetic or anonymized data when needed.

> _Spanish version: [README.es.md](./README.es.md)._

## Generated contents (git-ignored)

- `weekly_performance/` — one JSON snapshot per weekly pipeline run (quality counts, warnings, changes and published
  rows), written by the optional `write-eval-snapshot` task. Configurable with `PIPELINE_EVAL_DIR`.
