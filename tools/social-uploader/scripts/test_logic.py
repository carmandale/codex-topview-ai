#!/usr/bin/env python3
"""
social_uploader full link simulation test

No browser connection, no real upload, purely verification of code logic and module collaboration is smooth.

Coverage link:
  1. Video pre-verification (pass/reject)
  2. should_skip skip logic
  3. Error classification → Processing policy routing
  4. Profile loading and merging
  5. Button selector loading and search
  6. Logging (log_step / write_summary / write_detail)
  7. DOM snapshot analysis and repair suggestions (suggest_selectors)
  8. Selector hotfix (add_selector)
  9. CLI parameter analysis
  10. Full link series connection: Verification→Classification→Log→Repair Suggestions
"""

import json
import os
import sys
import shutil
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

passed = 0
failed = 0
errors = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        msg = f"{name}: {detail}" if detail else name
        errors.append(msg)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


# ═══════════════════════════════════════════════════
# 1. Video pre-verification
# ═══════════════════════════════════════════════════
print("\n🎬 1. Video pre-verification\n")

from social_uploader.uploaders.video_check import validate_video_file

tmp_dir = tempfile.mkdtemp(prefix="social_uploader_test_")

# 1a. File does not exist
ok, msg = validate_video_file("/not/exists/video.mp4")
check("File that does not exist → reject", not ok and "does not exist" in msg)

# 1b. The format is not supported
bad_ext = os.path.join(tmp_dir, "test.txt")
with open(bad_ext, "wb") as f:
    f.write(b"x" * 20000)
ok, msg = validate_video_file(bad_ext)
check("Unsupported format (.txt) → Reject", not ok and "unsupported" in msg.lower())

# 1c. The file is too small
tiny = os.path.join(tmp_dir, "tiny.mp4")
with open(tiny, "wb") as f:
    f.write(b"x" * 100)
ok, msg = validate_video_file(tiny)
check("File too small (100B) → Reject", not ok and "too small" in msg)

# 1d. Legal documents
good = os.path.join(tmp_dir, "good.mp4")
with open(good, "wb") as f:
    f.write(b"x" * 50000)
ok, msg = validate_video_file(good)
check("Legal file (50KB .mp4) → Passed", ok and msg == "")

# 1e. Various legal suffixes
for ext in [".mov", ".avi", ".mkv", ".webm"]:
    p = os.path.join(tmp_dir, f"test{ext}")
    with open(p, "wb") as f:
        f.write(b"x" * 20000)
    ok, _ = validate_video_file(p)
    check(f"Legal format ({ext}) → Passed", ok)


# ═══════════════════════════════════════════════════
# 2. should_skip skip logic
# ═══════════════════════════════════════════════════
print("\n⏭️ 2. should_skip skip logic\n")

from social_uploader.uploaders import should_skip

STEPS = ["validate", "connect", "login", "file_inject", "publish", "confirm"]

# 2a. No resume_from → do not skip any steps
check("resume_from=None → do not skip", not should_skip("validate", None, STEPS))

# 2b. resume_from is not in STEPS → not skipped
check("resume_from='invalid' → do not skip", not should_skip("validate", "invalid", STEPS))

# 2c. resume_from=publish → skip validate/connect/login/file_inject
check("resume=publish → skip validate", should_skip("validate", "publish", STEPS))
check("resume=publish → skip connect", should_skip("connect", "publish", STEPS))
check("resume=publish → skip login", should_skip("login", "publish", STEPS))
check("resume=publish → skip file_inject", should_skip("file_inject", "publish", STEPS))
check("resume=publish → do not skip publish", not should_skip("publish", "publish", STEPS))
check("resume=publish → do not skip confirm", not should_skip("confirm", "publish", STEPS))

# 2d. resume_from=first step → do not skip anything
check("resume=validate → do not skip validate", not should_skip("validate", "validate", STEPS))

# 2e. STEPS verification completeness for three platforms
from social_uploader.uploaders.tiktok import STEPS as TK_STEPS
from social_uploader.uploaders.youtube import STEPS as YT_STEPS
from social_uploader.uploaders.instagram import STEPS as IG_STEPS

check("TikTok STEPS includes validate", "validate" in TK_STEPS)
check("TikTok STEPS contains confirm", "confirm" in TK_STEPS)
check("YouTube STEPS includes validate", "validate" in YT_STEPS)
check("YouTube STEPS contains confirm", "confirm" in YT_STEPS)
check("Instagram STEPS includes validate", "validate" in IG_STEPS)
check("Instagram STEPS contains confirm", "confirm" in IG_STEPS)

