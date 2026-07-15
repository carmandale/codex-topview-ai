"""YouTube platform-specific auxiliary functions (excluding step arrangement).

[Architecture Agreement]
- `tools/` = Common infrastructure for all platforms
- `uploaders/youtube_helpers.py` = YouTube exclusive auxiliary (only youtube.py can be imported)
- `uploaders/youtube.py` = Step arranger (does not write underlying logic)

Cross-platform import is prohibited: tiktok.py / instagram.py This module is not allowed to be imported.

[This module includes]
- `ensure_upload_dialog_open` URL direct jump + polling waiting for ytcp-uploads-dialog (the most stable path)
- `find_file_input_deep` penetrates Shadow DOM to find video file input (with accept filtering)
- `_set_youtube_schedule` scheduled release recipe execution + CDP time field focus
- `_writeback_from_fallback` element found in index mode is written back button_config.json
"""

import re
import time
import logging

from social_uploader.tools.browser_manager import cdp_click_at, cdp_press_key
from social_uploader.tools.element_finder import add_selector
from social_uploader.tools.recipe_runner import run_recipe

logger = logging.getLogger(__name__)


# JS for deep search of video-specific file input.
# Reality:
# - The real YouTube Studio file input is in the ordinary DOM, accept is empty, name="Filedata".
# - Browser extensions (Glarity/translation plug-ins, etc.) will inject noisy inputs such as accept="application/pdf".
# - Actual measurement: YouTube currently does not have closed shadow DOM packaging, but depth traversal can still be used as a safety net.
# Filter rules:
# - accept is empty / null → accept (YouTube current form)
# - accept contains "video" / "mp4" / "*" → accept
# - Others (pdf / image / audio, etc.) → Reject, to prevent accidentally hitting the extension
#
# DrissionPage's run_js automatically wraps the code in `function(){<code>}` for execution.
# Therefore, the top-level return statement must be used, and (function(){...})() IIFE is strictly prohibited - otherwise the return value will be lost and become None.
_DEEP_VIDEO_FILE_INPUT_JS = r"""
function isVideoInput(inp) {
  var acc = (inp.getAttribute('accept') || '').toLowerCase().trim();
  if (!acc) return true;
  if (acc === '*' || acc === '*/*') return true;
  if (acc.indexOf('video') !== -1) return true;
  if (acc.indexOf('mp4') !== -1) return true;
  return false;
}
function deep(root) {
  if (!root) return null;
  var inputs = root.querySelectorAll ? root.querySelectorAll('input[type="file"]') : [];
  for (var i = 0; i < inputs.length; i++) {
    if (isVideoInput(inputs[i])) return inputs[i];
  }
  var nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
  for (var j = 0; j < nodes.length; j++) {
    if (nodes[j].shadowRoot) {
      var f = deep(nodes[j].shadowRoot);
      if (f) return f;
    }
  }
  return null;
}
return deep(document);
"""


# Upload dialog readiness detection JS.
# Actual measurement: ytcp-uploads-dialog itself has a height of 0 (internally, tp-yt-paper-dialog is used to implement position:fixed),
# Judgment using offsetParent / getBoundingClientRect is not reliable.
# A really reliable "dialog ready" sign is: ytcp-uploads-file-picker is mounted + the top-level file input exists.
#
# ⚠️ Same as above, IIFE is strictly prohibited and top-level return must be used.
_DIALOG_PROBE_JS = r"""
var picker = document.querySelector('ytcp-uploads-file-picker');
if (!picker) return false;
var input = document.querySelector('input[type="file"][name="Filedata"]') ||
            picker.querySelector('input[type="file"]');
return !!input;
"""


def _extract_channel_id(url):
    """Extract channel_id (UCxxxxxxxx) from studio.youtube.com URL."""
    if not url:
        return None
    m = re.search(r'/channel/([^/?#]+)', url)
    return m.group(1) if m else None


def ensure_upload_dialog_open(page, timeout=15):
    """Make sure YouTube Studio's video upload dialog is open.

    The most stable strategy tested (better than clicking #upload-icon, because clicking on the icon sometimes does not pop up the dialog box):
      1. Force to enter the studio homepage to get the channel_id (even if you are currently in the studio domain name, you must re-enter to prevent stale SPA status)
      2. URL jump `studio.youtube.com/channel/<id>/videos/upload?d=ud`
      3. SPA mounting waiting + polling detection <ytcp-uploads-dialog>

    Return True/False.
    """
    # The MutationObserver of popup_guard (browser_manager._POPUP_GUARD_JS) will listen to the newly added [role="dialog"].
    # It checks `if (!window.__popupGuard) return;`, in the first line of callback
    # So setting it to false will stop it from interfering.
    # SPA route switching (page.get) may not refresh the JS context and must be explicitly disabled.
    try:
        page.run_js("window.__popupGuard = false;")
    except Exception:
        pass

    try:
        # The channel homepage must be entered first, even if it is already on studio.youtube.com, it must be refreshed.
        # Because the page status may remain after the login/page_check/cleanup step (popup_guard JS / residual dialog)
        # Re-getting allows channel_id to extract the latest value, and also discards the old SPA state.
        logger.info("  🔄 Reset to studio homepage...")
        page.get('https://studio.youtube.com/')
        page.wait.doc_loaded(timeout=15)
        time.sleep(0.8)  # SPA routing completed

        channel_id = _extract_channel_id(page.url)
        if channel_id:
            upload_url = f'https://studio.youtube.com/channel/{channel_id}/videos/upload?d=ud'
        else:
            upload_url = 'https://studio.youtube.com/?d=ud'
            logger.info(f"  ⚠️ The channel_id is not resolved from {page.url}, use a cryptic URL")

        logger.info(f"  🎯 Direct upload URL: {upload_url}")
        page.get(upload_url)
        page.wait.doc_loaded(timeout=15)
        time.sleep(1.5)  # Give ytcp-uploads-dialog time to mount
    except Exception as e:
        logger.warning(f"  ⚠️ URL jump exception: {e}")

    deadline = time.time() + timeout
    last_url_log = 0.0
    while time.time() < deadline:
        try:
            if page.run_js(_DIALOG_PROBE_JS):
                logger.info("  ✅ Upload dialog is open (ytcp-uploads-dialog)")
                return True
            now = time.time()
            if now - last_url_log >= 3.0:
                cur_url = ""
                try:
                    cur_url = page.url or ""
                except Exception:
                    pass
                logger.info(f"  ⏳ Waiting dialog... (Current url: {cur_url[:90]})")
                last_url_log = now
        except Exception as e:
            logger.debug(f"  Detection anomaly: {e}")
        time.sleep(0.5)

    logger.warning(f"  ⚠️ The dialog box did not appear in {timeout}s")
    return False


