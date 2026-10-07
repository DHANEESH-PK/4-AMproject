"""
Messy multi-table dataset generator for HNX26PSI08 (Proof-Carrying Data Analyst).

Builds a CLEAN truth first, then deliberately dirties it. Because we know the
truth, every agent answer can be scored objectively (ground_truth.json).

Traps planted (one per line of the problem statement):
  - Units don't match      : us_shop sells in USD, eu_shop in EUR ("€1.234,50" style)
  - Dates are ambiguous    : us_shop writes MM/DD/YYYY, eu_shop DD/MM/YYYY,
                             legacy system writes NN/NN/YYYY with UNKNOWN order
  - Rows are duplicated    : exact re-exports of orders
  - Tables contradict      : monthly_summary.csv has a stale February figure;
                             3 customers appear twice with different regions
  - Data is missing        : blank amounts (light in March, heavy in April)
  - No valid answer        : questions about regions / periods / fields that don't exist
  - Designed to trick      : "Q2" (fiscal vs calendar), causal "why" questions

Run:  python data/generate_data.py      (deterministic, seed=42)
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
OUT = Path(__file__).resolve().parent
rng = random.Random(SEED)

REGIONS = ["North", "South", "East", "West"]
# EUR -> USD month-average rates (synthetic but realistic magnitude)
FX = {1: 1.0850, 2: 1.0790, 3: 1.0880, 4: 1.0720, 5: 1.0810, 6: 1.0920}

# ---------------------------------------------------------------- customers
customers = [{"customer_id": f"C{i:03d}", "name": f"Customer {i:03d}",
              "region": rng.choice(REGIONS)} for i in range(1, 61)]
# 3 North customers will ALSO appear as South -> contradiction confined to North/South
CONFLICT_IDS = [c["customer_id"] for c in customers if c["region"] == "North"][:3]

# ------------------------------------------------------------- clean orders
def rand_date(month, day_range=None):
    lo, hi = day_range or (1, 28)
    return date(2026, month, rng.randint(lo, hi))

orders = []
oid = 1
for month in range(1, 7):
    for _ in range(60):
        src = rng.choices(["us_shop", "eu_shop"], weights=[55, 45])[0]
        orders.append({
            "order_id": f"O{oid:04d}", "customer_id": rng.choice(customers)["customer_id"],
            "date": rand_date(month), "source": src,
            "currency": "USD" if src == "us_shop" else "EUR",
            "amount": round(rng.uniform(40, 2500), 2)})
        oid += 1
# make sure conflicting customers actually trade in Jan (so a region question hits them)
for cid in CONFLICT_IDS:
    orders.append({"order_id": f"O{oid:04d}", "customer_id": cid, "date": rand_date(1),
                   "source": "us_shop", "currency": "USD",
                   "amount": round(rng.uniform(300, 900), 2)})
    oid += 1

# legacy system: 14 unambiguous (day >= 13) + 6 ambiguous May/June rows
for i in range(20):
    if i < 14:
        d = rand_date(rng.randint(1, 6), (13, 28))
    else:
        d = rng.choice([date(2026, 6, 5), date(2026, 5, 6)])  # swap -> other month
    orders.append({"order_id": f"O{oid:04d}", "customer_id": rng.choice(customers)["customer_id"],
                   "date": d, "source": "legacy", "currency": "USD",
                   "amount": round(rng.uniform(100, 1500), 2)})
    oid += 1

# ----------------------------------------------------------- dirty: amounts
def fmt_amount(o, style):
    a = o["amount"]
    if o["currency"] == "USD":
        return [f"${a:,.2f}", f"{a:.2f}", f"USD {a:.2f}"][style % 3]
    eu = f"{a:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return [f"€{eu}", f"{eu} EUR", eu][style % 3]

def fmt_date(o):
    d = o["date"]
    if o["source"] == "us_shop":
        return d.strftime("%m/%d/%Y")
    if o["source"] == "eu_shop":
        return d.strftime("%d/%m/%Y")
    return d.strftime("%d/%m/%Y")  # legacy is actually DD/MM — but nobody documented it

missing_ids = set()
mar = [o for o in orders if o["date"].month == 3 and o["source"] != "legacy"]
apr = [o for o in orders if o["date"].month == 4 and o["source"] != "legacy"]
missing_ids |= {o["order_id"] for o in rng.sample(mar, 3)}    # ~5%  -> answer + warn
missing_ids |= {o["order_id"] for o in rng.sample(apr, 12)}   # ~19% -> refuse

rows = []
for i, o in enumerate(orders):
    eu_row = o["currency"] == "EUR"
    style = rng.randint(0, 2)
    amt = "" if o["order_id"] in missing_ids else fmt_amount(o, style)
    # currency column is blank when the symbol already tells you (messy but recoverable)
    cur = "" if (style == 0 and not eu_row) or (style in (0, 1) and eu_row) else o["currency"]
    if eu_row and style == 2:
        cur = "EUR"  # bare "1.234,50" needs the column
    rows.append({"order_id": o["order_id"], "customer_id": o["customer_id"],
                 "order_date": fmt_date(o), "source_system": o["source"],
                 "amount": amt, "currency": cur})

# exact duplicates (re-exported rows)
dupes = rng.sample(rows, 25)
rows += [dict(r) for r in dupes]
rng.shuffle(rows)

with open(OUT / "orders.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

# --------------------------------------------------------------- customers
cust_rows = [dict(c) for c in customers]
for cid in CONFLICT_IDS:
    c = next(x for x in customers if x["customer_id"] == cid)
    other = "South"
    cust_rows.append({"customer_id": cid, "name": c["name"], "region": other})
rng.shuffle(cust_rows)
with open(OUT / "customers.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["customer_id", "name", "region"])
    w.writeheader(); w.writerows(cust_rows)

# --------------------------------------------------------------------- FX
with open(OUT / "fx_rates.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["month", "from_ccy", "to_ccy", "rate"])
    for m, r in FX.items():
        w.writerow([f"2026-{m:02d}", "EUR", "USD", r])

# ---------------------------------------------------------------- refunds
refundable = [o for o in orders if o["date"].month == 1 and o["source"] != "legacy"]
refunds = []
for j, o in enumerate(rng.sample(refundable, 6), 1):
    amt = round(o["amount"] * rng.choice([0.25, 0.5, 1.0]), 2)
    refunds.append({"refund_id": f"R{j:03d}", "order_id": o["order_id"],
                    "refund_date": (o["date"] + timedelta(days=3)).isoformat(),
                    "amount": amt, "currency": o["currency"]})
with open(OUT / "refunds.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(refunds[0].keys()))
    w.writeheader(); w.writerows(refunds)

# ------------------------------------------------------------ ground truth
def usd(o):
    return o["amount"] * (FX[o["date"].month] if o["currency"] == "EUR" else 1.0)

def observable(month_set):
    """What a correct analyst CAN compute: known amounts only, deduped, converted."""
    return round(sum(usd(o) for o in orders
                     if o["date"].month in month_set and o["order_id"] not in missing_ids), 2)

region_of = {c["customer_id"]: c["region"] for c in customers}

# monthly summary: correct except a stale February figure (contradiction)
with open(OUT / "monthly_summary.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["month", "revenue_usd", "prepared_by"])
    for m in range(1, 7):
        v = observable({m})
        if m == 2:
            v = round(v * 0.91, 2)  # stale export, prepared before late orders landed
        w.writerow([f"2026-{m:02d}", f"{v:.2f}", "finance_ops"])

refund_usd_jan = round(sum(r["amount"] * (FX[1] if r["currency"] == "EUR" else 1.0)
                           for r in refunds), 2)

west_jan_clean = [o for o in orders if o["date"].month == 1
                  and region_of[o["customer_id"]] == "West"]
north_jan = [o for o in orders if o["date"].month == 1 and region_of[o["customer_id"]] == "North"]
conflict_regions = {cid: sorted({c["region"] for c in cust_rows if c["customer_id"] == cid})
                    for cid in CONFLICT_IDS}

# pick a region question that is NOT touched by conflicting customers, and one that IS
def touched(region):
    return any(region in conflict_regions[cid] for cid in CONFLICT_IDS)
clean_region = next(r for r in REGIONS if not touched(r)) if any(
    not touched(r) for r in REGIONS) else None
dirty_region = "North"

def region_total(region):
    return round(sum(usd(o) for o in orders if o["date"].month == 1
                     and region_of[o["customer_id"]] == region
                     and o["customer_id"] not in CONFLICT_IDS), 2)

questions = [
    {"id": "Q01", "question": "What was total revenue in USD for January 2026?",
     "expect": "ANSWER", "value": observable({1})},
    {"id": "Q02", "question": "How many unique orders were placed in February 2026?",
     "expect": "ANSWER", "value": sum(1 for o in orders if o["date"].month == 2)},
    {"id": "Q03", "question": "What was February 2026 revenue in USD?",
     "expect": "ANSWER", "value": observable({2}), "must_warn": "contradiction"},
    {"id": "Q04", "question": "What was March 2026 revenue in USD?",
     "expect": "ANSWER", "value": observable({3}), "must_warn": "missing"},
    {"id": "Q05", "question": "What was April 2026 revenue in USD?",
     "expect": "REFUSE", "reason": "missing"},
    {"id": "Q06", "question": "What was June 2026 revenue in USD?",
     "expect": "REFUSE", "reason": "ambiguous_date"},
    {"id": "Q07", "question": "What was total revenue in USD for H1 2026?",
     "expect": "ANSWER", "value": observable(set(range(1, 7))), "must_warn": "missing"},
    {"id": "Q08", "question": "What was revenue in the Antarctica region in January 2026?",
     "expect": "REFUSE", "reason": "unknown_entity"},
    {"id": "Q09", "question": "What was revenue in December 2026?",
     "expect": "REFUSE", "reason": "out_of_coverage"},
    {"id": "Q10", "question": "Why did revenue drop in March 2026?",
     "expect": "REFUSE", "reason": "unsupported_intent"},
    {"id": "Q11", "question": "What is the average order value for churned customers?",
     "expect": "REFUSE", "reason": "unknown_field"},
    {"id": "Q12", "question": "What was net revenue in USD for January 2026 after refunds?",
     "expect": "ANSWER", "value": round(observable({1}) - refund_usd_jan, 2)},
    {"id": "Q13", "question": "What was total revenue in Q2?",
     "expect": "REFUSE", "reason": "ambiguous_period"},
    {"id": "Q14", "question": "What was total revenue for January 2026?",
     "expect": "ANSWER", "value": observable({1}), "must_warn": "currency_assumed"},
    {"id": "Q15", "question": f"What was revenue in the {dirty_region} region in January 2026?",
     "expect": "REFUSE", "reason": "contradiction"},
]
# --- adversarial regressions (found by probing; each one used to give a confident wrong answer)
mar_eur = round(sum(usd(o) / FX[3] for o in orders
                    if o["date"].month == 3 and o["order_id"] not in missing_ids), 2)
questions += [
    {"id": "A01", "question": "Revenue in Jan 2026", "expect": "ANSWER", "value": observable({1})},
    {"id": "A02", "question": "What was revenue last month?", "expect": "REFUSE", "reason": "ambiguous_period"},
    {"id": "A03", "question": "Top 3 customers by revenue in January 2026",
     "expect": "REFUSE", "reason": "unsupported_intent"},
    {"id": "A04", "question": "Revenue for fiscal Q1 2026", "expect": "REFUSE", "reason": "ambiguous_period"},
    {"id": "A05", "question": "How many orders in June 2026?", "expect": "REFUSE", "reason": "ambiguous_date"},
    {"id": "A06", "question": "Total sales in euros for March 2026", "expect": "ANSWER", "value": mar_eur,
     "must_warn": "missing"},
    {"id": "A07", "question": "Revenue in 2026", "expect": "REFUSE", "reason": "out_of_coverage"},
    {"id": "A08", "question": "What was shipping revenue in Jan 2026?", "expect": "REFUSE", "reason": "unknown_field"},
]
if clean_region:
    questions.append({"id": "Q16",
                      "question": f"What was revenue in the {clean_region} region in January 2026?",
                      "expect": "ANSWER", "value": region_total(clean_region)})

with open(OUT / "ground_truth.json", "w", encoding="utf-8") as f:
    json.dump({"seed": SEED, "questions": questions,
               "planted": {"duplicates": 25, "missing_amount_rows": len(missing_ids),
                           "ambiguous_legacy_rows": 6, "conflict_customers": CONFLICT_IDS,
                           "stale_summary_month": "2026-02"}}, f, indent=2)
with open(OUT / "questions.json", "w", encoding="utf-8") as f:
    json.dump([{"id": q["id"], "question": q["question"]} for q in questions], f, indent=2)

print(f"orders.csv rows={len(rows)} (true orders={len(orders)}), customers.csv rows={len(cust_rows)}, "
      f"refunds={len(refunds)}, questions={len(questions)}")
