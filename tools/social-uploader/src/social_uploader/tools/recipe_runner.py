"""Recipe Executor — Reads a JSON recipe and performs browser interaction step by step.

Three layers of step-by-step coverage:
  Tier 1: Execute directly using the selector in the recipe
  Tier 2: When the selector fails, the dom_heuristic heuristic search is called, and the recipe is automatically written back after success.
  Tier 3: When all fails, enhanced DIAG is output and handed over to Agent (OpenClaw) to intervene.

Supported action types:
  click — Click on an element (CSS selector / JS querySelector)
  set_value — Set input value using nativeSet
  click_and_set — click first then set value (for custom dropdown/calendar)
  pick_option — Select by text in a list of options
  wait — wait for an element to appear
"""

import json
import logging
import re
import sys
import time
from pathlib import Path

from social_uploader.tools.dom_heuristic import (
    _scan_dom,
    discover_for_click,
    discover_for_value,
)
from social_uploader.tools.browser_manager import (
    cdp_click_at,
    cdp_press_key,
    cdp_type_text,
)

logger = logging.getLogger(__name__)

_PATTERNS_PATH = Path(__file__).resolve().parent.parent / "state_patterns.json"


def _load_patterns():
    try:
        return json.loads(_PATTERNS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read state_patterns.json: {e}")
        return {}


def _save_patterns(data):
    try:
        _PATTERNS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"Failed to write state_patterns.json: {e}")


def load_recipe(platform, recipe_key):
    """Loads the specified recipe from state_patterns.json."""
    data = _load_patterns()
    recipe = data.get(platform, {}).get(recipe_key)
    if not recipe:
        logger.warning(f"Recipe {platform}.{recipe_key} does not exist")
        return None
    return recipe


def _resolve_variables(text, variables):
    """Replace the template variable ${key} with the actual value."""
    if not isinstance(text, str):
        return text
    for k, v in variables.items():
        text = text.replace(f"${{{k}}}", str(v))
    return text


def _resolve_step(step, variables):
    """Perform variable substitution (deep copy) on all string fields in step."""
    resolved = {}
    for k, v in step.items():
        if isinstance(v, str):
            resolved[k] = _resolve_variables(v, variables)
        elif isinstance(v, dict):
            inner = {}
            for sk, sv in v.items():
                if isinstance(sv, str):
                    inner[sk] = _resolve_variables(sv, variables)
                elif isinstance(sv, list):
                    inner[sk] = [_resolve_variables(item, variables) if isinstance(item, str) else item
                                 for item in sv]
                else:
                    inner[sk] = sv
            resolved[k] = inner
        elif isinstance(v, list):
            resolved[k] = [_resolve_variables(item, variables) if isinstance(item, str) else item
                           for item in v]
        else:
            resolved[k] = v
    return resolved


def _get_selectors(step):
    """Extract the list of selectors (primary + fallbacks) from the step's target."""
    target = step.get("target", {})
    if isinstance(target, str):
        return [target]
    selectors = []
    primary = target.get("selector")
    if primary:
        selectors.append(primary)
    fallbacks = target.get("fallbacks", [])
    selectors.extend(fallbacks)
    return selectors


def _text_matches_verify(el, verify_list):
    """Checks whether the element text contains any of the values ​​in the verify_text list."""
    try:
        el_text = (el.text or "").strip()
    except Exception:
        el_text = ""
    for expected in verify_list:
        if expected in el_text:
            return True
    return False


def _exec_click(page, step):
    """Perform click action.

    Use DrissionPage native ele().click() to ensure React synthetic events are fired.
    Pure JS el.click() cannot trigger the onClick callback bound to the React event system.

    Optional verify_text: Verify that the element text contains the expected value before clicking, preventing CSS selectors
    False success caused by hitting the wrong element. If there is no match, skip this selector and continue trying the next one.
    """
    selectors = _get_selectors(step)
    fallback_texts = step.get("fallback", {}).get("text_match", []) if isinstance(step.get("fallback"), dict) else []
    verify_text = step.get("verify_text", [])

    for sel in selectors:
        try:
            el = page.ele(f'css:{sel}', timeout=2)
            if el:
                if verify_text and not _text_matches_verify(el, verify_text):
                    logger.debug(f"    verify_text does not match, skip {sel}")
                    continue
                el.click()
                return "ok", sel
        except Exception:
            pass

    if fallback_texts:
        for text in fallback_texts:
            try:
                el = page.ele(f'text:{text}', timeout=2)
                if el:
                    el.click()
                    return "ok_text", "text_match"
            except Exception:
                pass

    return "not_found", None


