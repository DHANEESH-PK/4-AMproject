"""
RESULT CHECK + FINAL VERIFIER.
  1. Result check : value is finite, right type, plausible magnitude.
  2. Auditor match: independent implementation agrees within 0.01.
  3. Re-run      : fresh process, DIFFERENT working directory, explicit data path
                   -> identical output (proves no hidden state / cwd dependency).
"""
import hashlib
import math
import tempfile

from . import auditor, executor


def result_check(result, spec):
    v = result.get("value")
    if not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)):
        return False, "Value is not a finite number."
    if spec["metric"] in ("sum", "count", "avg") and v < 0:
        return False, "Negative value for a non-negative metric."
    if result.get("rows_used", 0) == 0:
        return False, "Zero rows used — an empty sum is not an answer."
    return True, "ok"


def verify(script_path, spec, first_result, data_dir):
    checks = {}
    ok, msg = result_check(first_result, spec)
    checks["result_check"] = {"pass": ok, "detail": msg}

    try:
        indep = auditor.audit(spec, data_dir)
        agree = abs(float(indep) - float(first_result["value"])) <= 0.01
        checks["auditor"] = {"pass": agree, "independent_value": indep}
    except Exception as e:  # noqa: BLE001
        checks["auditor"] = {"pass": False, "detail": f"auditor crashed: {e}"}

    with tempfile.TemporaryDirectory() as tmp:
        rerun = executor.run(script_path, data_dir=data_dir, cwd=tmp)
    same = rerun.get("ok") and rerun["result"] == first_result
    checks["rerun"] = {"pass": bool(same)}

    code = open(script_path, "rb").read()
    checks["sha256"] = hashlib.sha256(code).hexdigest()
    checks["all_pass"] = all(c["pass"] for k, c in checks.items() if isinstance(c, dict))
    return checks
