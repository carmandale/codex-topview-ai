import time
import os
import logging

from social_uploader.uploaders import should_skip
from social_uploader.uploaders.video_check import validate_video_file, log_login_error, quick_login_check
from social_uploader.tools.browser_manager import connect_browser, dismiss_interfering_overlays, find_platform_tab, check_page_error, inject_popup_guard, cleanup_tabs
from social_uploader.tools.element_finder import find_element, preflight_check
from social_uploader.repair_engine import log_step, report_failure, generate_run_id, write_success, safe_page_url
from social_uploader.tools.upload_profile import load_profile, get_platform_config, validate_platform_config
from social_uploader.tools.pattern_checker import dismiss_popups as _dismiss_popups_cfg, check_signals, get_signal_list

logger = logging.getLogger(__name__)

"""
Code map (when making AI modifications, look here first to locate the code location):

Step name | What to do | Code location
----------------|----------------------------|---------------------------
validate | Verify video file | Start with upload_instagram()
connect | Connect browser | upload_instagram() middle section
login | Open home page + check login | _do_upload_instagram() → "Phase 1"
create_btn | Click the "New Post" button | _do_upload_instagram() → "Phase 2"
file_inject | Inject video file | _do_upload_instagram() → "Phase 3"
crop_wait | Wait for the cropping interface to be ready | _do_upload_instagram() → "Phase 4"
ratio | select original ratio | _do_upload_instagram() → "Phase 5"
next1 | first next step (crop→filter) | _do_upload_instagram() → "stage 6"
next2 | Second next step (filter→info) | _do_upload_instagram() → "Stage 7"
caption | Fill in the publication copy | _do_upload_instagram() → "Stage 8"
share | Click the share button | _do_upload_instagram() → "Stage 9"
confirm | Wait for publishing to complete | _do_upload_instagram() → "Phase 10"

Helper functions:
  _handle_popups() — close various distracting popups
  _find_text_button() — Find clickable elements by text (Instagram only)
  _click_next() — Find and click "Next"
  should_skip() — resume-from skip judgment (from uploaders.__init__)

Implemented profile configuration items (profile.instagram.*):
  share_to_feed — sync to feed (default true)
"""

INSTAGRAM_URL_PREFIX = "https://www.instagram.com"
STEPS = [
    "validate", "connect", "login", "page_check", "create_btn", "file_inject",
    "crop_wait", "ratio", "next1", "next2", "caption", "share", "confirm",
]


def _handle_popups(page, max_rounds=3):
    """Read Instagram popup close selector from state_patterns.json."""
    _dismiss_popups_cfg(page, "instagram", max_rounds=max_rounds)


def _find_text_button(page, keywords, scope='dialog'):
    """
    Universal Text Button Find: Match clickable elements by text content in dialogs or full pages.
    Instead of using <a>/<button>/role="button", Instagram wraps the text in plain <div>.
    Only return visible (has_rect) elements to avoid NoRectError.
    """
    target = page
    if scope == 'dialog':
        dialog = page.ele('xpath://div[@role="dialog"]', timeout=3)
        if dialog:
            target = dialog

    for kw in keywords:
        for el in target.eles(f'text={kw}', timeout=1):
            try:
                if el.states.has_rect:
                    return el
            except Exception:
                pass

    for kw in keywords:
        for tag in ['div', 'span', 'button', 'a']:
            el = target.ele(f'xpath:.//{tag}[text()="{kw}"]', timeout=0.5)
            if el:
                try:
                    if el.states.has_rect:
                        return el
                except Exception:
                    pass

    if scope == 'dialog':
        dialogs = page.eles('xpath://div[@role="dialog" or @role="presentation"]', timeout=2)
        for dlg in dialogs:
            for kw in keywords:
                for el in dlg.eles(f'text={kw}', timeout=0.5):
                    try:
                        if el.states.has_rect:
                            return el
                    except Exception:
                        pass

    return None


