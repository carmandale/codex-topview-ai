"""State pattern detection - read the signal list from state_patterns.json and uniformly detect the page status.

Extract the text/selector detection logic originally hard-coded in each upload script into the configuration file.
Enable the auto-repair system to hot-fix these copywriting changes through the fix-pattern command.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PATTERNS_PATH = Path(__file__).resolve().parent.parent / "state_patterns.json"
_cache = {}


def _load_all():
    """Read the full content of state_patterns.json with file-level caching."""
    if _cache:
        return _cache
    try:
        data = json.loads(_PATTERNS_PATH.read_text(encoding="utf-8"))
        _cache.update(data)
        return _cache
    except Exception as e:
        logger.warning(f"Failed to read state_patterns.json: {e}")
        return {}


def reload_patterns():
    """Clear the cache to force the file to be reloaded the next time it is read."""
    _cache.clear()


def get_patterns(platform, step):
    """Read all mode configurations for the specified platform/step."""
    data = _load_all()
    return data.get(platform, {}).get(step, {})


def get_signal_list(platform, step, signal_type):
    """Read the selector list for the specified platform/step/signal type."""
    patterns = get_patterns(platform, step)
    return patterns.get(signal_type, [])


def check_signals(page, platform, step, signal_type, timeout=0.3):
    """Read the signal list from state_patterns.json and detect page elements one by one.

    Return (matched: bool, matched_selector: str | None).
    Each item in the signal list can be:
      - String selector (such as "text:Post")
      - Dictionary with description (e.g. {"selector": "text:foo", "desc": "bar"})
    """
    signals = get_signal_list(platform, step, signal_type)
    for sig in signals:
        selector = sig["selector"] if isinstance(sig, dict) else sig
        try:
            el = page.ele(selector, timeout=timeout)
            if el and el.states.has_rect:
                return True, selector
        except Exception:
            pass
    return False, None


def check_error_signals(page, platform, step, signal_type="error_signals", timeout=0.3):
    """Specifically detects error signals and returns (has_error: bool, error_desc: str).

    Each item in the error_signals list is {"selector": "...", "desc": "..."}.
    """
    signals = get_signal_list(platform, step, signal_type)
    for sig in signals:
        if isinstance(sig, dict):
            selector = sig["selector"]
            desc = sig.get("desc", selector)
        else:
            selector = sig
            desc = sig
        try:
            el = page.ele(selector, timeout=timeout)
            if el and el.states.has_rect:
                return True, desc
        except Exception:
            pass
    return False, ""


_SWEEP_MODALS_JS = """
(function() {
    var dismissed = 0;
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
        '[class*="upload"]','[class*="Upload"]',
        '[class*="creator"]','[class*="Creator"]',
        '[class*="post-dialog"]','[class*="PostDialog"]'
    ];

    function exactMatch(text, list) {
        var t = text.toLowerCase().trim();
        if (t.length === 0 || t.length > 20) return false;
        for (var kw of list) { if (t === kw) return true; }
        return false;
    }

    function isDangerous(text) {
        var t = text.toLowerCase().trim();
        for (var dw of dangerWords) { if (t.indexOf(dw) >= 0) return true; }
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
        var text = (dlg.textContent || '').slice(0, 500).toLowerCase();
        if (text.indexOf('upload') >= 0 && text.indexOf('file') >= 0) return true;
        if (text.indexOf('上传') >= 0 && text.indexOf('文件') >= 0) return true;
        if (text.indexOf('select from computer') >= 0) return true;
        if (text.indexOf('从电脑选择') >= 0 || text.indexOf('从电脑中选择') >= 0) return true;
        if (text.indexOf('create new post') >= 0 || text.indexOf('创建新帖') >= 0) return true;
        if (text.indexOf('new reel') >= 0 || text.indexOf('新 reel') >= 0) return true;
        if (text.indexOf('drag photos') >= 0 || text.indexOf('drag video') >= 0) return true;
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

    var dialogs = document.querySelectorAll('[role="dialog"],[role="alertdialog"]');
    for (var dlg of dialogs) {
        if (isUploadRelated(dlg)) continue;
        if (isProtectedPublishDialog(dlg)) continue;
        var rect = dlg.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        if (rect.width > window.innerWidth * 0.85 && rect.height > window.innerHeight * 0.85) continue;

        var btns = dlg.querySelectorAll('button,[role="button"]');
        var clicked = false;
        var groups = [exactP1, exactP2, exactP3];

        for (var grp of groups) {
            if (clicked) break;
            for (var btn of btns) {
                var t = btn.textContent.trim();
                if (exactMatch(t, grp) && !isDangerous(t) && btn.getBoundingClientRect().width > 0) {
                    btn.click(); dismissed++; clicked = true; break;
                }
            }
        }

        if (!clicked) {
            var closeBtn = dlg.querySelector('[aria-label="Close"],[aria-label="close"],[aria-label="关闭"]');
            if (closeBtn) {
                var target = closeBtn.closest('button') || closeBtn;
                if (target.getBoundingClientRect().width > 0) { target.click(); dismissed++; clicked = true; }
            }
        }
    }

    var floats = document.querySelectorAll(
        '#tux-portal-container [class*="toast"], #tux-portal-container [class*="Toast"],'
        + '#tux-portal-container [class*="notification"], #tux-portal-container [class*="banner"]'
    );
    for (var fl of floats) {
        if (fl.getBoundingClientRect().width === 0) continue;
        var fb = fl.querySelector('button,[role="button"]');
        if (fb) { fb.click(); dismissed++; }
    }
    return dismissed;
})();
"""


def sweep_modals(page, max_rounds=3):
    """JS universal pop-up scanner: detect and close all visible dialogs/modal/overlays on the page.

    Does not rely on configuration files, automatically identifies pop-up windows through the DOM structure and attempts to close them.
    Returns the total number of closed pop-ups.
    """
    from social_uploader.tools.js_runner import run_iife
    total_dismissed = 0
    for _ in range(max_rounds):
        try:
            closed = run_iife(page, _SWEEP_MODALS_JS)
            count = int(closed) if closed else 0
            if count > 0:
                total_dismissed += count
                logger.info(f"  🧹 Pop-up scanner closed {count} pop-ups")
                time.sleep(0.3)
            else:
                break
        except Exception:
            break
    return total_dismissed


def dismiss_popups(page, platform, max_rounds=3):
    """Comprehensive pop-up window cleaning: first use the JS scanner to process general pop-up windows, and then use the configuration selector to clean up the dialog.

    Configure the selector to search only within role="dialog" / role="alertdialog" elements,
    Avoid accidental jumps caused by matching text with the same name in the main content area on the entire page.
    """
    sweep_modals(page, max_rounds=max_rounds)

    selectors = get_signal_list(platform, "popups", "dismiss")
    if not selectors:
        return
    for _ in range(max_rounds):
        dialogs = page.eles('xpath://*[@role="dialog" or @role="alertdialog"]', timeout=0.3)
        if not dialogs:
            break
        found_any = False
        for dlg in dialogs:
            try:
                dlg_text = (dlg.text or "").lower()
            except Exception:
                dlg_text = ""
            if (
                "continue to post" in dlg_text
                or "continue publishing" in dlg_text
                or "Check not yet completed" in dlg_text
            ):
                continue
            for selector in selectors:
                try:
                    for btn in dlg.eles(selector, timeout=0.05):
                        try:
                            if btn.states.has_rect:
                                btn.click()
                                logger.info(f"  ✅Close pop-up window ({selector})")
                                time.sleep(0.2)
                                found_any = True
                        except Exception:
                            pass
                except Exception:
                    pass
        if not found_any:
            break


def dismiss_error_popup(page, platform, step, signal_type="error_dismiss", timeout=0.3):
    """Close the upload error pop-up window (such as the close/replace button after TikTok's "unable to process" pop-up window)."""
    selectors = get_signal_list(platform, step, signal_type)
    for selector in selectors:
        try:
            btn = page.ele(selector, timeout=timeout)
            if btn and btn.states.has_rect:
                btn.click()
                time.sleep(0.5)
                return
        except Exception:
            pass


def add_pattern(platform, step, signal_type, value):
    """Safely insert the new signal at the beginning of the list in state_patterns.json at the corresponding position.

    Return (success: bool, message: str).
    """
    try:
        data = json.loads(_PATTERNS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Failed to read state_patterns.json: {e}"

    if platform not in data:
        return False, f"Platform \"{platform}\" does not exist in state_patterns.json (available: {', '.join(data.keys())})"

    if step not in data[platform]:
        data[platform][step] = {}

    if signal_type not in data[platform][step]:
        data[platform][step][signal_type] = []

    current_list = data[platform][step][signal_type]

    existing_selectors = []
    for item in current_list:
        if isinstance(item, dict):
            existing_selectors.append(item.get("selector", ""))
        else:
            existing_selectors.append(item)

    if value in existing_selectors:
        return True, f"The signal already exists in {platform}.{step}.{signal_type}, no need to add it again"

    current_list.insert(0, value)

    try:
        _PATTERNS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        return False, f"Failed to write state_patterns.json: {e}"

    reload_patterns()
    total = len(current_list)
    return True, f"OK: \"{value}\" has been added to the beginning of the {platform}.{step}.{signal_type} list ({total} total)"
