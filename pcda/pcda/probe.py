"""Unseen-phrasing robustness probe (no answer key — inspect by eye)."""
from agent import detective, pipeline
ctx = detective.DataContext("data")
qs = ["Total sales in euros for March 2026",
      "Average order value in February 2026",
      "How many orders in June 2026?",
      "Revenue for fiscal Q1 2026",
      "What was revenue last month?",
      "Revenue in Jan 2026",
      "What is the total revenue of the West region?",
      "Top 3 customers by revenue in January 2026"]
for i, q in enumerate(qs):
    c = pipeline.answer(f"P{i}", q, ctx)
    out = (f"{c['answer']:,} {c.get('unit')} conf={c['confidence']} warn={[w['kind'] for w in c['warnings']]}"
           if c["decision"] == "ANSWER" else "REFUSE " + c["refusal"][0]["kind"])
    print(f"{q:<48} -> {out}")
    
for i, q in enumerate(["Revenue in 2026", "Revenue in calendar Q1 2026", "Revenue for the first quarter of 2026"]):
    c = pipeline.answer(f"R{i}", q, ctx)
    print(f"{q:<48} -> {c['decision']} {c.get('answer')} {[r['kind'] for r in c.get('refusal', [])]}")
import glob, os
[os.remove(p) for p in glob.glob("runs/[PR]*.py") + glob.glob("answers/[PR]*.json")]