def _click_next(page):
    """Find and click "Next" to read keywords from state_patterns.json."""
    next_kws = get_signal_list("instagram", "navigation", "next_keywords")
    if not next_kws:
        next_kws = ['Next', 'Next step']
    btn = _find_text_button(page, next_kws, scope='dialog')
    if btn:
        btn.click()
        text = (btn.text or '').strip()[:20]
        logger.info(f"  ✅ Next step has been clicked (text='{text}')")
        return True
    logger.warning("  ⚠️ The [Next] button was not found")
    return False


def upload_instagram(video_path, caption, no_publish=False, run_id=None, resume_from=None, profile=None, account=None):
    if run_id is None:
        run_id = generate_run_id()
    if profile is None:
        profile = load_profile()
    config = get_platform_config(profile, "instagram")
    config, constraint_warnings = validate_platform_config("instagram", config)
    for w in constraint_warnings:
        logger.warning(f"  ⚠️ {w}")

    ok, err_msg = validate_video_file(video_path, platform="instagram")
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
            platform_tab = find_platform_tab(ctrl, INSTAGRAM_URL_PREFIX)
            if platform_tab:
                work = platform_tab
                logger.info(f"🔄 Find the Instagram page tag and restore it from {resume_from} steps")
            else:
                logger.warning("⚠️ Instagram page tag not found, will be executed from scratch")
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
        success = _do_upload_instagram(work, ctrl, baseline_tab_ids, video_path, caption, no_publish, run_id, resume_from, config)
        return success
    finally:
        if success:
            write_success(run_id, "instagram", elapsed_s=round(time.time() - _t0))
            cleanup_tabs(ctrl, baseline_tab_ids)
        else:
            logger.info("💡 The task window has been retained and can be resumed from the breakpoint with --resume-from")


