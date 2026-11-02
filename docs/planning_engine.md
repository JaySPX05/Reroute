# Planning engine: how ReRoute decides what to do

Owner: Kavana  
Files: `reroute/impact.py` (trace), `reroute/planner.py` (simulate and rank), `scripts/compare_plans.py` (results)

All data is synthetic. SAP IBP is represented by `planner.py`.

## 1. What it does

For every late or costlier purchase order (PO), the planner considers three options:

| Option | What it means | Cost in the model |
|---|---|---|
| Wait | Keep the order and accept the delay | No extra cost after a disruption. After a tariff, waiting means paying the higher duty. |
| Expedite | Same supplier ships express after restart | Saves 1 day, costs 8% of the PO value |
| Switch | Move the whole order to another supplier with spare capacity | Price difference plus 2% of the PO value (logistics and checks); arrives after that supplier's lead time |

Each option is scored on cost, delay and customer service (lower is better). Three sets of weights give three plans:

| Plan | Cost | Delay | Service |
|---|---|---|---|
| Fastest recovery | 0.10 | 0.55 | 0.35 |
| Lowest cost | 0.65 | 0.15 | 0.20 |
| Balanced (recommended) | 0.25 | 0.40 | 0.35 |

The Balanced weights are set in `reroute/config.py` by judgement. They were not tuned against the results.

Two rules in the scoring matter when explaining results:

- Spare capacity at alternate suppliers is shared by all late POs, so the order of planning matters. For delay events, high-priority customer orders are planned first. For a tariff (nothing is late), orders with the latest due dates are planned first.
- A delay that plant stock absorbs is worth only 10% of a delay that reaches a customer, so the planner does not pay to fix delays customers will never feel.

## 2. How the tracing works (`impact.py`)

1. A supplier hit directly is down for the event's duration.
2. Downtime travels up the tiers. A Tier-1 supplier that buys from a down Tier-2 supplier is down for (child downtime minus its own `buffer_days`). If the Tier-2 supplier provides less than 50% of that input, the result is multiplied by that share and rounded up.
3. A PO from a down supplier arrives the day after the supplier restarts. Delay is new arrival minus due date.
4. A customer order is late by the largest PO delay among its materials, minus the days of stock the plant holds for that material (`plant_cover_days`).

Note that there are two different stocks: supplier `buffer_days` (rule 2) and plant `plant_cover_days` (rule 4).

## 3. Why SO4501 is 2 days late (smelter flood, 8 days)

1. The Tier-2 smelter (S20) is down 8 days.
2. Tier-1 suppliers that buy from it are down: wheel maker 5 days, frame maker 3 days, Coimbatore backup 2 days (it buys 30% of its aluminium from the smelter, so its downtime is scaled down).
3. PO 4500000007 (150 chassis frames) arrives 4 days late.
4. Plant stock absorbs part of the delay. The frames PO alone makes SO4501 1 day late; the casting order makes it 2 days late overall.

## 4. Measured results

Produced with `python -m scripts.compare_plans`. Dataset snapshot date: 2026-10-29, according to `data/meta.csv`. Detection for this comparison is rule-based (`use_llm=False`).

### Balanced plan (the recommended plan)

| Scenario | POs changed | Extra cost | Late order-days avoided | High-priority on time |
|---|---:|---:|---|---|
| Hosur flood (news) | 10 | Rs 2.72 lakh | 5 of 7 | 3 of 3 |
| Smelter flood (S20, 8 days) | 4 | Rs 1.28 lakh | 4 of 5 | 2 of 2 |
| Pune fire (news) | 5 | Rs 3.92 lakh | 5 of 14 | 0 of 3 |
| Chennai port closed, 8 days | 3 | Rs 7.96 lakh | 6 of 6 | 2 of 2 |
| Li-ion tariff 10% to 35% | 14 | Remaining duty cost Rs 192.96 lakh; Rs 31.61 lakh avoided | n/a | n/a |

### All three plans

