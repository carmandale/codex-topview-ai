"""AgentQL intelligent element discovery - Tier 2b under the hood.

Adopt a two-stage discovery strategy:
  Phase 1 (AgentQL Semantic Identification): Send page HTML to AgentQL REST API,
          Use natural language to describe the target element and obtain coarse positioning attributes (aria-label, id, class, css_selector).
  Stage 2 (DrissionPage attribute refinement): Use coarse positioning attributes to find elements on the page,
          Extract all HTML attributes (including custom attributes such as data-e2e that cannot be seen by AgentQL) through JS,
          Select the most stable selector to write back the configuration.

When the API Key is not set, it will be downgraded silently and will not affect the existing Tier 1 / 2a / 3 process.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

def _load_api_key():
    key = os.environ.get("AGENTQL_API_KEY", "")
    if key:
        return key
    key_file = os.path.expanduser("~/.social_uploader/agentql.key")
    try:
        with open(key_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

_API_KEY = _load_api_key()
_API_URL = "https://api.agentql.com/v1/query-data"
_API_TIMEOUT = 15

DANGEROUS_KEYWORDS = [
    "delete", "删除", "discard", "丢弃", "remove", "移除",
    "cancel", "取消", "logout", "退出",
]

_QUERY_TEMPLATE = """{{
    target_element({description}) {{
        text_content
        aria_label
        id
        class_name
        css_selector
    }}
}}"""

_EXTRACT_ATTRS_JS = """
(function(el) {
    var result = {};
    for (var i = 0; i < el.attributes.length; i++) {
        var attr = el.attributes[i];
        result[attr.name] = attr.value;
    }
    result.__tag = el.tagName.toLowerCase();
    result.__text = (el.textContent || "").trim().substring(0, 60);
    return JSON.stringify(result);
})(arguments[0])
"""


# ---------------------------------------------------------------------------
# HTML optimization layer
# ---------------------------------------------------------------------------

def _clean_html(html):
    """Remove irrelevant tags such as script/style/svg/noscript to reduce API payload."""
    for tag in ("script", "style", "svg", "noscript", "link"):
        html = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            "", html, flags=re.DOTALL | re.IGNORECASE,
        )
        html = re.sub(
            rf"<{tag}[^>]*/>",
            "", html, flags=re.IGNORECASE,
        )
    return html


def _extract_relevant_html(page, context_hint=""):
    """Extracts an appropriately sized HTML fragment from the DrissionPage page object (target <300KB).

    Give priority to a small range (dialog/form), and then gradually expand it.
    """
    candidates = ["@role=dialog", "tag:form", "tag:main", "tag:body"]
    if context_hint:
        candidates.insert(0, context_hint)

    for selector in candidates:
        try:
            el = page.ele(selector, timeout=1)
            if not el:
                continue
            raw = el.html
            if not raw:
                continue
            if len(raw) < 300_000:
                return _clean_html(raw)
            cleaned = _clean_html(raw)
            if len(cleaned) < 500_000:
                return cleaned
        except Exception:
            continue

    try:
        fallback = page.html or ""
        return _clean_html(fallback[:300_000])
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# API call layer
# ---------------------------------------------------------------------------

def _call_agentql(html, query):
    """Call the AgentQL REST API (query syntax), returning a data dictionary or None."""
    try:
        import requests
    except ImportError:
        logger.debug("requests is not installed, skip AgentQL call")
        return None

    if not html or not query:
        return None

    headers = {
        "X-API-Key": _API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "html": html,
        "params": {"mode": "fast"},
    }

    try:
        resp = requests.post(
            _API_URL, json=payload, headers=headers, timeout=_API_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(f"AgentQL API returns {resp.status_code}: {resp.text[:200]}")
            return None
        result = resp.json()
        return result.get("data")
    except Exception as e:
        logger.warning(f"AgentQL API call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Phase 1: AgentQL Semantic Identification → Candidate Selector List
# ---------------------------------------------------------------------------

def _attrs_to_selectors(attrs):
    """Convert the element properties returned by AgentQL into a DrissionPage selector candidate list.

    Sorted in descending order of stability. Skip None and empty strings.
    """
    if not attrs or not isinstance(attrs, dict):
        return []

    selectors = []

    id_val = attrs.get("id")
    if id_val:
        selectors.append(f"@id={id_val}")

    aria = attrs.get("aria_label")
    if aria:
        selectors.append(f"@aria-label={aria}")

    cls = attrs.get("class_name")
    if cls:
        first_cls = cls.split()[0] if " " in cls else cls
        selectors.append(f".{first_cls}")

    css_sel = attrs.get("css_selector")
    if css_sel:
        selectors.append(f"css:{css_sel}")

    text = attrs.get("text_content") or attrs.get("text") or attrs.get("visible_text")
    if text and len(text) < 30:
        selectors.append(f"text:{text}")

    return selectors


def _agentql_identify(html, description, platform=""):
    """Phase 1: Call the AgentQL API to get the list of candidate selectors."""
    platform_hint = f" on {platform}" if platform else ""
    query = _QUERY_TEMPLATE.format(
        description=f"{description}{platform_hint}",
    )

    data = _call_agentql(html, query)
    if not data:
        return []

    target = data.get("target_element")
    if not target:
        first_key = next(iter(data), None)
        target = data.get(first_key) if first_key else None

    if isinstance(target, str):
        return [f"text:{target}"] if len(target) < 30 else []

    return _attrs_to_selectors(target)


# ---------------------------------------------------------------------------
# Stage 2: DrissionPage attribute refinement → optimal selector
# ---------------------------------------------------------------------------

_SELECTOR_PRIORITY = [
    ("data-e2e", "@data-e2e={}"),
    ("data-testid", "@data-testid={}"),
    ("id", "@id={}"),
    ("aria-label", "@aria-label={}"),
    ("name", "@name={}"),
]


def _extract_best_selector(page, element):
    """Extract all attributes from the found elements and select the most stable DrissionPage selector."""
    try:
        from social_uploader.tools.js_runner import run_iife
        raw = run_iife(page, _EXTRACT_ATTRS_JS, element)
        if not raw:
            return None
        attrs = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        logger.debug(f"Attribute refining failed: {e}")
        return None

    for attr_name, template in _SELECTOR_PRIORITY:
        val = attrs.get(attr_name)
        if val:
            return template.format(val)

    text = attrs.get("__text", "")
    if text and len(text) < 30:
        return f"text:{text}"

    return None


# ---------------------------------------------------------------------------
# Security check
# ---------------------------------------------------------------------------

def _is_safe_element(element, expected_description):
    """Prevent AI from targeting dangerous buttons (such as mistaking "delete" for "publish")."""
    try:
        el_text = (element.text or "").strip().lower()
    except Exception:
        return True

    desc_lower = expected_description.lower()
    for kw in DANGEROUS_KEYWORDS:
        if kw in el_text and kw not in desc_lower:
            logger.warning(
                f"AgentQL security interception: element text '{el_text}' contains the dangerous word '{kw}',"
                f"But the target description '{expected_description}' does not contain this word"
            )
            return False
    return True


# ---------------------------------------------------------------------------
# External interface
# ---------------------------------------------------------------------------

def find_element_with_ai(page, description, platform=""):
    """Two-stage discovery: AgentQL semantic recognition → DrissionPage attribute refinement.

    Return (element, best_selector) or (None, None).
    """
    if not _API_KEY:
        logger.debug("AGENTQL_API_KEY not set, skips AI discovery")
        return None, None

    html = _extract_relevant_html(page)
    if not html:
        logger.debug("Unable to extract page HTML, skipping AI discovery")
        return None, None

    logger.info(f"  🧠 AgentQL Tier 2b: Recognizing '{description}' (HTML {len(html)//1024}KB)...")
    candidates = _agentql_identify(html, description, platform)
    if not candidates:
        logger.info(f"  🧠 AgentQL did not return a valid attribute")
        return None, None

    logger.info(f"  🧠 AgentQL returns {len(candidates)} candidate selectors: {candidates}")

    for sel in candidates:
        try:
            el = page.ele(sel, timeout=2)
            if not el:
                continue
            if not _is_safe_element(el, description):
                continue

            best = _extract_best_selector(page, el)
            if best:
                logger.info(f"  🧠 Two-stage extraction optimal selector: {best}")
                return el, best
            else:
                return el, sel
        except Exception:
            continue

    return None, None


def discover_with_ai(page, semantic_hint, action="click", context_selector=None):
    """Simplified interface for recipe_runner to call, returning a selector string or None."""
    if not _API_KEY:
        return None

    el, sel = find_element_with_ai(page, semantic_hint)
    if el and sel:
        return sel
    return None