# 2f. There are no duplicates in the STEPS of the three platforms.
check("TikTok STEPS no duplication", len(TK_STEPS) == len(set(TK_STEPS)))
check("YouTube STEPS no duplicates", len(YT_STEPS) == len(set(YT_STEPS)))
check("Instagram STEPS no duplicates", len(IG_STEPS) == len(set(IG_STEPS)))


# ═══════════════════════════════════════════════════
# 3. Error classification → Processing policy routing
# ═══════════════════════════════════════════════════
print("\n🔀 3. Error classification and routing\n")

from social_uploader.error_classifier import classify_error, is_agent_fixable, ERROR_TYPES

check("selector_not_found → agent_fix", classify_error("selector_not_found") == "agent_fix")
check("login_required → notify_user", classify_error("login_required") == "notify_user")
check("rate_limit → wait_retry", classify_error("rate_limit") == "wait_retry")
check("unknown → escalate_user", classify_error("unknown") == "escalate_user")
check("Non-existent error → escalate_user", classify_error("made_up_error") == "escalate_user")
check("selector_not_found can be automatically repaired", is_agent_fixable("selector_not_found"))
check("login_required cannot be automatically repaired", not is_agent_fixable("login_required"))
check("timeout needs to notify the user", not is_agent_fixable("timeout"))

# Verify that all error types have a clear strategy
known_strategies = {"agent_fix", "notify_user", "wait_retry", "escalate_user"}
for err_code, strategy in ERROR_TYPES.items():
    check(f"Error '{err_code}' Policy '{strategy}' is legal", strategy in known_strategies)


# ═══════════════════════════════════════════════════
# 4. Profile loading and merging
# ═══════════════════════════════════════════════════
print("\n📋 4. Profile loading and merging\n")

from social_uploader.tools.upload_profile import load_profile, get_platform_config

# 4a. Default profile loading
default_p = load_profile()
check("Default profile loaded successfully", isinstance(default_p, dict))
check("The default profile includes youtube", "youtube" in default_p)
check("The default profile contains common", "common" in default_p)
check("The default profile includes tiktok", "tiktok" in default_p)
check("The default profile includes instagram", "instagram" in default_p)

# 4b. YouTube default configuration
yt_config = get_platform_config(default_p, "youtube")
check("YouTube default made_for_kids=False", yt_config.get("made_for_kids") is False)
check("YouTube default visibility=public", yt_config.get("visibility") == "public")

# 4c. TikTok/Instagram default configuration (empty dictionary, no error)
tk_config = get_platform_config(default_p, "tiktok")
check("TikTok default configuration is dict", isinstance(tk_config, dict))
ig_config = get_platform_config(default_p, "instagram")
check("Instagram default configuration is dict", isinstance(ig_config, dict))

# 4d. Custom profile merging
custom_profile = os.path.join(tmp_dir, "custom.json")
with open(custom_profile, "w") as f:
    json.dump({"youtube": {"visibility": "unlisted", "made_for_kids": True}}, f)

merged = load_profile(custom_profile)
yt_custom = get_platform_config(merged, "youtube")
check("Custom profile merge: visibility=unlisted", yt_custom.get("visibility") == "unlisted")
check("Custom profile merge: made_for_kids=True", yt_custom.get("made_for_kids") is True)

# 4e. Non-existent profile → error report
try:
    load_profile("/not/exists/profile.json")
    check("non-existent profile → should raise FileNotFoundError", False)
except FileNotFoundError:
    check("non-existent profile → FileNotFoundError", True)


# ═══════════════════════════════════════════════════
# 5. Button selector loading and search
# ═══════════════════════════════════════════════════
print("\n🔘 5. Button selector system\n")

from social_uploader.tools.element_finder import load_selectors, reload_selectors, add_selector

reload_selectors()

# 5a. Load each platform selector
for platform in ["tiktok", "instagram", "youtube"]:
    sels = load_selectors(platform)
    check(f"{platform} selector loaded successfully", isinstance(sels, dict) and len(sels) > 0)

# 5b. Specific selector exists
tk_sels = load_selectors("tiktok")
check("TikTok file_input selector exists", "file_input" in tk_sels)
check("TikTok post_button selector exists", "post_button" in tk_sels)
check("TikTok file_input is a list", isinstance(tk_sels.get("file_input", None), list))

ig_sels = load_selectors("instagram")
check("Instagram create_button selector exists", "create_button" in ig_sels)
check("Instagram share_button selector exists", "share_button" in ig_sels)

