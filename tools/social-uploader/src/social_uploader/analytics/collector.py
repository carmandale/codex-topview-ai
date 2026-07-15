"""Data collection layer - collects data dashboards from creators on each platform through the OpenCLI adapter.

Technical solution:
  Call `opencli <平台> creator-stats [参数] --format json` to obtain structured data.
  OpenCLI is responsible for browser control, page navigation, cookie authentication, and DOM/API data extraction.
  This module is only responsible for: calling commands → parsing JSON → converting to a unified format.

Supported platforms:
  - Platforms with creator-stats adapter (youtube, tiktok, instagram, etc.)
  - Platforms with other stats commands (douyin's stats command)
  - For new platforms, just add the JS adapter under ~/.opencli/clis/<platform>/
"""

import json
import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)

_OPENCLI_TIMEOUT = 120
_OPENCLI_TIMEOUT_YOUTUBE = 300

_COMMAND_MAP = {
    "youtube": {"command": "creator-stats", "positional": True},
    "tiktok": {"command": "creator-stats", "positional": False},
    "instagram": {"command": "creator-stats", "positional": False},
    "douyin": {"command": "stats", "positional": True},
}

_NUM_RE = re.compile(r"[\d,]+\.?\d*")


def _parse_number(text: str) -> float | None:
    """Extract numbers from text, supporting K/M/B/Ten Thousand/Billion suffixes and comma separation."""
    if not text:
        return None
    text = text.strip().replace("\n", "").replace("\u00a0", "")
    if text == "-" or text == "---":
        return None
    multiplier = 1
    lower = text.lower().rstrip("%")
    if lower.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif lower.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    elif lower.endswith("b"):
        multiplier = 1_000_000_000
        text = text[:-1]
    elif "万" in text:
        multiplier = 10_000
        text = text.replace("万", "")
    elif "亿" in text:
        multiplier = 100_000_000
        text = text.replace("亿", "")
    m = _NUM_RE.search(text)
    if m:
        try:
            return float(m.group().replace(",", "")) * multiplier
        except ValueError:
            return None
    return None


def _find_opencli() -> str | None:
    """Find the opencli executable path."""
    path = shutil.which("opencli")
    if path:
        return path
    for candidate in ("/usr/local/bin/opencli", "/opt/homebrew/bin/opencli"):
        if shutil.which(candidate):
            return candidate
    return None


_YT_CHANNEL_RE = re.compile(r"UC[\w-]{22}")


def _auto_detect_youtube_channel() -> str | None:
    """Automatically obtain the YouTube channel ID of the currently logged in user via the Chrome debug port.

    Detection strategy (by priority):
      1. Scan the opened tab URL to extract UCxxx
      2. Actively navigate to studio.youtube.com through CDP, wait for redirection and then extract from the URL
      3. Extract channel-id attribute from YouTube Studio page DOM
    """
    import urllib.request
    import urllib.error

    try:
        raw = urllib.request.urlopen("http://localhost:9222/json", timeout=5).read()
        tabs = json.loads(raw)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        logger.debug("  YouTube channel auto-detection: Unable to connect to Chrome debug port 9222")
        return None

    for tab in tabs:
        url = tab.get("url", "")
        if "studio.youtube.com" in url:
            m = _YT_CHANNEL_RE.search(url)
            if m:
                logger.debug(f"  Channel detected from YouTube Studio tab")
                return m.group()

    for tab in tabs:
        url = tab.get("url", "")
        if "youtube.com" in url:
            m = _YT_CHANNEL_RE.search(url)
            if m:
                logger.debug(f"  Channel detected from YouTube tab")
                return m.group()

    channel = _detect_youtube_channel_via_cdp(tabs)
    if channel:
        return channel

    logger.warning("  ⚠️ YouTube channel auto-detection failed: Failed to get channel ID from browser session")
    return None


def _cdp_send(ws, method: str, params: dict | None = None, msg_id: int = 1) -> dict:
    """Send the CDP command and wait for the response corresponding to the id, skipping the intermediate event push."""
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    ws.send(json.dumps(payload))
    for _ in range(50):
        resp = json.loads(ws.recv())
        if resp.get("id") == msg_id:
            return resp
    return {}


