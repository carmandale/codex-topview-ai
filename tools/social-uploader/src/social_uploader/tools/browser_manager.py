import os
import time
import logging
import subprocess
import signal
import platform as _platform
from DrissionPage import ChromiumOptions, ChromiumPage

logger = logging.getLogger(__name__)


_PROJECT_PROFILE_MARKER = ".social_uploader/chrome_profiles"


def _is_project_chrome_process(pid: int) -> tuple[bool, str]:
    """Determine whether the process with the given PID is the debug Chrome started by this project.

    Judgment basis: The process command line must also contain
    - "Google Chrome" (excluding other Electron apps)
    - "--user-data-dir=" and the path contains ".social_uploader/chrome_profiles"
      (Excluding daily Chrome and other third-party debug Chrome)

    Return (is_project_chrome: bool, command_line: str)
    """
    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True, text=True, timeout=3,
        )
        cmd = (result.stdout or "").strip()
    except Exception as e:
        logger.debug(f"  Unable to read PID {pid} Command line: {e}")
        return False, ""

    if not cmd:
        return False, ""
    if "Google Chrome" not in cmd:
        return False, cmd
    if _PROJECT_PROFILE_MARKER not in cmd:
        return False, cmd
    return True, cmd


def kill_browser(port=9222, force=False):
    """Terminate the "Debug Chrome for this project" occupying the specified debugging port for reconnection after account switching.

    Safety guardrails (forced on unless force=True):
      - Only kill Chrome processes whose command line contains ".social_uploader/chrome_profiles"
      - Skip all "Daily Chrome" (those launched by the user themselves)
      - This way even if lsof returns multiple PIDs, it will never accidentally kill other Chrome instances

    Args:
        port: debugging port, default 9222
        force: Bypass security checks in emergency situations (**strongly not recommended**), default False

    Return (killed: bool, message: str).
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP:" + str(port), "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5,
        )
        pids_raw = result.stdout.strip()
        if not pids_raw:
            return False, f"There is no Chrome process running on port {port}"

        pids = list(set(int(p.strip()) for p in pids_raw.splitlines() if p.strip()))
        killed = []
        skipped_safe = []

        for pid in pids:
            if not force:
                is_ours, cmd = _is_project_chrome_process(pid)
                if not is_ours:
                    skipped_safe.append((pid, cmd[:80]))
                    logger.warning(
                        f"  🛡️ Refuse to terminate PID {pid}: does not belong to this project debugging Chrome (user-data-dir does not match)"
                    )
                    continue

            try:
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except ProcessLookupError:
                pass
            except PermissionError:
                logger.warning(f"  ⚠️ No permission to terminate process {pid}, please close Chrome manually")

        if killed:
            time.sleep(1)
            msg = f"{len(killed)} debug Chrome processes for this project have been terminated (PID: {', '.join(str(p) for p in killed)})"
            if skipped_safe:
                msg += f";Safely skip {len(skipped_safe)} non-this project Chrome"
            return True, msg

        if skipped_safe:
            return False, (
                f"FOREIGN_CHROME: {len(skipped_safe)} Chrome processes detected on port {port},"
                f"But none of them belong to the debugging Chrome of this project (user-data-dir does not match) and have been safely skipped."
                f"If you need to force termination, please explicitly call kill_browser(force=True)."
            )
        return False, "Could not terminate any process"

    except FileNotFoundError:
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5,
            )
            target_pids = set()
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        try:
                            target_pids.add(int(parts[-1]))
                        except ValueError:
                            pass
            if target_pids:
                killed_win = []
                for pid in target_pids:
                    if not force:
                        is_ours, _ = _is_project_chrome_process(pid)
                        if not is_ours:
                            logger.warning(
                                f"  🛡️ Windows: Termination refused PID {pid}: Not part of this project Debugging Chrome"
                            )
                            continue
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=5)
                    killed_win.append(pid)
                if killed_win:
                    time.sleep(1)
                    return True, f"{len(killed_win)} Chrome processes for this project on port {port} have been terminated"
                return False, f"FOREIGN_CHROME: The processes on port {port} do not belong to this project's debug Chrome and were safely skipped."
            return False, f"There are no processes running on port {port}"
        except FileNotFoundError:
            return False, "Unable to detect port occupation (lsof/netstat are not available)"
    except Exception as e:
        return False, f"Error terminating browser: {e}"


_POPUP_GUARD_JS = """
(function() {
    if (window.__popupGuard) return 'already_active';

    var exactP1 = ['ok','got it','skip','dismiss','not now','maybe later',
                   'i understand','understood','later',
                   '知道了','确定','了解','跳过','以后再说','明白','好的','好'];
    var exactP2 = ['allow','accept','enable','agree','confirm','yes','sure',
                   'turn on',
                   '允许','开启','接受','同意','确认','是','打开'];
    var exactP3 = ['cancel','close','deny','reject','decline','no','no thanks',
                   'not interested','decline all','ignore',
                   '取消','关闭','拒绝','不用了','否','忽略','不感兴趣','全部拒绝'];

    var dangerWords = ['delete','remove','upload','post','publish','submit','send',
                       'save','download','share','pay','purchase','buy','sign',
                       'install','visit','learn more','get started',
                       'accept all',
                       '删除','移除','上传','发布','提交','发送','保存',
                       '下载','分享','付款','购买','签署',
                       '安装','访问','了解详情','了解更多','开始使用','立即体验',
                       '全部接受'];

    var safeIgnoreTags = ['ytcp-uploads-dialog'];
    var safeIgnoreSelectors = [
        '[class*="upload"]', '[class*="Upload"]',
        '[class*="creator"]', '[class*="Creator"]',
        '[class*="post-dialog"]', '[class*="PostDialog"]'
    ];

    function exactMatch(text, list) {
        var t = text.toLowerCase().trim();
        if (t.length === 0 || t.length > 20) return false;
        for (var kw of list) {
            if (t === kw) return true;
        }
        return false;
    }

    function isDangerous(text) {
        var t = text.toLowerCase().trim();
        for (var dw of dangerWords) {
            if (t.indexOf(dw) >= 0) return true;
        }
        return false;
    }

    function isUploadRelated(dlg) {
        for (var si of safeIgnoreTags) {
            if (dlg.tagName.toLowerCase() === si || dlg.closest(si)) return true;
        }
        for (var sel of safeIgnoreSelectors) {
            try { if (dlg.matches(sel) || dlg.querySelector(sel)) return true; } catch(e) {}
        }
        if (dlg.querySelector('input[type="file"]')) return true;
        var navKw = ['next','back','share','post','publish','下一步','返回','分享','发布'];
        var btns = dlg.querySelectorAll('button,[role="button"]');
        for (var b of btns) {
            var bt = (b.textContent || '').trim().toLowerCase();
            for (var nk of navKw) { if (bt === nk) return true; }
        }
        var text = (dlg.textContent || '').slice(0, 300).toLowerCase();
        if (text.indexOf('upload') >= 0 && text.indexOf('file') >= 0) return true;
        if (text.indexOf('上传') >= 0 && text.indexOf('文件') >= 0) return true;
        if (text.indexOf('select from computer') >= 0) return true;
        if (text.indexOf('从电脑中选择') >= 0 || text.indexOf('从电脑选择') >= 0) return true;
        if (text.indexOf('drag') >= 0 && text.indexOf('drop') >= 0) return true;
        if (text.indexOf('拖放') >= 0 || text.indexOf('拖拽') >= 0) return true;
        return false;
    }

    function isProtectedPublishDialog(dlg) {
        var text = (dlg.textContent || '').toLowerCase();
        if (text.indexOf('continue to post') >= 0) return true;
        if (text.indexOf('继续发布') >= 0) return true;
        if (text.indexOf('检查尚未完成') >= 0) return true;
        var btns = dlg.querySelectorAll('button,[role="button"]');
        var hasCancel = false;
        var hasConfirm = false;
        for (var btn of btns) {
            var bt = (btn.textContent || '').trim().toLowerCase();
            if (bt === 'cancel' || bt === '取消') hasCancel = true;
            if (bt === 'post now' || bt === 'publish now' || bt === '立即发布' || bt === '继续发布') hasConfirm = true;
        }
        return hasCancel && hasConfirm;
    }

    function handleDialog(dlg) {
        try {
            var rect = dlg.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            if (rect.width > window.innerWidth * 0.85 && rect.height > window.innerHeight * 0.85) return;
            if (isUploadRelated(dlg)) return;
            if (isProtectedPublishDialog(dlg)) return;

            var btns = dlg.querySelectorAll('button,[role="button"]');
            if (btns.length === 0) return;

            var groups = [exactP1, exactP2, exactP3];
            for (var grp of groups) {
                for (var btn of btns) {
                    var t = btn.textContent.trim();
                    if (exactMatch(t, grp) && !isDangerous(t) && btn.getBoundingClientRect().width > 0) {
                        btn.click();
                        return;
                    }
                }
            }

            var closeBtn = dlg.querySelector('[aria-label="Close"],[aria-label="close"],[aria-label="关闭"]');
            if (closeBtn) {
                var target = closeBtn.closest('button') || closeBtn;
                if (target.getBoundingClientRect().width > 0) { target.click(); return; }
            }
        } catch(e) {}
    }

    var obs = new MutationObserver(function(muts) {
        if (!window.__popupGuard) return;
        for (var m of muts) {
            for (var node of m.addedNodes) {
                if (node.nodeType !== 1) continue;
                var role = node.getAttribute && node.getAttribute('role');
                if (role === 'dialog' || role === 'alertdialog') {
                    setTimeout(handleDialog.bind(null, node), 600);
                }
                if (node.querySelectorAll) {
                    var inner = node.querySelectorAll('[role="dialog"],[role="alertdialog"]');
                    for (var d of inner) {
                        setTimeout(handleDialog.bind(null, d), 600);
                    }
                }
            }
        }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    window.__popupGuard = true;
    return 'activated';
})();
"""


def inject_popup_guard(page):
    """Inject pop-up window automatic guard (MutationObserver) to intercept and close random pop-up windows in real time.

    Priority strategy:
      P1 Neutral close (Got it/OK) → P2 Accept permission (Allow) → P3 Cancel (Cancel)
    Security: Skip the YouTube upload dialog, skip the main UI dialog that fills the screen.
    """
    try:
        # Use run_iife to get the IIFE return value (see the ASI explanation of tools/js_runner.py for details).
        # The IIFE body remains unchanged because cdp.addScriptToEvaluateOnNewDocument needs to be executed immediately when a new document is injected.
        from social_uploader.tools.js_runner import run_iife
        result = run_iife(page, _POPUP_GUARD_JS)
        if result == 'activated':
            logger.info("  🛡️ Pop-up automatic guard has been activated")
        return result
    except Exception:
        return None


_STALE_TASK_URL_FRAGMENTS = (
    "tiktok.com/tiktokstudio",
    "studio.youtube.com",
    "instagram.com/reels/create",
    "instagram.com/creation/",
    "about:blank",
)


def connect_browser(port=9222, new_window=True, data_dir=None):
    """Connect to the local Chrome debugging port and open a new tab to perform the task.

    parameter:
    - port: Chrome debugging port
    - new_window: True when a new tab page is opened to perform the task
    - data_dir: Chrome user data directory (for multi-account isolation), if it is None, only existing instances will be connected.

    Return (ctrl, work, baseline_tab_ids, work_tab_id):
    - ctrl: ChromiumPage, used for multi-tab management and cleanup
    - work: The tab that actually performs the operation (new tab or current tab)
    - baseline_tab_ids: existing user tag id when connecting (retained after the task is completed)
    - work_tab_id: task tag id
    """
    logger.info(f"🚀 Connecting to local browser (port {port})...")
    co = ChromiumOptions()
    co.set_local_port(port)
    if data_dir:
        co.set_user_data_path(data_dir)
    ctrl = ChromiumPage(co)
    ctrl.set.auto_handle_alert(accept=True)
    try:
        ctrl.run_cdp('Page.addScriptToEvaluateOnNewDocument',
                     source="delete Object.getPrototypeOf(navigator).webdriver")
    except Exception:
        pass
    try:
        ctrl.run_cdp('Page.addScriptToEvaluateOnNewDocument', source=_POPUP_GUARD_JS)
    except Exception:
        pass

    if new_window:
        _close_stale_task_tabs(ctrl)

    try:
        baseline_tab_ids = list(ctrl.tab_ids)
    except Exception:
        baseline_tab_ids = None

    if new_window:
        work = ctrl.new_tab(url="about:blank")
        work.set.auto_handle_alert(accept=True)
        work_tab_id = work.tab_id
        logger.info("  📑 A new tab has been opened to perform the task")
    else:
        work = ctrl
        work_tab_id = ctrl.tab_id

    return ctrl, work, baseline_tab_ids, work_tab_id


def _close_stale_task_tabs(ctrl):
    """Close the task tabs left over from the last run to prevent tab accumulation.

    Only called when new_window=True (fresh upload).
    All_ids[0] is always retained, and ensures that at least 1 tag remains after cleaning.
    """
    try:
        all_ids = list(ctrl.tab_ids)
    except Exception:
        return
    if len(all_ids) <= 1:
        return

    closed = 0
    for tid in all_ids[1:]:
        try:
            remaining = len(all_ids) - closed
            if remaining <= 1:
                break
            tab = ctrl.get_tab(tid)
            url = (tab.url or "").lower()
            if any(frag in url for frag in _STALE_TASK_URL_FRAGMENTS):
                tab.close()
                closed += 1
        except Exception:
            pass
    if closed:
        logger.info(f"  🧹 Cleaned {closed} task tabs left over from the last time")


_OVERLAY_CLEANUP_JS = """
(function() {
    var r = 0;
    document.querySelectorAll('iframe').forEach(function(f) {
        var s = f.src || '';
        if (s.startsWith('chrome-extension://') || s.startsWith('moz-extension://')) {
            f.remove(); r++;
        }
    });
    document.querySelectorAll('body > div, body > section, body > aside').forEach(function(el) {
        if (el.shadowRoot) { el.remove(); r++; return; }
        if (el.querySelector('[role="dialog"],[role="alertdialog"],input[type="file"]')) return;
        if (el.matches('[role="dialog"],[role="alertdialog"]')) return;
        var st = window.getComputedStyle(el);
        var z = parseInt(st.zIndex) || 0;
        if (z > 99999 && (st.position === 'fixed' || st.position === 'absolute')) {
            var rect = el.getBoundingClientRect();
            if (rect.width > 60 && rect.height > 60) { el.remove(); r++; }
        }
    });
    return r;
})();
"""


_JUNK_URL_PREFIXES = (
    "about:blank",
    "chrome-extension://",
    "moz-extension://",
    "chrome://",
    "edge://",
    "data:",
)


def dismiss_interfering_overlays(ctrl, work, baseline_tab_ids=None):
    """Clean up distracting elements: only close clear junk tags (blank pages/extension pages), keep user tags and platform tags."""
    closed_any = False

    if baseline_tab_ids is not None and ctrl is not None:
        try:
            protected = set(baseline_tab_ids) | {work.tab_id}
            for tid in ctrl.tab_ids:
                if tid not in protected:
                    try:
                        tab = ctrl.get_tab(tid)
                        tab_url = (tab.url or "").strip()
                        if not tab_url or any(tab_url.startswith(p) for p in _JUNK_URL_PREFIXES):
                            tab.close()
                            closed_any = True
                    except Exception:
                        pass
            if closed_any:
                logger.info("  🧹 Junk tab page (blank page/expanded page) has been closed")
        except Exception:
            pass

    try:
        # Use run_iife to get the IIFE return value (see the ASI explanation of tools/js_runner.py for details).
        from social_uploader.tools.js_runner import run_iife
        removed = run_iife(work, _OVERLAY_CLEANUP_JS)
        if removed and int(removed) > 0:
            logger.info(f"  🧹 Cleaned {removed} extension/plug-in interference elements")
            closed_any = True
    except Exception:
        pass

    return closed_any


def find_first(page_or_el, selectors, timeout_per=1):
    """Tries multiple selectors on a given page/element, returning the first hit (element, selector)"""
    for selector in selectors:
        el = page_or_el.ele(selector, timeout=timeout_per)
        if el:
            return el, selector
    return None, None


def find_platform_tab(ctrl, url_prefix):
    """Find the tab page whose URL contains url_prefix in existing tabs, which is used to resume-from the window where the connection failed last time."""
    try:
        for tid in ctrl.tab_ids:
            tab = ctrl.get_tab(tid)
            if url_prefix in (tab.url or ""):
                return tab
    except Exception:
        pass
    return None


def _select_all_modifier():
    """Cmd (4) for macOS, Ctrl (2) for other systems."""
    return 4 if _platform.system() == 'Darwin' else 2


def cdp_click_at(page, x, y):
    """Send real mouse clicks at specified coordinates via CDP (isTrusted=true)."""
    page.run_cdp('Input.dispatchMouseEvent',
                 type='mousePressed', x=int(x), y=int(y),
                 button='left', clickCount=1)
    page.run_cdp('Input.dispatchMouseEvent',
                 type='mouseReleased', x=int(x), y=int(y),
                 button='left', clickCount=1)


def cdp_click_element(page, js_selector):
    """Click through CDP on the element targeted by the JS selector (isTrusted=true).

    Returns True on success, False if the element does not exist.
    """
    rect = page.run_js(
        'var el = document.querySelector(arguments[0]);'
        'if (!el) return null;'
        'el.scrollIntoView({block: "center"});'
        'var r = el.getBoundingClientRect();'
        'return {x: r.x + r.width/2, y: r.y + r.height/2};',
        js_selector,
    )
    if not rect:
        return False
    cdp_click_at(page, rect['x'], rect['y'])
    return True


def cdp_press_key(page, key, code, key_code=0):
    """Send real keyboard keystrokes via CDP (isTrusted=true)."""
    page.run_cdp('Input.dispatchKeyEvent',
                 type='keyDown', key=key, code=code,
                 windowsVirtualKeyCode=key_code)
    page.run_cdp('Input.dispatchKeyEvent',
                 type='keyUp', key=key, code=code,
                 windowsVirtualKeyCode=key_code)


def cdp_select_all(page):
    """Send select-all shortcut key via CDP (macOS: Cmd+A, other: Ctrl+A, isTrusted=true)."""
    mod = _select_all_modifier()
    page.run_cdp('Input.dispatchKeyEvent',
                 type='keyDown', key='a', code='KeyA',
                 windowsVirtualKeyCode=65, modifiers=mod)
    page.run_cdp('Input.dispatchKeyEvent',
                 type='keyUp', key='a', code='KeyA',
                 windowsVirtualKeyCode=65, modifiers=mod)


def cdp_type_text(page, text):
    """Input text via CDP (isTrusted=true)."""
    page.run_cdp('Input.insertText', text=text)


_PAGE_ERROR_PATTERNS = {
    "tiktok": {
        "url_contains": ["/unavailable"],
        "texts": ["Feature unavailable", "Function not available", "Something went wrong", "something went wrong",
                  "Page not available", "Page unavailable"],
    },
    "instagram": {
        "url_contains": ["/sorry/", "/challenge/", "/suspended", "/disabled"],
        "texts": ["Sorry, this page isn't available", "This page is unavailable",
                  "Something went wrong", "something went wrong", "Try Again",
                  "Your account has been suspended", "Your account has been suspended"],
    },
    "youtube": {
        "url_contains": ["/oops"],
        "texts": ["Something went wrong", "something went wrong", "YouTube Studio is unavailable",
                  "YouTube Studio is unavailable", "This feature isn't available"],
    },
}


def check_page_error(page, platform):
    """Detect whether the page is in a platform error state (function unavailable, maintenance medium).

    Return (has_error, description). When has_error=True, description describes the cause of the error.
    """
    patterns = _PAGE_ERROR_PATTERNS.get(platform, {})
    current_url = (page.url or "").lower()

    for fragment in patterns.get("url_contains", []):
        if fragment.lower() in current_url:
            return True, f"URL contains '{fragment}'"

    for text in patterns.get("texts", []):
        el = page.ele(f'text:{text}', timeout=1)
        if el:
            try:
                if el.states.has_rect:
                    return True, text
            except Exception:
                pass

    return False, ""


def cleanup_tabs(ctrl, baseline_tab_ids):
    """Close the newly opened tab page for this task and keep the tabs that existed before the connection."""
    if baseline_tab_ids is None or ctrl is None:
        return
    try:
        current_tabs = list(ctrl.tab_ids)
        for tid in current_tabs:
            if tid not in baseline_tab_ids:
                try:
                    ctrl.get_tab(tid).close()
                except Exception:
                    pass
        if baseline_tab_ids:
            try:
                ctrl.get_tab(baseline_tab_ids[0])
            except Exception:
                pass
    except Exception:
        pass
