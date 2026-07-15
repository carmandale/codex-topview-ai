"""Automatic repair - core module: logging + page snapshot + repair recommendation

[What is this file responsible for]
1. Record "success/failure" log after each step of the script execution
2. Take a snapshot of the page when it fails (extract all button information)
3. Analyze which button may be the target based on the snapshot and recommend repair commands

【Things you may want to change】
- STEP_KEYWORDS dictionary: define what each button "looks like" (keyword matching)
- suggest_selectors() function: fix recommended output format
- _generate_selectors_for_element(): Rules for generating selectors from button information
"""

import json
import logging
import os
import sys
import time
import string
import random
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_SNIPPET_CHARS = 1500
_LOG_DIR = Path.home() / ".social_uploader"


def generate_run_id():
    """Generate a random 8-digit run_id."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=8))


def _ensure_log_dir():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_step(step, status, **kwargs):
    """Output a line of JSON to stderr (for Agent to parse), while retaining emoji logs to stdout.

    Success example: {"step":"navigate","status":"ok","time_s":0.8}
    Failure example: {"step":"find_element","status":"fail","error":"selector_not_found",...}
    """
    record = {"step": step, "status": status, **kwargs}
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr)

    if status == "ok":
        logger.info(f"  ✅ [{step}] Completed" + (f" ({kwargs.get('detail', '')})" if kwargs.get("detail") else ""))
    elif status == "fail":
        err = kwargs.get("error", "unknown")
        logger.error(f"  ❌ [{step}] failed — {err}")


def log_diag_line(run_id, platform, step, error, **hints):
    """Output the DIAG| index line to stdout for Agent detection to trigger repair.

    When error=recipe_step_failed, additional HINT| lines are output to help the Agent reason about repair solutions.
    """
    diag_parts = [f"DIAG|run_id={run_id}|platform={platform}|step={step}|error={error}"]
    for k, v in hints.items():
        diag_parts[0] += f"|{k}={v}"
    print(diag_parts[0])

    if error == "recipe_step_failed":
        failed_step = hints.get("failed_step", "")
        semantic_hint = hints.get("semantic_hint", "")
        recipe_key = hints.get("recipe_key", "schedule_recipe")
        if semantic_hint:
            print(f"HINT|The target of this step: {semantic_hint}")
        if failed_step:
            print(f"HINT|Fix command template: social-upload fix-recipe --target {platform} --recipe {recipe_key} --step {failed_step} --selector \"new selector\"")
        print(f"HINT|DOM snapshot saved: ~/.social_uploader/detail_{run_id}.jsonl")


def write_summary(run_id, platform, step, error, url, **extra):
    """Append to ~/.social_uploader/summary.jsonl (< 500 characters)."""
    _ensure_log_dir()
    record = {
        "run_id": run_id,
        "platform": platform,
        "failed_at": step,
        "error": error,
        "url": url,
        "detail_file": f"detail_{run_id}.jsonl",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **extra,
    }
    line = json.dumps(record, ensure_ascii=False)
    with (_LOG_DIR / "summary.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_success(run_id, platform, elapsed_s=0):
    """Append a success record to ~/.social_uploader/summary.jsonl.

    Shares the same file as write_summary (failure record), distinguished by status field.
    Enables success rate statistics: success_count / total_count.
    """
    _ensure_log_dir()
    record = {
        "run_id": run_id,
        "platform": platform,
        "status": "success",
        "elapsed_s": elapsed_s,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    line = json.dumps(record, ensure_ascii=False)
    with (_LOG_DIR / "summary.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_detail(run_id, step, error, **context):
    """Write ~/.social_uploader/detail_{run_id}.jsonl, including DOM snippet and other contexts."""
    _ensure_log_dir()
    record = {"step": step, "error": error, **context}
    line = json.dumps(record, ensure_ascii=False)
    with (_LOG_DIR / f"detail_{run_id}.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ⚠️ DrissionPage.run_js will package the script into `function(){<代码>}` for execution.
# Therefore, top-level return must be used; it is strictly prohibited to wrap (function(){...})() IIFE in the outer layer.
# Otherwise, the outer function does not return, and the result is always None on the Python side (verified by actual testing).
# Parameters are hardcoded into JS literals via %s / %d templates.
_DOM_EXTRACT_JS = """
var areaSelector = %s;
var maxChars = %d;
var root = document;
if (areaSelector) {
    var area = document.querySelector(areaSelector);
    if (area) root = area;
}

var result = [];

var pageMeta = {_page: true, title: document.title || '', url: location.href};
var h1 = document.querySelector('h1');
if (h1) pageMeta.h1 = (h1.textContent || '').trim().substring(0, 60);
var alert = document.querySelector('[role="alert"],[role="status"]');
if (alert) pageMeta.alert = (alert.textContent || '').trim().substring(0, 80);
result.push(pageMeta);

