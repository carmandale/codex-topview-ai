"""AI judgment engine - Provides semantic understanding capabilities in pop-up processing, success determination, and failure diagnosis.

OpenAI compatible API using Kimi K2.5 (Moonshot AI).
Obtain structured DOM snapshot + interactive element list through the page_sense module to give LLM a richer context.
The fast path (selector/URL) takes precedence; the AI ​​only bails out if the fast path fails.
Silently fallback when LLM is unavailable and does not block the upload process.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
_MOONSHOT_MODEL = "moonshot-v1-8k"
_TIMEOUT_S = 15
_MAX_TOKENS = 300
_TEMPERATURE = 0.3

_KEY_FILE = Path.home() / ".social_uploader" / "moonshot.key"

_client = None


def _load_api_key() -> str | None:
    key = os.environ.get("MOONSHOT_API_KEY")
    if key:
        return key.strip()
    if _KEY_FILE.exists():
        try:
            return _KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = _load_api_key()
    if not api_key:
        logger.debug("AI Judge: MOONSHOT_API_KEY is not configured and the AI ​​judgment function is disabled")
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=api_key, base_url=_MOONSHOT_BASE_URL, timeout=_TIMEOUT_S, max_retries=0)
        return _client
    except Exception as e:
        logger.debug(f"AI Judge: OpenAI client initialization failed: {e}")
        return None


def _call_llm(system_prompt: str, user_content: str) -> str | None:
    client = _get_client()
    if not client:
        return None
    try:
        resp = client.chat.completions.create(
            model=_MOONSHOT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.debug(f"AI Judge: LLM call failed: {e}")
        return None


def _parse_json_response(text: str | None) -> dict | None:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"^```(?:json)?\s*", "", text)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def _extract_page_context(page, dialog_el=None, use_dom_snapshot: bool = True) -> str:
    """Extract page context and support structured DOM snapshot enhancement."""
    parts = [f"URL: {page.url}"]

    if dialog_el:
        try:
            dialog_text = (dialog_el.text or "")[:1500]
            parts.append(f"Dialog text:\n{dialog_text}")
            btns = dialog_el.eles("tag:button", timeout=0.3)
            if btns:
                btn_texts = [b.text.strip() for b in btns if b.text and b.text.strip() and b.states.has_rect]
                if btn_texts:
                    parts.append(f"Buttons in dialog: {btn_texts}")
        except Exception:
            pass
    else:
        try:
            page_text = page.ele("tag:body", timeout=1)
            if page_text:
                raw = (page_text.text or "")[:3000]
                parts.append(f"Page text:\n{raw}")
        except Exception:
            pass

    if use_dom_snapshot:
        try:
            from social_uploader.tools.page_sense import get_interactive_elements, diagnose_page_state
            diag = diagnose_page_state(page)
            if diag.get("has_dialog") and not dialog_el:
                parts.append(f"[Auto-detected dialog]: {diag['dialog_text'][:300]}")
            if diag.get("error_indicators"):
                parts.append(f"Error keywords found: {diag['error_indicators']}")
            if diag.get("success_indicators"):
                parts.append(f"Success keywords found: {diag['success_indicators']}")
            interactive = get_interactive_elements(page)
            if interactive and interactive != "[]":
                parts.append(f"Interactive elements:\n{interactive[:2000]}")
        except Exception as e:
            logger.debug(f"DOM enhancement context acquisition failed: {e}")

    return "\n".join(parts)


_POPUP_SYSTEM_PROMPT = """You are a social media upload assistant. The user clicked the Publish/Post/Schedule button and a dialog/popup appeared.

Analyze the dialog content and decide what to do. Respond with ONLY a JSON object, no extra text.

