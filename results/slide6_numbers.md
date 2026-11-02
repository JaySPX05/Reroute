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

Across these tested scenarios, ranked-plan execution was under 0.2 seconds. Execution time varies by machine and environment. These are ReRoute execution timings, not manual planning timings.

## 2. Detection Evaluation

Source: `results/eval_summary.md`  
Command: `python scripts/evaluate.py --signals data/heldout_signals.json --llm`, run once per model on 2 Nov 2026  
Evaluation: 20 held-out labelled signals (14 real disruptions, 6 irrelevant), written without seeing the detection rules and never used for tuning. Generative AI Hub via orchestration.

| Metric | Claude 4.5 Haiku (demo model) | gpt-4o-mini | Keyword rules (offline fallback) |
|---|---:|---:|---:|
| Relevant vs. not relevant | 95% correct | 100% correct | 95% correct |
| Event type on real disruptions | 93% correct (13/14) | 93% correct (13/14) | 79% correct (11/14) |
| Supplier matching precision | 96% | 97% | 88% |
| Supplier matching recall | 96% | 100% | 82% |
| Median time per signal | 1,436 ms | 2,288 ms | 3 ms |

On the slide: "Disruptions correctly detected: 13 of 14 event types, 96% of affected suppliers found (Claude 4.5 Haiku on SAP Generative AI Hub, 20 held-out signals; keyword rules: 11 of 14, 82%)."

For contrast, on the 26 practice signals the rules were tuned on (`python scripts/evaluate.py --llm`, gpt-4o-mini), the rules score 100% and the model 84% on event type. That is why the held-out score is the one reported.

## 3. Delay Avoided Per Disruption

Source: `results/plan_comparison.csv`  
Plan: Balanced.

| Scenario | Delay avoided |
|---|---|
| Hosur flood | 5 of 7 late order-days |
| Smelter flood (S20, 8 days) | 4 of 5 late order-days |
| Pune fire | 5 of 14 late order-days |
| Chennai port closure | 6 of 6 late order-days |
| Li-ion tariff increase | Remaining duty cost Rs 192.96 lakh; Rs 31.61 lakh avoided (of Rs 224.57 lakh) |

## 4. Live Showcase Results

Source: `results/showcase_runs.md`  
Environment: SQLite (local)  
Date: 2026-11-01.

| Scenario | Agent messages before approvals | Messages incl. approvals | Autonomous actions | Human escalations |
|---|---:|---:|---:|---:|
| Chennai port closure | 8 | 14 | 0 | 3 |
| Li-ion tariff spike | 24 | 42 | 5 | 9 |
| Tamil Nadu transport strike | 8 | 10 | 1 | 1 |
| Chained disruption | 42 | 66 | 6 | 12 |

On the slide, say "42 agent messages, 66 including the 12 human approvals" for the chained run. Both numbers are measured;
see the note in `showcase_runs.md` for how they were checked.

## 5. Manual Baseline

Status: Not conducted.

Manual planning time, affected orders identified manually and manual recovery cost were not measured. A quantitative manual-versus-automated comparison is therefore unavailable.

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

## 8. Limitations

- The test data is synthetic.
- The manual baseline was not conducted.
- Human planner acceptance was not measured.
- Detection was scored on 20 held-out signals, a small sample.
- Showcase runs used SQLite local execution and offline explanation templates.

## 9. Sources

- `results/timing.csv`
- `results/eval_summary.md`
- `results/plan_comparison.csv`
- `results/showcase_runs.md`
- `results/manual_baseline.md`
- `results/planner_acceptance.md`
