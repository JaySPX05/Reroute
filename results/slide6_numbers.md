# Slide 6 - Verified Project Metrics

## Measurement rule

Only measured results are reported. Unavailable measurements are explicitly marked as not measured.

## 1. Planning Performance

Source: `results/timing.csv`
Command: `python -m scripts.measure_timing`
Runs: 5 per scenario.

| Scenario | Time to list affected orders | Time to ranked recovery plan |
|---|---:|---:|
| Smelter flood (S20, 8 days) | 17.9 ms | 72.8 ms |
| Chennai port closure (8 days) | 19.1 ms | 62.8 ms |
| Li-ion tariff increase (10% to 35%) | 16.0 ms | 133.6 ms |

These are ReRoute execution timings, not manual planning timings.

## 2. Detection Evaluation

Source: `results/eval_summary.md`
Evaluation: Rules-based detection on 20 labelled signals.
Generative AI Hub was not configured; LLM evaluation was skipped.

| Metric | Measured result |
|---|---:|
| Relevant vs. not relevant | 95% correct |
| Event type on real disruptions | 79% correct (11/14) |
| Supplier matching precision | 88% |
| Supplier matching recall | 82% |
| Median time per signal | 1 ms |

## 3. Delay Avoided Per Disruption

Source: `results/plan_comparison.csv`
Plan: Balanced.

| Scenario | Delay avoided |
|---|---|
| Hosur flood | 5 of 7 late order-days |
| Smelter flood (S20, 8 days) | 4 of 5 late order-days |
| Pune fire | 5 of 14 late order-days |
| Chennai port closure | 6 of 6 late order-days |
| Li-ion tariff increase | Rs 31.61 lakh of Rs 224.57 lakh in cost avoided |

## 4. Live Showcase Results

Source: `results/showcase_runs.md`
Environment: SQLite (local)
Date: 2026-11-01.

| Scenario | Messages | Autonomous actions | Human escalations |
|---|---:|---:|---:|
| Chennai port closure | 14 | 0 | 3 |
| Li-ion tariff spike | 14 | 5 | 9 |
| Tamil Nadu transport strike | 10 | 1 | 1 |
| Chained disruption | 66 | 6 | 12 |

The chained run produced 66 messages. The handbook's earlier figure of 42 is outdated.

## 5. Manual Baseline

Status: Not conducted.

Manual planning time, affected orders identified manually and manual recovery cost were not measured.

A quantitative manual-versus-automated comparison is therefore unavailable.

Source: `results/manual_baseline.md`.

## 6. Planner Acceptance

Status: Not conducted.

Human reviewer acceptance and rejection verdicts have not been measured.

Source: `results/planner_acceptance.md`.

## 7. Demo Scenario

Suggested measured example: Smelter flood (S20, 8 days).

- 4 purchase orders changed.
- Rs 1.28 lakh additional cost.
- 4 of 5 late order-days avoided.
- 2 of 2 high-priority customer orders kept on time.

Source: `results/plan_comparison.csv`.

Verify individual PO and supplier details against the application before presenting them.

## 8. Limitations

- The test data is synthetic.
- The manual baseline was not conducted.
- Human planner acceptance was not measured.
- LLM-assisted detection was not evaluated because Generative AI Hub was not configured.
- Showcase runs used SQLite local execution and offline explanation templates.

## 9. Sources

- `results/timing.csv`
- `results/eval_summary.md`
- `results/plan_comparison.csv`
- `results/showcase_runs.md`
- `results/manual_baseline.md`
- `results/planner_acceptance.md`