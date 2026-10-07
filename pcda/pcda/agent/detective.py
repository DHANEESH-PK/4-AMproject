"""
DATA DETECTIVE — question-scoped data quality checks.

It does not just say "the table has duplicates". It asks: do the problems
actually touch the rows THIS question needs? A June date ambiguity must not
block a January answer, and an H1 total is unaffected by May/June swaps.
"""
import pandas as pd

from . import cleaning

MISSING_REFUSE_SHARE = 0.10      # >10% of in-scope rows unusable -> refuse
CONTRADICTION_TOL = 0.005        # 0.5% gap vs. secondary source -> warn


class DataContext:
    """Loaded once per session; question-independent profiling."""
    def __init__(self, data_dir):
        from pathlib import Path
        self.data_dir = data_dir = str(Path(data_dir).resolve())  # scripts run from other cwds
        self.orders = cleaning.load_orders(data_dir)
        self.cust_regions = cleaning.load_customers(data_dir)
        self.refunds = cleaning.load_refunds(data_dir)
        self.fx = cleaning.load_fx(data_dir)
        self.summary = pd.read_csv(f"{data_dir}/monthly_summary.csv", dtype={"month": str})
        self.months = sorted(set(self.orders["month_a"].dropna()) | set(self.orders["month_b"].dropna()))
        self.regions = sorted({r for rs in self.cust_regions.values() for r in rs})
        self.profile = {
            "raw_rows": self.orders.attrs["n_raw"],
            "duplicates_removed": self.orders.attrs["n_exact_dupes"],
            "unique_orders": len(self.orders),
            "missing_amounts": int(self.orders["amount_missing"].sum()),
            "ambiguous_dates": int(self.orders["date_ambiguous"].sum()),
            "conflicting_customers": sorted(c for c, r in self.cust_regions.items() if len(r) > 1),
            "coverage": f"{self.months[0]} .. {self.months[-1]}",
        }


def investigate(spec, ctx):
    f = {"blocking": [], "warnings": [], "evidence": {}}
    if spec["intent"] != "aggregate" or any(k in ("unsupported_intent", "unknown_field",
                                                  "ambiguous_period") for k, _ in spec["flags"]):
        return f
    o, months = ctx.orders, spec["months"]

    # coverage
    outside = [m for m in months if m not in ctx.months]
    if outside:
        f["blocking"].append(("out_of_coverage",
            f"Requested period {outside[0]}..{outside[-1]} is outside data coverage "
            f"{ctx.profile['coverage']}. Reporting 0 would be a fabricated answer."))
        return f
    # entity existence
    if spec["region"] and spec["region"] not in ctx.regions:
        f["blocking"].append(("unknown_entity",
            f"Region '{spec['region']}' does not exist. Known regions: {', '.join(ctx.regions)}."))
        return f

    in_month = o["month_a"].isin(months) & ~o["date_ambiguous"]

    # ambiguous dates that straddle the scope boundary
    a_in, b_in = o["month_a"].isin(months), o["month_b"].isin(months)
    straddle = o[o["date_ambiguous"] & (a_in != b_in)]
    if spec["region"]:
        straddle = straddle[straddle["customer_id"].map(
            lambda c: spec["region"] in ctx.cust_regions.get(c, []))]
    if len(straddle):
        f["blocking"].append(("ambiguous_date",
            f"{len(straddle)} order(s) from source '{straddle['source'].iloc[0]}' have dates like "
            f"'05/06/2026' with an undocumented format; one reading falls inside the requested period, "
            f"the other outside. Value ranges by up to "
            f"{straddle['amount_usd'].sum():,.2f} USD. Cannot give one number."))
    in_scope_amb = o[o["date_ambiguous"] & a_in & b_in]
    if len(in_scope_amb):
        f["warnings"].append(("ambiguous_date_harmless",
            f"{len(in_scope_amb)} ambiguous-date order(s) fall inside the period under either "
            f"reading — included, answer unaffected."))
        in_month = in_month | (o["date_ambiguous"] & a_in & b_in)

    scope = o[in_month]
    # region contradiction
    if spec["region"]:
        conflicted = scope[scope["customer_id"].map(
            lambda c: len(ctx.cust_regions.get(c, [])) > 1 and spec["region"] in ctx.cust_regions[c])]
        if len(conflicted):
            f["blocking"].append(("contradiction",
                f"customers.csv lists {conflicted['customer_id'].nunique()} customer(s) "
                f"({', '.join(sorted(conflicted['customer_id'].unique()))}) in two regions; "
                f"{len(conflicted)} in-scope order(s) worth {conflicted['amount_usd'].sum():,.2f} USD "
                f"cannot be assigned to '{spec['region']}' reliably."))
        scope = scope[scope["customer_id"].map(lambda c: ctx.cust_regions.get(c, []) == [spec["region"]])]

    f["evidence"]["rows_in_scope"] = int(len(scope))

    # missing / unusable amounts
    if spec["metric"] != "count" and len(scope):
        bad = scope["amount_missing"] | scope["currency_unknown"] | scope["amount_usd"].isna()
        share = bad.mean()
        f["evidence"]["unusable_amount_rows"] = int(bad.sum())
        if share > MISSING_REFUSE_SHARE:
            f["blocking"].append(("missing",
                f"{int(bad.sum())} of {len(scope)} in-scope orders ({share:.0%}) have no usable amount "
                f"(threshold {MISSING_REFUSE_SHARE:.0%}). Any total would be materially understated."))
        elif bad.any():
            f["warnings"].append(("missing",
                f"{int(bad.sum())} of {len(scope)} in-scope orders ({share:.1%}) have blank amounts and "
                f"are excluded. True total is HIGHER than reported (this is a lower bound)."))
    if scope.get("key_conflict", pd.Series(dtype=bool)).any():
        f["warnings"].append(("key_conflict", "Some order_ids appear with conflicting content."))

    # contradiction with secondary source (single month, gross revenue only)
    if spec["metric"] == "sum" and len(months) == 1 and not spec["region"] and spec["currency"] == "USD":
        row = ctx.summary[ctx.summary["month"] == months[0]]
        if len(row):
            ours = scope["amount_usd"].sum()
            theirs = float(row["revenue_usd"].iloc[0])
            if ours and abs(ours - theirs) / ours > CONTRADICTION_TOL:
                f["warnings"].append(("contradiction",
                    f"monthly_summary.csv says {theirs:,.2f} USD for {months[0]}; orders.csv "
                    f"(system of record per data_dictionary.md) gives {ours:,.2f}. Gap "
                    f"{ours - theirs:,.2f}. Answer uses orders.csv."))

    if ctx.profile["duplicates_removed"]:
        f["warnings"].append(("duplicates_info",
            f"{ctx.profile['duplicates_removed']} duplicate order row(s) removed before calculation."))
    return f