var diagTags = 'h1,h2,h3,[role="alert"],[role="status"],[role="dialog"]';
var diagEls = root.querySelectorAll(diagTags);
for (var d = 0; d < diagEls.length && d < 5; d++) {
    var de = diagEls[d];
    var dr = de.getBoundingClientRect();
    if (dr.width === 0 && dr.height === 0) continue;
    var dObj = {tag: de.tagName.toLowerCase(), _diag: true};
    var dRole = de.getAttribute('role');
    if (dRole) dObj.role = dRole;
    var dTxt = (de.textContent || '').trim();
    if (dTxt) dObj.text = dTxt.substring(0, 60);
    result.push(dObj);
}

var tags = 'button,input,a,select,textarea,[role="button"],[contenteditable],[data-e2e],svg[aria-label]';
var els = root.querySelectorAll(tags);
var keep = ['id','class','name','type','role','aria-label','data-e2e','placeholder','aria-checked','aria-disabled','href'];
for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    var obj = {tag: el.tagName.toLowerCase()};
    for (var k = 0; k < keep.length; k++) {
        var v = el.getAttribute(keep[k]);
        if (v) {
            if (keep[k] === 'class') {
                v = v.split(/\\s+/).slice(0, 3).join(' ');
            }
            obj[keep[k]] = v;
        }
    }
    var txt = (el.textContent || '').trim();
    if (txt && txt.length > 0) {
        obj.text = txt.substring(0, 15);
    }
    result.push(obj);
}
var out = JSON.stringify(result);
if (out.length > maxChars) {
    out = out.substring(0, maxChars - 14) + '...[truncated]';
}
return out;
"""


def get_dom_snippet(page, area_selector=None, max_chars=MAX_SNIPPET_CHARS):
    """Extract the condensed DOM of the current page and return a JSON string (hard limit max_chars).

    The first is page meta information (title/url/h1/alert), followed by diagnostic elements (h1-h3/alert/dialog),
    Finally, there is the key attribute of the interactive element + textContent.
    """
    area_arg = f'"{area_selector}"' if area_selector else "null"
    js = _DOM_EXTRACT_JS % (area_arg, max_chars)
    try:
        raw = page.run_js(js)
        if not raw:
            return "[]"
        result = str(raw)
        if len(result) > max_chars:
            result = result[:max_chars - 14] + "...[truncated]"
        return result
    except Exception as e:
        return json.dumps({"error": str(e)[:200]}, ensure_ascii=False)


STEP_KEYWORDS = {
    "post_button":      ["post", "publish", "发布", "submit"],
    "upload_icon":      ["upload", "上传", "create", "创建"],
    "upload_dialog":    ["upload", "上传"],
    "upload_menu_item": ["upload video", "上传视频"],
    "file_input":       ["file", "input", "type"],
    "caption_box":      ["caption", "text", "write", "contenteditable", "textbox", "描述", "标题"],
    "title_box":        ["title", "标题"],
    "desc_box":         ["description", "描述", "tell viewers"],
    "create_button":    ["create", "new post", "新帖", "创建"],
    "share_button":     ["share", "分享"],
    "next_button":      ["next", "下一步"],
    "done_button":      ["done", "完成", "publish", "发布"],
    "select_from_computer": ["select", "computer", "从电脑", "从设备"],
}


def _generate_selectors_for_element(el):
    """Generates all possible DrissionPage format selectors for a single DOM element, ordered by priority."""
    candidates = []
    if el.get("data-e2e"):
        candidates.append(f'@data-e2e={el["data-e2e"]}')
    if el.get("id"):
        candidates.append(f'@id={el["id"]}')
    if el.get("aria-label"):
        candidates.append(f'@aria-label={el["aria-label"]}')
    if el.get("name"):
        candidates.append(f'@name={el["name"]}')
    if el.get("text") and len(el["text"].strip()) >= 2:
        candidates.append(f'text:{el["text"].strip()}')
    if el.get("role"):
        tag = el.get("tag", "*")
        candidates.append(f'xpath://{tag}[@role="{el["role"]}"]')
    if el.get("type") and el.get("tag") == "input":
        candidates.append(f'xpath://input[@type="{el["type"]}"]')
    if el.get("placeholder"):
        candidates.append(f'@placeholder={el["placeholder"]}')
    return candidates


def _element_matches_step(el, step):
    """Determine whether a DOM element semantically matches the target of a step."""
    keywords = STEP_KEYWORDS.get(step, [])
    if not keywords:
        return False
    searchable = " ".join([
        el.get("text", ""), el.get("aria-label", ""),
        el.get("data-e2e", ""), el.get("id", ""),
        el.get("name", ""), el.get("role", ""),
        el.get("type", ""), el.get("placeholder", ""),
    ]).lower()
    return any(kw.lower() in searchable for kw in keywords)


def suggest_selectors(run_id):
    """Read the detail file, extract candidate selectors from the DOM fragment, and output the complete fix-selector command."""
    summary_path = _LOG_DIR / "summary.jsonl"
    if not summary_path.exists():
        return "ERROR: summary.jsonl does not exist and there is no failure record"

    last_line = summary_path.read_text(encoding="utf-8").strip().split("\n")[-1]
    try:
        summary = json.loads(last_line)
    except Exception:
        return "ERROR: Parsing the last line of summary.jsonl failed"

    if summary.get("run_id") != run_id:
        return f"ERROR: run_id mismatch (expected {run_id}, actual {summary.get('run_id')})"

    platform = summary.get("platform", "unknown")
    step = summary.get("failed_at", "unknown")
    error = summary.get("error", "unknown")
    # selectors_tried is the button configuration key (such as "post_button") passed in by report_failure,
    # Corresponds to the key of STEP_KEYWORDS; step is the name of the upload step (such as "publish"), and they are different.
    # May contain multiple keys separated by commas (such as "file_input, select_from_computer").
    raw_keys = summary.get("selectors_tried", step)
    button_keys = [k.strip().split("(")[0].strip() for k in raw_keys.split(",")]

    if error != "selector_not_found":
        return f"STEP: {step}\nPLATFORM: {platform}\nERROR: {error}\nNO_FIX: This error type does not support automatic repair of the selector, please notify the user to handle it"

    detail_path = _LOG_DIR / f"detail_{run_id}.jsonl"
    if not detail_path.exists():
        return f"STEP: {step}\nPLATFORM: {platform}\nNO_CANDIDATES: detail file does not exist"

    last_detail = detail_path.read_text(encoding="utf-8").strip().split("\n")[-1]
    try:
        detail = json.loads(last_detail)
    except Exception:
        return f"STEP: {step}\nPLATFORM: {platform}\nNO_CANDIDATES: detail file parsing failed"

    dom_raw = detail.get("dom_snippet", "[]")
    try:
        if isinstance(dom_raw, str):
            clean = dom_raw
            if clean.endswith("...[truncated]"):
                last_bracket = clean.rfind("]")
                if last_bracket > 0:
                    clean = clean[:last_bracket + 1]
            elements = json.loads(clean)
        else:
            elements = dom_raw
    except Exception:
        elements = []

    if not elements:
        return f"STEP: {step}\nPLATFORM: {platform}\nNO_CANDIDATES: DOM fragment is empty or parsing failed"

    def _matches_any_key(el):
        return any(_element_matches_step(el, bk) for bk in button_keys)

    matched = [(el, _generate_selectors_for_element(el)) for el in elements
               if _matches_any_key(el) and _generate_selectors_for_element(el)]

    if not matched:
        return f"STEP: {step}\nPLATFORM: {platform}\nNO_CANDIDATES: No element matching the semantics \"{', '.join(button_keys)}\" was found in the DOM"

    primary_key = button_keys[0]
    lines = [f"STEP: {step}", f"PLATFORM: {platform}", "RUN_ONE:"]
    idx = 1
    for el, sels in matched:
        tag = el.get("tag", "?")
        text = el.get("text", "")[:15]
        label = f"<{tag}>{text}</{tag}>" if text else f"<{tag}>"
        for sel in sels[:2]:
            lines.append(f'  {idx}. social-upload fix-selector --target {platform} --key {primary_key} --selector "{sel}"    # {label}')
            idx += 1
            if idx > 8:
                break
        if idx > 8:
            break

    return "\n".join(lines)


def suggest_patterns(run_id):
    """Read the detail file and recommend text that can be used as a status signal from the _page/_diag entries of the DOM snapshot.

    Used for state_mismatch errors to help the agent find new state detection copy.
    """
    summary_path = _LOG_DIR / "summary.jsonl"
    if not summary_path.exists():
        return "ERROR: summary.jsonl does not exist and there is no failure record"

    last_line = summary_path.read_text(encoding="utf-8").strip().split("\n")[-1]
    try:
        summary = json.loads(last_line)
    except Exception:
        return "ERROR: Parsing the last line of summary.jsonl failed"

    if summary.get("run_id") != run_id:
        return f"ERROR: run_id mismatch (expected {run_id}, actual {summary.get('run_id')})"

    platform = summary.get("platform", "unknown")
    step = summary.get("failed_at", "unknown")
    error = summary.get("error", "unknown")

    if error not in ("state_mismatch", "timeout"):
        return f"STEP: {step}\nPLATFORM: {platform}\nERROR: {error}\nNO_FIX: This error type does not apply to fix-pattern, please use suggest-selectors or notify the user"

    detail_path = _LOG_DIR / f"detail_{run_id}.jsonl"
    if not detail_path.exists():
        return f"STEP: {step}\nPLATFORM: {platform}\nNO_CANDIDATES: detail file does not exist"

    last_detail = detail_path.read_text(encoding="utf-8").strip().split("\n")[-1]
    try:
        detail = json.loads(last_detail)
    except Exception:
        return f"STEP: {step}\nPLATFORM: {platform}\nNO_CANDIDATES: detail file parsing failed"

    dom_raw = detail.get("dom_snippet", "[]")
    try:
        if isinstance(dom_raw, str):
            clean = dom_raw
            if clean.endswith("...[truncated]"):
                last_bracket = clean.rfind("]")
                if last_bracket > 0:
                    clean = clean[:last_bracket + 1]
            elements = json.loads(clean)
        else:
            elements = dom_raw
    except Exception:
        elements = []

    if not elements:
        return f"STEP: {step}\nPLATFORM: {platform}\nNO_CANDIDATES: DOM fragment is empty or parsing failed"

    lines = [f"STEP: {step}", f"PLATFORM: {platform}", f"ERROR: {error}", ""]

    page_meta = [e for e in elements if isinstance(e, dict) and e.get("_page")]
    diag_items = [e for e in elements if isinstance(e, dict) and e.get("_diag")]

    if page_meta:
        pm = page_meta[0]
        lines.append("PAGE_META:")
        lines.append(f"  title: {pm.get('title', '')}")
        lines.append(f"  url: {pm.get('url', '')}")
        if pm.get("h1"):
            lines.append(f"  h1: {pm['h1']}")
        if pm.get("alert"):
            lines.append(f"  alert: {pm['alert']}")
        lines.append("")

    if diag_items:
        lines.append("DIAG_ELEMENTS:")
        for d in diag_items[:5]:
            tag = d.get("tag", "?")
            text = d.get("text", "")
            role = d.get("role", "")
            desc = f"<{tag}"
            if role:
                desc += f' role="{role}"'
            desc += f">{text}</{tag}>"
            lines.append(f"  - {desc}")
        lines.append("")

    text_candidates = []
    for e in elements:
        if not isinstance(e, dict):
            continue
        if e.get("_page") or e.get("_diag"):
            text = e.get("text") or e.get("h1") or e.get("alert") or ""
        else:
            text = e.get("text", "")
        if text and len(text.strip()) >= 3:
            text_candidates.append(text.strip())

    seen = set()
    unique_texts = []
    for t in text_candidates:
        if t not in seen:
            seen.add(t)
            unique_texts.append(t)

    if unique_texts:
        lines.append("CANDIDATE_TEXTS:")
        idx = 1
        for t in unique_texts[:10]:
            lines.append(f'  {idx}. social-upload fix-pattern --target {platform} --step {step} --signal success_signals --value "text:{t}"')
            idx += 1
        lines.append("")
        lines.append("NOTE: 请根据页面语义选择合适的信号类型（success_signals / error_signals / ready_signals 等）")
    else:
        lines.append("NO_CANDIDATES: No text found in the DOM that could be used as a status signal")

    return "\n".join(lines)


def safe_page_url(page, default="page_disconnected"):
    """Get page.url safely and avoid PageDisconnectedError causing the caller to crash."""
    try:
        return page.url or default
    except Exception:
        return default


def report_failure(page, run_id, platform, step, error, url, **extra):
    """One-stop failure reporting: write summary + detail + output DIAG line.

    Automatically extract DOM snippets for post-mortem diagnosis.
    Use error_classifier to mark whether the error can be automatically repaired.
    """
    from social_uploader.error_classifier import classify_error

    strategy = classify_error(error)
    if strategy == "agent_fix":
        logger.info(f"  🔧 Error type [{error}] can be automatically repaired")
    elif strategy == "notify_user":
        logger.warning(f"  👤 Error type [{error}] requires user intervention")
    elif strategy == "wait_retry":
        logger.info(f"  ⏳ Error type [{error}] It is recommended to wait and try again")
    else:
        logger.warning(f"  ⚠️ Error type [{error}] requires manual judgment")

    dom_snippet = None
    try:
        dom_snippet = get_dom_snippet(page)
    except Exception:
        dom_snippet = "[]"

    write_summary(
        run_id, platform, step, error, url,
        strategy=strategy,
        **{k: v for k, v in extra.items() if k != "dom_snippet"},
    )

    detail_ctx = {k: v for k, v in extra.items()}
    if dom_snippet:
        detail_ctx["dom_snippet"] = dom_snippet
    write_detail(run_id, step, error, **detail_ctx)

    diag_hints = {k: v for k, v in extra.items()
                  if k in ("failed_step", "semantic_hint", "recipe_key")}
    log_diag_line(run_id, platform, step, error, **diag_hints)
