#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path

def main():
    try:
        payload=json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("stop_hook_active") is True:
        return 0
    root=Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()
    agentflow=shutil_which("agentflow")
    if not agentflow:
        return 0
    cp=subprocess.run([agentflow,"hook-stop",str(root)],input=json.dumps(payload),text=True,capture_output=True)
    if cp.stdout:
        sys.stdout.write(cp.stdout)
    if cp.stderr:
        sys.stderr.write(cp.stderr)
    return cp.returncode

def shutil_which(name):
    import shutil
    return shutil.which(name)

if __name__=="__main__":
    raise SystemExit(main())