def _detect_youtube_channel_via_cdp(tabs: list[dict]) -> str | None:
    """Open YouTube Studio via CDP in a new tab and wait for the redirect to extract the channel ID.

    YouTube Studio redirects to /channel/UCxxx/... when the user is logged in,
    The channel ID can be extracted from the redirected URL. The temporary tab page will be automatically closed after the detection is completed.
    """
    import time
    import urllib.request
    import urllib.error

    try:
        import websocket
    except ImportError:
        logger.debug("  websocket-client is not installed, skipping CDP detection")
        return None

    tab_id = None
    ws = None
    channel_id = None

    try:
        logger.debug("  Automatically detecting YouTube channels via browser...")
        req = urllib.request.Request(
            "http://localhost:9222/json/new?https://studio.youtube.com",
            method="PUT",
        )
        raw = urllib.request.urlopen(req, timeout=10).read()
        new_tab = json.loads(raw)
        tab_id = new_tab.get("id")
        ws_url = new_tab.get("webSocketDebuggerUrl")
        if not ws_url:
            logger.debug("  New tab page is missing webSocketDebuggerUrl")
            return None

        ws = websocket.create_connection(ws_url, timeout=15)

        for attempt in range(8):
            time.sleep(3)
            resp = _cdp_send(ws, "Runtime.evaluate",
                             {"expression": "window.location.href"}, msg_id=10 + attempt)
            url = resp.get("result", {}).get("result", {}).get("value", "")
            m = _YT_CHANNEL_RE.search(url)
            if m:
                channel_id = m.group()
                logger.debug(f"  Channel detected from YouTube Studio redirect")
                break

        if not channel_id:
            resp = _cdp_send(ws, "Runtime.evaluate", {
                "expression": (
                    "document.querySelector('[channel-id]')?.getAttribute('channel-id') || "
                    "document.querySelector('ytcp-entity-page-header')?.getAttribute('channel-id') || "
                    "''"
                )
            }, msg_id=20)
            val = resp.get("result", {}).get("result", {}).get("value", "")
            if val and _YT_CHANNEL_RE.match(val):
                channel_id = val
                logger.debug(f"  Channel detected from YouTube Studio DOM")
    except (urllib.error.URLError, OSError) as e:
        logger.debug(f"  CDP new tab page creation failed: {e}")
    except Exception as e:
        logger.debug(f"  CDP detection exception: {e}")
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        if tab_id:
            try:
                close_req = urllib.request.Request(
                    f"http://localhost:9222/json/close/{tab_id}", method="GET",
                )
                urllib.request.urlopen(close_req, timeout=5)
            except Exception:
                pass

    return channel_id


def _run_opencli(platform: str, account_arg: str | None) -> dict | None:
    """Calls opencli <platform> <command> [parameters] --format json and returns parsed JSON.

    Returning None indicates that the command failed or opencli is unavailable.
    """
    opencli = _find_opencli()
    if not opencli:
        logger.error("  ❌ The opencli command was not found, please confirm it is installed: npm install -g @jackwener/opencli")
        return None

    spec = _COMMAND_MAP.get(platform)
    if not spec:
        spec = {"command": "creator-stats", "positional": bool(account_arg and account_arg is not True)}

    cmd = [opencli, platform, spec["command"]]
    if spec["positional"] and account_arg and account_arg is not True and str(account_arg).lower() != "true":
        cmd.append(str(account_arg))
    cmd.extend(["--format", "json"])

    timeout = _OPENCLI_TIMEOUT_YOUTUBE if platform == "youtube" else _OPENCLI_TIMEOUT
    safe_cmd = [c if not _YT_CHANNEL_RE.search(c) else "[CHANNEL_ID]" for c in cmd]
    logger.info(f"  🔧 Execution: {' '.join(safe_cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 77:
            logger.error(f"  ❌ {platform}: Not logged in to the target website (exit code 77)")
            return None
        if result.returncode == 69:
            logger.error(f"  ❌ {platform}: Browser Bridge is not connected (exit code 69), please run opencli doctor")
            return None
        if result.returncode != 0:
            stderr = result.stderr.strip()[:200] if result.stderr else ""
            logger.error(f"  ❌ {platform}: opencli exit code {result.returncode} {stderr}")
            return None

        stdout = result.stdout.strip()
        if not stdout:
            logger.warning(f"  ⚠️ {platform}: opencli returns empty output")
            return None

        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        logger.error(f"  ❌ {platform}: opencli timeout ({_OPENCLI_TIMEOUT}s)")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"  ❌ {platform}: JSON parsing failed: {e}")
        logger.debug(f"  First 500 characters of raw output: {result.stdout[:500] if result.stdout else '(空)'}")
        return None
    except Exception as e:
        logger.error(f"  ❌ {platform}: {e}")
        return None


