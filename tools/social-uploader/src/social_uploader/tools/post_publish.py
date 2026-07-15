"""Public release post-processing — pop-up window processing + success determination, shared by three platforms.

Fast paths (whitelist buttons/URL jumps/selector signals) are executed first, at zero cost.
AI judgment only bails out when the fast path fails, with throttling control (once every 3 rotations, up to 5 times).
"""

import json
import logging
import time
from typing import Callable

from social_uploader.tools.pattern_checker import (
    check_signals,
    get_patterns,
    get_signal_list,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIALOG_SELECTORS = [
    "xpath://*[@role='dialog' or @role='alertdialog']",
]

# Even if the whitelist matches, the button text (lower+strip) will not be clickable if it contains any of the following substrings.
# Prevent "Close/Cancel/Edit/Discard" in the TikTok content warning/copyright pop-up window from being accidentally clicked.
_DENY_BUTTON_SUBSTRINGS = [
    # Cancel/Close class
    "cancel", "取消", "close", "关闭", "back", "返回", "dismiss",
    # Edit/modify class (clicking will return to editing state instead of publishing)
    "edit", "编辑", "modify", "修改",
    # Discard/delete category (extremely dangerous, will lose the video)
    "discard", "丢弃", "放弃", "delete", "删除", "remove", "移除",
    # Replacement/retransmission class
    "replace", "替换", "re-upload", "reupload", "重新上传",
    # draft
    "save as draft", "save draft", "保存草稿", "存为草稿", "存草稿",
    # Single button "I Got It" type (pop-up window is only used to prompt, the video will not be released after closing)
    "got it", "知道了", "i understand", "我知道了", "了解",
]


def _is_denied_button(text: str) -> bool:
    """Returns True if the button text hits the blacklist. Empty text is considered a miss."""
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(sub in t for sub in _DENY_BUTTON_SUBSTRINGS)


def _list_dialog_buttons(dialog_el) -> list[dict]:
    """Detect the text and disabled status of all visible buttons in the pop-up window for debugging logs."""
    out = []
    try:
        btns = dialog_el.eles("xpath:.//button", timeout=0.5) or []
        for b in btns[:20]:
            try:
                if not b.states.has_rect:
                    continue
                txt = (b.text or "").strip()[:60]
                out.append({
                    "text": txt,
                    "aria_disabled": b.attr("aria-disabled"),
                    "data_type": b.attr("data-type"),
                    "denied": _is_denied_button(txt),
                })
            except Exception:
                continue
    except Exception:
        pass
    return out


def _dbg_log_popup(loc, msg, data):
    """Temporary debug log (shared with tiktok.py debug-social-upload.log)."""
    try:
        rec = {
            "sessionId": "66b267", "runId": "popup",
            "timestamp": int(time.time() * 1000),
            "location": loc, "message": msg, "data": data,
        }
        with open(
            "debug-social-upload.log",
            "a", encoding="utf-8",
        ) as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _find_dialog(page, platform: str):
    """Read the pop-up container selector from state_patterns.json and try to locate it in sequence."""
    patterns = get_patterns(platform, "publish_confirm")
    selectors = patterns.get("dialog_selectors", _DEFAULT_DIALOG_SELECTORS)
    for sel in selectors:
        try:
            el = page.ele(sel, timeout=0.8)
            if el and el.states.has_rect:
                return el
        except Exception:
            pass
    return None


def _resolve_button_selector(sel: str) -> tuple[str, str | None]:
    """Convert a ``text:xxx`` selector into an XPath targeting a button.

    Returns ``(selector_to_use, original_text_to_match)``.
    - 'text:Post now' → ('xpath:.//button[contains(normalize-space(.), "Post now")]', "Post now")
    - Other selectors are returned unchanged with ``text_to_match=None``.
    """
    if sel.startswith("text:"):
        text = sel[5:].strip()
        # Escape double quotes in xpath string
        if '"' in text:
            # Use concat to splice situations containing double quotes (very rare)
            parts = text.split('"')
            xp_str = "concat(" + ", '\"', ".join(f'"{p}"' for p in parts) + ")"
            xpath_expr = f'xpath:.//button[contains(normalize-space(.), {xp_str})]'
        else:
            xpath_expr = f'xpath:.//button[contains(normalize-space(.), "{text}")]'
        return xpath_expr, text
    return sel, None


def _try_whitelist_click(dialog_el, platform: str) -> bool:
    """Try clicking the whitelist button in the pop-up window. Returns whether the click was successful.

    Security mechanism:
    1. Detect all visible buttons in the pop-up window when entering, and write debugging logs (_DENY_BUTTON_SUBSTRINGS marks dangerous buttons)
    2. Convert the text:xxx selector to xpath and directly locate <button> (bypassing the problem of DrissionPage returning the inner span/div)
    3. Even if the whitelist selector matches, the button text will be skipped if it hits the deny list (to prevent accidentally clicking cancel/close/discard buttons)
    """
    confirm_texts = get_signal_list(platform, "publish_confirm", "secondary_confirm")

    # First record all the buttons in the pop-up window (write one regardless of whether you clicked or not) to facilitate review in case of failure.
    all_btns = _list_dialog_buttons(dialog_el)
    _dbg_log_popup(
        "post_publish.py:_try_whitelist_click:enter",
        f"{platform} All visible buttons in the secondary confirmation pop-up window",
        {"platform": platform, "buttons": all_btns, "whitelist_size": len(confirm_texts)},
    )

    if not confirm_texts:
        return False

    for item in confirm_texts:
        sel = item if isinstance(item, str) else item.get("selector", "")
        if not sel:
            continue

        resolved_sel, _expected_text = _resolve_button_selector(sel)
        try:
            el = dialog_el.ele(resolved_sel, timeout=0.3)
            if not el:
                continue

            # If the selector resolves to a child element, walk up to its button.
            btn = el
            if btn.tag != "button":
                try:
                    ancestor = btn.ele("xpath:./ancestor::button[1]", timeout=0.3)
                    if ancestor:
                        btn = ancestor
                except Exception:
                    pass

            if btn.tag != "button" or not btn.states.has_rect:
                _dbg_log_popup(
                    "post_publish.py:_try_whitelist_click:non_button",
                    "selector matches non-<button> elements and skips",
                    {"platform": platform, "selector": sel, "resolved": resolved_sel,
                     "matched_tag": el.tag, "matched_text": (el.text or "")[:60]},
                )
                continue

            btn_text = (btn.text or "").strip()

            # Security Gate: Hit deny list and skip directly (even if the whitelist selector matches)
            if _is_denied_button(btn_text):
                logger.warning(
                    f"  [Fast path] selector [{sel}] matches button [{btn_text[:30]}],"
                    f"But hit the deny list and skip it to prevent misoperation."
                )
                _dbg_log_popup(
                    "post_publish.py:_try_whitelist_click:denied",
                    f"Whitelist matched but blocked by deny list",
                    {"platform": platform, "selector": sel, "button_text": btn_text[:60]},
                )
                continue

            btn.click()
            logger.info(f"  [Quick Path] The pop-up button [{btn_text[:30]}] has been clicked (selector={sel})")
            _dbg_log_popup(
                "post_publish.py:_try_whitelist_click:clicked",
                f"Pop-up button clicked",
                {"platform": platform, "selector": sel, "resolved": resolved_sel,
                 "button_text": btn_text[:60]},
            )
            return True
        except Exception as e:
            _dbg_log_popup(
                "post_publish.py:_try_whitelist_click:exception",
                "selector handles exceptions",
                {"platform": platform, "selector": sel, "resolved": resolved_sel,
                 "err": str(e)[:120]},
            )
    return False


def handle_post_publish_popups(page, platform: str, max_rounds: int = 8, content_warning: bool = False) -> dict:
    """Post-release pop-up processing (whitelist fast path + AI cover-up).

    Args:
        content_warning: Whether a content restriction warning is detected during the pre-publish content_check phase.
            When it is True, if the content restriction keyword appears again in the pop-up window, abort directly without using AI.

    return:
        {"handled": bool, "action": str, "description": str}
        The caller should abort publishing when action is "abort".
    """
    try:
        page.handle_alert(accept=True, timeout=0.5)
    except Exception:
        pass

    # A short delay is sufficient: the caller (tiktok.py) has already used _handle_continue_to_post_dialog to handle the pop-up window closely to the click.
    # There is a high probability that the page will be stable when you enter here. The original 2 seconds of waiting is a historical burden, reducing it to 0.5 seconds can save 1.5 seconds.
    time.sleep(0.5)

    result = {"handled": False, "action": "none", "description": ""}
    ai_called = False

    for rnd in range(max_rounds):
        try:
            page.handle_alert(accept=True, timeout=0.3)
        except Exception:
            pass

        dialog = _find_dialog(page, platform)
        if not dialog:
            if rnd >= 3:
                break
            time.sleep(1.5)
            continue

        dialog_text = (dialog.text or "")[:200]
        dialog_lower = dialog_text.lower()
        logger.info(f"  Pop-up detected (round {rnd}): {dialog_text[:60]}...")

        progress_keywords = ["sharing", "uploading", "processing", "正在分享", "正在上传", "处理中"]
        if any(kw in dialog_lower for kw in progress_keywords):
            logger.info(f"  ↳ Progress prompt, skip processing")
            time.sleep(1.5)
            continue

        _restrict_keywords = ["restrict", "限制", "violation", "违规", "not recommend"]
        if content_warning and any(kw in dialog_lower for kw in _restrict_keywords):
            logger.warning("  ⚠️ Content restriction pop-up window (content_warning has been detected before publishing), publishing is terminated")
            result["action"] = "abort"
            result["description"] = "The video content has been marked as potentially restricted by the platform. It is recommended to check the video content and re-upload it."
            return result

        if _try_whitelist_click(dialog, platform):
            result["handled"] = True
            time.sleep(1)
            still_dialog = _find_dialog(page, platform)
            if not still_dialog:
                break
            continue

        if not ai_called:
            ai_called = True
            try:
                from social_uploader.tools.ai_judge import judge_popup
                ai_result = judge_popup(page, platform, dialog_el=dialog)
                if ai_result:
                    action = ai_result.get("action", "ignore")
                    result["description"] = ai_result.get("description", "")

                    if action == "abort":
                        result["action"] = "abort"
                        logger.warning(f"  AI recommended termination: {result['description']}")
                        return result

                    if action == "click_button":
                        btn_text = ai_result.get("button_text", "")
                        if btn_text:
                            # Content-related danger buttons (replace/delete/discard) → terminate publishing
                            _ABORT_BUTTONS = [
                                "replace video", "replace", "替换视频", "替换",
                                "重新上传", "re-upload", "reupload",
                                "delete", "删除", "discard", "丢弃", "放弃",
                            ]
                            if btn_text.strip().lower() in _ABORT_BUTTONS:
                                logger.warning(
                                    f"  [AI] It is recommended to click the dangerous button [{btn_text}], blocked."
                                    f" If it is deemed a content problem, publishing will be terminated and the user will be notified."
                                )
                                _dbg_log_popup(
                                    "post_publish.py:ai_judge:abort_button",
                                    "AI recommended content dangerous button, blocked and terminated",
                                    {"platform": platform, "button_text": btn_text},
                                )
                                result["action"] = "abort"
                                result["description"] = (
                                    f"A content restriction warning pops up on the platform, and the AI ​​recommends clicking [{btn_text}] (blocked)."
                                    f"Please check whether the video content complies with the platform specifications before uploading again."
                                )
                                return result
                            # Close/cancel/edit buttons → just skip this click and wait for the real publish button to appear
                            if _is_denied_button(btn_text):
                                logger.warning(
                                    f"  [AI] It is recommended to click [{btn_text}], but hit deny list (close/cancel/edit category),"
                                    f"Skip this click and wait for the real publish button"
                                )
                                _dbg_log_popup(
                                    "post_publish.py:ai_judge:denied",
                                    "AI recommendations are blocked by deny list",
                                    {"platform": platform, "button_text": btn_text},
                                )
                                if rnd >= 5:
                                    break
                                time.sleep(1.5)
                                continue
                            btn = dialog.ele(f"text:{btn_text}", timeout=0.5)
                            if btn and btn.states.has_rect:
                                btn.click()
                                logger.info(f"  [AI] Pop-up button [{btn_text}] clicked")
                                _dbg_log_popup(
                                    "post_publish.py:ai_judge:clicked",
                                    "AI recommendation button clicked",
                                    {"platform": platform, "button_text": btn_text},
                                )
                                result["handled"] = True
                                time.sleep(1)
                                still = _find_dialog(page, platform)
                                if not still:
                                    break
                                continue

                    if action == "dismiss":
                        close_btn = dialog.ele("[aria-label='Close']", timeout=0.3)
                        if close_btn and close_btn.states.has_rect:
                            close_btn.click()
                            result["handled"] = True
                            time.sleep(0.5)
                            break
            except Exception as e:
                logger.debug(f"  AI pop-up window judgment exception: {e}")

        if rnd >= 5:
            break
        time.sleep(1.5)

    try:
        page.handle_alert(accept=True, timeout=0.3)
    except Exception:
        pass

    if result["handled"]:
        logger.info("  Release confirmation pop-up window processed")
    return result


def wait_for_publish_confirmation(
    page,
    platform: str,
    timeout_s: int = 30,
    error_check_fn: Callable | None = None,
) -> tuple[bool, str]:
    """Wait for confirmation of successful release (URL fast path + signal + YouTube dialog disappear + AI cover).

    Args:
        page: DrissionPage page object
        platform: "tiktok" | "youtube" | "instagram"
        timeout_s: maximum waiting seconds
        error_check_fn: platform-level error detection callback, signature (page) -> (bool, str)

    Returns:
        (is_success, reason)
    """
    logger.info("  Waiting for confirmation of successful release...")

    url_pattern = get_patterns(platform, "confirm").get("success_url_pattern", {})
    url_not_contains = url_pattern.get("not_contains", [])
    url_or_contains = url_pattern.get("or_contains", [])

    confirm_patterns = get_patterns(platform, "confirm")
    yt_close_sels = confirm_patterns.get("close_button", [])
    yt_dialog_sels = confirm_patterns.get("dialog_selector", [])

    try:
        initial_url = page.url.lower()
    except Exception:
        initial_url = ""
    already_on_content = url_or_contains and any(kw in initial_url for kw in url_or_contains)

    deadline = time.time() + timeout_s
    ai_calls = 0
    max_ai_calls = 3
    poll_interval = 2
    i = 0

    while time.time() < deadline:
        elapsed = int(time.time() + timeout_s - deadline)
        try:
            page.handle_alert(accept=True, timeout=0.3)
        except Exception:
            pass

        try:
            current_url = page.url.lower()
        except Exception:
            logger.warning(f"  ⚠️ Page connection disconnected - Unable to confirm publishing status, please check manually (takes about {elapsed} seconds)")
            return False, "page_disconnected_unverified"

        # 0. Cover-up: detect a delayed secondary confirmation pop-up window every 3 rounds (about 6 seconds) (whitelist mode)
        # Prevent pop-ups from appearing after handle_post_publish_popups exits, resulting in dead wait
        # No detection in each round: the successful path is completely empty polling, wasting CPU + slowing down the normal process
        if i % 3 == 0:
            try:
                late_dialog = _find_dialog(page, platform)
                if late_dialog:
                    dlg_text = (late_dialog.text or "").strip().lower()
                    if not any(kw in dlg_text for kw in [
                        "sharing", "uploading", "processing", "Sharing", "Uploading", "Processing",
                    ]):
                        if _try_whitelist_click(late_dialog, platform):
                            logger.info(f"  ✅ The wait phase handles the delayed pop-up window (it takes about {elapsed} seconds)")
                            time.sleep(1)
                            continue
            except Exception:
                pass

        # 1. URL fast path (excluding the case where the script itself navigates to the content page)
        if url_or_contains and not already_on_content and any(kw in current_url for kw in url_or_contains):
            logger.info(f"  The page has jumped to the management page and was published successfully (it took about {elapsed} seconds)")
            return True, "url_redirect"

        # 2. error_signals 检查
        err_matched, err_sel = check_signals(page, platform, "confirm", "error_signals", timeout=0.3)
        if err_matched:
            logger.error(f"  Publishing failure signal detected: {err_sel}")
            return False, f"error_signal: {err_sel}"

        # 3. Platform-level error detection (such as TikTok asynchronous upload error)
        if error_check_fn and elapsed >= 4:
            try:
                has_err, err_desc = error_check_fn(page)
                if has_err:
                    logger.error(f"  Platform error detection: {err_desc}")
                    return False, f"platform_error: {err_desc}"
            except Exception:
                pass

        # 4. success_signals 快路径
        success_matched, matched_sel = check_signals(page, platform, "confirm", "success_signals", timeout=0.5)
        if success_matched:
            logger.info(f"  Detected publishing success prompt (takes about {elapsed} seconds)")
            return True, f"success_signal: {matched_sel}"

        # 5. YouTube 特有: close_button 可见 + (success_signals 再检 OR dialog 消失)
        if yt_close_sels:
            close_btn = None
            for sel in yt_close_sels:
                try:
                    close_btn = page.ele(sel, timeout=0.3)
                    if close_btn and close_btn.states.has_rect:
                        break
                    close_btn = None
                except Exception:
                    close_btn = None
            if close_btn:
                recheck, _ = check_signals(page, platform, "confirm", "success_signals", timeout=0.3)
                if recheck:
                    logger.info(f"  Release completed (close button + signal confirmation, takes about {elapsed} seconds)")
                    return True, "close_button_with_signal"
                dialog_gone = True
                for sel in yt_dialog_sels:
                    try:
                        dlg = page.ele(sel, timeout=0.3)
                        if dlg and dlg.states.has_rect:
                            dialog_gone = False
                            break
                    except Exception:
                        pass
                if dialog_gone:
                    logger.info(f"  Publishing completed (dialog box closed, took about {elapsed} seconds)")
                    return True, "dialog_closed"

        # 6. AI back-up (wall-clock control: only after 6 seconds, at most once every 8 seconds, and no more than half of the remaining time)
        remaining = deadline - time.time()
        if elapsed >= 6 and i % 4 == 3 and ai_calls < max_ai_calls and remaining > 10:
            ai_calls += 1
            try:
                from social_uploader.tools.ai_judge import judge_success
                ai_result = judge_success(page, platform)
                if ai_result:
                    status = ai_result.get("status", "pending")
                    reason = ai_result.get("reason", "")
                    confidence = ai_result.get("confidence", 0)
                    if status == "success" and confidence >= 0.7:
                        logger.info(f"  [AI] Determine the release is successful: {reason} (it takes about {elapsed} seconds)")
                        return True, f"ai_judge: {reason}"
                    # —— Scheduled release scenario: AI returns pending but reason contains the scheduling keyword, which is considered successful.
                    # Because "scheduled" means that the video has been successfully delivered to the platform scheduling queue and the publishing action has been completed.
                    # It’s just that the platform has not yet reached the release time point. There is no point in continuing to wait for "published" (possibly a few days at most).
                    # Keyword coverage in Chinese and English: scheduled / scheduled / planned / scheduled time / will be published
                    _SCHEDULED_KEYWORDS = (
                        "scheduled", "schedule for", "set to publish", "will be published",
                        "已排定", "已计划", "已安排", "排定时间", "定时发布", "计划于",
                    )
                    reason_lc = reason.lower()
                    if status == "pending" and confidence >= 0.6 and any(
                        kw in reason_lc or kw in reason for kw in _SCHEDULED_KEYWORDS
                    ):
                        logger.info(f"  [AI] It is determined that the scheduled release has taken effect: {reason} (it takes about {elapsed} seconds)")
                        return True, f"ai_judge_scheduled: {reason}"
                    if status == "failed" and confidence >= 0.8:
                        logger.error(f"  [AI] Determination of release failure: {reason}")
                        return False, f"ai_judge: {reason}"
            except Exception as e:
                logger.debug(f"  AI success judgment exception: {e}")

        if i % 5 == 4:
            logger.info(f"   Waiting... ({elapsed} seconds)")
        time.sleep(poll_interval)
        i += 1

    logger.warning(f"  Timeout waiting for release confirmation ({timeout_s} seconds)")
    return False, f"timeout_{timeout_s}s"
