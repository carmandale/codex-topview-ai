import time
import os
import json
import logging


# region agent log — Debug session 66b267 (TK confirm debugging)
def _dbg_log_tk(loc, msg, data, hyp, run_id="initial"):
    """Temporary NDJSON debug log (tiktok confirm), written to debug-social-upload.log."""
    try:
        rec = {
            "sessionId": "66b267", "runId": run_id, "hypothesisId": hyp,
            "timestamp": int(time.time() * 1000),
            "location": loc, "message": msg, "data": data,
        }
        with open("debug-social-upload.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


_DBG_TK_PROBE_JS = r"""
var __r = {url: location.href, title: document.title};
try {
    var modals = document.querySelectorAll('[class*="TUXModal"], [role="dialog"], [class*="modal"]');
    var visModals = [];
    modals.forEach(function(m){
        if (m.offsetParent === null) return;
        var t = (m.innerText || '').trim().slice(0, 200);
        visModals.push({tag: m.tagName, cls: (m.className||'').toString().slice(0,100), text: t});
    });
    __r.visible_modals = visModals;
} catch(e) { __r.modal_err = String(e); }
try {
    var pb = document.querySelector('[data-e2e="post_video_button"]') ||
             document.querySelector('button[aria-label*="发布"]') ||
             document.querySelector('button[aria-label*="Post"]');
    if (pb) {
        __r.post_btn = {
            visible: pb.offsetParent !== null,
            aria_disabled: pb.getAttribute('aria-disabled'),
            data_disabled: pb.getAttribute('data-disabled'),
            disabled_attr: pb.disabled,
            text: (pb.textContent||'').trim().slice(0,40),
        };
    } else {
        __r.post_btn = null;
    }
} catch(e) { __r.btn_err = String(e); }
try {
    var toasts = document.querySelectorAll('[class*="toast"], [class*="Toast"], [role="status"], [role="alert"]');
    var visToasts = [];
    toasts.forEach(function(t){
        if (t.offsetParent === null) return;
        var txt = (t.innerText || '').trim().slice(0,200);
        if (txt) visToasts.push(txt);
    });
    __r.visible_toasts = visToasts;
} catch(e) {}
try {
    var cards = document.querySelectorAll('[class*="video"], [class*="card"], [class*="item"]');
    var seen = {};
    var keywords = ['Debug', '已发布', '已计划', '已安排', '审核', 'Scheduled', 'Processing', '处理中', 'Public', '公开', '草稿', 'Draft', '待发布'];
    var rowHits = [];
    cards.forEach(function(c){
        if (c.offsetParent === null) return;
        var t = (c.innerText || '').trim();
        if (t.length < 5 || t.length > 400) return;
        var kwHit = keywords.some(function(kw){ return t.indexOf(kw) >= 0; });
        if (!kwHit) return;
        var sample = t.slice(0,160).replace(/\s+/g,' ');
        if (seen[sample]) return;
        seen[sample] = true;
        rowHits.push(sample);
        if (rowHits.length >= 8) return;
    });
    __r.video_card_hits = rowHits;
} catch(e) { __r.card_err = String(e); }
return JSON.stringify(__r);
"""


def _dbg_tk_probe(page):
    try:
        wrapped = "var __dp_iife_r = (function(){" + _DBG_TK_PROBE_JS + "})(); return __dp_iife_r;"
        raw = page.run_js(wrapped)
        return json.loads(raw) if raw else {}
    except Exception as e:
        return {"probe_err": str(e)}
# endregion

from social_uploader.uploaders import should_skip
from social_uploader.uploaders.video_check import validate_video_file, log_login_error, quick_login_check
from social_uploader.uploaders.tiktok_helpers import (
    _set_toggle,
    _set_checkbox,
    _set_tiktok_visibility,
    _set_tiktok_schedule,
    _set_tiktok_options,
)
from social_uploader.tools.browser_manager import connect_browser, dismiss_interfering_overlays, find_platform_tab, check_page_error, inject_popup_guard, cleanup_tabs
from social_uploader.tools.element_finder import find_element, preflight_check
from social_uploader.repair_engine import log_step, report_failure, generate_run_id, write_success, safe_page_url
from social_uploader.tools.upload_profile import load_profile, get_platform_config, validate_platform_config
from social_uploader.tools.pattern_checker import check_signals, check_error_signals, dismiss_popups, dismiss_error_popup, get_signal_list, get_patterns

logger = logging.getLogger(__name__)

"""
Code map (when making AI modifications, look here first to locate the code location):

Step name | What to do | Code location
----------------|----------------------------|---------------------------
validate | Verify video file | Start with upload_tiktok()
connect | connect browser | upload_tiktok() middle section
login | Open upload page + check login | _do_upload_tiktok() → "Phase 1"
file_inject | Inject video file | _do_upload_tiktok() → "Phase 3"
wait_upload | Wait for Post button enabled | _do_upload_tiktok() → "Wait for upload to be ready"
form_fill | Fill in title and description | _do_upload_tiktok() → "Phase 4"
cover | Upload custom cover | _upload_cover_image() independent function
scroll | scroll to bottom | _do_upload_tiktok() → "Phase 5"
options | Set platform options | _set_tiktok_options() → "Phase 5.5"
copyright | Wait for copyright check to complete | _do_upload_tiktok() → "Phase 6"
publish | Click the publish button | _do_upload_tiktok() → "Phase 7"
confirm | Wait for confirmation of successful release | _do_upload_tiktok() → "Phase 9"

Auxiliary functions in this file (only related to TikTok step arrangement):
  _check_upload_error() — Detect upload error pop-up window
  _dismiss_error_popup() — Close the upload error popup window
  _handle_popups() — close various distracting popups
  should_skip() — resume-from skip judgment (from uploaders.__init__)

TikTok platform-specific helpers (located at uploaders/tiktok_helpers.py, import from other platforms is prohibited):
  _set_toggle() — Set the toggle switch via label text
  _set_checkbox() — Set a custom checkbox via label text
  _set_tiktok_visibility() — Set the visibility drop-down (recipe recipe + three-layer cover)
  _set_tiktok_schedule() — Set scheduled release (recipe recipe + three-layer guarantee)
  _set_tiktok_options() — Unified entrance, set all options according to config

Implemented profile configuration items (profile.tiktok.*):
  visibility — Visibility: everyone/friends/only_me (default everyone)
  schedule — scheduled release: null=immediately, "YYYY-MM-DD HH:MM"=scheduled
  allow_comments — Allow comments (default true)
  allow_reuse — Allow re-creation (default true)
  disclose_content — Content disclosure (default false)
  ai_generated — AI generated tags (default false)
  high_quality — High quality upload (default true)
"""

TIKTOK_UPLOAD_URL_PREFIX = "https://www.tiktok.com"
STEPS = [
    "validate", "connect", "login", "page_check", "file_inject", "wait_upload",
    "form_fill", "cover", "scroll", "options", "copyright", "publish", "confirm",
]


def _check_upload_error(page):
    """Detect TikTok upload error pop-ups and read signals from state_patterns.json."""
    return check_error_signals(page, "tiktok", "wait_upload")


def _dismiss_error_popup(page):
    """Close the upload error pop-up window and read the close selector from state_patterns.json."""
    dismiss_error_popup(page, "tiktok", "wait_upload")


def _handle_popups(page):
    """Read the popup closing selector from state_patterns.json."""
    dismiss_popups(page, "tiktok", max_rounds=1)


def _handle_continue_to_post_dialog(page, total_wait_s: int = 8) -> bool:
    """Dedicated quick processing: TikTok "Continue to post?" review pop-up window → click Post now.

    Pop-up window copy:
        Continue to post?
        We're still checking your video for potential issues.
        Do you want to continue posting before the check is complete?
    Button: [Cancel] [Post now]

    This pop-up window only appears when you click Post before the video review is completed, and it will almost certainly pop up within 0-3 seconds after clicking.
    You must actively click Post now to continue publishing.

    Strategy: "Quick Probe" polling on clicks (300ms interval, default 8s)
    - URL jump/Video has been published toast/Post button disappears → Exit immediately (has been published, this function is not needed)
    - A pop-up window appears → Click Post now
    - There is no pop-up window or success signal within 8s → Let it go and leave it to the follow-up wait_for_publish_confirmation to find out the details

    Why 8s and not 30s?
    - Extremely delayed pop-ups (>8s) by wait_for_publish_confirmation's round-by-round _find_dialog
      + _try_whitelist_click (state_patterns.json whitelist contains "Post now")
    - No more waiting for 30 seconds in a smooth release path, and the overall process is shortened by 20+ seconds

    Return: True = Pop-up window is detected and Post now is successfully clicked; False = No pop-up window appears (posted or timed out)

    Note: The post_btn.click() call must be followed closely, and no sleep can be inserted in the middle, otherwise the pop-up window may be missed.
    """
    dialog_xpath = (
        "xpath://*[contains(@class,'TUXModal') or @role='dialog' or @role='alertdialog']"
        "[.//button[@data-type='primary'] or .//button[2]]"
    )
    post_now_selectors = [
        "xpath:.//button[normalize-space(.)='????']",
        "xpath:.//button[normalize-space(.)='Post now']",
        "xpath:.//button[normalize-space(.)='Publish now']",
        "xpath:.//button[@data-type='primary']",
        "xpath:.//button[not(@aria-disabled='true')][last()]",
        "xpath:.//button[last()]",
    ]
    main_post_xpath = "xpath://button[@data-e2e='post_video_button']"

    POLL_INTERVAL = 0.3
    deadline = time.time() + total_wait_s
    started_at = time.time()
    log_first = True
    while time.time() < deadline:
        elapsed = time.time() - started_at

        # 1) URL has been redirected → published
        try:
            cur_url = (page.url or "").lower()
        except Exception:
            cur_url = ""
        if "/content" in cur_url or "/manage" in cur_url:
            if elapsed > 0.5:
                logger.info(f"  ✅ The URL has been redirected ({cur_url[:60]}), no Continue-to-post processing is required (it takes {elapsed:.1f}s)")
            return False

        # 2) Detect "Video published" toast → Published
        try:
            toast = page.ele("text:Video published", timeout=0.1)
            if toast and toast.states.has_rect:
                logger.info(
                    f'  ✅ Detected the "Video published" toast; no additional post-processing '
                    f"is required ({elapsed:.1f}s)"
                )
                return False
        except Exception:
            pass

        # 3) The main Post button disappears → the form switches to the sharing/processing state, and the publishing process has been advanced.
        # This is a newly added early exit signal: check after 1.5s (leave reaction time for clicks) to avoid misjudgment
        if elapsed >= 1.5:
            try:
                main_post = page.ele(main_post_xpath, timeout=0.1)
            except Exception:
                main_post = None
            if not main_post or (main_post and not main_post.states.has_rect):
                logger.info(f"  ✅ The main Post button has disappeared (the page status is advanced), and there is no Continue-to-post pop-up window (time consuming {elapsed:.1f}s)")
                return False

        # 4) Detect target pop-up window
        try:
            dialog = page.ele(dialog_xpath, timeout=0.1)
        except Exception:
            dialog = None

        if not dialog:
            if log_first:
                logger.info(
                    f'  ⏳ Watching for the "Continue to post?" review dialog '
                    f"(poll every {POLL_INTERVAL}s for up to {total_wait_s}s)"
                )
                log_first = False
            time.sleep(POLL_INTERVAL)
            continue

        # Find the pop-up window → click now
        try:
            dialog_text = (dialog.text or "").strip()[:200]
        except Exception:
            dialog_text = ""
        logger.info(
            f'  🔔 Detected the "Continue to post?" review dialog '
            f"{elapsed:.1f}s after clicking Post"
        )
        logger.info(f"     Pop-up content: {dialog_text[:100]}")

        btn = None
        for post_now_xpath in post_now_selectors:
            try:
                btn = dialog.ele(post_now_xpath, timeout=0.2)
            except Exception:
                btn = None
            if btn and btn.states.has_rect:
                break
        if not btn:
            logger.warning("  ?? ?????????????????????")
            return False

        try:
            btn.click()
            logger.info(f"  ✅ Click [Post now] (response delay {elapsed:.1f}s)")
        except Exception as e:
            logger.warning(f"  ⚠️Click [Post now] failed: {e}, try again after {POLL_INTERVAL}s")
            time.sleep(POLL_INTERVAL)
            continue

        # Wait for the pop-up window to disappear, up to 5 seconds
        for _ in range(25):
            time.sleep(0.2)
            try:
                still = page.ele(dialog_xpath, timeout=0.1)
            except Exception:
                still = None
            if not still:
                logger.info("  ✅ The pop-up window has been closed and the publishing submission was successful.")
                return True
        logger.info("  ⏳ The pop-up window has not disappeared, please continue to poll.")

    logger.info(f"  ℹ️ {total_wait_s}s Quick test did not find the Continue-to-post pop-up window, leaving it to the follow-up")
    return False


def _upload_cover_image(page, target, cover_path):
    """Upload a custom cover image to TikTok"""
    if not cover_path:
        return
    if not os.path.exists(cover_path):
        logger.warning(f"⚠️The cover image file does not exist: {cover_path}, skip the cover setting")
        return
    ext = os.path.splitext(cover_path)[1].lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
        logger.warning(f"⚠️ The cover image format does not support '{ext}', only jpg/png/webp is supported, and the cover setting is skipped")
        return

    logger.info(f"🖼️ Setting custom cover image: {os.path.basename(cover_path)}")

    cover_selectors = [
        'text:Edit cover', 'text:编辑封面',
        'text:Change cover', 'text:更换封面',
        'text:Select cover', 'text:选择封面',
        '@data-e2e=edit_cover',
    ]
    cover_btn = None
    for sel in cover_selectors:
        cover_btn = target.ele(sel, timeout=2)
        if cover_btn:
            break

    if not cover_btn:
        cover_btn = target.ele('xpath://*[contains(@class, "cover") or contains(@class, "thumbnail")]', timeout=3)

    if cover_btn:
        try:
            cover_btn.click()
            time.sleep(1)
            logger.info("  ✅Clicked the cover editing area")
        except Exception as e:
            logger.warning(f"  ⚠️ Failed to click on the cover to edit: {e}")
            return
    else:
        logger.warning("  ⚠️ The cover editing entrance was not found, skipping the cover settings")
        return

    cover_input = page.ele(
        'xpath://input[@type="file" and (@accept="image/*" or contains(@accept, "image/"))]',
        timeout=3,
    )

    if not cover_input:
        upload_selectors = [
            'text:Upload cover', 'text:上传封面',
            'text:From device', 'text:从设备选择',
        ]
        for sel in upload_selectors:
            upload_btn = page.ele(sel, timeout=2)
            if upload_btn:
                try:
                    upload_btn.click()
                    time.sleep(1)
                except Exception:
                    pass
                break

        cover_input = page.ele(
            'xpath://input[@type="file" and (@accept="image/*" or contains(@accept, "image/"))]',
            timeout=3,
        )

    if cover_input:
        accept_attr = cover_input.attr('accept') or ''
        if 'video' in accept_attr and 'image' not in accept_attr:
            logger.warning("  ⚠️ The file input found is a video type rather than an image type, skip uploading the cover to avoid misoperation")
            return

        cover_input.input(cover_path)
        logger.info("  ✅ Cover image has been uploaded")
        time.sleep(2)

        confirm_selectors = ['text:Done', 'text:完成', 'text:Save', 'text:保存', 'text:Confirm', 'text:确认']
        for sel in confirm_selectors:
            btn = page.ele(sel, timeout=2)
            if btn:
                try:
                    if btn.states.has_rect:
                        btn.click()
                        logger.info("  ✅ Cover settings confirmed")
                        time.sleep(1)
                        break
                except Exception:
                    pass
    else:
        logger.warning("  ⚠️ Image upload entry not found (TikTok cover may only support selection from video frames), skip cover upload")


def upload_tiktok(video_path, title, description, no_publish=False, cover_path=None, run_id=None, resume_from=None, profile=None, account=None):
    if run_id is None:
        run_id = generate_run_id()
    if profile is None:
        profile = load_profile()
    config = get_platform_config(profile, "tiktok")
    config, constraint_warnings = validate_platform_config("tiktok", config)
    for w in constraint_warnings:
        logger.warning(f"  ⚠️ {w}")

    ok, err_msg = validate_video_file(video_path, platform="tiktok")
    if not ok:
        logger.error(f"❌ Video pre-verification failed: {err_msg}")
        log_step("validate", "fail", error="file_rejected", detail=err_msg)
        return False
    file_size = os.path.getsize(video_path)
    logger.info(f"✅ Video pre-verification passed ({os.path.basename(video_path)}, {file_size/1024:.0f}KB)")
    log_step("validate", "ok", file=os.path.basename(video_path), size_kb=round(file_size / 1024))

    data_dir = None
    if account is not None:
        from social_uploader.account_manager import get_data_dir
        data_dir = get_data_dir(account)
        logger.info(f"👤 User account: {account}")

    try:
        if resume_from:
            ctrl, work, baseline_tab_ids, _ = connect_browser(new_window=False, data_dir=data_dir)
            platform_tab = find_platform_tab(ctrl, TIKTOK_UPLOAD_URL_PREFIX)
            if platform_tab:
                work = platform_tab
                logger.info(f"🔄 Find the TikTok page tag, which will be restored from {resume_from} steps")
            else:
                logger.warning("⚠️ TikTok page tag not found, will be executed from scratch")
                work = ctrl.new_tab(url="about:blank")
                work.set.auto_handle_alert(accept=True)
                resume_from = None
        else:
            ctrl, work, baseline_tab_ids, _ = connect_browser(data_dir=data_dir)
        log_step("connect", "ok", port=9222)
    except Exception as e:
        logger.error(f"❌ Failed to connect to the browser, please make sure you run start_chrome_debug.sh\n {e}")
        log_step("connect", "fail", error="unknown", detail=str(e)[:200])
        return False

    success = False
    _t0 = time.time()
    try:
        success = _do_upload_tiktok(work, ctrl, baseline_tab_ids, video_path, title, description, no_publish, cover_path, run_id, resume_from, config)
        return success
    finally:
        if success:
            write_success(run_id, "tiktok", elapsed_s=round(time.time() - _t0))
            cleanup_tabs(ctrl, baseline_tab_ids)
        else:
            logger.info("💡 The task window has been retained and can be resumed from the breakpoint with --resume-from")


def _do_upload_tiktok(work, ctrl, baseline_tab_ids, video_path, title, description, no_publish, cover_path, run_id, resume_from, config):
    platform = "tiktok"
    page = work

    # resume-from page status verification
    if resume_from:
        current_url = page.url or ""
        if TIKTOK_UPLOAD_URL_PREFIX not in current_url:
            logger.warning(f"⚠️ The page has left TikTok ({current_url[:60]}...), ignore resume-from, and execute from the beginning")
            log_step("resume_check", "fail", reason="page_url_changed", url=current_url[:100])
            resume_from = None
        else:
            log_step("resume_check", "ok", resume_from=resume_from)

    # === Stage 1: Open TikTok upload page ===
    if not should_skip("login", resume_from, STEPS):
        logger.info("🌐 Visiting TikTok upload page...")
        _target_url = 'https://www.tiktok.com/tiktokstudio/upload?from=upload'
        for _nav_attempt in range(3):
            try:
                page.get(_target_url)
                break
            except Exception as _nav_err:
                _err_name = type(_nav_err).__name__
                if _nav_attempt < 2:
                    logger.warning(f"  ⚠️ Page navigation failed ({_err_name}), reconnecting... (try {_nav_attempt+2}/3)")
                    time.sleep(2)
                    try:
                        reconnected_tab = find_platform_tab(ctrl, "tiktok.com")
                        if reconnected_tab:
                            page = reconnected_tab
                            work = reconnected_tab
                            logger.info("  🔄 Reconnected to TikTok tag")
                        else:
                            page = ctrl.new_tab(url=_target_url)
                            work = page
                            logger.info("  🔄 New tab opened")
                            break
                    except Exception:
                        page = ctrl.new_tab(url=_target_url)
                        work = page
                        logger.info("  🔄 Failed to reconnect, a new tab has been opened")
                        break
                else:
                    logger.error(f"  ❌ Page navigation failed 3 times: {_err_name}")
                    log_step("login", "fail", error="page_disconnected", detail=str(_nav_err)[:200])
                    report_failure(page, run_id, platform, "login", "page_disconnected", "", detail=str(_nav_err)[:200])
                    return False
        page.wait.doc_loaded(timeout=10)
        time.sleep(1)
        inject_popup_guard(page)

        logged_in, detail = quick_login_check(page, platform)
        if not logged_in:
            log_login_error('TikTok')
            log_step("login", "fail", error="login_required", page_url=page.url)
            report_failure(page, run_id, platform, "login", "login_required", safe_page_url(page))
            return False

        if 'login' in page.url.lower() or page.ele('text:Log in', timeout=2) or page.ele('text:登录', timeout=1):
            log_login_error('TikTok')
            log_step("login", "fail", error="login_required", page_url=page.url)
            report_failure(page, run_id, platform, "login", "login_required", safe_page_url(page))
            return False
        log_step("login", "ok")

        _handle_popups(page)
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)

    # === Phase 2: Page status detection ===
    if not should_skip("page_check", resume_from, STEPS):
        has_page_error, page_error_desc = check_page_error(page, platform)
        if has_page_error:
            logger.error(f"❌ TikTok platform exception: {page_error_desc}")
            log_step("page_check", "fail", error="platform_unavailable", detail=page_error_desc)
            report_failure(page, run_id, platform, "page_check", "platform_unavailable", safe_page_url(page),
                           detail=page_error_desc)
            return False
        log_step("page_check", "ok")

        preflight_check(page, platform)

    # === Stage 3: Inject video file ===
    if not should_skip("file_inject", resume_from, STEPS):
        _handle_popups(page)
        logger.info("📁 Injecting video files...")
        iframe = page.get_frame('@src^https://www.tiktok.com/creator#/upload')
        target = iframe if iframe else page

        # Residual detection: If the video card uploaded last time is still there, <input type="file"> will be destroyed, resulting in file_input not being found no matter how you look for it.
        # The performance is as follows: the page has data-e2e="upload_status_container" card or [Replace] button
        # Solution: Refresh the current upload page → return to the blank state → look for file_input again
        try:
            stale_card = target.ele('@data-e2e=upload_status_container', timeout=0.5)
        except Exception:
            stale_card = None
        try:
            replace_btn = target.ele('@aria-label=Replace', timeout=0.3) if not stale_card else None
        except Exception:
            replace_btn = None
        if stale_card or replace_btn:
            logger.warning("  ⚠️ It is detected that the last video card remains on the upload page, refresh the page to clean up the status")
            try:
                _clean_url = "https://www.tiktok.com/tiktokstudio/upload?from=upload"
                page.get(_clean_url)
                page.wait.doc_loaded(timeout=15)
                time.sleep(2)
                _handle_popups(page)
                iframe = page.get_frame('@src^https://www.tiktok.com/creator#/upload')
                target = iframe if iframe else page
                logger.info("  ✅ upload page has been reset")
            except Exception as _e:
                logger.warning(f"  ⚠️ Failed to refresh the upload page: {_e}, continue to try according to the original strategy")

        file_input, sel = find_element(target, platform, "file_input", timeout=15)
        if not file_input:
            logger.error("❌ The file upload entry was not found. The page structure may have changed.")
            log_step("file_inject", "fail", error="selector_not_found", detail="file_input not found")
            report_failure(page, run_id, platform, "file_inject", "selector_not_found", safe_page_url(page),
                           selectors_tried="file_input")
            return False

        # --- Make sure you get the real <input type="file">, not the packaging container ---
        try:
            _fi_tag = file_input.tag
            _fi_type = file_input.attr('type')
        except Exception:
            _fi_tag = _fi_type = None

        if _fi_tag != "input" or _fi_type != "file":
            logger.info(f"  ⚠️ The located element is not <input type='file'> (tag={_fi_tag}, type={_fi_type}), look for the real file input inside/in the page...")
            real_fi = None
            # First search inside the positioned element
            try:
                real_fi = file_input.ele("xpath:.//input[@type='file']", timeout=2)
            except Exception:
                pass
            # Then search within the target range
            if not real_fi:
                try:
                    real_fi = target.ele("xpath://input[@type='file']", timeout=3)
                except Exception:
                    pass
            # Finally, find it in the page scope
            if not real_fi:
                try:
                    real_fi = page.ele("xpath://input[@type='file']", timeout=3)
                except Exception:
                    pass

            if real_fi:
                logger.info(f"  ✅ Find the real file input (tag={real_fi.tag}, type={real_fi.attr('type')})")
                file_input = real_fi
            else:
                logger.warning("  ⚠️ No real <input type='file'> found, try injecting with original element...")

        logger.info(f"   Injection file: {video_path}")
        try:
            file_input.input(video_path)
        except Exception as e:
            logger.error(f"  ❌ File injection failed: {e}")
            log_step("file_inject", "fail", error="inject_exception", detail=str(e)[:200])
            report_failure(page, run_id, platform, "file_inject", "inject_exception", safe_page_url(page),
                           detail=str(e)[:200])
            return False
        log_step("file_inject", "ok", file=os.path.basename(video_path))
    else:
        iframe = page.get_frame('@src^https://www.tiktok.com/creator#/upload')
        target = iframe if iframe else page

    # === Waiting for the upload to be ready (judged by the enabled status of the Post button) ===
    if not should_skip("wait_upload", resume_from, STEPS):
        logger.info("⏳ Waiting for the video upload to be processed...")
        upload_ready = False
        for i in range(120):
            time.sleep(1)

            has_error, error_desc = _check_upload_error(page)
            if has_error:
                logger.error(f"❌ TikTok upload error: {error_desc}")
                _dismiss_error_popup(page)
                logger.info("   Error popup has been closed. This video cannot be uploaded. Please check whether the video file is complete and in the correct format.")
                log_step("wait_upload", "fail", error="file_rejected", detail=error_desc)
                report_failure(page, run_id, platform, "wait_upload", "file_rejected", safe_page_url(page), detail=error_desc)
                return False

            editor_ready, _ = check_signals(target, platform, "wait_upload", "editor_ready", timeout=1)
            if not editor_ready:
                if i % 5 == 4:
                    logger.info(f"   Wait for the editor to appear... ({i+1} seconds)")
                continue

            post_btn, _ = find_element(page, platform, "post_button", timeout=1)
            if post_btn and post_btn.attr('aria-disabled') != 'true' and post_btn.attr('data-disabled') != 'true':
                upload_ready = True
                logger.info(f"   ✅ The Post button is ready and the video processing is completed (it takes about {i+1} seconds)")
                break

            if i % 10 == 9:
                logger.info(f"   Video processing... ({i+1} seconds)")

        if not upload_ready:
            has_error, error_desc = _check_upload_error(page)
            if has_error:
                logger.error(f"❌ TikTok upload error: {error_desc}")
                _dismiss_error_popup(page)
                log_step("wait_upload", "fail", error="file_rejected", detail=error_desc)
                report_failure(page, run_id, platform, "wait_upload", "file_rejected", safe_page_url(page), detail=error_desc)
                return False
            logger.warning("   ⚠️ Waiting for timeout (120 seconds), continue trying...")
        log_step("wait_upload", "ok" if upload_ready else "warn_timeout")
        _handle_popups(page)
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)

    # === Stage 4: Fill in title and description ===
    if not should_skip("form_fill", resume_from, STEPS):
        _handle_popups(page)
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("📝 Filling in title and description...")
        full_text = f"{title or ''}\n\n{description or ''}".strip()[:3900]

        caption_box, _ = find_element(target, platform, "caption_box", timeout=15)

        if caption_box:
            try:
                caption_box.clear()
                caption_box.input(full_text)
                logger.info("✅ Title and description filled in")
            except Exception as e:
                logger.warning(f"⚠️ Failed to fill in: {e}")
        else:
            logger.warning("⚠️ Description input box not found, skip.")
            log_step("form_fill", "fail", error="selector_not_found", detail="caption_box not found")
            report_failure(page, run_id, platform, "form_fill", "selector_not_found", safe_page_url(page),
                           selectors_tried="caption_box")
            return False
        log_step("form_fill", "ok")

    # === Stage 4.5: Upload custom cover image ===
    if not should_skip("cover", resume_from, STEPS):
        if cover_path:
            _upload_cover_image(page, target, cover_path)
        log_step("cover", "ok", has_cover=bool(cover_path))

    # === Stage 5: Scroll to Bottom ===
    if not should_skip("scroll", resume_from, STEPS):
        logger.info("📜Scroll to the bottom...")
        try:
            target.scroll.to_bottom()
            time.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Rolling failed: {e}")
        _handle_popups(page)
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        log_step("scroll", "ok")

    # === Phase 5.5: Setting platform options ===
    if not should_skip("options", resume_from, STEPS):
        _handle_popups(page)
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("⚙️ Setting upload options...")
        changed, recipe_diag = _set_tiktok_options(page, config)
        if changed:
            logger.info(f"  📋 Set: {', '.join(changed)}")
        else:
            logger.info("  ℹ️ Keep all options at their default values")

        requested_schedule = config.get("schedule")
        schedule_set = any(c.startswith("schedule=") for c in changed)
        if requested_schedule and not schedule_set:
            logger.error(f"  ❌ The scheduled publishing setting failed (target: {requested_schedule}). To prevent the video from being published immediately, it has been aborted.")
            log_step("options", "fail", error="recipe_step_failed",
                     detail=f"Scheduled release {requested_schedule} failed to set, the release is suspended to prevent immediate disclosure.")
            schedule_diag = recipe_diag.get("schedule") or {}
            report_failure(page, run_id, platform, "options", "recipe_step_failed", safe_page_url(page),
                           detail=f"Scheduled publishing {requested_schedule} setting failed",
                           recipe_key=schedule_diag.get("recipe_key", "schedule_recipe"),
                           failed_step=schedule_diag.get("failed_step", ""),
                           semantic_hint=schedule_diag.get("semantic_hint", ""),
                           selectors_tried="schedule_recipe")
            return False

        requested_visibility = config.get("visibility", "everyone")
        visibility_set = any(c.startswith("visibility=") for c in changed)
        if requested_visibility != "everyone" and not visibility_set:
            logger.error(f"  ❌ Visibility setting failed (Target: {requested_visibility}), aborted to prevent video from being published publicly.")
            log_step("options", "fail", error="visibility_failed",
                     detail=f"Visibility {requested_visibility} failed to set, publishing aborted to prevent disclosure")
            visibility_diag = recipe_diag.get("visibility") or {}
            report_failure(page, run_id, platform, "options", "visibility_failed", safe_page_url(page),
                           detail=f"Visibility {requested_visibility} setup failed",
                           recipe_key=visibility_diag.get("recipe_key", "visibility_recipe"),
                           failed_step=visibility_diag.get("failed_step", ""),
                           semantic_hint=visibility_diag.get("semantic_hint", ""),
                           selectors_tried="visibility_recipe")
            return False

        log_step("options", "ok", changed=changed)
        time.sleep(0.5)

    # === Stage 6: Wait for copyright check to complete ===
    if not should_skip("copyright", resume_from, STEPS):
        _handle_popups(page)
        logger.info("🔍 Waiting for the copyright check to complete...")
        required_checks = 1  # By default, only 1 item is passed, and the actual quantity is dynamically detected
        time.sleep(1)
        toggle_on_sels = get_signal_list(platform, "copyright", "toggle_selector")
        toggle_off_sels = get_signal_list(platform, "copyright", "toggle_off_selector")
        try:
            enabled_count = 0
            for sel in toggle_on_sels:
                toggles_on = page.eles(sel, timeout=3)
                enabled_count += len(toggles_on) if toggles_on else 0
            if enabled_count > 0:
                required_checks = enabled_count
                logger.info(f"   Detected {required_checks} checks turned on")
            else:
                off_count = 0
                for sel in toggle_off_sels:
                    toggles_off = page.eles(sel, timeout=1)
                    off_count += len(toggles_off) if toggles_off else 0
                if off_count > 0:
                    required_checks = max(1, 2 - off_count)
                    logger.info(f"   Detected that {off_count} check items have been closed, need to wait for {required_checks} items to pass")
                else:
                    logger.info(f"   The switch status is not detected, and the default is to wait for the {required_checks} item to pass.")
        except Exception:
            logger.info(f"   The switch detection is abnormal, and the default is to wait for the {required_checks} item to pass.")

        passed_sels = get_signal_list(platform, "copyright", "passed_signals")
        check_passed = False
        for i in range(15):
            total_passed = 0
            for sel in passed_sels:
                items = page.eles(sel, timeout=0.5)
                total_passed += len(items) if items else 0
            if total_passed >= required_checks:
                logger.info(f"   ✅ All copyright checks passed ({total_passed}/{required_checks} items, which took about {i*2} seconds)")
                check_passed = True
                break
            if i % 5 == 4:
                logger.info(f"   Inspection in progress... Passed {total_passed}/{required_checks} items ({i*2} seconds)")
            time.sleep(2)

        if not check_passed:
            logger.warning("   ⚠️ Copyright check waiting timeout (30 seconds), try to continue publishing...")
        log_step("copyright", "ok" if check_passed else "fail",
                 error="" if check_passed else "timeout",
                 detail="" if check_passed else "Copyright check wait timeout")

    # === Phase 6.5: Pre-Publish Content Restrictions Scan ===
    _has_content_warning = False
    _content_check_warnings = [
        'text:Content may be restricted',
        'text:内容可能会受到限制',
        'text:content check',
    ]
    for _cw_sel in _content_check_warnings:
        _cw_el = page.ele(_cw_sel, timeout=1)
        if _cw_el and _cw_el.states.has_rect:
            _has_content_warning = True
            _cw_text = (_cw_el.text or "").strip()[:150]
            logger.warning(f"  ⚠️ Content restriction warning detected before publishing: {_cw_text}")
            logger.warning("  ⚠️TikTok prompts that the content of this video may be restricted and its visibility may be reduced, but it can still be posted")
            log_step("content_check", "ok", detail=f"content_warning: {_cw_text[:80]}")
            break

    # === Stage 7: Click Publish ===
    if no_publish:
        logger.info("⏸️ --no-publish mode: The form has been filled in, skip the publishing step. Please check and post manually in your browser.")
        log_step("complete", "ok", mode="no_publish")
        return True

    if not should_skip("publish", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)

        # Recheck the upload for errors before publishing (video processing may fail asynchronously)
        has_error, error_desc = _check_upload_error(page)
        if has_error:
            logger.warning(f"  ⚠️Upload error detected before publishing: {error_desc}, try clicking Retry...")
            retry_btn = page.ele('text:Retry', timeout=2) or page.ele('text:重试', timeout=1)
            if retry_btn:
                try:
                    retry_btn.click()
                    logger.info("  🔄 Clicked Retry, waiting for re-upload...")
                    time.sleep(3)
                    for _rw in range(60):
                        time.sleep(2)
                        still_error, _ = _check_upload_error(page)
                        if still_error:
                            if _rw % 10 == 9:
                                logger.info(f"   Reuploading... ({_rw*2} seconds)")
                            continue
                        post_btn_check, _ = find_element(page, platform, "post_button", timeout=1)
                        if post_btn_check and post_btn_check.attr('aria-disabled') != 'true':
                            logger.info(f"  ✅ Re-upload successful (took about {_rw*2} seconds)")
                            break
                    else:
                        logger.error("  ❌ The re-upload times out (120 seconds) and publication is aborted.")
                        log_step("publish", "fail", error="file_rejected", detail=f"Failed after retrying: {error_desc}")
                        report_failure(page, run_id, platform, "publish", "file_rejected", safe_page_url(page), detail=error_desc)
                        return False
                except Exception as e:
                    logger.error(f"  ❌ Click Retry failed: {e}")
                    log_step("publish", "fail", error="file_rejected", detail=error_desc)
                    report_failure(page, run_id, platform, "publish", "file_rejected", safe_page_url(page), detail=error_desc)
                    return False
            else:
                logger.error(f"  ❌ Upload error and no Retry button: {error_desc}")
                log_step("publish", "fail", error="file_rejected", detail=error_desc)
                report_failure(page, run_id, platform, "publish", "file_rejected", safe_page_url(page), detail=error_desc)
                return False

        logger.info("🚀 Looking for the [Publish] button...")
        post_btn, _ = find_element(page, platform, "post_button", timeout=10)

        if not post_btn:
            logger.warning("⚠️ Publish button not found, please check your browser manually.")
            log_step("publish", "fail", error="selector_not_found", detail="post_button not found")
            report_failure(page, run_id, platform, "publish", "selector_not_found", safe_page_url(page),
                           selectors_tried="post_button")
            return False

        for i in range(15):
            if post_btn.attr('aria-disabled') == 'true' or post_btn.attr('data-disabled') == 'true':
                logger.info(f"   Button not ready, waiting... ({i+1}/15)")
                time.sleep(2)
            else:
                break

        if post_btn.attr('aria-disabled') == 'true' or post_btn.attr('data-disabled') == 'true':
            has_error_final, error_desc_final = _check_upload_error(page)
            if has_error_final:
                logger.error(f"❌ Publish button remains disabled, error detected: {error_desc_final}")
                log_step("publish", "fail", error="file_rejected", detail=error_desc_final)
                report_failure(page, run_id, platform, "publish", "file_rejected", safe_page_url(page), detail=error_desc_final)
                return False
            logger.warning("⚠️ Publish button remains disabled (30 seconds), force try to click...")

        # region agent log — TL1: Before publish click (T-A: Is the forced click legal?)
        _dbg_log_tk(
            "tiktok.py:publish:before_click",
            "publish click page state before (post button disabled / top-level modal)",
            {"run_id": run_id, **_dbg_tk_probe(page)},
            "T-A+T-B",
        )
        # endregion

        try:
            post_btn.click()
            logger.info("✅ Publish button clicked")
            # Immediately start monitoring the "Continue to post?" audit pop-up window (close to the click, no sleep in the middle)
            # The pop-up window usually appears within 0-3 seconds after clicking. If the window period is missed, it will be misjudged as "published" by subsequent processes.
            ctp_handled = _handle_continue_to_post_dialog(page)
        except Exception as e:
            logger.warning(f"⚠️ Failed to click publish button: {e}")
            log_step("publish", "fail", error="unknown", detail=str(e)[:200])
            report_failure(page, run_id, platform, "publish", "unknown", safe_page_url(page), detail=str(e)[:200])
            return False
        log_step("publish", "ok")
        if ctp_handled:
            logger.info("  ℹ️ Continue-to-post pop-up window has been processed, waiting for platform jump/release to complete")

    # === Phase 8: Handling possible secondary confirmation pop-ups ===
    from social_uploader.tools.post_publish import handle_post_publish_popups, wait_for_publish_confirmation
    from social_uploader.tools.retry_engine import retry_step, StepResult

    popup_result = handle_post_publish_popups(page, platform, content_warning=_has_content_warning)
    if popup_result.get("action") == "abort":
        logger.error(f"❌ Posting blocked: {popup_result.get('description', '')}")
        log_step("publish_confirm", "fail", error="platform_unavailable",
                 detail=popup_result.get("description", "")[:200])
        report_failure(page, run_id, platform, "publish_confirm", "platform_unavailable",
                       page.url, detail=popup_result.get("description", "")[:200])
        return False

    # === Phase 9: Waiting for confirmation of successful release (with smart retries) ===
    if not should_skip("confirm", resume_from, STEPS):

        def _idempotent_check():
            """Idempotent check: whether the video is already in the works list.
            The URL alone is not enough to determine success (the script may have navigated there on its own),
            Must also detect success_signals or video title.
            """
            try:
                cur = page.url.lower()
            except Exception:
                return False
            matched, _ = check_signals(page, platform, "confirm", "success_signals", timeout=0.5)
            if matched:
                return True
            url_or = get_patterns(platform, "confirm").get("success_url_pattern", {}).get("or_contains", [])
            on_content_page = url_or and any(kw in cur for kw in url_or)
            if on_content_page and title:
                short_title = title[:20]
                title_el = page.ele(f'text:{short_title}', timeout=2)
                if title_el:
                    return True
            return False

        def _do_confirm():
            try:
                ok, reason = wait_for_publish_confirmation(
                    page, platform, timeout_s=30,
                    error_check_fn=_check_upload_error,
                )
                if ok:
                    return StepResult(True, value=reason)

                try:
                    cur = page.url.lower()
                except Exception:
                    logger.warning("  ⚠️ The page connection is disconnected and the publishing status cannot be confirmed. Please check manually.")
                    return StepResult(False, error="page_disconnected_unverified")

                if "upload" in cur:
                    logger.info("  The page is still uploading, proactively check the content management page...")
                    page.get("https://www.tiktok.com/tiktokstudio/content")
                    page.wait.doc_loaded(timeout=10)
                    time.sleep(2)
                    # region agent log — TL3: probe after jumping to content page (T-C, T-D, T-E)
                    _dbg_log_tk(
                        "tiktok.py:confirm:on_content_page",
                        "跳转到 tiktokstudio/content 后页面状态（视频卡片 / success_signals）",
                        {"run_id": run_id, "title_short_for_search": (title[:20] if title else None), **_dbg_tk_probe(page)},
                        "T-C+T-D+T-E",
                    )
                    # endregion
                    matched, sel = check_signals(page, platform, "confirm", "success_signals", timeout=1)
                    if matched:
                        logger.info(f"  ✅ Content page detected success signal: {sel}")
                        return StepResult(True, value=f"manual_nav_signal: {sel}")
                    if title:
                        short_title = title[:20]
                        title_el = page.ele(f'text:{short_title}', timeout=3)
                        if title_el:
                            logger.info(
                                f'  ✅ Found the video title "{short_title}" on the content page; '
                                "treating the upload as successfully published"
                            )
                            return StepResult(True, value="manual_nav_title_verified")
                    logger.warning("  ⚠️ No evidence of successful publishing was found on the content page and it was judged as a failure.")
                    # region agent log — TL4: Final probe before failure (T-C, T-D)
                    _dbg_log_tk(
                        "tiktok.py:confirm:before_fail",
                        "No evidence found on the content page, final page status before failure",
                        {"run_id": run_id, **_dbg_tk_probe(page)},
                        "T-C+T-D",
                    )
                    # endregion
                    try:
                        page.get("https://www.tiktok.com/tiktokstudio/upload?from=upload")
                        page.wait.doc_loaded(timeout=5)
                    except Exception:
                        pass

                return StepResult(False, error=reason)
            except Exception as e:
                err_name = type(e).__name__
                if "Disconnected" in err_name or "disconnected" in str(e).lower():
                    logger.warning("  ⚠️ The page connection is disconnected and the publishing status cannot be confirmed. Please check manually.")
                    return StepResult(False, error="page_disconnected_unverified")
                raise

        confirm_result = retry_step(
            page, platform, "confirm",
            step_fn=_do_confirm,
            max_retries=2,
            is_irreversible=True,
            pre_retry_check=_idempotent_check,
        )

        if confirm_result.success:
            reason = confirm_result.value or "retry_success"
            logger.info(f"🎉 The TikTok upload process is over. ({reason})")
            log_step("confirm", "ok", detail=str(reason)[:200])
            return True
        else:
            reason = confirm_result.error or "unknown"
            logger.warning(f"  ⚠️ Release confirmation failed: {reason}")
            logger.info("❌ The TikTok upload process ends (success is not confirmed).")
            log_step("confirm", "fail", error="state_mismatch", detail=str(reason)[:200])
            try:
                current_url = page.url
            except Exception:
                current_url = "page_disconnected"
            report_failure(page, run_id, platform, "confirm", "state_mismatch",
                           current_url, detail=str(reason)[:200])
            return False