def _normalize_opencli_output(platform: str, raw_data) -> dict:
    """Convert opencli's JSON output to a unified internal format.

    Two output formats are supported:
      Old format (flat): [{metric, value, trend}, ...]
      New format (per-video): [{video, tab, metric, value}, ...] ← YouTube video-by-video capture

    Internal format: {"account_metrics": {key: number}, "video_metrics": [...]}
    """
    rows = raw_data if isinstance(raw_data, list) else []
    if not rows:
        return {"account_metrics": {}, "video_metrics": [], "account_identity": {}, "collection_method": "opencli"}

    has_video_col = any(isinstance(r, dict) and "video" in r and "tab" in r for r in rows)
    if has_video_col:
        return _normalize_per_video_output(rows)
    return _normalize_flat_output(rows)


def _normalize_flat_output(rows: list) -> dict:
    """Processing unified format: [{metric, value, trend}, ...]

    Segmentation is supported:
      - Account level metrics (top, row before separator)
      - "--- Top Videos ---" / "--- Single post data ---" and other delimiters are followed by video/post level data
      - "--- Summary of recent content ---" followed by summary statistics
      - "---Analysis data ---" is followed by platform analysis indicators

    Identity fields (user name, account type, etc.) are not discarded and stored in account_identity.
    """
    account_metrics = {}
    video_metrics = []
    account_identity = {}
    section = "account"

    _IDENTITY_METRICS = {
        "用户名 (username)": "username",
        "用户名": "username",
        "username": "username",
        "账号类型": "account_type",
        "info": "info",
    }

    _SKIP_METRICS = {
        "Popular posts", "Audience profile", "Follower profile", "Gender distribution",
        "Age distribution", "Regional distribution", "Follower gender", "Follower age",
        "Follower region", "热门帖子", "人群画像", "粉丝画像", "性别分布",
        "年龄分布", "地区分布", "粉丝性别", "粉丝年龄", "粉丝地区",
    }

    for row in rows:
        if not isinstance(row, dict):
            continue

        metric = row.get("metric", "")
        value = row.get("value", "")

        if "---" in str(metric):
            val_lower = str(value).lower()
            if "top video" in val_lower or "single post" in val_lower or "top content" in val_lower or "单帖" in str(value):
                section = "videos"
            elif "recent content" in val_lower or "近期内容" in str(value) or ("content" in val_lower and "top" not in val_lower):
                section = "summary"
            elif ("analyze data" in val_lower or "analytics" in val_lower
                  or "overview" in val_lower or "viewers" in val_lower
                  or "audience" in val_lower or "followers" in val_lower
                  or "fan" in val_lower
                  or any(label in str(value) for label in ("分析数据", "概览", "观众", "粉丝"))):
                section = "analytics"
            else:
                section = "other"
            continue

        identity_key = _IDENTITY_METRICS.get(metric)
        if identity_key:
            account_identity[identity_key] = str(value).strip()
            continue

        if metric in _SKIP_METRICS:
            continue

        if section == "videos" and metric and value:
            entry = {"title": metric}
            kv_match = re.findall(r"(\w+)=(\d+)", str(value))
            if kv_match:
                for k, v in kv_match:
                    entry[k] = float(v)
            else:
                entry["views"] = _parse_number(str(value))
            video_metrics.append(entry)
            continue

        if metric and value:
            metric_key = _metric_to_key(metric)
            num_val = _parse_number(str(value))
            if num_val is not None:
                account_metrics[metric_key] = num_val

    return {
        "account_metrics": account_metrics,
        "video_metrics": video_metrics,
        "account_identity": account_identity,
        "collection_method": "opencli",
    }


