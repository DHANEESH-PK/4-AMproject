# Proof-Carrying Data Analyst — HNX26PSI08 starter

Working baseline for your layout. Every answered number ships with a standalone
script a judge can run; every unanswerable question is refused with a reason.

```
pip install -r requirements.txt
python data/generate_data.py     # rebuild messy data + answer key (seed 42)
python eval.py                   # run all 24 questions, score vs ground truth
python runs/Q01.py               # judge's view: re-run any proof script on its own
python probe.py                  # throw new phrasings at it (no answer key)
```

Current score: 10/10 answers correct, 14/14 refusals correct, 5/5 required warnings,
10/10 scripts re-run identically (also verified on pandas 2.2.3 from a copied folder),
**0 confident-wrong answers**.

## Your layout → files

| Your box | File | What it actually does |
|---|---|---|
| Question Analyzer (ambiguity / data need / intent) | `agent/analyzer.py` | Text → JSON spec. Whitelist parser: any word it can't map → refuse. Optional LLM front-end in `agent/llm_parser.py`. |
| Data Detective (dupes / missing / unit-date) | `agent/detective.py` + `agent/cleaning.py` | Profiles data once at load, then checks only the rows *this* question touches. |
| Truth Gate | `agent/truth_gate.py` | Deterministic rules → ANSWER or REFUSE, plus a confidence score. No LLM vote. |
| Code Generator | `agent/codegen.py` | Template + `cleaning.py` pasted in verbatim → standalone script in `runs/`. |
| Code Execution | `agent/executor.py` | Subprocess, `python -I`, timeout, one JSON line out. |
| Result Check + Auditor + Final Verifier | `agent/verifier.py`, `agent/auditor.py` | Sanity check → **independent re-implementation** (stdlib csv, no shared code) must agree → re-run from a different folder must match → SHA-256 of the code. |
| Answer + Code + Evidence + Warnings + Confidence | `answers/<id>.json` | One card per question. |

## Changes I made to your layout (and why)

1. **The LLM never writes the proof code.** It only fills in the spec; tested templates write the code. If an LLM writes free-form pandas, sooner or later it writes code that runs but is wrong, and the verifier can't tell.
2. **Auditor = a second, independent implementation.** "Ask another LLM to review" is not verification. Two different implementations that agree is.
3. **Ambiguity can refuse straight away.** "Q2" (fiscal or calendar?) goes to REFUSAL without touching the data.
4. **The Detective works per question.** A June date problem must not block a January answer, and an H1 total isn't affected by a May/June mix-up.
5. **If the code fails or checks fail, it refuses.** It never falls back to an LLM's guess.

## Traps planted (problem statement → data)

| Trap | Where | Expected behaviour |
|---|---|---|
| Units $/€ | eu_shop amounts `€1.234,50`, `1.234,50 EUR`; `fx_rates.csv` | Convert at monthly rate; flag the assumption if no currency was asked for (Q14) |
| Ambiguous dates | us_shop MM/DD, eu_shop DD/MM, legacy undocumented `05/06/2026` | Refuse June/May (Q06, A05); answer H1 (Q07) |
| Duplicates | 25 re-exported rows | Count = 63, not 63+dupes (Q02) |
| Tables contradict | stale Feb in `monthly_summary.csv`; 3 customers in two regions | Warn + use system of record (Q03); refuse North (Q15) |
| Missing data | 3 blanks in March (5%), 12 in April (19%) | Answer March + lower-bound warning (Q04); refuse April (Q05) |
| No valid answer | Antarctica, December, churn, shipping, 2026 full year | Refuse; never report 0 (Q08, Q09, Q11, A07, A08) |
| Designed to trick | "why", "last month", "top 3", "fiscal Q1 2026" | Refuse (Q10, A02–A04) |

## Where to get data

**Use the synthetic set as your main demo.** It's the only data where you know the true
answer, so it's the only data where you can *prove* the agent is right. Then show it on one
real dataset to prove it isn't overfit:

- **UCI Online Retail II** (UCI ML Repository / Kaggle): about 1M UK retail transactions, GBP, cancellations as `C` invoices with negative quantities, missing CustomerIDs, duplicates. The best real-world trap dataset for this brief.
- **Olist Brazilian E-Commerce** (Kaggle): 9 linked tables (orders, items, payments, reviews, customers, sellers), BRL, real nulls and multi-table joins. Good for "multiple tables and documents".
- **FX rates:** ECB reference rates via the Frankfurter API (free, no key) or the ECB Data Portal. Freeze a CSV snapshot into `data/`. A live API breaks re-runnability.
- **Avoid** AdventureWorks/Contoso. They're too clean to show anything.

## Known gaps (fix before the demo, in this order)

1. **Numbers inside refusal messages** (e.g. "ranges by up to 5,731.49 USD") don't come with a proof script yet. Either give each refusal an evidence script or take the figures out.
2. **The LLM path is untested.** There was no API key in the build environment. Test `PCDA_USE_LLM=1` with your key.
3. **The analyzer only handles one metric over one period/region.** Rankings, breakdowns and date ranges are refused, not answered. That's the right failure mode, but it limits coverage.
4. **The eval is self-graded.** I wrote both the answer key and the agent. Get a teammate who hasn't read the code to write 20 new questions and run `probe.py`.
