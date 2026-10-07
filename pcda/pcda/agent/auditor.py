"""
AUDITOR AGENT — an INDEPENDENT re-implementation (stdlib csv only, no pandas,
no shared code with cleaning.py). If two different implementations agree, a
bug in one of them is unlikely to be the answer. This is N-version
programming, the cheapest real verification you can buy.
"""
import csv
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def _num(text, eu):
    s = re.sub(r"[^\d,.\-]", "", text)
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if eu else s.replace(",", "")
    return float(s)


def _ccy(amount, col):
    a = amount.upper()
    sym = "EUR" if ("€" in amount or "EUR" in a) else "USD" if ("$" in amount or "USD" in a) else ""
    return col.strip().upper() or sym


def _months(date_text, source):
    a, b, y = (int(x) for x in re.split(r"[/-]", date_text))
    readings = {"us_shop": [(a, b)], "eu_shop": [(b, a)]}.get(source)
    if readings is None:  # undocumented: every calendar-valid reading
        readings = [r for r in {(b, a), (a, b)} if 1 <= r[0] <= 12]
    return {f"{y}-{m:02d}" for m, _ in readings}


def audit(spec, data_dir):
    d = Path(data_dir)
    fx = {(r["month"], r["from_ccy"]): float(r["rate"]) for r in csv.DictReader(open(d / "fx_rates.csv"))}
    regions = {}
    for r in csv.DictReader(open(d / "customers.csv", encoding="utf-8")):
        regions.setdefault(r["customer_id"], set()).add(r["region"])

    seen, rows = set(), []
    for r in csv.DictReader(open(d / "orders.csv", encoding="utf-8")):
        if r["order_id"] in seen:
            continue
        seen.add(r["order_id"])
        ms = _months(r["order_date"], r["source_system"])
        if not ms <= set(spec["months"]):
            continue
        if spec["region"] and regions.get(r["customer_id"]) != {spec["region"]}:
            continue
        cur = _ccy(r["amount"], r["currency"])
        val = _num(r["amount"], cur == "EUR")
        month = next(iter(ms))
        usd = None if val is None or cur not in ("USD", "EUR") else val * (fx[(month, "EUR")] if cur == "EUR" else 1)
        rows.append((r["order_id"], month, usd))

    def conv(usd, month):
        return usd if spec["currency"] == "USD" else usd / fx[(month, "EUR")]

    usable = [(o, m, conv(u, m)) for o, m, u in rows if u is not None]
    q = lambda x: float(Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP))
    if spec["metric"] == "count":
        return len(rows)
    total = sum(v for _, _, v in usable)
    if spec["metric"] == "sum":
        return q(total)
    if spec["metric"] == "avg":
        return q(total / len(usable))
    if spec["metric"] == "net_sum":
        month_of = {o: m for o, m, _ in usable}
        ref = 0.0
        for r in csv.DictReader(open(d / "refunds.csv")):
            if r["order_id"] in month_of:
                m = month_of[r["order_id"]]
                usd = float(r["amount"]) * (fx[(m, "EUR")] if r["currency"] == "EUR" else 1)
                ref += conv(usd, m)
        return q(total - q(ref))
    raise ValueError(spec["metric"])
