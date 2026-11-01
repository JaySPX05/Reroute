# Slide 6 numbers

Rule: only measured numbers go on the slide. Every cell needs a source. Leave a cell blank rather than guess.

| Row on slide 6 | Manual baseline | ReRoute (measured) | Where it came from |
|---|---|---|---|
| Time to list affected orders | [from results/manual_baseline.md] | [median_ms_to_list_affected_orders in results/timing.csv] | stopwatch / `python -m scripts.measure_timing` |
| Time to a ranked recovery plan | [from results/manual_baseline.md] | [median_ms_to_ranked_plan in results/timing.csv] | stopwatch / `python -m scripts.measure_timing` |
| Disruptions correctly detected | n/a | [from results/eval_summary.md] | `python scripts/evaluate.py --signals data/heldout_signals.json --llm`, run once by the detection owner |
| Delay avoided per disruption | n/a | [see table below] | `python -m scripts.compare_plans` |
| Plans accepted by the planner | n/a | [X of Y verdicts, from results/planner_acceptance.md] | reviewer verdicts |

## Delay avoided per disruption (Balanced plan, measured)

Source: `results/plan_comparison.csv`, produced by `python -m scripts.compare_plans` on data generated 2026-10-31.

| Scenario | Late order-days avoided |
|---|---|
| Hosur flood | 5 of 7 |
| Smelter flood (S20, 8 days) | 4 of 5 |
| Pune fire | 5 of 14 |
| Chennai port closed, 8 days | 6 of 6 |
| Tariff (no delay; cost avoided instead) | Rs 31.61 lakh of Rs 224.57 lakh |

If the slide needs one average, state exactly how it was calculated (for example "mean of the four delay scenarios") and
check it by hand before it goes on the slide.

## Demo box on slide 6

The current box (a 5-day halt, 12 affected orders, shift 60% to Coimbatore, 4 days avoided) matches no output of the code.
Replace it with one real scenario from the table above, for example the smelter flood:
2 high-priority orders kept on time for Rs 1.28 lakh, 4 of 5 late order-days avoided.
Check the scenario's supplier and order counts against `python scratch_walkthrough.py` before putting them on the slide.

## Footnote (edit so it is true)

"Synthetic test bed: 19 suppliers, 8 disruption scenarios, 20 held-out signals. Manual baseline: one participant, one scenario."

Check each part before using it:
- 19 suppliers: `data/suppliers.csv` has 19 rows
- 8 disruption scenarios: the number `scripts/evaluate.py` actually runs
- 20 held-out signals: `data/heldout_signals.json` has 20 items

## Do not put on the slide

Emissions savings, percentage gains from real companies, or any figure not listed above.
