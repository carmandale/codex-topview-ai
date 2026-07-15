"""Analysis engine—rule-based judgment on structured data (not relying on LLM).

Function:
  - Identification of hot items/downturns
  - Interaction rate calculation
  - Trend comparison (current snapshot vs last snapshot)
  - Release rhythm analysis (read from summary.jsonl)
"""

import json
import logging
import statistics
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_ANALYTICS_DIR = Path.home() / ".social_uploader" / "analytics"

HIT_THRESHOLD = 2.0      # Indicator > Mean * 2 → Hot item
FLOP_THRESHOLD = 0.3     # Indicator < mean * 0.3 → downturn

_METRIC_LABELS = {
    "views": "Play volume",
    "video_views": "Play volume",
    "watch_time_hours": "Viewing time (h)",
    "subscribers": "Subscribe to changes",
    "impressions": "Impressions",
    "ctr": "Click-through rate (%)",
    "likes": "Like",
    "comments": "Comment",
    "shares": "share",
    "saves": "collect",
    "followers": "Fan changes",
    "following": "Number of followers",
    "new_followers": "Add new fans",
    "profile_views": "Home page visit",
    "profile_visits": "Home page visit",
    "accounts_reached": "Number of people reached",
    "hearts": "Total number of likes",
    "video_count": "Number of videos",
    "estimated_reward": "Estimated reward",
    "plays": "Play volume",
    "engagement_rate": "Interaction rate (%)",
    "posts": "Number of posts",
    "reels_plays": "Reels play",
}


def analyze(
    current_snapshots: dict[str, dict],
    previous_snapshots: dict[str, dict | None] | None = None,
    period_days: int = 28,
    account: str = "default",
) -> dict:
    """Main analysis entrance.

    parameter:
      current_snapshots:  {"youtube": {...}, "tiktok": {...}, ...}
      previous_snapshots: Same structure, last collection (optional)
      period_days: analysis period days
      account: account name, used to read the account’s own collection history (the global summary.jsonl is not read)

    Return AnalysisResult dict:
      {
        "generated_at": ...,
        "period_days": ...,
        "platforms": {
          "youtube": { "metrics": {...}, "trend": {...}, "videos": {...} },
          ...
        },
        "publish_cadence": {...},
        "highlights": [...],
        "warnings": [...],
      }
    """
    previous_snapshots = previous_snapshots or {}
    result = {
        "generated_at": datetime.now().isoformat(),
        "period_days": period_days,
        "platforms": {},
        "publish_cadence": _analyze_publish_cadence(period_days, account=account),
        "highlights": [],
        "warnings": [],
    }

    for platform, snapshot in current_snapshots.items():
        if not snapshot or snapshot.get("error"):
            result["warnings"].append(f"{platform} collection failed: {snapshot.get('error', 'no data')}")
            continue

        prev = previous_snapshots.get(platform)
        platform_analysis = _analyze_platform(platform, snapshot, prev)
        result["platforms"][platform] = platform_analysis

        result["highlights"].extend(platform_analysis.get("highlights", []))
        result["warnings"].extend(platform_analysis.get("warnings", []))

    return result


def _analyze_platform(platform: str, current: dict, previous: dict | None) -> dict:
    """Analyze data from a single platform."""
    account_metrics = current.get("account_metrics", {})
    video_metrics = current.get("video_metrics", [])
    prev_account = previous.get("account_metrics", {}) if previous else {}

    trend = _compute_trend(account_metrics, prev_account)

    engagement_rate = _compute_engagement_rate(account_metrics, platform)

    video_analysis = _analyze_videos(video_metrics, platform)

    highlights = []
    warnings = []

    for metric, info in trend.items():
        pct = info.get("change_pct")
        if pct is not None:
            label = _METRIC_LABELS.get(metric, metric)
            if pct > 50:
                highlights.append(f"[{platform}] {label} substantial growth +{pct:.0f}%")
            elif pct < -30:
                warnings.append(f"[{platform}] {label} significant decrease {pct:.0f}%")

    if video_analysis.get("hits"):
        for i, v in enumerate(video_analysis["hits"], 1):
            views = v.get("views", 0)
            highlights.append(f"[{platform}] Popular video {i} (view count: {views})")

    return {
        "metrics": account_metrics,
        "trend": trend,
        "engagement_rate": engagement_rate,
        "videos": video_analysis,
        "highlights": highlights,
        "warnings": warnings,
    }