def _normalize_per_video_output(rows: list) -> dict:
    """Process video-by-video format: [{video, tab, metric, value}, ...]

    Combine the 4 tab page metrics of each video and aggregate account_metrics (take the sum/average of all videos).
    """
    from collections import OrderedDict

    videos_map: dict[str, dict] = OrderedDict()

    for row in rows:
        if not isinstance(row, dict):
            continue
        video_title = row.get("video", "")
        tab = row.get("tab", "")
        metric = row.get("metric", "")
        value = row.get("value", "")

        if not video_title or not metric or metric.startswith("_"):
            continue

        if video_title not in videos_map:
            videos_map[video_title] = {"title": video_title, "tabs": {}}

        vid = videos_map[video_title]
        if tab not in vid["tabs"]:
            vid["tabs"][tab] = {}

        metric_key = _metric_to_key(metric)
        num_val = _parse_number(str(value))
        if num_val is not None:
            vid["tabs"][tab][metric_key] = num_val

    video_metrics = []
    agg: dict[str, list[float]] = {}

    for title, vid in videos_map.items():
        flat = {}
        for _tab, metrics in vid["tabs"].items():
            flat.update(metrics)

        entry = {"title": title}
        entry.update(flat)
        video_metrics.append(entry)

        for k, v in flat.items():
            agg.setdefault(k, []).append(v)

    account_metrics = {}
    _SUM_KEYS = {"views", "watch_time_hours", "likes", "comments", "shares",
                 "impressions", "subscribers", "unique_viewers",
                 "returning_viewers", "new_viewers", "saves"}
    _AVG_KEYS = {"ctr", "avg_view_duration", "avg_percentage_viewed"}

    for k, vals in agg.items():
        if k in _SUM_KEYS:
            account_metrics[k] = sum(vals)
        elif k in _AVG_KEYS:
            account_metrics[k] = sum(vals) / len(vals) if vals else 0
        else:
            account_metrics[k] = sum(vals)

    account_identity = {}
    if video_metrics:
        first_title = video_metrics[0].get("title", "")
        if first_title:
            account_identity["channel_hint"] = first_title

    return {
        "account_metrics": account_metrics,
        "video_metrics": video_metrics,
        "account_identity": account_identity,
        "collection_method": "opencli",
    }


def _metric_to_key(metric_label: str) -> str:
    """Convert the Chinese and English indicator names output by opencli into standardized keys."""
    mapping = {
        # ── YouTube API interception version ──
        "播放量 (views)": "views",
        "观看时长-小时 (watch time hours)": "watch_time_hours",
        "观看时长 (watch time hours)": "watch_time_hours",
        "订阅变化 (subscribers)": "subscribers",
        "观看时长（小时） (watch_time_hours)": "watch_time_hours",
        "订阅人数 (subscribers)": "subscribers",
        "展示次数 (impressions)": "impressions",
        "展示点击率 (CTR)": "ctr",
        "唯一观看者 (unique viewers)": "unique_viewers",
        "平均观看时长 (avg view duration)": "avg_view_duration",
        # ── Instagram REST API version ──
        "粉丝数 (followers)": "followers",
        "关注数 (following)": "following",
        "帖子数 (posts)": "posts",
        "总点赞 (total likes)": "likes",
        "总评论 (total comments)": "comments",
        "总播放 (total plays)": "plays",
        "平均互动率 (engagement rate %)": "engagement_rate",
        "触达人数 (accounts reached)": "accounts_reached",
        "曝光量 (impressions)": "impressions",
        "互动 (interactions)": "interactions",
        "保存 (saves)": "saves",
        "Reels 播放 (reels plays)": "reels_plays",
        "主页访问 (profile visits)": "profile_visits",
        # ──TikTok Studio version──
        "获赞总数 (hearts)": "hearts",
        "视频数 (videos)": "video_count",
        "观看次数 (views)": "views",
        "主页访问量 (profile_views)": "profile_views",
        "赞 (likes)": "likes",
        "评论 (comments)": "comments",
        "分享次数 (shares)": "shares",
        "预估奖励 (estimated_reward)": "estimated_reward",
        "新粉丝 (new_followers)": "new_followers",
        # ── TikTok Studio 4-tab New ──
        "Video views (views)": "video_views",
        "Profile views (profile_views)": "profile_views",
        "Likes (likes)": "likes",
        "Comments (comments)": "comments",
        "Shares (shares)": "shares",
        "Est. rewards (estimated_reward)": "estimated_reward",
        "Total viewers (total_viewers)": "total_viewers",
        "New viewers (new_viewers)": "new_viewers",
        "Total followers (total_followers)": "total_followers",
        "Net followers (net_followers)": "net_followers",
        # ── Common / old format ──
        "点赞 (likes)": "likes",
        "评论 (comments)": "comments",
        "分享 (shares)": "shares",
        "收藏 (saves)": "saves",
        "视频播放量 (video views)": "video_views",
        "主页访问 (profile views)": "profile_views",
        "粉丝变化 (followers)": "followers",
        # ── YouTube video by video (Chinese UI)──
        "观看次数": "views",
        "观看时长(小时)": "watch_time_hours",
        "订阅人数": "subscribers",
        "点赞次数": "likes",
        "评论": "comments",
        "分享次数": "shares",
        "保存到播放列表": "saves",
        "展示次数": "impressions",
        "展示点击率(%)": "ctr",
        "唯一观看者": "unique_viewers",
        "平均观看时长": "avg_view_duration",
        "平均观看百分比(%)": "avg_percentage_viewed",
        "回访观看者": "returning_viewers",
        "新观看者": "new_viewers",
        "非订阅者(%)": "non_subscriber_pct",
        # ── YouTube video by video (English UI)──
        "Views": "views",
        "Watch time (hours)": "watch_time_hours",
        "Subscribers": "subscribers",
        "Likes": "likes",
        "Comments": "comments",
        "Shares": "shares",
        "Impressions": "impressions",
        "CTR (%)": "ctr",
        "Avg view duration": "avg_view_duration",
        "Avg % viewed": "avg_percentage_viewed",
        "Unique viewers": "unique_viewers",
        "Returning viewers": "returning_viewers",
        "New viewers": "new_viewers",
    }
    normalized = mapping.get(metric_label)
    if normalized:
        return normalized
    key = metric_label.lower()
    key = re.sub(r"\s*\(.*?\)\s*", "", key)
    key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", key)
    key = key.strip("_")
    return key or "unknown"


