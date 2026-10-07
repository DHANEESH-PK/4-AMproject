"""
Judge simulator. Runs every question, then scores against the problem
statement's "How You'll Be Judged" list using ground_truth.json.

    python eval.py
"""
import json
import sys
import tempfile
from pathlib import Path

from agent import detective, executor, pipeline

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main():
    gt = json.loads((DATA / "ground_truth.json").read_text())
    ctx = detective.DataContext(str(DATA))
    print("DATA PROFILE:", json.dumps(ctx.profile))
    print("planted    :", json.dumps(gt["planted"]), "\n")

    rows, score = [], {"correct_answers": [0, 0], "correct_refusals": [0, 0], "warned": [0, 0],
                       "code_reruns": [0, 0], "wrong_confident": 0}
    for q in gt["questions"]:
        card = pipeline.answer(q["id"], q["question"], ctx)
        ok = False
        if q["expect"] == "ANSWER":
            score["correct_answers"][1] += 1
            ok = card["decision"] == "ANSWER" and abs(card["answer"] - q["value"]) <= 0.01
            score["correct_answers"][0] += ok
            if card["decision"] == "ANSWER" and not ok:
                score["wrong_confident"] += 1
            if "must_warn" in q:
                score["warned"][1] += 1
                score["warned"][0] += any(w["kind"] == q["must_warn"] for w in card.get("warnings", []))
            # judge's own re-run: different cwd, script moved nowhere, explicit data path
            if card["decision"] == "ANSWER":
                score["code_reruns"][1] += 1
                with tempfile.TemporaryDirectory() as tmp:
                    r = executor.run(ROOT / card["code"], data_dir=DATA, cwd=tmp)
                score["code_reruns"][0] += r["ok"] and abs(r["result"]["value"] - q["value"]) <= 0.01
        else:
            score["correct_refusals"][1] += 1
            kinds = [x["kind"] for x in card.get("refusal", [])]
            ok = card["decision"] == "REFUSE" and q["reason"] in kinds
            score["correct_refusals"][0] += ok
            if card["decision"] == "ANSWER":
                score["wrong_confident"] += 1
        shown = (f"{card['answer']:,} {card.get('unit','')} (conf {card['confidence']})"
                 if card["decision"] == "ANSWER" else "REFUSED: " + card["refusal"][0]["kind"])
        rows.append((q["id"], "PASS" if ok else "FAIL", shown, q["question"]))

    for r in rows:
        print(f"{r[0]}  {r[1]}  {r[2]:<38}  {r[3]}")
    print("\nSCORE", json.dumps(score))
    all_ok = (score["correct_answers"][0] == score["correct_answers"][1]
              and score["correct_refusals"][0] == score["correct_refusals"][1]
              and score["warned"][0] == score["warned"][1]
              and score["code_reruns"][0] == score["code_reruns"][1]
              and score["wrong_confident"] == 0)
    (ROOT / "eval_report.json").write_text(json.dumps({"score": score, "rows": rows}, indent=2))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