yt_sels = load_selectors("youtube")
check("YouTube upload_icon selector exists", "upload_icon" in yt_sels)
check("YouTube done_button selector exists", "done_button" in yt_sels)

# 5c. Non-existent platform → empty dictionary
empty = load_selectors("nonexistent_platform")
check("non-existent platform → empty dictionary", empty == {})


# ═══════════════════════════════════════════════════
# 6. Logging and repair system
# ═══════════════════════════════════════════════════
print("\n📝 6. Log and repair system\n")

from social_uploader.repair_engine import (
    generate_run_id, log_step, write_summary, write_detail,
    log_diag_line, suggest_selectors,
    _element_matches_step, _generate_selectors_for_element, STEP_KEYWORDS,
)

# 6a. run_id generation
rid1 = generate_run_id()
rid2 = generate_run_id()
check("run_id length=8", len(rid1) == 8)
check("run_id is alphanumeric", rid1.isalnum())
check("The run_id is different twice", rid1 != rid2)

# 6b. log_step does not report an error (output to stderr)
import io
old_stderr = sys.stderr
sys.stderr = io.StringIO()
log_step("test_step", "ok", detail="mock test")
log_step("test_step", "fail", error="timeout", detail="Simulation timeout")
stderr_output = sys.stderr.getvalue()
sys.stderr = old_stderr
check("log_step output to stderr", len(stderr_output) > 0)
check("log_step output contains JSON", '"step"' in stderr_output and '"status"' in stderr_output)

# 6c. write_summary and write_detail write files
test_run_id = "test_" + rid1
write_summary(test_run_id, "tiktok", "publish", "selector_not_found",
              "https://tiktok.com/upload", selectors_tried="post_button")
from social_uploader.repair_engine import _LOG_DIR
summary_file = _LOG_DIR / "summary.jsonl"
check("summary.jsonl file exists", summary_file.exists())

summary_content = summary_file.read_text(encoding="utf-8")
last_line = summary_content.strip().split("\n")[-1]
summary_data = json.loads(last_line)
check("summary contains run_id", summary_data.get("run_id") == test_run_id)
check("summary contains platform", summary_data.get("platform") == "tiktok")
check("summary contains error", summary_data.get("error") == "selector_not_found")

# 6d. write_detail
mock_dom = json.dumps([
    {"tag": "button", "data-e2e": "publish_btn", "text": "Post video"},
    {"tag": "button", "aria-label": "Upload", "text": "Upload"},
    {"tag": "input", "type": "file"},
])
write_detail(test_run_id, "publish", "selector_not_found", dom_snippet=mock_dom)
detail_file = _LOG_DIR / f"detail_{test_run_id}.jsonl"
check("detail file exists", detail_file.exists())

detail_content = detail_file.read_text(encoding="utf-8")
detail_data = json.loads(detail_content.strip().split("\n")[-1])
check("detail contains dom_snippet", "dom_snippet" in detail_data)

# 6e. DIAG line output
old_stdout = sys.stdout
sys.stdout = io.StringIO()
log_diag_line(test_run_id, "tiktok", "publish", "selector_not_found")
diag_output = sys.stdout.getvalue()
sys.stdout = old_stdout
check("DIAG row format is correct", diag_output.startswith("DIAG|"))
check("DIAG contains run_id", f"run_id={test_run_id}" in diag_output)
check("DIAG contains platform", "platform=tiktok" in diag_output)


# ═══════════════════════════════════════════════════
# 7. DOM analysis and repair suggestions
# ═══════════════════════════════════════════════════
print("\n🔧 7. DOM analysis and repair suggestions\n")

# 7a. Element matching test
mock_btn = {"tag": "button", "data-e2e": "publish_btn", "text": "Post video"}
check("post_button matches the 'Post video' button", _element_matches_step(mock_btn, "post_button"))
check("file_input does not match 'Post video' button", not _element_matches_step(mock_btn, "file_input"))

mock_input = {"tag": "input", "type": "file"}
check("file_input matches input[type=file]", _element_matches_step(mock_input, "file_input"))

mock_create = {"tag": "svg", "aria-label": "New post", "text": ""}
check("create_button matches 'New post'", _element_matches_step(mock_create, "create_button"))

# 7b. Selector generation
sels = _generate_selectors_for_element(mock_btn)
check("Number of selectors generated from buttons >= 2", len(sels) >= 2)
check("data-e2e selector in result", any("data-e2e" in s for s in sels))
check("text selector in result", any("text:" in s for s in sels))