Rules:
- If it's a publish confirmation dialog (asking to confirm posting), recommend clicking the confirm/post button.
- If it's a content warning (content may be restricted but can still post), recommend clicking the continue/post button (e.g. "Post", "Upload", "Schedule", "Continue", "Post anyway").
- NEVER recommend "Replace video", "Replace", "Re-upload", "Delete", "Discard" or similar buttons that would cancel the upload. These buttons abort the publish flow. If the only visible buttons are dangerous (replace/delete/discard), recommend "abort" instead.
- If it's a serious error that prevents publishing, recommend "abort".
- If the dialog is unrelated to publishing (cookie consent, notification prompt), recommend "dismiss".

JSON format:
{"type":"confirm|warning|error|info|unknown","description":"brief description","action":"click_button|dismiss|abort|ignore","button_text":"exact button text to click","confidence":0.95}"""

_SUCCESS_SYSTEM_PROMPT = """You are a social media upload assistant. The user published/scheduled a video and you need to determine if it was successful.

Analyze the page content and URL to determine the current state. Respond with ONLY a JSON object, no extra text.

Rules:
- "success": Page shows confirmation of publishing/scheduling, or redirected to content management page.
- "failed": Page shows an error message, upload failure, or content rejection.
- "pending": Page is still processing, no clear success or failure signal yet.

JSON format:
{"status":"success|failed|pending","reason":"brief explanation","confidence":0.9}"""


def judge_popup(page, platform: str, dialog_el=None) -> dict | None:
    context = _extract_page_context(page, dialog_el=dialog_el)
    user_msg = f"Platform: {platform}\n{context}"
    raw = _call_llm(_POPUP_SYSTEM_PROMPT, user_msg)
    result = _parse_json_response(raw)
    if result and "action" in result:
        logger.info(f"  🤖 AI pop-up window judgment: {result.get('type', '?')} → {result.get('action', '?')} [{result.get('button_text', '')}]")
        return result
    return None


def judge_success(page, platform: str) -> dict | None:
    context = _extract_page_context(page)
    user_msg = f"Platform: {platform}\n{context}"
    raw = _call_llm(_SUCCESS_SYSTEM_PROMPT, user_msg)
    result = _parse_json_response(raw)
    if result and "status" in result:
        logger.info(f"  🤖 AI success judgment: {result.get('status', '?')} — {result.get('reason', '?')}")
        return result
    return None


_DIAGNOSE_SYSTEM_PROMPT = """You are a browser automation expert. A step in a social media upload flow failed.

Analyze the current page state and diagnose why the step failed. Suggest a recovery action.

Respond with ONLY a JSON object, no extra text.

Possible recovery actions:
- "retry_same": Retry the same step as-is (e.g. element was temporarily hidden)
- "dismiss_and_retry": Close a blocking popup/overlay first, then retry
- "scroll_and_retry": Scroll to make the target element visible, then retry
- "wait_and_retry": Wait longer for page to load/process, then retry
- "navigate_back": Go back to previous page and retry from there
- "refresh_and_retry": Refresh the page and retry
- "skip": This step is no longer needed (e.g. already completed)
- "abort": Unrecoverable error, stop the upload

JSON format:
{"diagnosis":"brief explanation of what went wrong","recovery":"retry_same|dismiss_and_retry|scroll_and_retry|wait_and_retry|navigate_back|refresh_and_retry|skip|abort","dismiss_selector":"CSS selector of blocking element to close (if dismiss_and_retry)","wait_seconds":5,"confidence":0.85}"""


def diagnose_failure(page, platform: str, step_name: str, error_msg: str) -> dict | None:
    """Diagnose the cause of step failure and provide recovery suggestions. This is the core AI capability of step-level retries."""
    context = _extract_page_context(page, use_dom_snapshot=True)
    user_msg = (
        f"Platform: {platform}\n"
        f"Failed step: {step_name}\n"
        f"Error: {error_msg}\n"
        f"\n{context}"
    )
    raw = _call_llm(_DIAGNOSE_SYSTEM_PROMPT, user_msg)
    result = _parse_json_response(raw)
    if result and "recovery" in result:
        logger.info(
            f"  🤖 AI Diagnosis: {result.get('diagnosis', '?')} → {result.get('recovery', '?')}"
        )
        return result
    return None