| Scenario | Plan | POs changed | Extra cost | Late order-days avoided | High-priority on time |
|---|---|---:|---:|---|---|
| Smelter flood | Fastest recovery | 8 | Rs 2.18 lakh | 4 of 5 | 2 of 2 |
| Smelter flood | Lowest cost | 0 | Rs 0 | 0 of 5 | 0 of 2 |
| Smelter flood | Balanced | 4 | Rs 1.28 lakh | 4 of 5 | 2 of 2 |
| Pune fire | Fastest recovery | 8 | Rs 6.41 lakh | 5 of 14 | 0 of 3 |
| Pune fire | Lowest cost | 0 | Rs 0 | 0 of 14 | 0 of 3 |
| Pune fire | Balanced | 5 | Rs 3.92 lakh | 5 of 14 | 0 of 3 |
| Chennai port | Fastest recovery | 8 | Rs 30.33 lakh | 5 of 6 | 2 of 2 |
| Chennai port | Lowest cost | 2 | Rs 2.77 lakh | 4 of 6 | 2 of 2 |
| Chennai port | Balanced | 3 | Rs 7.96 lakh | 6 of 6 | 2 of 2 |
| Li-ion tariff | All three plans | 14 | Remaining duty cost Rs 192.96 lakh; Rs 31.61 lakh avoided | n/a | n/a |

## 5. What the results show

- **Smelter flood:** Balanced matches Fastest recovery on outcome (4 of 5 order-days, both high-priority orders on time) for Rs 1.28 lakh instead of Rs 2.18 lakh, with 4 POs changed instead of 8.
- **Chennai port:** Balanced avoids all 6 late order-days for Rs 7.96 lakh. Fastest recovery spends Rs 30.33 lakh and avoids only 5. Why: Pune Battery Systems has 600 units of spare capacity for one week, shared by all late POs, and high-priority POs are planned first. Fastest switched high-priority PO 4500000029 (400 units) even though plant stock already absorbed its delay, which left too little capacity for Medium PO 4500000005 (300 units). That order was expedited instead and stayed 1 day late. Fastest also spent Rs 5.16 lakh expediting PO 4500000069 for a 1-day delay. The point: shared spare capacity means the order of planning matters.
- **Chennai port, honest note:** Lowest cost also keeps both high-priority orders on time, for Rs 2.77 lakh. Balanced's extra Rs 5.19 lakh buys the Medium order, which takes the result from 4 of 6 to 6 of 6 order-days. Do not claim Balanced is needed to protect high-priority customers in this scenario.
- **Pune fire:** No plan protects the 3 high-priority orders (0 of 3), because there is no quick alternative magnet source. Balanced still avoids 5 of 14 late order-days. The earlier we know, the more options exist.
- **Tariff:** All three plans are identical. Pune Battery Systems has 2,400 units of spare capacity over the 4-week horizon (600 per week x 4), and the 14 switched orders use about 2,370 of them, so every plan hits the same limit and the weights make no difference. The other 26 orders wait and pay the higher duty. Remaining duty cost is Rs 192.96 lakh; cost avoided is Rs 31.61 lakh of Rs 224.57 lakh (about 14%).
- **Hidden dependency:** The Coimbatore backup wheel maker buys part of its aluminium from the flooded smelter, so it is also slowed. ReRoute still uses it, just later. A view of direct suppliers alone would assume the backup is safe.

> Derivation notes: a switch to Pune Battery Systems costs Rs 1,730 per unit (Rs 1,300 price difference plus 2% of Rs 21,500). Dividing each switch cost by 1,730 gives the order quantities used above. Pune Battery Systems is supplier S15 in `data/suppliers.csv`; its 600 units a week are 1,200 weekly capacity x 0.5 spare share in `data/supplier_materials.csv`.

## 6. What we have not measured yet

The manual-planner baseline and planner acceptance by reviewers.

Detection on unseen signals is now measured (`python scripts/evaluate.py --signals data/heldout_signals.json`,
rules only, 20 held-out signals): 95% relevant vs not relevant, 79% event type (11/14),
supplier matching precision 88% and recall 82%. See `results/slide6_numbers.md`.

## 7. Likely judge questions

- **Why not SAP IBP?** IBP is not on the trial or practice systems. `planner.py` follows the same idea, and the Sourcing agent would call IBP in production.
- **Is the data real?** No. It is synthetic, modelled on the Hosur, Chennai and Bengaluru supplier belts.
- **What if the AI is wrong?** The numbers come from this code. The AI only explains them, and important changes need a human.
- **How did you choose the weights?** By judgement, in `config.py`. We did not tune them against the results.
- **Why do the three tariff plans match?** Spare capacity at the domestic battery maker is the limit, so every plan hits it.
- **Why can a cheaper plan beat the "fastest" one?** Spare capacity is shared, so spending it on an order that stock already protects can leave a later order unprotected.
- **What can't the planner do?** Pune fire: with no alternative source of a Tier-2 input, no plan can save the high-priority orders.
