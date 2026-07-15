#!/usr/bin/env python3
"""
The social_uploader code is modified to automate the verification script.

Usage: .venv/bin/python scripts/verify_code.py

The inspection is divided into two levels:
  P0 (must pass): import validation, JSON syntax, CLI availability
  P1 (recommended to pass): grep pattern matching to detect old writing methods and common errors
"""

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "social_uploader"

results = []


def record(level, name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((level, name, passed, detail))
    icon = "✅" if passed else "❌"
    print(f"  {icon} [{level}] {name}" + (f" — {detail}" if detail and not passed else ""))


# ──────────────── P0: Must pass ────────────────

print("\n🔍 P0 inspection (must pass)\n")

# P0-1: Full import
try:
    import importlib
    modules = [
        "social_uploader.command_entry",
        "social_uploader.repair_engine",
        "social_uploader.error_classifier",
        "social_uploader.tools.element_finder",
        "social_uploader.tools.browser_manager",
        "social_uploader.tools.upload_profile",
        "social_uploader.uploaders",
        "social_uploader.uploaders.tiktok",
        "social_uploader.uploaders.instagram",
        "social_uploader.uploaders.youtube",
        "social_uploader.uploaders.video_check",
    ]
    failed_imports = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            failed_imports.append(f"{mod}: {e}")
    if failed_imports:
        record("P0", "Full import", False, "; ".join(failed_imports))
    else:
        record("P0", "Full import", True)
except Exception as e:
    record("P0", "Full import", False, str(e))

# P0-2: button_config.json syntax
btn_cfg = SRC_DIR / "button_config.json"
try:
    data = json.loads(btn_cfg.read_text(encoding="utf-8"))
    is_valid = isinstance(data, dict) and all(
        isinstance(v, dict) and all(isinstance(sels, list) for sels in v.values())
        for v in data.values()
    )
    if is_valid:
        record("P0", "button_config.json syntax", True)
    else:
        record("P0", "button_config.json syntax", False, "The structure does not conform to the platform→button name→list format")
except Exception as e:
    record("P0", "button_config.json syntax", False, str(e))

# P0-3: default.json syntax
default_json = SRC_DIR / "profiles" / "default.json"
try:
    json.loads(default_json.read_text(encoding="utf-8"))
    record("P0", "default.json syntax", True)
except Exception as e:
    record("P0", "default.json syntax", False, str(e))

# P0-4: CLI availability
try:
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "social-upload"
    if not venv_python.exists():
        venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "social-upload"
    result = subprocess.run(
        [str(venv_python), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        record("P0", "CLI --help", True)
    else:
        record("P0", "CLI --help", False, result.stderr[:200])
except FileNotFoundError:
    record("P0", "CLI --help", False, "social-upload command not found, may not be installed (pip install -e .)")
except Exception as e:
    record("P0", "CLI --help", False, str(e)[:200])

# ──────────────── P1: Recommended to pass ────────────────

print("\n🔍P1 inspection (recommended to pass)\n")

uploaders_dir = SRC_DIR / "uploaders"
uploader_files = list(uploaders_dir.glob("*.py"))
all_py_files = list(SRC_DIR.rglob("*.py"))

# P1-1: No legacy _should_skip call
old_skip_hits = []
for f in uploader_files:
    if f.name == "__init__.py":
        continue
    content = f.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines(), 1):
        if "_should_skip(" in line and not line.strip().startswith("#") and not line.strip().startswith('"') and not line.strip().startswith("'"):
            old_skip_hits.append(f"{f.name}:{i}")
if old_skip_hits:
    record("P1", "No legacy _should_skip call", False, f"Found on: {', '.join(old_skip_hits)}")
else:
    record("P1", "No legacy _should_skip call", True)

# P1-2: The should_skip call passes 3 parameters (step, resume_from, STEPS)
bad_skip_calls = []
for f in uploader_files:
    if f.name == "__init__.py":
        continue
    content = f.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
            continue
        match = re.search(r'should_skip\(([^)]+)\)', line)
        if match:
            args = [a.strip() for a in match.group(1).split(",")]
            if len(args) != 3:
                bad_skip_calls.append(f"{f.name}:{i} (number of parameters={len(args)})")
if bad_skip_calls:
    record("P1", "should_skip passes 3 parameters", False, f"Incorrect: {', '.join(bad_skip_calls)}")
else:
    record("P1", "should_skip passes 3 parameters", True)

# P1-3: connect_browser unpacked to 4 value
bad_connect = []
for f in all_py_files:
    content = f.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines(), 1):
        if "connect_browser(" in line and "=" in line and "def " not in line and "import " not in line:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            lhs = line.split("=")[0].strip()
            comma_count = lhs.count(",")
            if comma_count < 3 and "connect_browser" not in lhs:
                bad_connect.append(f"{f.relative_to(SRC_DIR)}:{i}")
if bad_connect:
    record("P1", "connect_browser unpacks to 4 value", False, f"Incorrect: {', '.join(bad_connect)}")
else:
    record("P1", "connect_browser unpacks to 4 value", True)

# P1-4: dismiss_interfering_overlays passes 3 parameters
bad_dismiss = []
for f in all_py_files:
    content = f.read_text(encoding="utf-8")
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or "def dismiss" in line or "import " in line:
            continue
        match = re.search(r'dismiss_interfering_overlays\(([^)]+)\)', line)
        if match:
            args = [a.strip() for a in match.group(1).split(",")]
            if len(args) != 3:
                bad_dismiss.append(f"{f.relative_to(SRC_DIR)}:{i} (number of parameters={len(args)})")
if bad_dismiss:
    record("P1", "dismiss_interfering_overlays passes 3 parameters", False, f"Incorrect: {', '.join(bad_dismiss)}")
else:
    record("P1", "dismiss_interfering_overlays passes 3 parameters", True)

# ─────────────── Summary ────────────────

print("\n" + "=" * 50)
p0_pass = all(r[2] for r in results if r[0] == "P0")
p1_pass = all(r[2] for r in results if r[0] == "P1")
total_pass = sum(1 for r in results if r[2])
total = len(results)

if p0_pass and p1_pass:
    print(f"🎉 All passed ({total_pass}/{total})")
    sys.exit(0)
elif p0_pass:
    failed_p1 = [r[1] for r in results if r[0] == "P1" and not r[2]]
    print(f"⚠️ All P0 passed, P1 failed {len(failed_p1)} items: {', '.join(failed_p1)}")
    sys.exit(1)
else:
    failed_p0 = [r[1] for r in results if r[0] == "P0" and not r[2]]
    print(f"❌ P0 has {len(failed_p0)} items that failed (must be repaired): {', '.join(failed_p0)}")
    sys.exit(2)
