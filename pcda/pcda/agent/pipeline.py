"""
Orchestrator — mirrors the team's layout exactly:

QUESTION ANALYZER -> DATA DETECTIVE -> TRUTH GATE -> CODE GENERATOR ->
CODE EXECUTION -> RESULT CHECK -> AUDITOR -> FINAL VERIFIER -> ANSWER CARD
"""
import json
import os
from pathlib import Path

from . import analyzer, codegen, detective, executor, truth_gate, verifier

ROOT = Path(__file__).resolve().parent.parent


def parse(question, ctx):
    if os.getenv("PCDA_USE_LLM") == "1":
        from . import llm_parser
        return llm_parser.analyze(question, ctx.months, ctx.regions)
    return analyzer.analyze(question, ctx.months)


def answer(qid, question, ctx, out_dir=ROOT):
    spec = parse(question, ctx)                                      # 1 analyzer
    findings = detective.investigate(spec, ctx)                      # 2 detective
    gate = truth_gate.decide(spec, findings)                         # 3 truth gate
    card = {"id": qid, "question": question, "decision": gate["decision"],
            "spec": {k: spec[k] for k in ("intent", "metric", "months", "region", "currency")}}

    if gate["decision"] == "REFUSE":
        card.update(answer=None, confidence=None,
                    refusal=[{"kind": k, "why": v} for k, v in gate["reasons"]],
                    message="I can't determine this reliably from the data. " + gate["reasons"][0][1])
    else:
        runs = out_dir / "runs"; runs.mkdir(exist_ok=True)
        script = runs / f"{qid}.py"
        script.write_text(codegen.generate(qid, spec), encoding="utf-8")          # 4 codegen
        first = executor.run(script, data_dir=ctx.data_dir)                       # 5 execute
        if not first["ok"]:
            card.update(decision="REFUSE", answer=None, confidence=None,
                        refusal=[{"kind": "execution_error", "why": first["error"]}],
                        message="Generated code failed; refusing rather than guessing.")
        else:
            checks = verifier.verify(script, spec, first["result"], ctx.data_dir)  # 6-8 verify
            if not checks["all_pass"]:
                card.update(decision="REFUSE", answer=None, confidence=None, checks=checks,
                            refusal=[{"kind": "verification_failed", "why": json.dumps(checks)}],
                            message="Verification failed; refusing rather than guessing.")
            else:
                card.update(answer=first["result"]["value"], unit=first["result"]["unit"],
                            confidence=gate["confidence"],
                            code=str(script.relative_to(out_dir)),
                            evidence={**first["result"], **findings["evidence"],
                                      "auditor_value": checks["auditor"]["independent_value"],
                                      "code_sha256": checks["sha256"]},
                            warnings=[{"kind": k, "note": v} for k, v in gate["warnings"]])
    ans = out_dir / "answers"; ans.mkdir(exist_ok=True)
    (ans / f"{qid}.json").write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    return card