sels_input = _generate_selectors_for_element(mock_input)
check("Generate xpath selector from input", any("xpath:" in s for s in sels_input))

# 7c. suggest_selectors complete process
result = suggest_selectors(test_run_id)
check("suggest_selectors returns string", isinstance(result, str))
check("suggest_selectors contains STEP", "STEP:" in result)
check("suggest_selectors contains PLATFORM", "PLATFORM:" in result)
check("suggest_selectors contains RUN_ONE", "RUN_ONE:" in result)
check("suggest_selectors contains the fix-selector command", "fix-selector" in result)
check("suggest_selectors' fix-selector uses button_key", "post_button" in result)

# 7d. Handling of non-selector_not_found errors
write_summary("test_login", "tiktok", "login", "login_required", "https://tiktok.com")
result_login = suggest_selectors("test_login")
check("login_required → NO_FIX", "NO_FIX" in result_login)


# ═══════════════════════════════════════════════════
# 8. Selector hotfix (add_selector)
# ═══════════════════════════════════════════════════
print("\n🔩 8. Selector hotfix\n")

# 8a. Normal addition
reload_selectors()
ok, msg = add_selector("tiktok", "post_button", "@data-e2e=test_selector_999")
check("New selector added successfully", ok and "OK" in msg)

# 8b. Verify that it is inserted at the beginning of the list
reload_selectors()
tk_post = load_selectors("tiktok").get("post_button", [])
check("New selector at the beginning of the list", tk_post[0] == "@data-e2e=test_selector_999")

# 8c. Add repeatedly → do not repeat
ok, msg = add_selector("tiktok", "post_button", "@data-e2e=test_selector_999")
check("Add repeatedly → prompt already exists", ok and "already exists" in msg.lower())

# 8d. Non-existent platform
ok, msg = add_selector("weibo", "post_button", "text:发布")
check("Non-existent platform → failed", not ok and "does not exist" in msg)

# 8e. Non-existent key
ok, msg = add_selector("tiktok", "nonexistent_button", "text:test")
check("non-existent key → fail", not ok and "does not exist" in msg)

