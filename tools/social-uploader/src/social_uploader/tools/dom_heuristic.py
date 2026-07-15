"""Tier 2 heuristic DOM finder — Automatically searches the page for replacement elements when a selector in a recipe expires.

Without calling the AI ​​API, locate the target in the DOM through semantic keywords + element characteristics (labels, value formats, position relationships).
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# DrissionPage.run_js wraps the script in `function(){<code>}` for execution.
# Therefore, top-level return must be used; it is strictly prohibited to wrap (function(){...})() IIFE in the outer layer.
# Otherwise, the outer function does not return, and the result is always None on the Python side (verified by actual testing).
# Parameters are hard-coded into JS literals through the %s template (consistent with _DOM_EXTRACT_JS writing method).
_DISCOVER_JS = """
var contextSel = %s;
var root = document;
if (contextSel) {
    var ctx = document.querySelector(contextSel);
    if (ctx) root = ctx;
}
var tags = 'button,input,select,textarea,label,span,div,[role="button"],[role="radio"],'
         + '[role="option"],[role="listbox"],[contenteditable],[data-e2e]';
var els = root.querySelectorAll(tags);
var keep = ['id','class','name','type','role','aria-label','data-e2e',
            'placeholder','value','aria-checked','aria-expanded','for'];
var result = [];
for (var i = 0; i < els.length && result.length < 200; i++) {
    var el = els[i];
    var rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    var obj = {tag: el.tagName.toLowerCase(), x: Math.round(rect.x), y: Math.round(rect.y)};
    for (var k = 0; k < keep.length; k++) {
        var v = el.getAttribute(keep[k]);
        if (v) {
            if (keep[k] === 'class') v = v.split(/\\s+/).slice(0, 4).join(' ');
            if (keep[k] === 'value') v = v.substring(0, 30);
            obj[keep[k]] = v;
        }
    }
    var txt = '';
    for (var c = el.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) txt += c.textContent;
    }
    txt = txt.trim();
    if (txt && txt.length > 0) obj.text = txt.substring(0, 40);
    result.push(obj);
}
return JSON.stringify(result);
"""


def _scan_dom(page, context_selector=None):
    """Extract the list of interactable elements of the current page (or specified area)."""
    ctx_arg = f'"{context_selector}"' if context_selector else "null"
    js = _DISCOVER_JS % ctx_arg
    try:
        raw = page.run_js(js)
        if not raw:
            return []
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        logger.warning(f"DOM scan failed: {e}")
        return []


def _build_selector(el):
    """Generates a CSS selector string based on an element's properties."""
    tag = el.get("tag", "*")
    if el.get("id"):
        return f'{tag}#{el["id"]}'
    if el.get("name"):
        return f'{tag}[name="{el["name"]}"]'
    if el.get("data-e2e"):
        return f'{tag}[data-e2e="{el["data-e2e"]}"]'
    if el.get("class"):
        first_cls = el["class"].split()[0]
        return f'{tag}.{first_cls}'
    if el.get("role"):
        return f'{tag}[role="{el["role"]}"]'
    if el.get("type") and tag == "input":
        return f'input[type="{el["type"]}"]'
    if el.get("aria-label"):
        return f'{tag}[aria-label="{el["aria-label"]}"]'
    return None


def _matches_hint(el, hint_keywords):
    """Determine whether the element semantically matches any keyword in the keyword list."""
    searchable = " ".join([
        el.get("text", ""), el.get("aria-label", ""),
        el.get("name", ""), el.get("id", ""),
        el.get("placeholder", ""), el.get("class", ""),
        el.get("data-e2e", ""),
    ]).lower()
    return any(kw.lower() in searchable for kw in hint_keywords)


def _matches_value_pattern(el, pattern):
    """Determine whether the value attribute of the element matches the given regular expression."""
    val = el.get("value", "")
    if not val or not pattern:
        return False
    try:
        return bool(re.match(pattern, val))
    except re.error:
        return False


def discover_for_click(page, semantic_hint, fallback_texts=None, context_selector=None):
    """Discover clickable elements (for click / pick_option actions).

    Strategy:
    1. Match the text/attributes of the element according to the keywords in semantic_hint
    2. If there is fallback_texts, match the exact text
    Return (css_selector, element_info) or (None, None).
    """
    elements = _scan_dom(page, context_selector)
    if not elements:
        return None, None

    hint_keywords = [w for w in re.split(r'[,，\s]+', semantic_hint) if len(w) >= 2]

    for el in elements:
        if _matches_hint(el, hint_keywords):
            sel = _build_selector(el)
            if sel:
                return sel, el

    if fallback_texts:
        for el in elements:
            el_text = el.get("text", "").strip()
            if el_text and el_text in fallback_texts:
                sel = _build_selector(el)
                if sel:
                    return sel, el

    return None, None


def discover_for_value(page, value_pattern, semantic_hint="", context_selector=None):
    """Found a settable input element (for use with the set_value action).

    Strategy:
    1. Find all input/textarea/select
    2. Press value_pattern to match the current value format
    3. If there is semantic_hint, it is used as auxiliary filtering
    Return (css_selector, element_info) or (None, None).
    """
    elements = _scan_dom(page, context_selector)
    if not elements:
        return None, None

    input_els = [e for e in elements if e.get("tag") in ("input", "textarea", "select")]

    for el in input_els:
        if _matches_value_pattern(el, value_pattern):
            sel = _build_selector(el)
            if sel:
                return sel, el

    hint_keywords = [w for w in re.split(r'[,，\s]+', semantic_hint) if len(w) >= 2]
    if hint_keywords:
        for el in input_els:
            if _matches_hint(el, hint_keywords):
                sel = _build_selector(el)
                if sel:
                    return sel, el

    return None, None


def discover_for_pick(page, semantic_hint, container_hint="", context_selector=None):
    """Discover optional elements in an option list (used in the pick_option action).

    Strategy:
    1. Find role=option / role=listitem / li / element with click attribute
    2. Search in semantically related containers
    Return (container_selector, item_selector, element_info) or (None, None, None).
    """
    elements = _scan_dom(page, context_selector)
    if not elements:
        return None, None, None

    hint_keywords = [w for w in re.split(r'[,，\s]+', semantic_hint) if len(w) >= 2]
    option_tags = ("li", "div", "span", "button")
    option_roles = ("option", "listitem", "menuitem")

    for el in elements:
        is_option = (el.get("tag") in option_tags and el.get("role") in option_roles)
        if not is_option:
            continue
        if hint_keywords and _matches_hint(el, hint_keywords):
            sel = _build_selector(el)
            if sel:
                return None, sel, el

    for el in elements:
        if el.get("role") in option_roles:
            sel = _build_selector(el)
            if sel:
                return None, sel, el

    return None, None, None