def _compute_trend(current: dict, previous: dict) -> dict:
    """Calculate indicator trend (current vs last time)."""
    trend = {}
    for key, cur_val in current.items():
        try:
            cur_f = float(cur_val)
        except (ValueError, TypeError):
            continue

        prev_val = previous.get(key)
        entry = {"current": cur_f, "previous": None, "change_abs": None, "change_pct": None}
        if prev_val is not None:
            try:
                prev_f = float(prev_val)
                entry["previous"] = prev_f
                entry["change_abs"] = cur_f - prev_f
                if prev_f != 0:
                    entry["change_pct"] = ((cur_f - prev_f) / prev_f) * 100
            except (ValueError, TypeError):
                pass
        trend[key] = entry
    return trend


def _compute_engagement_rate(metrics: dict, platform: str) -> float | None:
    """Calculate interaction rate = (likes + comments + shares [+ saves]) / views."""
    views_key = "views" if platform == "youtube" else "video_views"
    views = _as_float(metrics.get(views_key, metrics.get("views", metrics.get("accounts_reached"))))
    if not views or views == 0:
        return None

    likes = _as_float(metrics.get("likes", 0))
    comments = _as_float(metrics.get("comments", 0))
    shares = _as_float(metrics.get("shares", 0))
    saves = _as_float(metrics.get("saves", 0))

    interactions = likes + comments + shares + saves
    return round(interactions / views * 100, 2)


def _analyze_videos(video_metrics: list[dict], platform: str) -> dict:
    """Analyze the video list: ranking, hit/down mark."""
    if not video_metrics:
        return {"ranked": [], "hits": [], "flops": [], "count": 0}

    for v in video_metrics:
        v.setdefault("views", 0)
        try:
            v["views"] = float(v["views"]) if v["views"] else 0
        except (ValueError, TypeError):
            v["views"] = 0

    ranked = sorted(video_metrics, key=lambda v: v.get("views", 0), reverse=True)

    view_values = [v["views"] for v in ranked if v["views"] > 0]
    if not view_values:
        return {"ranked": ranked[:10], "hits": [], "flops": [], "count": len(ranked)}

    mean_views = statistics.mean(view_values)

    hits = [v for v in ranked if v["views"] >= mean_views * HIT_THRESHOLD]
    flops = [v for v in ranked if 0 < v["views"] <= mean_views * FLOP_THRESHOLD]

    return {
        "ranked": ranked[:10],
        "hits": hits,
        "flops": flops,
        "count": len(ranked),
        "mean_views": round(mean_views, 1),
    }


def _analyze_publish_cadence(period_days: int = 28, account: str = "default") -> dict:
    """Analyze the collection rhythm from the account's analytics/history.jsonl (the global summary.jsonl is not read)."""
    cadence = {
        "total_uploads": 0,
        "successful_uploads": 0,
        "failed_uploads": 0,
        "by_platform": {},
        "avg_interval_days": None,
    }
    history_path = _ANALYTICS_DIR / account / "history.jsonl"
    if not history_path.exists():
        return cadence

    cutoff = datetime.now() - timedelta(days=period_days)
    records = []
    try:
        for line in history_path.read_text(encoding="utf-8").strip().splitlines():
            try:
                rec = json.loads(line)
                ts_str = rec.get("ts", "")
                ts = datetime.fromisoformat(ts_str) if ts_str else None
                if ts and ts >= cutoff:
                    records.append(rec)
            except (json.JSONDecodeError, ValueError):
                pass
    except OSError:
        return cadence

    cadence["total_uploads"] = len(records)
    successful = [r for r in records if r.get("status") == "success" or "failed_at" not in r and "error" not in r]
    failed = [r for r in records if r.get("failed_at") or r.get("error")]
    cadence["successful_uploads"] = len(successful) if successful else 0
    cadence["failed_uploads"] = len(failed) if failed else 0

    by_platform = {}
    for r in records:
        p = r.get("platform", "unknown")
        by_platform[p] = by_platform.get(p, 0) + 1
    cadence["by_platform"] = by_platform

    success_dates = []
    for r in successful:
        ts_str = r.get("ts", "")
        try:
            success_dates.append(datetime.fromisoformat(ts_str))
        except ValueError:
            pass
    if len(success_dates) >= 2:
        success_dates.sort()
        intervals = [(success_dates[i + 1] - success_dates[i]).total_seconds() / 86400
                     for i in range(len(success_dates) - 1)]
        cadence["avg_interval_days"] = round(statistics.mean(intervals), 1)

    return cadence


def _as_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