def _do_upload_instagram(work, ctrl, baseline_tab_ids, video_path, caption, no_publish, run_id, resume_from, config):
    platform = "instagram"
    page = work

    # resume-from page status verification
    if resume_from:
        current_url = page.url or ""
        if INSTAGRAM_URL_PREFIX not in current_url:
            logger.warning(f"⚠️ The page has left Instagram ({current_url[:60]}...), ignore resume-from, and execute from the beginning")
            log_step("resume_check", "fail", reason="page_url_changed", url=current_url[:100])
            resume_from = None
        else:
            log_step("resume_check", "ok", resume_from=resume_from)

    # === Stage 1: Open Instagram ===
    if not should_skip("login", resume_from, STEPS):
        logger.info("🌐 Visiting Instagram...")
        page.get('https://www.instagram.com/')
        page.wait.doc_loaded(timeout=15)
        inject_popup_guard(page)

        logged_in, detail = quick_login_check(page, platform)
        if not logged_in:
            log_login_error('Instagram')
            log_step("login", "fail", error="login_required", page_url=page.url)
            report_failure(page, run_id, platform, "login", "login_required", safe_page_url(page))
            return False

        if 'accounts/login' in page.url:
            log_login_error('Instagram')
            log_step("login", "fail", error="login_required", page_url=page.url)
            report_failure(page, run_id, platform, "login", "login_required", safe_page_url(page))
            return False
        log_step("login", "ok")

    # === Page status detection ===
    if not should_skip("page_check", resume_from, STEPS):
        has_page_error, page_error_desc = check_page_error(page, platform)
        if has_page_error:
            logger.error(f"❌ Instagram platform exception: {page_error_desc}")
            log_step("page_check", "fail", error="platform_unavailable", detail=page_error_desc)
            report_failure(page, run_id, platform, "page_check", "platform_unavailable", safe_page_url(page),
                           detail=page_error_desc)
            return False
        log_step("page_check", "ok")

        preflight_check(page, platform)

    # === Stage 2: Wait for the "New Post" SVG to appear and click ===
    if not should_skip("create_btn", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)

        logger.info("➕ Wait for the [New Post] button to appear and click...")

        create_btn = None
        matched = ''

        start = time.time()
        while time.time() - start < 15:
            _handle_popups(page, max_rounds=1)
            create_btn, matched_sel = find_element(page, platform, "create_button", timeout=0.5)
            if create_btn:
                matched = matched_sel or 'create_button'
                break
            time.sleep(0.5)

        if not create_btn:
            logger.error("❌ The [New Post] button was not found within 15 seconds, please check the page.")
            log_step("create_btn", "fail", error="selector_not_found", detail="create_button not found")
            report_failure(page, run_id, platform, "create_btn", "selector_not_found", safe_page_url(page),
                           selectors_tried="create_button")
            return False

        elapsed = round(time.time() - start, 1)
        logger.info(f"  ✅ Found the create button ({matched}) [{elapsed}s]")

        create_btn.click()
        time.sleep(1)

        log_step("create_btn", "ok", matched=str(matched)[:50], elapsed_s=elapsed)

    # === Stage 3: Inject video file ===
    if not should_skip("file_inject", resume_from, STEPS):
        logger.info("📂 Inject video files...")

        # Wait for the create post dialog to appear (do not call dismiss_interfering_overlays/_handle_popups at this stage,
        # Because sweep_modals JS and OVERLAY_CLEANUP_JS may close the Instagram upload pop-up window by mistake)
        dlg = None
        for _w in range(15):
            dlg = page.ele('xpath://div[@role="dialog"]', timeout=1)
            if dlg:
                logger.info(f"  ✅ Dialog box has appeared [{_w}s]")
                break
            time.sleep(1)

        if not dlg:
            logger.warning("  ⚠️ The dialog box does not appear, try clicking the create button again...")
            create_btn2, _ = find_element(page, platform, "create_button", timeout=3)
            if create_btn2:
                create_btn2.click()
                time.sleep(3)
                dlg = page.ele('xpath://div[@role="dialog"]', timeout=5)

        # Find the file input directly in the page (without passing the has_rect check of find_element)
        file_input = page.ele('xpath://input[@type="file"]', timeout=5)
        if not file_input and dlg:
            file_input = dlg.ele('xpath:.//input[@type="file"]', timeout=3)

        if not file_input:
            # Try clicking the "Choose from PC" button
            select_btn = None
            for txt in ['Select from computer', 'Select from computer', 'Select from computer', 'Select from device']:
                select_btn = page.ele(f'text:{txt}', timeout=1)
                if select_btn:
                    break
            if select_btn:
                logger.info(f'  📎 Clicking "{(select_btn.text or "").strip()[:30]}"...')
                select_btn.click()
                time.sleep(2)
                file_input = page.ele('xpath://input[@type="file"]', timeout=5)

        if not file_input:
            logger.error("❌ The file upload entry was not found.")
            log_step("file_inject", "fail", error="selector_not_found", detail="file_input not found")
            report_failure(page, run_id, platform, "file_inject", "selector_not_found", safe_page_url(page),
                           selectors_tried="file_input, select_from_computer")
            return False

        try:
            file_input.input(video_path)
        except Exception as e:
            logger.error(f"  ❌ File injection failed: {e}")
            log_step("file_inject", "fail", error="inject_exception", detail=str(e)[:200])
            report_failure(page, run_id, platform, "file_inject", "inject_exception", safe_page_url(page),
                           detail=str(e)[:200])
            return False

        logger.info(f"  ✅ Injected: {os.path.basename(video_path)}")
        log_step("file_inject", "ok", file=os.path.basename(video_path))

    # === Phase 4: Waiting for the cropping interface to be ready ===
    if not should_skip("crop_wait", resume_from, STEPS):
        logger.info("⏳ Waiting for the cutting interface...")
        _handle_popups(page, max_rounds=2)

        confirm_selectors = get_signal_list(platform, "crop_wait", "confirm_dismiss")
        for sel in confirm_selectors:
            for btn in page.eles(sel, timeout=0.5):
                try:
                    if btn.states.has_rect:
                        btn.click()
                        logger.info("  ✅ Confirmed pop-up window")
                        break
                except Exception:
                    pass

        ready_sels = get_signal_list(platform, "crop_wait", "ready_signals")
        for i in range(20):
            dialog = page.ele('xpath://div[@role="dialog"]', timeout=1)
            if dialog:
                found_next = False
                for sel in ready_sels:
                    nxt = dialog.ele(sel, timeout=0.5)
                    if nxt:
                        found_next = True
                        break
                if found_next:
                    logger.info(f"  ✅ Cropping interface ready [{i}s]")
                    break
            time.sleep(1)
        else:
            logger.warning("  ⚠️ Waiting for the cropping interface to time out, try to continue...")
        log_step("crop_wait", "ok")

    # === Stage 5: Select Scale (Original) ===
    if not should_skip("ratio", resume_from, STEPS):
        logger.info("📐 Select size ratio (original)...")
        dialog = page.ele('xpath://div[@role="dialog"]', timeout=2)
        if dialog:
            crop_labels = get_signal_list(platform, "ratio", "crop_labels")
            ratio_btn = None
            for label in crop_labels:
                ratio_btn = dialog.ele(f'xpath:.//*[local-name()="svg" and @aria-label="{label}"]', timeout=0.5)
                if ratio_btn:
                    break
            if ratio_btn:
                ratio_btn.click()
                time.sleep(0.5)
                ratio_options = get_signal_list(platform, "ratio", "ratio_options")
                orig = None
                for sel in ratio_options:
                    orig = page.ele(sel, timeout=0.5)
                    if orig:
                        break
                if orig:
                    orig.click()
                    logger.info("  ✅ Original proportion selected")
                time.sleep(0.3)
            else:
                logger.warning("  ⚠️ Scale button not found, keep default")
        log_step("ratio", "ok")

    # === Stage 6: The first “next step” ===
    if not should_skip("next1", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("⏭️ Next step (Crop → Filter)...")
        if not _click_next(page):
            logger.error("❌ Unable to click [Next] and the process is aborted.")
            log_step("next1", "fail", error="selector_not_found", detail="next_button not found")
            report_failure(page, run_id, platform, "next1", "selector_not_found", safe_page_url(page),
                           selectors_tried="next_button (text=Next/Next)")
            return False
        time.sleep(1)
        log_step("next1", "ok")

    # === Stage 7: The Second "Next Step" ===
    if not should_skip("next2", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("⏭️ Next step (Filter → Fill in information)...")
        if not _click_next(page):
            logger.error("❌ Unable to click [Next] and the process is aborted.")
            log_step("next2", "fail", error="selector_not_found", detail="next_button not found")
            report_failure(page, run_id, platform, "next2", "selector_not_found", safe_page_url(page),
                           selectors_tried="next_button (text=Next/Next)")
            return False
        time.sleep(1)
        log_step("next2", "ok")

    # === Stage 8: Fill in the copy ===
    if not should_skip("caption", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("📝 Fill in the publishing copy...")
        safe_caption = (caption or "")[:2200]

        caption_box, _ = find_element(page, platform, "caption_box", timeout=1)
        if caption_box:
            caption_box.click()
            time.sleep(0.3)
            caption_box.input(safe_caption)
            logger.info("  ✅The copy has been filled in")
        else:
            logger.warning("  ⚠️ Copywriting input box not found, skip.")
        log_step("caption", "ok", filled=bool(caption_box))

    # === Stage 8.5: Setting up share_to_feed ===
    share_to_feed = config.get("share_to_feed", True)
    if not share_to_feed:
        logger.info('⚙️ Turning off "Share to feed"...')
        result = page.run_js("""
            var switches = document.querySelectorAll('input[type="checkbox"], [role="switch"], [role="checkbox"]');
            for (var sw of switches) {
                var row = sw;
                for (var i = 0; i < 8; i++) {
                    row = row.parentElement;
                    if (!row) break;
                    if (row.textContent.includes('Also share to feed') || row.textContent.includes('同步到动态')) {
                        var isOn = sw.checked || sw.getAttribute('aria-checked') === 'true';
                        if (isOn) { sw.click(); return 'toggled'; }
                        return 'ok';
                    }
                }
            }
            return 'not_found';
        """)
        if result in ('toggled', 'ok'):
            logger.info(
                f"  ✅ share_to_feed disabled ({'toggled' if result == 'toggled' else 'already disabled'})"
            )
        else:
            logger.warning("  ⚠️ The share_to_feed switch is not found, the video may be synchronized to the dynamic stream")
            log_step("share_to_feed", "fail", error="switch_not_found",
                     detail="share_to_feed switch not found, video will be published with default settings (sync to dynamic stream)")

    # === no_publish check ===
    if no_publish:
        logger.info("⏸️ --no-publish mode: The form has been filled in, skip the sharing step. Please check manually in your browser and share.")
        log_step("complete", "ok", mode="no_publish")
        return True

    # === Stage 9: Click "Share" ===
    if not should_skip("share", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("🚀 Click [Share]...")
        share_kws = get_signal_list(platform, "navigation", "share_keywords")
        if not share_kws:
            share_kws = ['Share', 'share']
        share_btn = _find_text_button(page, share_kws)
        if share_btn:
            share_btn.click()
            logger.info("  ✅ Clicked [Share]")
            log_step("share", "ok")
        else:
            logger.warning("  ⚠️ The [Share] button was not found, please check manually.")
            log_step("share", "fail", error="selector_not_found", detail="share_button not found")
            report_failure(page, run_id, platform, "share", "selector_not_found", safe_page_url(page),
                           selectors_tried="share_button (text=Share/share)")
            return False

    # === Phase 10: Waiting for release to complete (with smart retries) ===
    if not should_skip("confirm", resume_from, STEPS):
        from social_uploader.tools.post_publish import handle_post_publish_popups, wait_for_publish_confirmation
        from social_uploader.tools.retry_engine import retry_step, StepResult

        popup_result = handle_post_publish_popups(page, platform, max_rounds=3)
        if popup_result.get("action") == "abort":
            logger.error(f"❌ Posting blocked: {popup_result.get('description', '')}")
            log_step("confirm", "fail", error="popup_abort",
                     detail=popup_result.get("description", "")[:200])
            report_failure(page, run_id, platform, "confirm", "popup_abort",
                           page.url, detail=popup_result.get("description", "")[:200])
            return False

        def _ig_idempotent_check():
            matched, _ = check_signals(page, platform, "confirm", "success_signals", timeout=0.5)
            return matched

        def _do_confirm():
            ok, reason = wait_for_publish_confirmation(page, platform, timeout_s=120)
            return StepResult(ok, value=reason, error="" if ok else reason)

        confirm_result = retry_step(
            page, platform, "confirm",
            step_fn=_do_confirm,
            max_retries=2,
            is_irreversible=True,
            pre_retry_check=_ig_idempotent_check,
        )

        if confirm_result.success:
            reason = confirm_result.value or "retry_success"
            logger.info(f"🎉 The Instagram upload process is over. ({reason})")
            log_step("confirm", "ok", detail=str(reason)[:200])
            return True
        else:
            reason = confirm_result.error or "unknown"
            logger.warning(f"  ⚠️ Release confirmation failed: {reason}")
            logger.info("❌ The Instagram upload process ends (success is not confirmed).")
            log_step("confirm", "fail", error="state_mismatch", detail=str(reason)[:200])
            report_failure(page, run_id, platform, "confirm", "state_mismatch",
                           page.url, detail=str(reason)[:200])
            return False
