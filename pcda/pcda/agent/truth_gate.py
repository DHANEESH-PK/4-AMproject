"""
TRUTH GATE — deterministic. No LLM gets a vote on whether to answer.
"""
REFUSAL_KINDS = {"unsupported_intent", "unknown_field", "ambiguous_period"}
WARNING_PENALTY = {"missing": 0.15, "contradiction": 0.10, "currency_assumed": 0.05,
                   "year_assumed": 0.05, "period_assumed": 0.10, "key_conflict": 0.15,
                   "ambiguous_date_harmless": 0.02, "duplicates_info": 0.0}


def decide(spec, findings):
    reasons = [(k, v) for k, v in spec["flags"] if k in REFUSAL_KINDS] + findings["blocking"]
    if reasons:
        return {"decision": "REFUSE", "confidence": None, "reasons": reasons, "warnings": []}
    warnings = list(spec["assumptions"]) + findings["warnings"]
    conf = 1.0 - sum(WARNING_PENALTY.get(k, 0.1) for k, _ in warnings)
    return {"decision": "ANSWER", "confidence": round(max(conf, 0.3), 2),
            "reasons": [], "warnings": warnings}