def _exec_set_value(page, step):
    """Execute set_value action (set value via CDP Input layer, all events isTrusted=true).

    Support Shadow DOM penetration: first use standard querySelectorAll, and then recursively search Shadow DOM after failure.
    Process: JS locate element → CDP click to focus → CDP select all → CDP enter new value → CDP Tab triggers change.
    """
    selectors = _get_selectors(step)
    value = step.get("value", "")
    value_pattern = step.get("target", {}).get("value_pattern", "")

    js_find_rect = (
        'var sel = arguments[0]; var valPat = arguments[1];'
        'function findInputs(root, depth) {'
        '  if (depth > 10) return [];'
        '  var results = [];'
        '  try {'
        '    var els = root.querySelectorAll(sel);'
        '    for (var e of els) results.push(e);'
        '    if (results.length === 0) {'
        '      var all = root.querySelectorAll("*");'
        '      for (var c of all) {'
        '        if (c.shadowRoot) results = results.concat(findInputs(c.shadowRoot, depth + 1));'
        '      }'
        '    }'
        '  } catch(e) {}'
        '  return results;'
        '}'
        'var els = findInputs(document, 0);'
        'for (var inp of els) {'
        '  var rect = inp.getBoundingClientRect();'
        '  if (rect.width === 0) continue;'
        '  if (valPat && !(new RegExp(valPat)).test(inp.value)) continue;'
        '  inp.scrollIntoView({block: "center"});'
        '  var r = inp.getBoundingClientRect();'
        '  return {x: r.x + r.width/2, y: r.y + r.height/2};'
        '}'
        'return null;'
    )

    for sel in selectors:
        rect = page.run_js(js_find_rect, sel, value_pattern)
        if not rect:
            continue

        try:
            cdp_click_at(page, rect['x'], rect['y'])
            time.sleep(0.1)

            select_result = page.run_js(
                'var el = document.activeElement;'
                'if (!el) return "no_element";'
                'if (el.select) { el.select(); return "select_called"; }'
                'else if (el.isContentEditable) {'
                '  var r = document.createRange(); r.selectNodeContents(el);'
                '  var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);'
                '  return "range_selected";'
                '}'
                'return "no_method";'
            )
            time.sleep(0.05)

            cdp_type_text(page, value)
            time.sleep(0.1)

            actual_value = page.run_js(
                'var el = document.activeElement;'
                'if (!el) return null;'
                'return el.value;',
            )

            if actual_value != value:
                for _ in range(len(actual_value or "")):
                    cdp_press_key(page, 'Backspace', 'Backspace', 8)
                time.sleep(0.05)

                cdp_type_text(page, value)
                time.sleep(0.1)
                actual_value = page.run_js(
                    'var el = document.activeElement; return el ? el.value : null;'
                )

            verify = "ok" if actual_value == value else "set_but_unverified"

            cdp_press_key(page, 'Tab', 'Tab', 9)
            return verify or "set_but_unverified", sel
        except Exception as e:
            logger.debug(f"CDP set_value failed for {sel}: {e}")
            continue

    return "not_found", None


