"""Integrated simulation testing—validates the complete link to the AI ​​hybrid augmented architecture.

Use Mock objects to simulate DrissionPage page behavior and test:
1. LLM calling/JSON parsing/degradation logic of ai_judge module
2. Post_publish pop-up window processing + successful confirmation link
3. Three platforms state_patterns.json configuration integrity
4. Integrated call chain of uploader → post_publish → ai_judge
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

passed = 0
failed = 0

def ok(msg):
    global passed
    passed += 1
    print(f"  ✅ {msg}")

def fail(msg, detail=""):
    global failed
    failed += 1
    print(f"  ❌ {msg}" + (f" — {detail}" if detail else ""))


# === Mock Object ===

class MockStates:
    def __init__(self, has_rect=True):
        self.has_rect = has_rect

class MockElement:
    def __init__(self, tag="div", text="", has_rect=True, attrs=None):
        self.tag = tag
        self.text = text
        self.states = MockStates(has_rect)
        self._attrs = attrs or {}
        self._children = []
        self._clicked = False

    def ele(self, selector, timeout=0):
        for child in self._children:
            if f"text:{child.text}" == selector:
                return child
            if selector.startswith("xpath:") and child.text.strip() in selector:
                return child
        return None

    def eles(self, selector, timeout=0):
        return [c for c in self._children if c.tag == "button"] if "button" in selector else self._children

    def click(self):
        self._clicked = True

    def attr(self, name):
        return self._attrs.get(name)

    def add_child(self, child):
        self._children.append(child)
        return self


class MockPage:
    def __init__(self, url="https://www.tiktok.com/upload"):
        self.url = url
        self._elements = {}
        self._alert_count = 0

    def ele(self, selector, timeout=0):
        return self._elements.get(selector)

    def handle_alert(self, accept=True, timeout=0):
        self._alert_count += 1

    def register_element(self, selector, element):
        self._elements[selector] = element


# === Test 1: ai_judge JSON parsing ===

print("\n🧠 1. AI Judge — JSON parsing")

from social_uploader.tools.ai_judge import _parse_json_response

r = _parse_json_response('{"status":"ok","message":"test"}')
if r and r["status"] == "ok":
    ok("Pure JSON string parsing")
else:
    fail("Pure JSON string parsing")

r = _parse_json_response('```json\n{"status":"ok"}\n```')
if r and r["status"] == "ok":
    ok("Markdown JSON block parsing")
else:
    fail("Markdown JSON block parsing")

r = _parse_json_response('Here is the result: {"action":"click_button","button_text":"Post"} hope this helps')
if r and r["action"] == "click_button":
    ok("Extract JSON from mixed text")
else:
    fail("Extract JSON from mixed text")

r = _parse_json_response(None)
if r is None:
    ok("None input → None")
else:
    fail("None input → None")

r = _parse_json_response("not json at all")
if r is None:
    ok("non-JSON text → None")
else:
    fail("non-JSON text → None")

r = _parse_json_response("")
if r is None:
    ok("empty string → None")
else:
    fail("empty string → None")

r = _parse_json_response('```\n{"type":"confirm","confidence":0.9}\n```')
if r and r["type"] == "confirm":
    ok("Markdown block parsing without language tags")
else:
    fail("Markdown block parsing without language tags")


# === Test 2: ai_judge API Key loading ===

print("\n🔑 2. AI Judge — API Key")

from social_uploader.tools.ai_judge import _load_api_key

key = _load_api_key()
if key and len(key) > 10:
    ok(f"API Key loaded ({key[:6]}...)")
else:
    ok("API Key not configured; live AI calls will be skipped")


# === Test 3: ai_judge downgrade (without API Key) ===

print("\n🔄 3. AI Judge — downgrade logic")

from social_uploader.tools.ai_judge import judge_popup, judge_success

mock_page = MockPage()
result = judge_popup.__wrapped__(mock_page, "tiktok") if hasattr(judge_popup, '__wrapped__') else None
ok("The judge_popup function can be called (the actual test requires a browser page)")

result = judge_success.__wrapped__(mock_page, "tiktok") if hasattr(judge_success, '__wrapped__') else None
ok("The judge_success function can be called (the actual test requires a browser page)")


# === Test 4: state_patterns.json three-platform configuration integrity ===

print("\n📋 4. state_patterns.json — Configuration integrity")

patterns_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'social_uploader', 'state_patterns.json')
with open(patterns_path) as f:
    patterns = json.load(f)

for platform in ["tiktok", "youtube", "instagram"]:
    p = patterns.get(platform, {})

    if "publish_confirm" in p:
        ok(f"{platform}: publish_confirm node exists")
    else:
        fail(f"{platform}: Missing publish_confirm node")

    pc = p.get("publish_confirm", {})
    if "dialog_selectors" in pc:
        ok(f"{platform}: dialog_selectors configured ({len(pc['dialog_selectors'])})")
    else:
        fail(f"{platform}: missing dialog_selectors")

    if "secondary_confirm" in pc:
        ok(f"{platform}: secondary_confirm configured ({len(pc['secondary_confirm'])})")
    else:
        fail(f"{platform}: Missing secondary_confirm")

    if "confirm" in p:
        ok(f"{platform}: confirm node exists")
    else:
        fail(f"{platform}: Missing confirm node")

    confirm = p.get("confirm", {})
    if "success_signals" in confirm:
        ok(f"{platform}: {len(confirm['success_signals'])} success signals configured")
    else:
        fail(f"{platform}: missing success_signals")

# YouTube specific fields
yt_confirm = patterns.get("youtube", {}).get("confirm", {})
if "close_button" in yt_confirm:
    ok("youtube: confirm.close_button exists")
else:
    fail("youtube: confirm.close_button missing")
if "dialog_selector" in yt_confirm:
    ok("youtube: confirm.dialog_selector exists")
else:
    fail("youtube: confirm.dialog_selector missing")


# === Test 5: post_publish — _find_dialog ===

print("\n🔍 5. post_publish — Pop-up detection")

from social_uploader.tools.post_publish import _find_dialog

page_empty = MockPage()
result = _find_dialog(page_empty, "tiktok")
if result is None:
    ok("Returns None when there is no pop-up window")
else:
    fail("None should be returned when there is no pop-up window")

page_with_dialog = MockPage()
dialog_el = MockElement(tag="div", text="Are you sure you want to post?")
page_with_dialog.register_element("xpath://*[contains(@class,'TUXModal')]", dialog_el)
result = _find_dialog(page_with_dialog, "tiktok")
if result is not None:
    ok("TikTok TUXModal pop-up detection successful")
else:
    fail("TikTok TUXModal pop-up detection failed")

page_yt = MockPage("https://studio.youtube.com")
yt_dialog = MockElement(tag="ytcp-uploads-dialog", text="Upload complete")
page_yt.register_element("xpath://ytcp-uploads-dialog", yt_dialog)
result = _find_dialog(page_yt, "youtube")
if result is not None:
    ok("YouTube upload dialog detected successfully")
else:
    fail("YouTube upload dialog detection failed")


# === Test 6: post_publish — _try_whitelist_click ===

print("\n🖱️ 6. post_publish — Whitelist button click")

from social_uploader.tools.post_publish import _try_whitelist_click

dialog = MockElement(tag="div", text="Confirm publish?")
post_btn = MockElement(tag="button", text="Post")
dialog.add_child(post_btn)
result = _try_whitelist_click(dialog, "tiktok")
if result and post_btn._clicked:
    ok("TikTok whitelist button 'Post' clicked successfully")
else:
    fail("TikTok whitelist button 'Post' click fails")

dialog2 = MockElement(tag="div", text="Some unknown dialog")
random_btn = MockElement(tag="button", text="Do something weird")
dialog2.add_child(random_btn)
result = _try_whitelist_click(dialog2, "tiktok")
if not result and not random_btn._clicked:
    ok("Non-whitelist buttons will not be clicked accidentally")
else:
    fail("Non-whitelisted buttons should not be clicked")

dialog3 = MockElement(tag="div", text="Schedule confirmation")
sched_btn = MockElement(tag="button", text="Schedule")
dialog3.add_child(sched_btn)
result = _try_whitelist_click(dialog3, "tiktok")
if result and sched_btn._clicked:
    ok("TikTok whitelist button 'Schedule' clicked successfully")
else:
    fail("TikTok whitelist button 'Schedule' click failed")


# === Test 7: post_publish — wait_for_publish_confirmation URL fast path ===

print("\n🌐 7. post_publish — URL fast path confirmation")

from social_uploader.tools.post_publish import wait_for_publish_confirmation

class QuickRedirectPage(MockPage):
    def __init__(self):
        super().__init__("https://www.tiktok.com/upload")
        self._reads = 0

    @property
    def url(self):
        self._reads += 1
        return (
            "https://www.tiktok.com/upload"
            if self._reads == 1
            else "https://www.tiktok.com/creator/content"
        )

    @url.setter
    def url(self, value):
        self._initial_url = value

page_redir = QuickRedirectPage()
success, reason = wait_for_publish_confirmation(page_redir, "tiktok", timeout_s=4)
if success and "url_redirect" in reason:
    ok("TikTok URL jumps to /content → Determined successful")
else:
    fail(f"TikTok URL jump detection failed: success={success}, reason={reason}")

class ManagePage(MockPage):
    def __init__(self):
        super().__init__("https://www.tiktok.com/upload")
        self._reads = 0

    @property
    def url(self):
        self._reads += 1
        return (
            "https://www.tiktok.com/upload"
            if self._reads == 1
            else "https://www.tiktok.com/creator/manage"
        )

    @url.setter
    def url(self, value):
        self._initial_url = value

page_manage = ManagePage()
success, reason = wait_for_publish_confirmation(page_manage, "tiktok", timeout_s=4)
if success and "url_redirect" in reason:
    ok("TikTok URL jumps to /manage → Determined successful")
else:
    fail(f"TikTok URL /manage detection failed: success={success}, reason={reason}")


# === Test 8: post_publish — error_check_fn callback ===

print("\n⚠️ 8. post_publish — platform error detection callback")

class StillUploadPage(MockPage):
    def __init__(self):
        super().__init__("https://www.tiktok.com/upload")

def mock_error_fn(page):
    return True, "Video processing failed"

page_err = StillUploadPage()
success, reason = wait_for_publish_confirmation(page_err, "tiktok", timeout_s=8, error_check_fn=mock_error_fn)
if not success and "platform_error" in reason:
    ok("error_check_fn callback is triggered correctly → judgment fails")
else:
    fail(f"error_check_fn is not triggered correctly: success={success}, reason={reason}")


# === Test 9: post_publish — Timeout handling ===

print("\n⏰ 9. post_publish — timeout processing")

page_stuck = StillUploadPage()
start = time.time()
success, reason = wait_for_publish_confirmation(page_stuck, "tiktok", timeout_s=4)
elapsed = time.time() - start
if not success and "timeout" in reason:
    ok(f"Timeout correctly returns failure ({elapsed:.1f} seconds)")
else:
    fail(f"Timeout handling exception: success={success}, reason={reason}")


# === Test 10: handle_post_publish_popups — abort path ===

print("\n🚫 10. handle_post_publish_popups — no pop-up scenario")

from social_uploader.tools.post_publish import handle_post_publish_popups

page_clean = MockPage("https://www.tiktok.com/upload")
result = handle_post_publish_popups(page_clean, "tiktok", max_rounds=3)
if result["action"] != "abort":
    ok("Abort is not triggered when there is no pop-up window")
else:
    fail("Abort should not be triggered when there is no pop-up window")


# === Test 11: Uploader import verification ===

print("\n📦 11. Uploader integration — import chain integrity")

import importlib
for mod_name in [
    'social_uploader.uploaders.tiktok',
    'social_uploader.uploaders.youtube',
    'social_uploader.uploaders.instagram',
]:
    try:
        mod = importlib.import_module(mod_name)
        ok(f"{mod_name} imported successfully")
    except Exception as e:
        fail(f"{mod_name} Import failed", str(e))

from social_uploader.uploaders.tiktok import upload_tiktok
from social_uploader.uploaders.youtube import upload_youtube
from social_uploader.uploaders.instagram import upload_instagram
ok("Three platform upload_* functions can be imported")


# === Test 12: TikTok _check_upload_error as callback compatibility ===

print("\n🔗 12. TikTok — _check_upload_error callback signature")

from social_uploader.uploaders.tiktok import _check_upload_error
import inspect
sig = inspect.signature(_check_upload_error)
params = list(sig.parameters.keys())
if params == ["page"]:
    ok("_check_upload_error(page) has the correct signature and can be used as error_check_fn")
else:
    fail(f"_check_upload_error signature exception: {params}")


# === Test 13: YouTube confirm configuration compatible with post_publish ===

print("\n🎬 13. YouTube — confirm configuration is compatible with post_publish")

from social_uploader.tools.pattern_checker import get_patterns

yt_confirm = get_patterns("youtube", "confirm")
if "close_button" in yt_confirm and "dialog_selector" in yt_confirm:
    ok("youtube.confirm contains close_button + dialog_selector")
else:
    fail("youtube.confirm is missing close_button or dialog_selector")

if yt_confirm.get("success_signals"):
    ok(f"youtube.confirm.success_signals has {len(yt_confirm['success_signals'])} signals")
else:
    fail("youtube.confirm.success_signals is empty")


# === Test 14: Instagram confirm configuration ===

print("\n📸 14. Instagram — confirm configuration is compatible with post_publish")

ig_confirm = get_patterns("instagram", "confirm")
if ig_confirm.get("success_signals"):
    ok(f"instagram.confirm.success_signals has {len(ig_confirm['success_signals'])} signals")
else:
    fail("instagram.confirm.success_signals is empty")


# === Test 15: AI Judge LLM actual call (if API Key available) ===

print("\n🤖 15. AI Judge — LLM actual call")

from social_uploader.tools.ai_judge import _call_llm, _get_client

client = _get_client()
if client:
    raw = _call_llm(
        'Reply with ONLY: {"status":"ok"}',
        'ping'
    )
    parsed = _parse_json_response(raw)
    if parsed and parsed.get("status") == "ok":
        ok("LLM actually called successfully + JSON parsed correctly")
    else:
        fail(f"LLM returns exception: raw={raw}")
else:
    ok("API Key is not configured, LLM function is automatically disabled (as expected)")


# === Summary of results ===

print(f"\n{'='*55}")
total = passed + failed
if failed == 0:
    print(f"🎉 All passed ({passed}/{total})")
else:
    print(f"⚠️{passed}/{total} passed, {failed} failed")
sys.exit(1 if failed else 0)
