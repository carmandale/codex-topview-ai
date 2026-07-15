import time
import os
import logging

from social_uploader.uploaders import should_skip
from social_uploader.uploaders.video_check import validate_video_file, log_login_error, quick_login_check
from social_uploader.uploaders.youtube_helpers import (
    ensure_upload_dialog_open,
    find_file_input_deep,
    _writeback_from_fallback,
    _set_youtube_schedule,
)
from social_uploader.tools.browser_manager import connect_browser, dismiss_interfering_overlays, find_platform_tab, check_page_error, inject_popup_guard, cleanup_tabs
from social_uploader.tools.element_finder import find_element, preflight_check
from social_uploader.repair_engine import log_step, report_failure, generate_run_id, write_success, safe_page_url
from social_uploader.tools.upload_profile import load_profile, get_platform_config, validate_platform_config
from social_uploader.tools.pattern_checker import check_signals, get_signal_list, get_patterns, dismiss_popups

logger = logging.getLogger(__name__)

"""
Code map (when making AI modifications, look here first to locate the code location):

Step name | What to do | Code location
----------------|----------------------------|---------------------------
validate | Verify video file | Start with upload_youtube()
connect | connect browser | upload_youtube() middle section
login | Open Studio + Detect login | _do_upload_youtube() → Step 1
cleanup | Close remaining pop-ups | _do_upload_youtube() → Step 2
upload_dialog | Bring up the upload pop-up window | _do_upload_youtube() → Step 3
file_inject | Inject video file | _do_upload_youtube() → Step 4
form_fill | Fill in title and description | _do_upload_youtube() → Step 5
kids | Set not directed to children | _do_upload_youtube() → Step 6
next_steps | Loop click next | _do_upload_youtube() → Step 7
visibility | set to public | _do_upload_youtube() → step 8
publish | Click the publish button | _do_upload_youtube() → Step 9
confirm | Wait for confirmation of successful publishing | _do_upload_youtube() → Step 10

Helper functions:
  should_skip() — resume-from skip judgment (from uploaders.__init__)

YouTube platform-specific helpers (located in uploaders/youtube_helpers.py, other platforms are prohibited from importing):
  find_file_input_deep() — Find file input through Shadow DOM (required for YouTube Studio)
  _set_youtube_schedule() — Scheduled release (format: YYYY-MM-DD HH:MM) + CDP time field focus
  _writeback_from_fallback() — Writeback of elements found in index pattern button_config.json

Implemented profile configuration items (profile.youtube.*):
  made_for_kids — Whether it is made for children (default false)
  visibility — Visibility: public / unlisted / private (default public)
  tags — tags, comma separated string (default null)
  category — category name (default null)
  schedule — Scheduled release time: 'YYYY-MM-DD HH:MM' (default null = publish immediately)
"""

YOUTUBE_UPLOAD_URL_PREFIX = "https://studio.youtube.com"
STEPS = [
    "validate", "connect", "login", "page_check", "cleanup", "upload_dialog",
    "file_inject", "form_fill", "kids", "next_steps", "visibility",
    "publish", "confirm",
]


def upload_youtube(video_path, title, description, no_publish=False, run_id=None, resume_from=None, profile=None, account=None):
    if run_id is None:
        run_id = generate_run_id()
    if profile is None:
        profile = load_profile()
    config = get_platform_config(profile, "youtube")
    config, constraint_warnings = validate_platform_config("youtube", config)
    for w in constraint_warnings:
        logger.warning(f"  ⚠️ {w}")

    ok, err_msg = validate_video_file(video_path, platform="youtube")
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
            platform_tab = find_platform_tab(ctrl, YOUTUBE_UPLOAD_URL_PREFIX)
            if platform_tab:
                work = platform_tab
                logger.info(f"🔄 Find the YouTube Studio page tag, which will be restored from the {resume_from} step")
            else:
                logger.warning("⚠️ YouTube Studio page tag not found, will be executed from scratch")
                work = ctrl.new_tab(url="about:blank")
                work.set.auto_handle_alert(accept=True)
                resume_from = None
        else:
            ctrl, work, baseline_tab_ids, _ = connect_browser(data_dir=data_dir)
        log_step("connect", "ok", port=9222)
    except Exception as e:
        logger.error(f"❌ Failed to connect to the browser, please make sure start_chrome_debug.sh is run. Error details: {e}")
        log_step("connect", "fail", error="unknown", detail=str(e)[:200])
        return False

    success = False
    _t0 = time.time()
    try:
        success = _do_upload_youtube(work, ctrl, baseline_tab_ids, video_path, title, description, no_publish, run_id, resume_from, config)
        return success
    finally:
        if success:
            write_success(run_id, "youtube", elapsed_s=round(time.time() - _t0))
            cleanup_tabs(ctrl, baseline_tab_ids)
        else:
            logger.info("💡 The task window has been retained and can be resumed from the breakpoint with --resume-from")


