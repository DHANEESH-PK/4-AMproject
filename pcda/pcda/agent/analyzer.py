"""
QUESTION ANALYZER  ->  structured spec (intent / data need / ambiguity).

Design rule: the LLM (optional, llm_parser.py) may only PRODUCE THIS SPEC.
It never writes the proof code. Code comes from audited templates (codegen.py).
That is the single biggest reliability decision in the whole system.
"""
import re

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}

KNOWN_WORDS = set("""
what was were is are the a an in for of on to during from at and with by
how many much number count total sum overall gross net after before refunds refund refunded
revenue revenues sales sale income turnover orders order placed unique distinct value amount
average mean aov usd eur dollars dollar euros euro us $ € region calendar fiscal fy q h
did do does give me tell show please our we
""".split())
ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
RELATIVE_TIME = (r"\b(last|this|next|previous|prior|current|recent|recently|past)\s+"
                 r"(month|quarter|year|week|period)\b|\b(ytd|mtd|qtd|yesterday|today|lately)\b")
SHAPE_UNSUPPORTED = (r"\b(top|bottom|rank|ranking|highest|lowest|best|worst|largest|smallest|"
                     r"breakdown|each|per)\b|\bby (customer|region|month|source)\b")
UNSUPPORTED = r"\b(why|cause[sd]?|reason|predict|forecast|should|will .* next|recommend)\b"
# concepts users ask about that this schema does NOT contain
UNKNOWN_FIELDS = ["churn", "profit", "margin", "cost", "product", "category", "discount",
                  "units", "quantity", "inventory", "employee", "salesperson", "loyal", "vip"]


def analyze(question, data_months, fiscal_year_start=4):
    q = question.lower()
    spec = {"question": question, "intent": "aggregate", "metric": "sum", "months": [],
            "region": None, "currency": "USD", "currency_specified": False,
            "flags": [], "assumptions": []}

    # ---- intent detection
    if re.search(UNSUPPORTED, q):
        spec["intent"] = "unsupported"
        spec["flags"].append(("unsupported_intent",
                              "Causal / predictive / advisory question — data shows WHAT, not WHY."))
        return spec
    # Principle: anything we cannot FULLY parse is refused, never defaulted.
    if re.search(SHAPE_UNSUPPORTED, q):
        spec["flags"].append(("unsupported_intent",
            "Ranking / breakdown questions are not supported by this agent yet; "
            "answering with a single total would be wrong."))
        return spec
    if re.search(RELATIVE_TIME, q):
        spec["flags"].append(("ambiguous_period",
            "Relative period ('last month', 'recent', 'YTD'...) — relative to which date? "
            "Please give an explicit month/quarter and year."))
        return spec
    # whitelist: every content word must be understood, otherwise refuse
    region_m = re.search(r"\b(\w+) region\b", q)
    leftovers = [w for w in re.findall(r"[a-z€$]+", q)
                 if w not in KNOWN_WORDS and w not in MONTHS and w not in ABBR
                 and not (region_m and w == region_m.group(1))]
    if leftovers:
        spec["flags"].append(("unknown_field",
            f"Question uses term(s) this agent can't map to the data: {', '.join(leftovers)}."))
        return spec
    hits = [w for w in UNKNOWN_FIELDS if w in q]
    if hits:
        spec["flags"].append(("unknown_field",
                              f"Question needs field(s) not in any table: {', '.join(hits)}."))
        return spec

    # ---- data need: metric
    if re.search(r"\bnet\b|after refunds", q):
        spec["metric"] = "net_sum"
    elif re.search(r"how many|number of|\bcount\b", q):
        spec["metric"] = "count"
    elif re.search(r"average|mean|\baov\b", q):
        spec["metric"] = "avg"

    # ---- currency
    if re.search(r"\beur\b|€|euro", q):
        spec["currency"], spec["currency_specified"] = "EUR", True
    elif re.search(r"\busd\b|\$|dollar", q):
        spec["currency_specified"] = True
    elif spec["metric"] != "count":
        spec["assumptions"].append(("currency_assumed",
            "No currency stated; reporting in USD per data_dictionary.md (EUR converted at monthly FX)."))

    # ---- region
    m = re.search(r"\b(?:in|for) the (\w+) region\b|\b(\w+) region\b", question)
    if m:
        spec["region"] = (m.group(1) or m.group(2)).title()

    # ---- period (ambiguity detection)
    years = re.findall(r"\b(20\d\d)\b", q)
    year = int(years[0]) if years else None
    data_years = sorted({int(x[:4]) for x in data_months})
    qm = re.search(r"\b(fiscal |calendar |fy\s?)?q([1-4])\b", q)
    hm = re.search(r"\bh([12])\b", q)
    month_hits = [MONTHS[w] for w in re.findall(r"\b(" + "|".join(MONTHS) + r")\b", q)]
    month_hits += [ABBR[w] for w in re.findall(r"\b(" + "|".join(ABBR) + r")\b\.?", q)]
    if not (qm or hm) and re.search(r"\bq[1-4]|\bfy|\bfiscal|\bquarter|\bhalf\b|\bweek", q):
        spec["flags"].append(("ambiguous_period", "Period mentioned but could not be parsed exactly."))
        return spec
    if len(set(years)) > 1:
        spec["flags"].append(("ambiguous_period", "Multiple years mentioned; ranges not supported yet."))
        return spec

    if (qm or hm or month_hits) and year is None:
        if len(data_years) == 1:
            year = data_years[0]
            spec["assumptions"].append(("year_assumed", f"No year stated; data only covers {year}."))
        else:
            spec["flags"].append(("ambiguous_period", "No year stated and data spans several years."))
            return spec

    if qm:
        kind = (qm.group(1) or "").strip()
        n = int(qm.group(2))
        if not kind:
            spec["flags"].append(("ambiguous_period",
                f"'Q{n}' is ambiguous: calendar Q{n} vs fiscal Q{n} (fiscal year starts month "
                f"{fiscal_year_start} per data_dictionary.md). Please specify."))
            return spec
        if kind != "calendar" and fiscal_year_start != 1 and years:
            spec["flags"].append(("ambiguous_period",
                f"'Fiscal Q{n} {year}' is ambiguous: the fiscal year starts in month {fiscal_year_start}, "
                f"and data_dictionary.md does not say whether FY{year} starts in {year - 1} or {year}."))
            return spec
        start = 1 + 3 * (n - 1) if kind == "calendar" else ((fiscal_year_start - 1 + 3 * (n - 1)) % 12) + 1
        spec["months"] = [f"{year}-{((start - 1 + i) % 12) + 1:02d}" for i in range(3)]
    elif hm:
        start = 1 if hm.group(1) == "1" else 7
        spec["months"] = [f"{year}-{m:02d}" for m in range(start, start + 6)]
    elif month_hits:
        spec["months"] = [f"{year}-{m:02d}" for m in sorted(set(month_hits))]
    elif year is not None:
        spec["months"] = [f"{year}-{m:02d}" for m in range(1, 13)]   # full calendar year
        spec["assumptions"].append(("period_assumed", f"'{year}' read as calendar year {year}."))
    else:
        spec["months"] = list(data_months)
        spec["assumptions"].append(("period_assumed", "No period stated; using all available data."))
    return spec