def _exec_pick_option(page, step):
    """Execute the pick_option action (select in a list of options).

    ``match_text`` supports multiple candidate labels separated by ``|``, for example
    ``"Only me|仅自己|Only Me"``. The localized label is retained for Chinese platform UIs.
    The JS side will match in sequence, and click if you hit any one.

    Will automatically skip invisible/disabled/cross-month filling and other non-clickable candidates to avoid calendar type
    The control was clicked incorrectly because there are "days" with the same name in the previous and following months in the DOM (for example, the first row of the April calendar
    March 30). You can add a custom filtering class name through step configuration ``exclude_classes``.
    """
    container = step.get("container", "")
    item_selector = step.get("item_selector", "")
    match_text = step.get("match_text", "")
    extra_excludes = step.get("exclude_classes") or []
    if isinstance(extra_excludes, str):
        extra_excludes = [extra_excludes]

    if not item_selector or not match_text:
        return "missing_config", None

    default_exclude_classes = [
        "disabled", "is-disabled", "gray", "grey",
        "other-month", "outside", "not-current",
        "prev-month", "next-month", "muted",
    ]
    exclude_classes = list({*default_exclude_classes, *extra_excludes})

    exclude_classes_json = json.dumps(exclude_classes)

    js_locate = (
        'var containerSel = arguments[0]; var itemSel = arguments[1];'
        'var target = arguments[2]; var excludeClasses = JSON.parse(arguments[3] || "[]");'
        'var root = containerSel ? document.querySelector(containerSel) : document;'
        'if (!root) return {result: "container_not_found"};'
        'var targets = target.indexOf("|") >= 0 ? target.split("|") : [target];'
        'function isClickable(el) {'
        '  if (!el) return false;'
        '  if (el.offsetParent === null && el.getClientRects().length === 0) return false;'
        '  var rect = el.getBoundingClientRect();'
        '  if (rect.width === 0 || rect.height === 0) return false;'
        '  if (el.hasAttribute("disabled")) return false;'
        '  if (el.getAttribute("aria-disabled") === "true") return false;'
        '  if (el.getAttribute("data-disabled") === "true") return false;'
        '  for (var c of excludeClasses) { if (c && el.classList.contains(c)) return false; }'
        '  var style = window.getComputedStyle(el);'
        '  if (style.pointerEvents === "none") return false;'
        '  if (style.visibility === "hidden") return false;'
        '  return true;'
        '}'
        'var items = root.querySelectorAll(itemSel);'
        'var skippedDisabled = 0;'
        'for (var item of items) {'
        '  var txt = item.textContent.trim();'
        '  for (var t of targets) {'
        '    if (txt === t || txt.startsWith(t)) {'
        '      if (!isClickable(item)) { skippedDisabled++; continue; }'
        '      item.scrollIntoView({block:"center"});'
        '      var r = item.getBoundingClientRect();'
        '      return {result: "ok", x: r.x + r.width/2, y: r.y + r.height/2};'
        '    }'
        '  }'
        '}'
        'return {result: skippedDisabled > 0 ? "option_disabled_only" : "option_not_found"};'
    )
    located = page.run_js(js_locate, container, item_selector, match_text, exclude_classes_json)
    if not isinstance(located, dict):
        return "locate_invalid", item_selector
    status = located.get("result", "option_not_found")
    if status != "ok":
        return status, item_selector

    try:
        cdp_click_at(page, located["x"], located["y"])
    except Exception as e:
        logger.debug(f"CDP click failed for pick_option {item_selector}: {e}")
        return "click_failed", item_selector
    return "ok", item_selector


