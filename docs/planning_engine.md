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
| Switch | Move the whole order to another supplier with spare capacity | Price difference, plus 2% of the PO value (logistics and checks), plus freight for any extra road distance to the plant (Rs 60 per km, one truck per PO); arrives after that supplier's lead time |

Each option is scored on cost, delay and customer service (lower is better). Three sets of weights give three plans:

| Plan | Cost | Delay | Service |
|---|---|---|---|
| Fastest recovery | 0.10 | 0.55 | 0.35 |
| Lowest cost | 0.50 | 0.20 | 0.30 |
| Balanced (recommended) | 0.25 | 0.40 | 0.35 |

The Balanced weights are set in `reroute/config.py` by judgement. They were not tuned against the results.

Lowest cost was 0.65 / 0.15 / 0.20 until 3 Nov. With those weights waiting (Rs 0 extra) always scored better than even an 8% expedite, so the plan almost never changed anything. At 0.50 / 0.20 / 0.30 cost still leads, but a cheap expedite or switch can beat waiting. Balanced is unchanged.

Fastest recovery has one extra step (also 3 Nov). Planning one PO at a time, it could switch a PO whose customer order plant stock already protects and so use up the spare capacity a later PO needed; in the smelter flood it then avoided fewer late order-days than Balanced while costing more. After its first pass, a PO that is still late may now take a switched PO's capacity when that PO's customer stays on time without it. A hand-over is kept only if total customer delay goes down, and the giving order's card says so ("Gave its spare capacity at ... to PO ...").

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

Produced with `python -m scripts.compare_plans` (`results/plan_comparison.csv`). Dataset snapshot date: 2026-10-29, according to `data/meta.csv`. Detection for this comparison is rule-based (`use_llm=False`). Extra costs include freight for farther suppliers.

### Balanced plan (the recommended plan)

| Scenario | POs changed | Extra cost | Late order-days avoided | High-priority on time |
|---|---:|---:|---|---|
| Hosur flood (news) | 10 | Rs 3.44 lakh | 5 of 7 | 3 of 3 |
| Smelter flood (S20, 8 days) | 4 | Rs 1.58 lakh | 5 of 5 | 2 of 2 |
| Pune fire (news) | 5 | Rs 3.92 lakh | 5 of 14 | 0 of 3 |
| Chennai port closed, 8 days | 3 | Rs 9.09 lakh | 6 of 6 | 2 of 2 |
| Li-ion tariff 10% to 35% | 14 | Rs 198.26 lakh of duty still paid; Rs 26.32 lakh avoided | No late orders | None at risk |

### All three plans

| Scenario | Plan | POs changed | Extra cost | Late order-days avoided | High-priority on time |
|---|---|---:|---:|---|---|
| Hosur flood | Fastest recovery | 21 | Rs 6.36 lakh | 5 of 7 | 3 of 3 |
| Hosur flood | Lowest cost | 8 | Rs 2.24 lakh | 4 of 7 | 3 of 3 |
| Hosur flood | Balanced | 10 | Rs 3.44 lakh | 5 of 7 | 3 of 3 |
| Smelter flood | Fastest recovery | 8 | Rs 2.47 lakh | 5 of 5 | 2 of 2 |
| Smelter flood | Lowest cost | 2 | Rs 0.55 lakh | 3 of 5 | 2 of 2 |
| Smelter flood | Balanced | 4 | Rs 1.58 lakh | 5 of 5 | 2 of 2 |
| Pune fire | Fastest recovery | 8 | Rs 6.41 lakh | 5 of 14 | 0 of 3 |
| Pune fire | Lowest cost | 0 | Rs 0 | 0 of 14 | 0 of 3 |
| Pune fire | Balanced | 5 | Rs 3.92 lakh | 5 of 14 | 0 of 3 |
| Chennai port | Fastest recovery | 7 | Rs 24.57 lakh | 6 of 6 | 2 of 2 |
| Chennai port | Lowest cost | 3 | Rs 8.71 lakh | 6 of 6 | 2 of 2 |
| Chennai port | Balanced | 3 | Rs 9.09 lakh | 6 of 6 | 2 of 2 |
| Li-ion tariff | All three plans | 14 | Rs 198.26 lakh of duty still paid; Rs 26.32 lakh avoided of Rs 224.57 lakh | No late orders | None at risk |

## 5. What the results show

- **Smelter flood:** Balanced avoids all 5 late order-days for Rs 1.58 lakh with 4 POs changed. Fastest recovery also avoids all 5 but changes 8 POs for Rs 2.47 lakh: it expedites orders whose customers are already covered so the parts arrive sooner. High-priority PO 4500000017 gives its Coimbatore capacity to Medium PO 4500000001, whose customer would otherwise be 1 day late. Lowest cost protects both high-priority orders for Rs 0.55 lakh by changing 2 POs, but leaves 2 order-days late on Medium orders.
- **Chennai port:** Balanced and Lowest cost both avoid all 6 late order-days. The only difference is high-priority PO 4500000021 (40 units): Lowest cost expedites it for Rs 68,800 and it reaches the plant 3 days late; Balanced switches it to Pune Battery Systems for Rs 1,07,006 and it reaches the plant 1 day late. Plant stock covers both, so the customer order is on time either way; Balanced pays the Rs 0.38 lakh difference to lean less on that stock. Fastest recovery also avoids all 6 but spends Rs 24.57 lakh on 7 changes, mostly expedites that bring parts in sooner. High-priority PO 4500000029 (400 units) gives its Pune Battery Systems capacity to Medium PO 4500000005, because plant stock already covers PO 4500000029's customer. Shared spare capacity means the order of planning matters.
- **Pune fire:** No plan protects the 3 high-priority orders (0 of 3), because there is no quick alternative magnet source. Lowest cost changes nothing; Balanced still avoids 5 of 14 late order-days. The earlier we know, the more options exist.
- **Tariff:** Nothing is late, so the three plans differ only on cost and all make the same 14 switches. Pune Battery Systems has 2,400 units of spare capacity over the 4-week horizon (600 per week x 4); the 14 switched orders use 2,370 of them. The other 26 orders wait and pay the higher duty. Cost avoided is Rs 26.32 lakh of Rs 224.57 lakh (about 12%).
- **Hidden dependency:** The Coimbatore backup wheel maker buys part of its aluminium from the flooded smelter, so it is also slowed. ReRoute still uses it, just later. A view of direct suppliers alone would assume the backup is safe.

> Pune Battery Systems is supplier S15 in `data/suppliers.csv`; its 600 spare units a week are 1,200 weekly capacity x 0.5 spare share in `data/supplier_materials.csv`.

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
- **Why do the three tariff plans match?** Nothing is late, so the plans differ only on cost, and spare capacity at the domestic battery maker limits how many orders can move.
- **Why recommend Balanced at the Chennai port when Lowest cost avoids the same delay for less?** For one small high-priority order, Lowest cost expedites (3 days late at the plant) and Balanced switches supplier (1 day late). Plant stock covers either, so the customer is on time both ways; Balanced pays Rs 38,206 more to leave more stock as a buffer. The planner sees both plans and can pick either.
- **Why does Fastest recovery cost more than Balanced for the same delay avoided?** It also expedites orders whose customers stock already covers, so parts arrive sooner at the plant. It never avoids less customer delay than Balanced: a still-late order can take backup capacity from one that doesn't need it.
- **What can't the planner do?** Pune fire: with no alternative source of a Tier-2 input, no plan can save the high-priority orders.