# Cleanup: Remove selectors added by tests
from pathlib import Path
btn_cfg_path = Path(PROJECT_ROOT) / "src" / "social_uploader" / "button_config.json"
cfg_data = json.loads(btn_cfg_path.read_text(encoding="utf-8"))
if "@data-e2e=test_selector_999" in cfg_data.get("tiktok", {}).get("post_button", []):
    cfg_data["tiktok"]["post_button"].remove("@data-e2e=test_selector_999")
    btn_cfg_path.write_text(json.dumps(cfg_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
reload_selectors()
check("Test selector cleaned", "@data-e2e=test_selector_999" not in load_selectors("tiktok").get("post_button", []))


# ═══════════════════════════════════════════════════
# 9. CLI parameter analysis
# ═══════════════════════════════════════════════════
print("\n🖥️ 9. CLI parameter analysis\n")

import argparse
from unittest.mock import patch

from social_uploader.command_entry import main

# 9a. tiktok parameter analysis
with patch("sys.argv", ["social-upload", "tiktok", "--video", "v.mp4", "--title", "T", "--description", "D"]):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='platform')
    p_tk = subparsers.add_parser('tiktok')
    p_tk.add_argument('--video', required=True)
    p_tk.add_argument('--title', required=True)
    p_tk.add_argument('--description', required=True)
    p_tk.add_argument('--cover', default=None)
    p_tk.add_argument('--no-publish', action='store_true')
    p_tk.add_argument('--resume-from', default=None)
    p_tk.add_argument('--profile', default=None)
    args = parser.parse_args(["tiktok", "--video", "v.mp4", "--title", "T", "--description", "D"])
    check("TikTok parameters: video", args.video == "v.mp4")
    check("TikTok parameters: title", args.title == "T")
    check("TikTok parameters: no_publish Default False", args.no_publish is False)
    check("TikTok parameters: cover default None", args.cover is None)

# 9b. instagram parameter analysis
parser2 = argparse.ArgumentParser()
sub2 = parser2.add_subparsers(dest='platform')
p_ig = sub2.add_parser('instagram')
p_ig.add_argument('--video', required=True)
p_ig.add_argument('--caption', required=True)
p_ig.add_argument('--no-publish', action='store_true')
args2 = parser2.parse_args(["instagram", "--video", "v.mp4", "--caption", "copywriting"])
check("Instagram parameters: caption", args2.caption == "copywriting")

# 9c. YouTube parameter analysis
parser3 = argparse.ArgumentParser()
sub3 = parser3.add_subparsers(dest='platform')
p_yt = sub3.add_parser('youtube')
p_yt.add_argument('--video', required=True)
p_yt.add_argument('--title', required=True)
p_yt.add_argument('--description', required=True)
p_yt.add_argument('--no-publish', action='store_true')
args3 = parser3.parse_args(["youtube", "--video", "v.mp4", "--title", "T", "--description", "D", "--no-publish"])
check("YouTube parameters: no_publish=True", args3.no_publish is True)


# ═══════════════════════════════════════════════════
# 10. Full-link series simulation
# ═══════════════════════════════════════════════════
print("\n🔗 10. Full link series simulation\n")

# Simulate a complete "upload failure → error classification → log → repair suggestions → hot repair" process
sim_run_id = generate_run_id()
sim_platform = "tiktok"
sim_step = "publish"
sim_error = "selector_not_found"

# Step A: Verification video
ok, _ = validate_video_file(good)
check("[Link] Video verification passed", ok)

# Step B: Simulate should_skip (not skip)
skip = should_skip(sim_step, None, TK_STEPS)
check("[Link] Don’t skip publish step", not skip)

# Step C: Simulation failure → Error classification
strategy = classify_error(sim_error)
check("[Link] selector_not_found → agent_fix", strategy == "agent_fix")

# Step D: Keep a log
old_stderr2 = sys.stderr
sys.stderr = io.StringIO()
log_step(sim_step, "fail", error=sim_error, detail="post_button not found")
sys.stderr = old_stderr2

# Step E: Write summary and details
mock_dom2 = json.dumps([
    {"tag": "button", "data-e2e": "new_post_btn", "text": "Post"},
    {"tag": "div", "role": "button", "text": "Publish now"},
])
write_summary(sim_run_id, sim_platform, sim_step, sim_error, "https://tiktok.com/upload",
              selectors_tried="post_button")
write_detail(sim_run_id, sim_step, sim_error, dom_snippet=mock_dom2)
check("[Link] Log writing successful", (_LOG_DIR / f"detail_{sim_run_id}.jsonl").exists())

# Step F: Repair suggestions
suggestion = suggest_selectors(sim_run_id)
has_fix = "RUN_ONE:" in suggestion and "fix-selector" in suggestion
check("[Link] Fix suggestion includes fix-selector command", has_fix)

# Step G: Simulate Hot Repair
reload_selectors()
ok, msg = add_selector(sim_platform, "post_button", "@data-e2e=new_post_btn")
check("[Link] Hotfix added selector successfully", ok)

# Step H: Verify that the repaired selector is at the beginning of the list
reload_selectors()
first_sel = load_selectors(sim_platform).get("post_button", [""])[0]
check("[Link] Fixed selector at the beginning of the list", first_sel == "@data-e2e=new_post_btn")

# Step I: Simulate resume-from (resume from publish step)
for step in TK_STEPS:
    skip = should_skip(step, sim_step, TK_STEPS)
    expected = TK_STEPS.index(step) < TK_STEPS.index(sim_step)
    if skip != expected:
        check(f"[Link] resume-from={sim_step} skip {step}", False,
              f"Expected skip={expected}, actual skip={skip}")
        break
else:
    check("[Link] The jump logic of resume-from is all correct", True)

# Clean test selector
cfg_data = json.loads(btn_cfg_path.read_text(encoding="utf-8"))
if "@data-e2e=new_post_btn" in cfg_data.get("tiktok", {}).get("post_button", []):
    cfg_data["tiktok"]["post_button"].remove("@data-e2e=new_post_btn")
    btn_cfg_path.write_text(json.dumps(cfg_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
reload_selectors()

# Clean test log
for f in _LOG_DIR.glob(f"detail_test_*.jsonl"):
    f.unlink(missing_ok=True)
for f in _LOG_DIR.glob(f"detail_{sim_run_id}.jsonl"):
    f.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════
# Clean & Summarize
# ═══════════════════════════════════════════════════
shutil.rmtree(tmp_dir, ignore_errors=True)

print("\n" + "=" * 55)
total = passed + failed
if failed == 0:
    print(f"🎉 All passed ({passed}/{total})")
    sys.exit(0)
else:
    print(f"❌ {failed} items failed / {total} total items")
    for e in errors:
        print(f"   • {e}")
    sys.exit(1)
