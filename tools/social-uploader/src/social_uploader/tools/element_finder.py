"""Three-tier element finder — Track A (quick selector) → Tier 2 (local heuristic) → Track B (AI semantic targeting)

[Three layers of step-by-step strategy]
Track A (Fast Path): Read button_config.json selector list, 1.5s fast try
Tier 2 (Heuristic): Local DOM keyword matching, no API adjustment, automatic write-back after success
Track B (AI Path): Structured semantic query through UltimateLocator, automatic write-back after success

[Automatic write-back mechanism]
After Tier 2 / Track B is successful, the effective selector will be written back to button_config.json.
So that next time you go straight to track A in the same scene, the system selector library will automatically grow with use.

[Reserved functions]
load_selectors / reload_selectors / add_selector — used by the fix-selector CLI and automatic fix processes
"""

import json
import logging
import time
from pathlib import Path

from social_uploader.tools.browser_manager import find_first

logger = logging.getLogger(__name__)

_SELECTORS_PATH = Path(__file__).resolve().parent.parent / "button_config.json"
_cache = {}

_TRACK_A_TIMEOUT = 1.5

_WRITEBACK_BLOCKLIST = {"close_buttons"}

_WRITEBACK_VALUE_BLOCKLIST = {
    "create_button": {"@aria-label=Menu", "@aria-label=menu"},
}

_EXPECTED_ELEMENT = {
    "file_input": {"tags": {"input"}, "attrs": {"type": "file"}},
    "caption_box": {"tags": {"div", "textarea", "p"}},
    "title_box": {"tags": {"div", "textarea", "input"}},
    "desc_box": {"tags": {"div", "textarea", "input"}},
}


def _verify_element_type(el, key):
    """Verify that element tags/attributes are as expected, preventing AI from returning the wrong type of element.

    Returning True indicates that verification passed or no verification is required.
    """
    spec = _EXPECTED_ELEMENT.get(key)
    if not spec:
        return True
    try:
        tag = (el.tag or "").lower()
    except Exception:
        return True
    expected_tags = spec.get("tags", set())
    if expected_tags and tag not in expected_tags:
        logger.debug(f"    Type assertion failed: {key} expected {expected_tags}, actual <{tag}>")
        return False
    expected_attrs = spec.get("attrs", {})
    for attr_name, attr_val in expected_attrs.items():
        try:
            actual = (el.attr(attr_name) or "").lower()
            if actual != attr_val.lower():
                logger.debug(f"    Property assertion failed: {key} expected {attr_name}={attr_val}, actual {actual}")
                return False
        except Exception:
            return False
    return True


def load_selectors(platform):
    """Read the selector dictionary for the specified platform in button_config.json, with file-level caching."""
    if platform in _cache:
        return _cache[platform]
    try:
        data = json.loads(_SELECTORS_PATH.read_text(encoding="utf-8"))
        _cache.update(data)
        return _cache.get(platform, {})
    except Exception as e:
        logger.warning(f"Failed to read button_config.json, falling back to empty dictionary: {e}")
        return {}


def reload_selectors():
    """Clears the cache, forcing the file to be re-read the next time load_selectors is called."""
    _cache.clear()