def find_file_input_deep(page, timeout=15):
    """Penetrate all Shadow DOM to find <input type="file"> specific to YouTube video uploads.

    With accept filter: exclude non-video file input injected by browser extension (Glarity PDF/Translation plugin),
    Prevent the injection file from being received by the wrong target and causing failure.

    Returns ChromiumElement or None.
    """
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            el = page.run_js(_DEEP_VIDEO_FILE_INPUT_JS)
            if el:
                return el
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    if last_err is not None:
        logger.debug(f"  Shadow DOM depth search exception: {last_err}")
    return None


def _writeback_from_fallback(el, platform, key):
    """When the uploader's own fallback logic finds the element, the valid selector is written back to button_config.json.

    Currently only used in YouTube's form_fill index mode, the move out of the Community Zone is to ensure that the platform code is independent.
    If other platforms also need it in the future, extract tools/.
    """
    try:
        tag = (el.tag or "").lower()
        el_id = el.attr("id") or ""
        aria = el.attr("aria-label") or ""
    except Exception:
        return
    sel = None
    if el_id:
        sel = f"#{el_id}" if "." not in el_id and " " not in el_id else f'@id={el_id}'
    elif aria:
        sel = f'@aria-label={aria}'
    if sel:
        ok, msg = add_selector(platform, key, sel)
        if ok and "already" in msg.lower():
            logger.info(f"  📝 fallback Write back: {platform}.{key} ← {sel}")


def _set_youtube_schedule(page, schedule_str):
    """Set YouTube scheduled publishing (format: 'YYYY-MM-DD HH:MM').

    Use the recipe recipe system (three layers of coverage):
    - Tier 1: Execute by state_patterns.json → youtube.schedule_recipe
    - Tier 2: Heuristically discovers alternative elements when the selector fails, and automatically writes back the recipe when successful.
    - Tier 3: When all fails, enhanced DIAG is output and handed over to Agent for intervention.

    Return (success: bool, diag: dict|None).
    diag contains failed_step / semantic_hint / recipe_key for transparent transmission of report_failure.
    """
    def _format_diag(reason):
        return {
            "failed_step": "format_check",
            "semantic_hint": reason,
            "recipe_key": "schedule_recipe",
        }

    parts = schedule_str.strip().split(' ')
    if len(parts) != 2:
        logger.warning(f"  ⚠️ Timing format error (requires 'YYYY-MM-DD HH:MM'): {schedule_str}")
        return False, _format_diag(f"schedule_str format error: {schedule_str}")
    date_str, time_str = parts
    date_parts = date_str.split('-')
    if len(date_parts) != 3:
        logger.warning(f"  ⚠️ Wrong date format (requires 'YYYY-MM-DD'): {date_str}")
        return False, _format_diag(f"date_str format error: {date_str}")

    try:
        target_day = str(int(date_parts[2]))
    except ValueError:
        logger.warning(f"  ⚠️ The day in the date cannot be parsed as a number: {date_str}")
        return False, _format_diag(f"date_str date field non-numeric: {date_str}")

    time_parts = time_str.split(':')
    if len(time_parts) != 2:
        logger.warning(f"  ⚠️ Incorrect time format (requires 'HH:MM'): {time_str}")
        return False, _format_diag(f"time_str format error: {time_str}")
    try:
        int(time_parts[0])
        int(time_parts[1])
    except ValueError:
        logger.warning(f"  ⚠️ The time contains non-numeric characters: {time_str}")
        return False, _format_diag(f"time_str contains non-digits: {time_str}")

    variables = {
        "date": date_str,
        "time": time_str,
        "day": target_day,
    }

    success, failed_step, hint = run_recipe(page, "youtube", "schedule_recipe", variables)

    if success:
        # Let the YouTube Polymer component complete time verification through CDP focus + Tab (all events isTrusted=true)
        input_rects = page.run_js("""
            var inputs = document.querySelectorAll('#second-container input, #time-of-day-container input');
            var rects = [];
            for (var inp of inputs) {
                var r = inp.getBoundingClientRect();
                if (r.width > 0) rects.push({x: r.x + r.width/2, y: r.y + r.height/2});
            }
            return rects;
        """)
        if input_rects:
            for rect in input_rects:
                cdp_click_at(page, rect['x'], rect['y'])
                time.sleep(0.15)
                cdp_press_key(page, 'Tab', 'Tab', 9)
                time.sleep(0.15)
        time.sleep(1)
        logger.info(f"  ✅ YouTube scheduled release: {schedule_str}")
        return True, None
    logger.warning(f"  ⚠️ YouTube scheduled publishing failed (step={failed_step}, hint={hint})")
    return False, {
        "failed_step": failed_step or "",
        "semantic_hint": hint or "",
        "recipe_key": "schedule_recipe",
    }