def _exec_wait(page, step):
    """Execute the wait action (wait for the element to appear)."""
    selectors = _get_selectors(step)
    max_wait = step.get("max_wait_ms", 5000)
    interval = 500
    attempts = max(1, max_wait // interval)

    for _ in range(attempts):
        for sel in selectors:
            js = (
                'var el = document.querySelector(arguments[0]);'
                'return el && el.offsetParent !== null ? "visible" : "hidden";'
            )
            result = page.run_js(js, sel)
            if result == "visible":
                return "ok", sel
        time.sleep(interval / 1000)

    return "not_found", None


_ACTION_MAP = {
    "click": _exec_click,
    "set_value": _exec_set_value,
    "pick_option": _exec_pick_option,
    "wait": _exec_wait,
}


def _try_discover(page, step, action):
    """Tier 2a (Heuristic) → Tier 2b (AgentQL AI) Discover alternative selectors step by step."""
    hint = step.get("semantic_hint", "")
    context = step.get("context_selector")

    # Tier 2a: dom_heuristic heuristic (native, free, fast)
    if action in ("click", "wait"):
        fallback_texts = step.get("fallback", {}).get("text_match", []) if isinstance(step.get("fallback"), dict) else []
        sel, el_info = discover_for_click(page, hint, fallback_texts, context)
        if sel:
            logger.info(f"    🔍 Tier 2a Found: {sel}")
            return sel
    elif action == "set_value":
        val_pat = step.get("target", {}).get("value_pattern", "")
        sel, el_info = discover_for_value(page, val_pat, hint, context)
        if sel:
            logger.info(f"    🔍 Tier 2a Found: {sel}")
            return sel
    elif action == "pick_option":
        match_text = step.get("match_text", "")
        texts = match_text.split("|") if "|" in match_text else [match_text]
        for text in texts:
            sel, el_info = discover_for_click(page, f"{hint} {text}", [text], context)
            if sel:
                logger.info(f"    🔍 Tier 2a Found: {sel}")
                return sel

    # Tier 2b: AgentQL AI (cloud, 10s delay, API Key required)
    if hint:
        try:
            from social_uploader.tools.agentql_client import discover_with_ai
            sel = discover_with_ai(page, hint, action, context)
            if sel:
                logger.info(f"    🧠 Tier 2b AgentQL found: {sel}")
                return sel
        except ImportError:
            pass

    return None


def _update_recipe_step(platform, recipe_key, step_id, new_selector):
    """Write the new selector discovered by Tier 2 back to the recipe (the old selector falls back)."""
    data = _load_patterns()
    recipe = data.get(platform, {}).get(recipe_key)
    if not recipe:
        return

    for step in recipe.get("steps", []):
        if step.get("id") != step_id:
            continue

        target = step.get("target", {})
        if isinstance(target, str):
            step["target"] = {
                "selector": new_selector,
                "fallbacks": [target],
            }
        else:
            old = target.get("selector")
            target["selector"] = new_selector
            fallbacks = target.get("fallbacks", [])
            if old and old not in fallbacks:
                fallbacks.insert(0, old)
            target["fallbacks"] = fallbacks

        break

    recipe["version"] = recipe.get("version", 0) + 1
    _save_patterns(data)

    from social_uploader.tools.pattern_checker import reload_patterns
    reload_patterns()

    logger.info(f"  📝 Recipe updated: {platform}.{recipe_key}.{step_id} → {new_selector} (v{recipe['version']})")


def _emit_failure_candidates(page, step, hint, action, context_selector=None, top_n=3):
    """When Tier 1+2 fails, scan the DOM and output the top_n candidate elements to stderr to facilitate subsequent diagnosis.

    Output format (one line of JSON):
      {"step":"recipe_candidates","step_id":...,"hint":...,"candidates":[...]}
    Candidates are sorted by the number of hint keyword hits. When the hint is empty, it is reduced to outputting the first top_n visible interactive elements in the current DOM.
    """
    try:
        elements = _scan_dom(page, context_selector)
    except Exception as e:
        elements = []
        logger.debug(f"Scan DOM failed: {e}")

    if not elements:
        return

    keywords = [w.lower() for w in re.findall(r"[\w\u4e00-\u9fff]+", hint or "") if len(w) >= 2]
    if not keywords:
        return  # No meaningless output without hint keyword

    def _score(el):
        searchable = " ".join([
            str(el.get("text", "")), str(el.get("aria-label", "")),
            str(el.get("data-e2e", "")), str(el.get("id", "")),
            str(el.get("name", "")), str(el.get("placeholder", "")),
            str(el.get("role", "")),
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    scored = [(el, _score(el)) for el in elements]
    scored = [item for item in scored if item[1] > 0]
    scored.sort(key=lambda x: -x[1])
    top = [el for el, _ in scored[:top_n]]

    if not top:
        return

    summary = []
    for el in top:
        summary.append({
            "tag": el.get("tag"),
            "text": (el.get("text") or "")[:30],
            "aria_label": el.get("aria-label"),
            "id": el.get("id"),
            "data_e2e": el.get("data-e2e"),
            "role": el.get("role"),
            "class": (el.get("class") or "")[:60],
        })

    record = {
        "step": "recipe_candidates",
        "step_id": step.get("id"),
        "action": action,
        "hint": hint,
        "candidates": summary,
    }
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr)


def run_recipe(page, platform, recipe_key, variables):
    """Execute the interactive recipe and return (success: bool, failed_step_id: str|None, hint: str).

    Each step tries Tier 1 (recipe selector) first, and if it fails, Tier 2 (heuristic discovery),
    After success in Tier 2, the recipe will be written back automatically, and you will go directly to Tier 1 next time.
    """
    recipe = load_recipe(platform, recipe_key)
    if not recipe:
        return False, None, f"Recipe {platform}.{recipe_key} does not exist"

    steps = recipe.get("steps", [])
    if not steps:
        return False, None, "Recipe step is empty"

    logger.info(f"  📋 Execute recipe: {platform}.{recipe_key} (v{recipe.get('version', 1)}, {len(steps)} steps)")

    for step in steps:
        step_id = step.get("id", "unknown")
        action = step.get("action", "")
        hint = step.get("semantic_hint", "")
        resolved = _resolve_step(step, variables)

        executor = _ACTION_MAP.get(action)
        if not executor:
            logger.warning(f"  ⚠️ [{step_id}] Unknown action: {action}")
            return False, step_id, f"Unknown action type: {action}"

        # Tier 1: Executed according to recipe
        retry_count = resolved.get("retry", 1)
        wait_before = resolved.get("wait_before_ms", 0)
        if wait_before:
            time.sleep(wait_before / 1000)

        result, used_sel = "not_found", None
        for attempt in range(max(1, retry_count)):
            result, used_sel = executor(page, resolved)
            if result and result != "not_found" and result != "not_found":
                break
            if attempt < retry_count - 1:
                time.sleep(0.5)

        if result and (result.startswith("ok") or result == "set_but_unverified"):
            if result == "set_but_unverified":
                logger.info(f"  ⚠️ [{step_id}] The {action} value has been written but failed to pass verification. It is considered to continue successfully.")
            else:
                logger.info(f"  ✅ [{step_id}] {action} successful")
            wait_after = resolved.get("wait_after_ms", 0)
            if wait_after:
                time.sleep(wait_after / 1000)
            continue

        # Tier 2: Heuristic Discovery
        logger.info(f"  ⚠️ [{step_id}] Tier 1 failed ({result}), tried Tier 2 and found...")
        discovered = _try_discover(page, resolved, action)

        if discovered:
            tier2_step = dict(resolved)
            target = tier2_step.get("target", {})
            if isinstance(target, dict):
                tier2_step["target"] = {**target, "selector": discovered}
            else:
                tier2_step["target"] = {"selector": discovered}

            result2, _ = executor(page, tier2_step)
            if result2 and result2.startswith("ok"):
                logger.info(f"  ✅ [{step_id}] Tier 2 successful, automatically update the recipe")
                _update_recipe_step(platform, recipe_key, step_id, discovered)
                wait_after = resolved.get("wait_after_ms", 0)
                if wait_after:
                    time.sleep(wait_after / 1000)
                continue

        # Tier 1+2 all failed
        if resolved.get("optional"):
            logger.info(f"  ⏭️ [{step_id}] Optional step failed, skip to continue")
            continue
        logger.error(f"  ❌ [{step_id}] Tier 1+2 failed: {result}")
        _emit_failure_candidates(
            page, resolved, hint, action,
            context_selector=resolved.get("context_selector"),
        )
        return False, step_id, hint or f"{action} Operation failed"

    return True, None, ""


def show_recipe(platform, recipe_key):
    """Outputs the recipe contents in a readable format."""
    recipe = load_recipe(platform, recipe_key)
    if not recipe:
        return f"Recipe {platform}.{recipe_key} does not exist"

    lines = [
        f"RECIPE: {platform}.{recipe_key}",
        f"VERSION: {recipe.get('version', 1)}",
        f"STEPS: {len(recipe.get('steps', []))}",
        "",
    ]
    for i, step in enumerate(recipe.get("steps", []), 1):
        step_id = step.get("id", "?")
        action = step.get("action", "?")
        hint = step.get("semantic_hint", "")
        target = step.get("target", {})
        sel = target.get("selector", str(target)) if isinstance(target, dict) else str(target)
        fallbacks = target.get("fallbacks", []) if isinstance(target, dict) else []

        lines.append(f"  {i}. [{step_id}] {action}")
        lines.append(f"     selector: {sel}")
        if fallbacks:
            lines.append(f"     fallbacks: {fallbacks}")
        if hint:
            lines.append(f"     hint: {hint}")
        lines.append("")

    return "\n".join(lines)


def fix_recipe_step(platform, recipe_key, step_id, new_selector):
    """CLI command interface: manually update the selector of a step in the recipe."""
    data = _load_patterns()
    recipe = data.get(platform, {}).get(recipe_key)
    if not recipe:
        return False, f"Recipe {platform}.{recipe_key} does not exist"

    found = False
    for step in recipe.get("steps", []):
        if step.get("id") != step_id:
            continue
        found = True

        target = step.get("target", {})
        if isinstance(target, str):
            step["target"] = {"selector": new_selector, "fallbacks": [target]}
        else:
            old = target.get("selector")
            target["selector"] = new_selector
            fallbacks = target.get("fallbacks", [])
            if old and old not in fallbacks:
                fallbacks.insert(0, old)
            target["fallbacks"] = fallbacks
        break

    if not found:
        available = [s.get("id") for s in recipe.get("steps", [])]
        return False, f"Step {step_id} does not exist (available: {', '.join(available)})"

    recipe["version"] = recipe.get("version", 0) + 1
    _save_patterns(data)
    return True, f"OK: {platform}.{recipe_key}.{step_id} selector has been updated to \"{new_selector}\" (v{recipe['version']})"