def collect_platform(platform: str, account_arg: str | None) -> dict:
    """Collect data from a single platform.

    The YouTube channel ID is automatically obtained from the YouTube Studio page through the Chrome debug port,
    This module does not cache or persist channel IDs.

    Return a unified format dict:
      {"account_metrics": {...}, "video_metrics": [...], "collection_method": "opencli"}
    or a dict with an error field.
    """

    logger.info(f"📊 Start collecting {platform} data...")
    raw = _run_opencli(platform, account_arg)
    if raw is None:
        return {"error": f"opencli {platform} creator-stats execution failed", "account_metrics": {}, "video_metrics": [], "account_identity": {}}

    result = _normalize_opencli_output(platform, raw)
    if not result["account_metrics"] and not result["video_metrics"]:
        logger.warning(f"  ⚠️ {platform}: 0 indicators collected, may not be logged in or the page structure may have changed")

    return result


def run_collect(account_platforms: dict, **_kwargs) -> dict[str, dict]:
    """Collect data from all configured platforms. For CLI calls.

    account_platforms example:
      {"youtube": "UCxxx", "tiktok": true, "instagram": true}

    YouTube channel ID is automatically detected (from upload history/browser session) and does not need to be provided manually by the user.
    Other platforms (TikTok / Instagram) only require the user to be logged in in Chrome.

    Return {"youtube": {...}, "tiktok": {...}, ...}
    """
    opencli = _find_opencli()
    if not opencli:
        logger.error("❌ opencli not found, please install: npm install -g @jackwener/opencli")
        return {}

    results = {}
    for platform, arg in account_platforms.items():
        if not arg and arg is not True:
            continue
        val_str = str(arg).strip().lower()
        if val_str in ("", "false"):
            continue

        explicit_arg = None
        if arg is not True and val_str != "true":
            explicit_arg = str(arg)

        try:
            data = collect_platform(platform, explicit_arg)
            if data.get("error"):
                logger.error(f"  ❌ {platform}: {data['error']}")
            else:
                logger.info(f"  ✅ {platform} data collection completed")
            results[platform] = data
        except Exception as e:
            logger.error(f"  ❌ {platform} Collection exception: {e}")
            results[platform] = {"error": str(e), "account_metrics": {}, "video_metrics": [], "account_identity": {}}

    if not results:
        logger.warning("  ⚠️ No platform account is configured, no data can be collected")

    return results
