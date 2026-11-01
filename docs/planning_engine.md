# Planning engine: how ReRoute decides what to do

Owner: [your name]. Files: reroute/impact.py, reroute/planner.py, scripts/compare_plans.py.
All data is synthetic. SAP IBP is represented by planner.py.

## What it does
For every late purchase order it considers three options:
- Wait: no extra cost, the delay stays.
- Expedite: saves 1 day, costs 8% of the PO value.
- Switch: move the order to another supplier with spare capacity. Cost is the
  price difference plus 2% for logistics and checks.

Each option is scored on cost, delay and customer service (lower is better).
Three weightings give three plans: Fastest recovery, Lowest cost, Balanced (recommended).
Spare capacity at alternate suppliers is shared by all late POs, so high-priority
customer orders are planned first.

## Why SO4501 is 2 days late (smelter flood, 8 days)
1. The Tier-2 smelter is down 8 days.
2. Tier-1 suppliers that buy from it are down 8 days minus their own aluminium stock:
   wheel maker 5 days, frame maker 3 days, Coimbatore backup 2 days.
3. A PO from a down supplier arrives the day after restart (PO 4500000007, frames: 4 days late).
4. The plant's safety stock absorbs part of the delay. The frames PO alone makes
   SO4501 1 day late; the casting order makes it 2 days late overall.

## Measured results (Balanced plan, python -m scripts.compare_plans)
| Scenario | POs changed | Extra cost | Late order-days avoided | High-priority on time |
|---|---|---|---|---|
| Hosur flood | 10 | Rs 2.72 lakh | 5 of 7 | 3 of 3 |
| Smelter flood (S20, 8 days) | 4 | Rs 1.28 lakh | 4 of 5 | 2 of 2 |
| Pune fire | 5 | Rs 3.92 lakh | 5 of 14 | 0 of 3 |
| Chennai port, 8 days | 3 | Rs 7.96 lakh | 6 of 6 | 2 of 2 |
| Li-ion tariff 10% to 35% | 14 | Rs 192.96 lakh | cost avoided Rs 31.61 lakh | n/a |

## Findings to explain
- Balanced vs Fastest (smelter): same 4 of 5 days avoided and 2 of 2 high-priority
  on time, Rs 1.28 lakh instead of Rs 2.18 lakh, 4 POs changed instead of 8.
- Chennai port: Balanced avoids all 6 late order-days for Rs 7.96 lakh; Fastest
  recovery spends Rs 30.33 lakh and avoids 5. [add the reason from scratch_out.txt]
- Pune fire: no plan protects the 3 high-priority orders (0 of 3). There is no
  alternative magnet supplier. This is the limit of replanning: the earlier we
  know, the more options exist.
- Tariff: all three plans are identical. Pune Battery Systems can take 14 of the
  40 battery orders, so every plan hits the same capacity limit. Cost avoided is
  Rs 31.61 lakh of Rs 224.57 lakh (about 14%).
- Hidden dependency: the Coimbatore backup buys 30% of its aluminium from the same
  flooded smelter, so it is slowed by 2 days. ReRoute still uses it, just later.

## What we have not measured
Detection accuracy on unseen signals, the manual-planner baseline, and planner acceptance.

## Likely judge questions
- Why not IBP? It is not on trial or practice systems; planner.py follows the same idea.
- Is the data real? No, it is synthetic, modelled on the Hosur, Chennai and Bengaluru belts.
- What if the AI is wrong? Numbers come from this code; the AI only explains them.