def add_selector(platform, key, selector):
    """Safely insert the new selector into button_config.json at the beginning of the corresponding platform.key list.

    Return (success: bool, message: str).
    """
    try:
        data = json.loads(_SELECTORS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Failed to read button_config.json: {e}"

    if platform not in data:
        return False, f"Platform \"{platform}\" does not exist in button_config.json (available: {', '.join(data.keys())})"

    if key not in data[platform]:
        return False, f"key \"{key}\" does not exist in {platform} (available: {', '.join(data[platform].keys())})"

    current_list = data[platform][key]
    if selector in current_list:
        return True, f"The selector already exists in {platform}.{key}, no need to add it again"

    current_list.insert(0, selector)

    try:
        _SELECTORS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        return False, f"Failed to write button_config.json: {e}"

    reload_selectors()
    total = len(current_list)
    return True, f"OK: \"{selector}\" has been added to the beginning of the {platform}.{key} selector list ({total} in total)"


def _track_a(page, platform, key):
    """Track A: button_config.json fast path, 1.5s timeout.

    Return (element, selector) or (None, None).
    """
    sels = load_selectors(platform).get(key, [])
    if not sels:
        return None, None

    el, sel = find_first(page, sels, timeout_per=_TRACK_A_TIMEOUT)
    if el:
        if key == "file_input":
            return el, sel
        try:
            if el.states.has_rect:
                return el, sel
        except Exception:
            pass
    return None, None


def _tier2_heuristic(page, platform, key):
    """Tier 2: Local DOM heuristic, no API adjustment, based on keyword matching.

    Get semantic hints from platform_semantics and search the page with dom_heuristic.
    Return (element, selector) or (None, None).
    """
    try:
        from social_uploader.tools.platform_semantics import get_semantic_query
        from social_uploader.tools.dom_heuristic import discover_for_click, discover_for_value
    except ImportError:
        return None, None

    query = get_semantic_query(platform, key)
    hint = query.get("target", key.replace("_", " "))

    if key in ("file_input",):
        sel, info = discover_for_value(page, "", hint)
    else:
        fallback_texts = []
        sel, info = discover_for_click(page, hint, fallback_texts)

    if not sel:
        return None, None

    try:
        el = page.ele(sel, timeout=1.5)
        if el:
            return el, sel
    except Exception:
        pass
    return None, None


def _track_b(page, platform, key):
    """Track B: AI semantic positioning path.

    Return (element, selector) or (None, None).
    """
    try:
        from social_uploader.tools.pattern_checker import dismiss_popups, sweep_modals
        dismiss_popups(page, platform, max_rounds=1)
        sweep_modals(page, max_rounds=1)
    except Exception:
        pass

    try:
        from social_uploader.tools.platform_semantics import get_semantic_query
        from social_uploader.tools.ai_locator import UltimateLocator
    except ImportError:
        logger.debug("AI positioning module is unavailable, skipping track B")
        return None, None

    query_dict = get_semantic_query(platform, key)
    locator = UltimateLocator(page)
    locator.prepare_page()
    return locator.find_element(query_dict, platform)


def _auto_writeback(platform, key, selector):
    """Write back valid selectors discovered by Tier 2 / Track B to button_config.json.

    Skip keys in _WRITEBACK_BLOCKLIST (such as close_buttons).
    """
    if key in _WRITEBACK_BLOCKLIST:
        return
    if not selector or not isinstance(selector, str):
        return
    blocked_vals = _WRITEBACK_VALUE_BLOCKLIST.get(key, set())
    if selector in blocked_vals:
        logger.info(f"  ⛔ Deny writeback: {platform}.{key} ← {selector} (in value blacklist)")
        return
    ok, msg = add_selector(platform, key, selector)
    if ok:
        logger.info(f"  📝 Automatic write-back: {platform}.{key} ← {selector}")


def find_element(page, platform, key, timeout=5):
    """Three-level search for elements step by step (with element type assertion).

    Track A (Fast Path): button_config.json main selector, 1.5s timeout
    Tier 2 (Heuristic): Local DOM keyword matching, write back after success
    Track B (AI Path): UltimateLocator semantic search, write back after success

    The elements returned by each level are subject to the _verify_element_type assertion,
    Prevent AI or heuristics from returning the wrong type of element (such as treating a div as an input).

    Return (element, selector) or (None, None).
    """
    el, sel = _track_a(page, platform, key)
    if el and _verify_element_type(el, key):
        return el, sel

    logger.info(f"  ⚡ Track A miss {platform}.{key}, trying local heuristic Tier 2...")
    el, sel = _tier2_heuristic(page, platform, key)
    if el and _verify_element_type(el, key):
        logger.info(f"  🔍 Tier 2 hits {platform}.{key}: {sel}")
        _auto_writeback(platform, key, sel)
        return el, sel

    logger.info(f"  🔍 Tier 2 miss, switch to AI track B...")
    el, sel = _track_b(page, platform, key)
    if el and _verify_element_type(el, key):
        logger.info(f"  🧠 Track B hits {platform}.{key}: {sel}")
        _auto_writeback(platform, key, sel)
        return el, sel

    if not load_selectors(platform).get(key):
        logger.warning(f"{platform}.{key} not found in button_config.json")
    return None, None


_CRITICAL_KEYS = {
    "tiktok": ["file_input"],
    "instagram": ["create_button"],
    "youtube": ["upload_icon"],
}


def preflight_check(page, platform):
    """Check if key selectors are alive before uploading (Track A only).

    Called before the upload process starts, you can quickly detect selector failures caused by UI changes.
    Does not trigger Tier 2/Track B to avoid side effects.

    Returns a list of broken keys (empty list = full health).
    """
    keys = _CRITICAL_KEYS.get(platform, [])
    broken = []
    for key in keys:
        el, _ = _track_a(page, platform, key)
        if not el:
            broken.append(key)
    if broken:
        logger.warning(
            f"  ⚠️ Selector preflight: {platform} There are {len(broken)} key selectors invalid: {broken}"
        )
    else:
        logger.info(f"  ✅ Selector pre-check: {platform} all {len(keys)} key selectors are OK")
    return broken


def find_and_click(page, platform, key, timeout=5):
    """Find an element and click it, with post-click state checking.

    After clicking, check whether the page URL or DOM changes. If there is no change, try track B again.
    Return (clicked: bool, element, selector).
    """
    el, sel = find_element(page, platform, key, timeout)
    if not el:
        return False, None, None

    try:
        url_before = page.url
    except Exception:
        url_before = ""

    try:
        el.click()
    except Exception as e:
        logger.warning(f"  ⚠️Click {platform}.{key} failed: {e}")
        return False, el, sel

    time.sleep(0.5)

    try:
        url_after = page.url
        if url_after != url_before:
            return True, el, sel
    except Exception:
        pass

    try:
        if not el.states.has_rect:
            return True, el, sel
    except Exception:
        return True, el, sel

    logger.info(f"  ⚠️ There is no change in the page after clicking {platform}.{key}, try again track B...")
    el2, sel2 = _track_b(page, platform, key)
    if el2:
        try:
            el2.click()
            time.sleep(0.3)
            return True, el2, sel2
        except Exception:
            pass

    return True, el, sel