def _do_upload_youtube(work, ctrl, baseline_tab_ids, video_path, title, description, no_publish, run_id, resume_from, config):
    platform = "youtube"
    page = work

    # resume-from page status verification
    if resume_from:
        current_url = page.url or ""
        if YOUTUBE_UPLOAD_URL_PREFIX not in current_url:
            logger.warning(f"⚠️ The page has left YouTube Studio ({current_url[:60]}...), ignore resume-from, and execute from the beginning")
            log_step("resume_check", "fail", reason="page_url_changed", url=current_url[:100])
            resume_from = None
        else:
            log_step("resume_check", "ok", resume_from=resume_from)

    # 1. Login status detection
    if not should_skip("login", resume_from, STEPS):
        logger.info("🌐 Checking YouTube login status...")
        page.get('https://studio.youtube.com/')
        page.wait.doc_loaded(timeout=10)
        inject_popup_guard(page)

        logged_in, detail = quick_login_check(page, platform)
        if not logged_in:
            log_login_error('YouTube')
            log_step("login", "fail", error="login_required", page_url=page.url)
            report_failure(page, run_id, platform, "login", "login_required", safe_page_url(page))
            return False

        if 'accounts.google.com' in page.url or 'signin' in page.url.lower():
            log_login_error('YouTube')
            log_step("login", "fail", error="login_required", page_url=page.url)
            report_failure(page, run_id, platform, "login", "login_required", safe_page_url(page))
            return False
        log_step("login", "ok")

    # Page status detection
    if not should_skip("page_check", resume_from, STEPS):
        has_page_error, page_error_desc = check_page_error(page, platform)
        if has_page_error:
            logger.error(f"❌ YouTube platform exception: {page_error_desc}")
            log_step("page_check", "fail", error="platform_unavailable", detail=page_error_desc)
            report_failure(page, run_id, platform, "page_check", "platform_unavailable", safe_page_url(page),
                           detail=page_error_desc)
            return False
        log_step("page_check", "ok")

        preflight_check(page, platform)

    # 2. Close remaining pop-up windows
    if not should_skip("cleanup", resume_from, STEPS):
        logger.info("🧹 Scanning and cleaning possible pop-ups...")
        dismiss_popups(page, platform, max_rounds=1)
        cleanup_patterns = get_patterns(platform, "cleanup")
        dialog_js = cleanup_patterns.get("dialog_js", "")
        if dialog_js:
            try:
                page.run_js(dialog_js)
                time.sleep(1)
            except Exception as e:
                logger.debug(f"  JS execution failed to clear pop-up windows: {e}")
        log_step("cleanup", "ok")

    # 3. Call up the upload pop-up window
    # The most stable path measured: URL jump `studio.youtube.com/channel/<id>/videos/upload?d=ud`
    # More reliable than clicking #upload-icon (icon clicks are sometimes silently invalid and the dialog box does not pop up)
    if not should_skip("upload_dialog", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("📤 Calling up the upload pop-up window...")

        dialog_open = ensure_upload_dialog_open(page, timeout=15)

        # Bottom line: URL redirection fails and returns to the original #upload-icon path
        if not dialog_open:
            logger.info("  ↩️ The URL jumps directly without popping up the dialog box, downgrades to #upload-icon click...")
            try:
                upload_icon, _ = find_element(page, platform, "upload_icon", timeout=3)
                if upload_icon:
                    upload_icon.click()
                    time.sleep(2)
                    dialog_open = ensure_upload_dialog_open(page, timeout=5)
                else:
                    create_btn, _ = find_element(page, platform, "create_button", timeout=2)
                    if create_btn:
                        create_btn.click()
                        time.sleep(1)
                        upload_menu_item, _ = find_element(page, platform, "upload_menu_item", timeout=2)
                        if upload_menu_item:
                            upload_menu_item.click()
                            time.sleep(2)
                            dialog_open = ensure_upload_dialog_open(page, timeout=5)
            except Exception as e:
                logger.warning(f"  ⚠️ Abnormal downgrade path: {e}")

        if not dialog_open:
            logger.error("❌ Failed to open the upload dialog box (URL direct jump + #upload-icon + #create-icon all failed)")
            log_step("upload_dialog", "fail", error="dialog_not_open",
                     detail="ytcp-uploads-dialog does not appear within 15s")
            report_failure(page, run_id, platform, "upload_dialog", "dialog_not_open", safe_page_url(page),
                           selectors_tried="ensure_upload_dialog_open + upload_icon + create_button")
            return False

        log_step("upload_dialog", "ok")

    # 4. Wait and upload the file
    if not should_skip("file_inject", resume_from, STEPS):
        logger.info("⏳ Waiting for the upload component to load...")
        # Three layers of security (Track A → Tier2 heuristic → Track B AI)
        file_input, _ = find_element(page, platform, "file_input", timeout=15)
        # The fourth layer of cover: YouTube Studio wraps the file input in the shadowRoot of the web component.
        # Standard querySelector / page.ele cannot penetrate closed shadow root,
        # Use JS to recursively traverse all shadowRoots.
        if not file_input:
            logger.info("  🌑 Three-layer selector miss, try Shadow DOM depth search...")
            file_input = find_file_input_deep(page, timeout=15)
            if file_input:
                logger.info("  ✅ Shadow DOM depth search hits file input")
        if not file_input:
            logger.error("❌ If the upload button is not found within 30 seconds, it may be that the network is too slow or the page structure has changed suddenly.")
            log_step("file_inject", "fail", error="selector_not_found",
                     detail="file input not found (three-layer selector + Shadow DOM depth search failed)")
            report_failure(page, run_id, platform, "file_inject", "selector_not_found", safe_page_url(page),
                           selectors_tried="file_input + shadow_dom_deep")
            return False

        logger.info(f"📁 Silently injecting video file: {video_path}")
        try:
            file_input.input(video_path)
        except Exception as e:
            logger.error(f"  ❌ File injection failed: {e}")
            log_step("file_inject", "fail", error="inject_exception", detail=str(e)[:200])
            report_failure(page, run_id, platform, "file_inject", "inject_exception", safe_page_url(page),
                           detail=str(e)[:200])
            return False
        log_step("file_inject", "ok", file=os.path.basename(video_path))

    # 5. Fill in the form
    if not should_skip("form_fill", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        logger.info("📝 Filling in video information...")
        safe_title = (title or "")[:95]
        safe_desc = (description or "")[:4900]

        title_box = None
        desc_box = None

        title_box, _ = find_element(page, platform, "title_box", timeout=5)
        desc_box, _ = find_element(page, platform, "desc_box", timeout=5)

        if not title_box or not desc_box:
            logger.info("  Not all found by semantic selector, downgraded to index mode...")
            fallback_sels = get_signal_list(platform, "form_fill", "textbox_fallback")
            fallback_sel = fallback_sels[0] if fallback_sels else '#textbox'
            textboxes = page.eles(fallback_sel, timeout=20)
            if len(textboxes) >= 2:
                if not title_box:
                    title_box = textboxes[0]
                    _writeback_from_fallback(title_box, platform, "title_box")
                if not desc_box:
                    desc_box = textboxes[1]
                    _writeback_from_fallback(desc_box, platform, "desc_box")

        if title_box:
            title_box.clear()
            title_box.input(safe_title)
            logger.info("  ✅The title has been filled in")
        else:
            logger.warning("  ⚠️ Title input box not found, skip")

        if desc_box:
            desc_box.clear()
            desc_box.input(safe_desc)
            logger.info("  ✅ Description has been filled in")
        else:
            logger.warning("  ⚠️ Description input box not found, skip")

        tags = config.get("tags")
        if tags:
            logger.info("🏷️ Filling in tags...")
            show_more = page.ele('text:Show more', timeout=2) or page.ele('text:展开', timeout=1)
            if show_more:
                try:
                    show_more.click()
                    time.sleep(1)
                except Exception:
                    pass
            tags_input = page.ele('xpath://input[contains(@aria-label,"Tag") or contains(@placeholder,"Tag")]', timeout=3)
            if not tags_input:
                tags_input = page.ele('xpath://input[contains(@aria-label,"标签") or contains(@placeholder,"标签")]', timeout=2)
            if tags_input:
                tag_list = [t.strip() for t in tags.split(',') if t.strip()]
                tags_text = ','.join(tag_list)
                tags_input.clear()
                tags_input.input(tags_text)
                time.sleep(0.3)
                logger.info(f"  ✅ {len(tag_list)} tags filled in")
            else:
                logger.warning("  ⚠️ Tag input box not found")

        category = config.get("category")
        if category:
            safe_cat = category.replace("'", "\\'")
            logger.info(f"🗂️ Setting category: {category}...")
            cat_info = page.run_js(f"""
                var safe = '{safe_cat}';
                var selects = document.querySelectorAll('select, [role="listbox"]');
                for (var sel of selects) {{
                    var row = sel;
                    for (var i=0;i<5;i++) {{ row=row.parentElement; if(!row)break; }}
                    if (row && (row.textContent.includes('Category') || row.textContent.includes('分类'))) {{
                        if (sel.tagName === 'SELECT') {{
                            for (var idx=0; idx < sel.options.length; idx++) {{
                                if (sel.options[idx].textContent.includes(safe)) {{
                                    var rect = sel.getBoundingClientRect();
                                    return {{type: 'select', x: rect.x + rect.width/2, y: rect.y + rect.height/2, delta: idx - sel.selectedIndex}};
                                }}
                            }}
                        }} else {{
                            sel.click();
                            return {{type: 'opened'}};
                        }}
                    }}
                }}
                return null;
            """)
            cat_result = 'not_found'
            if cat_info:
                if cat_info.get('type') == 'select':
                    delta = cat_info.get('delta', 0)
                    if delta == 0:
                        cat_result = 'ok_select'
                    else:
                        cdp_click_at(page, cat_info['x'], cat_info['y'])
                        time.sleep(0.3)
                        arrow = 'ArrowDown' if delta > 0 else 'ArrowUp'
                        for _ in range(abs(delta)):
                            cdp_press_key(page, arrow, arrow)
                            time.sleep(0.05)
                        cdp_press_key(page, 'Enter', 'Enter', 13)
                        cat_result = 'ok_select'
                elif cat_info.get('type') == 'opened':
                    cat_result = 'opened'
            if cat_result == 'ok_select':
                logger.info(f"  ✅ Category: {category}")
            elif cat_result == 'opened':
                time.sleep(0.5)
                opt = page.ele(f'text:{category}', timeout=3)
                if opt:
                    try:
                        opt.click()
                        logger.info(f"  ✅ Category: {category} (Customized drop-down)")
                    except Exception:
                        logger.warning(f"  ⚠️Clicking the category option failed")
                else:
                    logger.warning(f"  ⚠️ Category option not found: {category}")
            else:
                logger.warning(f"  ⚠️Failed to set category: {cat_result}")

        log_step("form_fill", "ok", title_filled=bool(title_box), desc_filled=bool(desc_box),
                 tags=bool(tags), category=bool(category))

    # 6. Set child-oriented options (according to config.made_for_kids)
    if not should_skip("kids", resume_from, STEPS):
        dismiss_interfering_overlays(ctrl, work, baseline_tab_ids)
        made_for_kids = config.get("made_for_kids", False)
        kids_label = "for children" if made_for_kids else "Not for children"
        logger.info(f"👶 Setting viewer limit ({kids_label})...")

        try:
            page.run_js("""
                var sc = document.querySelector('#scrollable-content');
                if (sc) sc.scrollTop = sc.scrollHeight;
            """)
            time.sleep(1.5)
        except Exception:
            pass

        kids_radio_name = "VIDEO_MADE_FOR_KIDS_MFK" if made_for_kids else "VIDEO_MADE_FOR_KIDS_NOT_MFK"

        def verify_kids_selected():
            try:
                result = page.run_js(f"""
                    var radio = document.querySelector('tp-yt-paper-radio-button[name="{kids_radio_name}"]');
                    if (!radio) return 'not_found';
                    if (radio.getAttribute('aria-checked') === 'true' || radio.hasAttribute('checked') || radio.checked) return 'checked';
                    var inner = radio.querySelector('#radioContainer iron-icon, #radioContainer .checked');
                    if (inner) return 'checked';
                    return 'unchecked';
                """)
                return str(result) == 'checked'
            except Exception:
                return False

        kids_clicked = False
        MAX_KIDS_ATTEMPTS = 3

        for attempt in range(MAX_KIDS_ATTEMPTS):
            if attempt > 0:
                logger.info(
                    f'  🔄 Attempt {attempt + 1} to select "No, it is not made for kids"...'
                )
                time.sleep(1)
                try:
                    page.run_js("""
                        var sc = document.querySelector('#scrollable-content');
                        if (sc) sc.scrollTop = sc.scrollHeight;
                    """)
                    time.sleep(1)
                except Exception:
                    pass

            try:
                rect = page.run_js(f"""
                    var radio = document.querySelector('tp-yt-paper-radio-button[name="{kids_radio_name}"]');
                    if (!radio) return null;
                    radio.scrollIntoView({{block: 'center'}});
                    var r = radio.getBoundingClientRect();
                    return {{x: r.x + r.width/2, y: r.y + r.height/2}};
                """)
                if rect:
                    cdp_click_at(page, rect['x'], rect['y'])
                    time.sleep(0.5)
                    if verify_kids_selected():
                        kids_clicked = True
                        logger.info(f"  ✅ Selected (CDP click, {attempt+1}th time)")
                        break
                    else:
                        logger.info("  ⚠️ CDP click executed, but verification failed")
            except Exception:
                pass

            if not kids_clicked:
                kids_radio = page.ele(f'@name={kids_radio_name}', timeout=3)
                if kids_radio:
                    try:
                        kids_radio.click(by_js=False)
                        time.sleep(0.5)
                        if verify_kids_selected():
                            kids_clicked = True
                            logger.info(f"  ✅ Selected (native coordinate click, {attempt+1}th time)")
                            break
                    except Exception:
                        pass

            if not kids_clicked:
                labels = page.eles('#radioLabel', timeout=2)
                for label in labels:
                    text = (label.text or '').strip()
                    text_lower = text.lower()
                    is_match = False
                    if made_for_kids:
                        positive = (
                            'for children' in text_lower
                            or 'made for kids' in text_lower
                            or '面向儿童' in text
                        )
                        negative = (
                            'no' in text_lower
                            or 'not' in text_lower
                            or '不' in text
                        )
                        if positive and not negative:
                            is_match = True
                    else:
                        if 'no' in text_lower or 'not' in text_lower or '不' in text:
                            is_match = True
                    if not is_match:
                        continue
                    try:
                        label.click(by_js=False)
                        time.sleep(0.5)
                        if verify_kids_selected():
                            kids_clicked = True
                            logger.info(f"  ✅ Selected (radioLabel click: {text[:20]}, 1st time {attempt+1})")
                            break
                    except Exception:
                        pass
                if kids_clicked:
                    break

            if not kids_clicked:
                try:
                    result = page.run_js(f"""
                        var radio = document.querySelector('tp-yt-paper-radio-button[name="{kids_radio_name}"]');
                        if (!radio) return 'not_found';
                        var container = radio.querySelector('#radioContainer') || radio.querySelector('.radioContainer');
                        if (container) {{
                            container.scrollIntoView({{block: 'center'}});
                            container.click();
                            return 'ok_container';
                        }}
                        var inp = radio.querySelector('input[type="radio"]');
                        if (inp) {{ inp.click(); return 'ok_input'; }}
                        return 'no_inner';
                    """)
                    if result and str(result).startswith('ok'):
                        time.sleep(0.5)
                        if verify_kids_selected():
                            kids_clicked = True
                            logger.info(f"  ✅ Selected (inner container click: {result}, 1st time {attempt+1})")
                            break
                except Exception:
                    pass

            if not kids_clicked:
                signal_key = "made_for_kids_text" if made_for_kids else "not_made_for_kids_text"
                kids_text_selectors = get_signal_list(platform, "kids", signal_key)
                if not kids_text_selectors:
                    if made_for_kids:
                        kids_text_selectors = [
                            'text:是，内容面向儿童', "text:Yes, it's Made for Kids",
                        ]
                    else:
                        kids_text_selectors = [
                            'text:不，内容不是面向儿童的', "text:No, it's not Made for Kids",
                        ]
                for sel in kids_text_selectors:
                    el = page.ele(sel, timeout=1)
                    if el:
                        try:
                            el.click(by_js=False)
                            time.sleep(0.5)
                            if verify_kids_selected():
                                kids_clicked = True
                                logger.info(f"  ✅ Selected (text selector, time {attempt+1})")
                                break
                        except Exception:
                            pass
                if kids_clicked:
                    break

        if kids_clicked:
            logger.info(f"  ✅ Audience limit setting completed: {kids_label} (selected status verified)")
        else:
            logger.error(
                f'  ❌ Could not select "{kids_label}" automatically; publishing was stopped '
                "to avoid a compliance issue"
            )
            log_step("kids", "fail", error="kids_setting_failed",
                     detail="Multiple strategy attempts failed verification")
            report_failure(page, run_id, platform, "kids", "kids_setting_failed", safe_page_url(page),
                           detail="Failed to set children's options")
            return False

        log_step("kids", "ok")
        time.sleep(1)

    # 7. Cycle through and click Next
    if not should_skip("next_steps", resume_from, STEPS):
        logger.info("⏭️ Skipping intermediate steps (video elements/inspections)...")
        step_names = ['video element', 'examine', 'visibility']
        for i in range(3):
            step_label = step_names[i] if i < len(step_names) else f'Step {i+1}'

            next_btn_sels = get_signal_list(platform, "next_steps", "next_button")
            if not next_btn_sels:
                next_btn_sels = ['#next-button']
            next_btn = None
            for wait in range(15):
                for sel in next_btn_sels:
                    try:
                        candidate = page.ele(sel, timeout=1)
                        if candidate and candidate.states.has_rect:
                            aria_disabled = candidate.attr('aria-disabled')
                            if aria_disabled != 'true':
                                next_btn = candidate
                                break
                    except Exception:
                        continue
                if next_btn:
                    break
                try:
                    _ = page.url
                except Exception:
                    try:
                        ctrl, work, baseline_tab_ids, _ = connect_browser(new_window=False)
                        page = work
                        logger.info("  🔄 Browser reconnected")
                    except Exception:
                        pass
                time.sleep(1)

            if next_btn:
                try:
                    next_btn.click()
                    logger.info(f"  ✅【{step_label}】 has been skipped")
                except Exception:
                    try:
                        page.run_js(f'document.querySelector("{next_btn_sels[0]}").click()')
                        logger.info(f"  ✅【{step_label}】(JS) has been skipped")
                    except Exception:
                        logger.warning(f"  ⚠️ Failed to skip【{step_label}】")
            else:
                logger.warning(f"  ⚠️Next button not found ({step_label}), try to continue...")

            time.sleep(1)
        log_step("next_steps", "ok")

    # === no_publish check ===
    if no_publish:
        logger.info("⏸️ --no-publish mode: The form has been filled in, skip the publishing step. Please select visibility manually in your browser and publish.")
        log_step("complete", "ok", mode="no_publish")
        return True

    # 8. Set visibility (according to config.visibility)
    if not should_skip("visibility", resume_from, STEPS):
        visibility = (config.get("visibility") or "public").upper()
        visibility_labels = {
            "PUBLIC": ("public", "Public"),
            "UNLISTED": ("Not publicly listed", "Unlisted"),
            "PRIVATE": ("Private", "Private"),
        }
        vis_cn, vis_en = visibility_labels.get(visibility, ("public", "Public"))
        logger.info(f"🌍 Setting the video to [{vis_cn} ({vis_en})]...")
        visibility_clicked = False
        for attempt in range(3):
            try:
                info = page.run_js(f"""
                    var selectors = [
                        'tp-yt-paper-radio-button[name="{visibility}"]',
                        '[name="{visibility}"]'
                    ];
                    for (var s of selectors) {{
                        var r = document.querySelector(s);
                        if (r) {{
                            r.scrollIntoView({{block: 'center'}});
                            var rect = r.getBoundingClientRect();
                            return {{type: 'ok_event', x: rect.x + rect.width/2, y: rect.y + rect.height/2}};
                        }}
                    }}
                    var labels = document.querySelectorAll('#radioLabel');
                    for (var l of labels) {{
                        if (l.textContent.includes('{vis_cn}') || l.textContent.includes('{vis_en}')) {{
                            var btn = l.closest('tp-yt-paper-radio-button') || l.parentElement;
                            if (btn) {{
                                btn.scrollIntoView({{block: 'center'}});
                                var rect = btn.getBoundingClientRect();
                                return {{type: 'ok_label', x: rect.x + rect.width/2, y: rect.y + rect.height/2}};
                            }}
                        }}
                    }}
                    return null;
                """)
                if info:
                    cdp_click_at(page, info['x'], info['y'])
                    visibility_clicked = True
                    logger.info(f"  ✅ Set to {vis_cn} (CDP click: {info['type']})")
                    break
            except Exception:
                pass

            vis_radio = page.ele(f'@name={visibility}', timeout=3)
            if vis_radio:
                try:
                    vis_radio.click(by_js=False)
                    visibility_clicked = True
                    logger.info(f"  ✅ Set to {vis_cn} (native click)")
                    break
                except Exception:
                    pass
            time.sleep(1)

        if not visibility_clicked:
            if visibility != "PUBLIC":
                logger.error(f"  ❌ Visibility setting failed (Target: {vis_cn}), aborted to prevent video from being published with wrong visibility.")
                log_step("visibility", "fail", error="visibility_failed",
                         detail=f"Visibility {vis_cn} failed to set, publishing is aborted to prevent leakage")
                report_failure(page, run_id, platform, "visibility", "visibility_failed", safe_page_url(page),
                               detail=f"Visibility {vis_cn} setup failed")
                return False
            else:
                logger.warning(f"  ⚠️ Unable to confirm that {vis_cn} is selected but exposed as default, continue publishing...")
        log_step("visibility", "ok" if visibility_clicked else "fail",
                 error="" if visibility_clicked else "unknown",
                 detail="" if visibility_clicked else f"{vis_cn} setting failed")

        # 8.5 Scheduled release (only in visibility step, PUBLIC needs to be set up first)
        schedule_str = config.get("schedule")
        if schedule_str:
            logger.info(f"📅 Detected scheduled release configuration: {schedule_str}")
            schedule_ok, schedule_diag = _set_youtube_schedule(page, schedule_str)
            if schedule_ok:
                logger.info(f"✅ YouTube scheduled release has been set: {schedule_str}")
                log_step("schedule", "ok", schedule=schedule_str)
            else:
                logger.error(f"❌ YouTube scheduled publishing setting failed: {schedule_str}")
                logger.error("🚨 Security gate control: If the timing setting fails, publishing will be suspended to prevent the video from being made public immediately.")
                log_step("schedule", "fail", error="recipe_step_failed", detail=schedule_str)
                diag = schedule_diag or {}
                report_failure(page, run_id, platform, "schedule", "recipe_step_failed", safe_page_url(page),
                               detail=f"Scheduled publishing {schedule_str} setting failed",
                               recipe_key=diag.get("recipe_key", "schedule_recipe"),
                               failed_step=diag.get("failed_step", ""),
                               semantic_hint=diag.get("semantic_hint", ""),
                               selectors_tried="schedule_recipe")
                return False

    # 9. Click the Publish button
    if not should_skip("publish", resume_from, STEPS):
        logger.info("⏳ Waiting for the publish button to be ready...")
        time.sleep(1.5)

        max_publish_attempts = 20
        clicked = False
        for attempt in range(max_publish_attempts):
            try:
                result = page.run_js("""
                    var btn = document.querySelector('#done-button');
                    if (!btn) return 'not_found';
                    if (btn.disabled || btn.getAttribute('aria-disabled') === 'true'
                        || btn.classList.contains('disabled') || btn.hasAttribute('disabled'))
                        return 'disabled';
                    btn.click();
                    return 'ok';
                """)
                if result == 'ok':
                    logger.info("✅ Video release instruction has been sent!")
                    clicked = True
                    break
                elif result == 'disabled':
                    if attempt % 5 == 4:
                        logger.info(f"  The publish button is not ready yet, waiting... ({attempt+1}/{max_publish_attempts})")
                    time.sleep(1.5)
                    continue
            except Exception:
                pass

            done_btn, _ = find_element(page, platform, "done_button", timeout=3)
            if done_btn:
                try:
                    aria_disabled = done_btn.attr('aria-disabled')
                    if aria_disabled == 'true':
                        time.sleep(1.5)
                        continue
                    if done_btn.states.has_rect:
                        done_btn.click()
                        logger.info("✅ Video release instruction has been sent!")
                        clicked = True
                        break
                except Exception:
                    pass
            logger.warning(f"  ⚠️ Failed to click the publish button, trying again... ({attempt+1}/{max_publish_attempts})")
            time.sleep(1.5)

        if not clicked:
            logger.warning("⚠️ If you still cannot click the publish button after multiple attempts, please check manually.")
            log_step("publish", "fail", error="selector_not_found", detail="done_button is not clickable")
            report_failure(page, run_id, platform, "publish", "selector_not_found", safe_page_url(page),
                           selectors_tried="done_button")
            return False
        log_step("publish", "ok")

    # 10. Wait for confirmation of successful release (with smart retry)
    if not should_skip("confirm", resume_from, STEPS):
        from social_uploader.tools.post_publish import wait_for_publish_confirmation
        from social_uploader.tools.retry_engine import retry_step, StepResult

        def _yt_idempotent_check():
            matched, _ = check_signals(page, platform, "confirm", "success_signals", timeout=0.5)
            return matched

        def _do_confirm():
            ok, reason = wait_for_publish_confirmation(page, platform, timeout_s=60)
            return StepResult(ok, value=reason, error="" if ok else reason)

        confirm_result = retry_step(
            page, platform, "confirm",
            step_fn=_do_confirm,
            max_retries=2,
            is_irreversible=True,
            pre_retry_check=_yt_idempotent_check,
        )

        if confirm_result.success:
            reason = confirm_result.value or "retry_success"
            logger.info(f"🎉The YouTube automated upload process ends. ({reason})")
            log_step("confirm", "ok", detail=str(reason)[:200])
            return True
        else:
            reason = confirm_result.error or "unknown"
            logger.warning(f"  ⚠️ Release confirmation failed: {reason}")
            logger.info("❌The YouTube upload process ends (success is not confirmed).")
            log_step("confirm", "fail", error="state_mismatch", detail=str(reason)[:200])
            report_failure(page, run_id, platform, "confirm", "state_mismatch",
                           page.url, detail=str(reason)[:200])
            return False
