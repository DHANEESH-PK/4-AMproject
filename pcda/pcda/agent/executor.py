"""CODE EXECUTION — isolated subprocess, timeout, parse exactly one JSON line."""
import json
import subprocess
import sys
import tempfile


def run(script_path, data_dir=None, cwd=None, timeout=60):
    args = [sys.executable, "-I", str(script_path)] + ([str(data_dir)] if data_dir else [])
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                       cwd=cwd or tempfile.gettempdir())
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip()[-2000:]}
    try:
        return {"ok": True, "result": json.loads(p.stdout.strip().splitlines()[-1])}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Unparseable output: {e}: {p.stdout[-500:]}"}
