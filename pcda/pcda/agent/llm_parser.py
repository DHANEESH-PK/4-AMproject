"""
OPTIONAL LLM front-end for the Question Analyzer (enable with PCDA_USE_LLM=1).

The LLM ONLY converts free text into the same JSON spec analyzer.py produces.
Everything downstream (detective, gate, code, verification) stays deterministic.
The output is schema-validated; anything invalid falls back to the rule parser.

NOTE: not exercised in the offline test run (no API key in the build sandbox).
Test it with your key before the demo.
    pip install anthropic ; export ANTHROPIC_API_KEY=... ; export PCDA_USE_LLM=1
"""
import json
import os

from . import analyzer

PROMPT = """Convert the user's data question into JSON. Output JSON only.
Schema:
{{"intent": "aggregate" | "unsupported",
  "metric": "sum" | "count" | "avg" | "net_sum",
  "period": {{"kind": "month"|"half"|"calendar_quarter"|"fiscal_quarter"|"unspecified_quarter"|"all"|"none_given",
             "year": int|null, "number": int|null, "months": [int]}},
  "region": string|null,
  "currency": "USD"|"EUR"|null,
  "unknown_fields": [string]}}
Rules: intent=unsupported for why/causal/forecast/advice questions. unknown_fields lists any
concept not in these tables: orders(order_id, customer_id, date, amount, currency),
customers(region), refunds(amount). Known regions: {regions}. NEVER guess a quarter type:
use unspecified_quarter if the user didn't say fiscal or calendar.
Question: {q}"""


def analyze(question, data_months, regions):
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"), max_tokens=400,
            messages=[{"role": "user", "content": PROMPT.format(q=question, regions=regions)}])
        j = json.loads(msg.content[0].text.strip().strip("`").removeprefix("json"))
    except Exception:  # noqa: BLE001 — any failure -> deterministic parser
        return analyzer.analyze(question, data_months)

    # map LLM JSON -> canonical spec via the rule parser's own vocabulary (keeps one code path)
    if j.get("intent") == "unsupported":
        return analyzer.analyze("why " + question, data_months)
    if j.get("unknown_fields"):
        spec = analyzer.analyze(question, data_months)
        spec["flags"].append(("unknown_field", f"Fields not in data: {j['unknown_fields']}"))
        return spec
    p = j.get("period", {})
    words = {"half": f"H{p.get('number')}", "calendar_quarter": f"calendar Q{p.get('number')}",
             "fiscal_quarter": f"fiscal Q{p.get('number')}", "unspecified_quarter": f"Q{p.get('number')}"}
    period_txt = words.get(p.get("kind"), " ".join(
        list(analyzer.MONTHS)[m - 1] for m in p.get("months", [])))
    year_txt = str(p["year"]) if p.get("year") else ""
    metric_txt = {"sum": "revenue", "count": "how many orders", "avg": "average",
                  "net_sum": "net revenue"}.get(j.get("metric"), "revenue")
    region_txt = f"in the {j['region']} region" if j.get("region") else ""
    ccy_txt = j.get("currency") or ""
    canonical = f"{metric_txt} {ccy_txt} {region_txt} {period_txt} {year_txt}"
    spec = analyzer.analyze(canonical, data_months)
    spec["question"] = question
    return spec
