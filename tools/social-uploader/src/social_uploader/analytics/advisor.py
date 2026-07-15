"""Creation suggestion generation - a pure rules engine that outputs executable suggestions based on analysis results.

Design principles:
- Does not rely on any external LLM service (no network, no API Key, no timeout risk)
- Output fields remain consistent with historical LLM versions to ensure reporter.py template compatibility
- Suggestions must be based on real data values ​​and avoid empty slogans
"""

import logging

logger = logging.getLogger(__name__)

_DEFAULT_PERIOD_DAYS = 28

_PLATFORM_DISPLAY = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "douyin": "Tik Tok",
}

_PLATFORM_FORMAT_TIPS = {
    "youtube": "Horizontal screen 16:9 long video (5-15 minutes) + Shorts vertical screen (< 60 seconds) dual-track parallel, long video retains subscriptions, and Shorts attract new users",
    "tiktok": "Vertical screen 9:16, duration 15-60 seconds, the first 3 seconds must have a strong hook (contrast/suspense/visual impact)",
    "instagram": "Reels priority (vertical screen 9:16, 15-30 seconds), the cover has a unified style, and the theme is concentrated to facilitate the establishment of account recognition.",
    "douyin": "Vertical screen 9:16, 15-60 seconds, strong conflict or reversal in the first 3 seconds, combined with popular BGM to improve the completion of the broadcast",
}

_PLATFORM_TITLE_HOOKS = {
    "youtube": [
        "How to ___ in ___ (data: ___)",
        "I tried ___ for 7 days — here's what happened",
        "___ you should NEVER do (and why)",
    ],
    "tiktok": [
        "POV: ___",
        "Watch till the end 👀",
        "Wait for it…",
    ],
    "instagram": [
        "Save this for later 📌",
        "3 things I wish I knew about ___",
        "The truth about ___",
    ],
    "douyin": [
        "Don't do this___",
        "It turns out ___ can still be like this",
        "Don't cry after reading this",
    ],
}


def generate_advice(analysis_result: dict) -> dict:
    """Generate creative suggestions based on analysis results (pure rules, no LLM dependencies)."""
    advice = {
        "recommended_topics": [],
        "content_format": "",
        "title_hooks": [],
        "publish_schedule": "",
        "improvements": [],
        "summary": "",
        "source": "rules",
    }

    platforms = analysis_result.get("platforms", {}) or {}
    period_days = analysis_result.get("period_days", _DEFAULT_PERIOD_DAYS)

    if not platforms:
        advice["summary"] = "No platform data was collected. Please confirm that the browser has logged in to the target platform and try again."
        return advice

    engagement_rates = []
    has_hits = False
    has_flops = False
    total_videos = 0
    platform_breakdowns = []

    for platform, data in platforms.items():
        plat_label = _PLATFORM_DISPLAY.get(platform, platform.upper())
        metrics = data.get("metrics", {}) or {}
        videos = data.get("videos", {}) or {}
        trend = data.get("trend", {}) or {}

        er = data.get("engagement_rate")
        if er is not None:
            engagement_rates.append((platform, plat_label, er))

        hits = videos.get("hits", []) or []
        flops = videos.get("flops", []) or []
        if hits:
            has_hits = True
        if flops:
            has_flops = True

        video_count = len(videos.get("all", []) or []) or len(hits) + len(flops)
        total_videos += video_count

        platform_breakdowns.append({
            "platform": platform,
            "label": plat_label,
            "metrics": metrics,
            "engagement_rate": er,
            "trend": trend,
            "hits": hits,
            "flops": flops,
            "video_count": video_count,
        })

        _append_platform_format_tip(advice, platform, hits, flops, metrics)
        _append_platform_title_hooks(advice, platform, hits)

        for tip in _build_per_platform_topics(platform, plat_label, hits, flops, metrics):
            if tip not in advice["recommended_topics"]:
                advice["recommended_topics"].append(tip)

        for tip in _build_trend_improvements(plat_label, trend):
            if tip not in advice["improvements"]:
                advice["improvements"].append(tip)

        for tip in _build_metrics_improvements(plat_label, metrics, video_count):
            if tip not in advice["improvements"]:
                advice["improvements"].append(tip)

    advice["publish_schedule"] = _build_publish_schedule(
        analysis_result.get("publish_cadence", {}) or {},
        period_days,
    )

    if engagement_rates:
        engagement_rates.sort(key=lambda x: x[2], reverse=True)
        best = engagement_rates[0]
        worst = engagement_rates[-1]
        advice["improvements"].insert(
            0,
            f"{best[1]} has the highest interaction rate ({best[2]}%). It is recommended to invest in serialized content first.",
        )
        if len(engagement_rates) > 1 and worst[2] < best[2] * 0.5:
            advice["improvements"].append(
                f"The interaction rate of {worst[1]} is only {worst[2]}%, which is much behind {best[1]}."
                "You may consider suspending investment or refer to the content format of {best_label}".format(best_label=best[1])
            )

    if has_hits and not advice["recommended_topics"]:
        advice["recommended_topics"].append("Extract common themes from existing popular videos and create 3-5 issues of a series of content with the same theme")

    if has_flops and not any(
        "downturn" in t.lower() or "improv" in t.lower()
        for t in advice["improvements"]
    ):
        advice["improvements"].append("Sluggish video review: Check title appeal, cover contrast, retention rate in the first 3 seconds")

    if not advice["recommended_topics"]:
        advice["recommended_topics"].append("The amount of data is small. It is recommended to publish 2-3 items per week stably first, and then do thematic analysis after accumulating for 4 weeks.")

    if not advice["improvements"]:
        advice["improvements"].append("All indicators are stable. You can try to increase investment in a single period or test new topic selection directions.")

    advice["recommended_topics"] = advice["recommended_topics"][:5]
    advice["improvements"] = advice["improvements"][:6]
    advice["title_hooks"] = advice["title_hooks"][:5]

    advice["summary"] = _build_summary(
        period_days,
        platform_breakdowns,
        engagement_rates,
        total_videos,
        analysis_result.get("publish_cadence", {}) or {},
        has_hits,
        has_flops,
    )

    return advice


def _append_platform_format_tip(advice: dict, platform: str, hits: list, flops: list, metrics: dict) -> None:
    """Add content form suggestions based on platform characteristics (only the first platform tip that is obviously lagging behind will be added)."""
    if advice["content_format"]:
        return
    tip = _PLATFORM_FORMAT_TIPS.get(platform)
    if not tip:
        return
    if flops and len(flops) > len(hits):
        plat_label = _PLATFORM_DISPLAY.get(platform, platform.upper())
        advice["content_format"] = f"{plat_label}：{tip}"


def _append_platform_title_hooks(advice: dict, platform: str, hits: list) -> None:
    """When there is a popular product, the title template of the popular platform will be used first."""
    if advice["title_hooks"]:
        return
    if not hits:
        return
    hooks = _PLATFORM_TITLE_HOOKS.get(platform)
    if hooks:
        advice["title_hooks"].extend(hooks)


def _build_per_platform_topics(
    platform: str, plat_label: str, hits: list, flops: list, metrics: dict
) -> list:
    """Specific topic recommendations based on single platform data."""
    tips = []
    if hits:
        top = hits[0]
        title = (top.get("title") or "").strip()
        views = top.get("views")
        if title and views is not None:
            preview = title[:24] + ("…" if len(title) > 24 else "")
            tips.append(
                f'[{plat_label}] Follow the winning pattern: "{preview}" '
                f"({_fmt_num(views)} views), then create three videos on the same theme"
            )
        elif views is not None:
            tips.append(f"[{plat_label}] Make a series of copies around the most played video ({_fmt_num(views)})")

    if platform == "youtube" and metrics.get("subscribers") is not None:
        subs = float(metrics.get("subscribers") or 0)
        if subs < 1000:
            tips.append(f"[{plat_label}] Subscribe to {_fmt_num(subs)} < 1000, give priority to subscription guidance (end CTA + Shorts to attract traffic)")
        elif subs < 10000:
            tips.append(f"[{plat_label}] Subscribe to {_fmt_num(subs)}, it is recommended to make 1-2 long videos to establish professionalism, and use Shorts to increase the volume")

    if platform == "tiktok" and metrics:
        followers = metrics.get("followers")
        if followers is not None:
            try:
                fnum = float(followers)
                if fnum < 1000:
                    tips.append(f"[{plat_label}] Fans {_fmt_num(fnum)} < 1000, it is recommended to post 1-2 hot BGM posts every day to test popular items")
            except (TypeError, ValueError):
                pass

    return tips


def _build_trend_improvements(plat_label: str, trend: dict) -> list:
    """Generate improvements based on trend changes (focusing on significant decline indicators)."""
    tips = []
    for metric, info in (trend or {}).items():
        if not isinstance(info, dict):
            continue
        pct = info.get("change_pct")
        if pct is None:
            continue
        try:
            pct_val = float(pct)
        except (TypeError, ValueError):
            continue
        if pct_val <= -30:
            tips.append(f"[{plat_label}] {metric} has dropped {abs(pct_val):.0f}% compared to the last time. It is recommended to review the content of the last week.")
        elif pct_val >= 50:
            tips.append(f"[{plat_label}] {metric} increased by {pct_val:.0f}% compared to the last time, which can increase the output of similar content")
    return tips


def _build_metrics_improvements(plat_label: str, metrics: dict, video_count: int) -> list:
    """Improvement suggestions based on absolute value thresholds."""
    tips = []
    views = metrics.get("views")
    if views is not None:
        try:
            v = float(views)
            if v < 100 and video_count > 0:
                tips.append(f"[{plat_label}] The total number of plays in the cycle is only {_fmt_num(v)}. It is recommended to optimize the cover/title click-through rate")
        except (TypeError, ValueError):
            pass

    watch_time = metrics.get("watch_time_hours")
    if watch_time is not None:
        try:
            w = float(watch_time)
            if w < 10 and video_count > 0:
                tips.append(f"[{plat_label}] The total viewing time {w:.1f} hours is low, the completion rate needs to be improved (opening hook + rhythm)")
        except (TypeError, ValueError):
            pass

    return tips


def _build_publish_schedule(cadence: dict, period_days: int) -> str:
    """Generate cadence recommendations based on release cadence data."""
    total = cadence.get("total_uploads", 0) or 0
    avg_interval = cadence.get("avg_interval_days")
    successful = cadence.get("successful_uploads", 0) or 0
    failed = cadence.get("failed_uploads", 0) or 0

    if total == 0:
        return f"There is no upload record within the cycle ({period_days} days). It is recommended to immediately establish a publishing rhythm of 2-3 articles per week."

    if avg_interval is None:
        return f"{total} was uploaded in total during the cycle ({successful} was successful, {failed} was failed), it is recommended to maintain stable output."

    try:
        interval = float(avg_interval)
    except (TypeError, ValueError):
        return f"{total} uploads in total during the cycle ({successful} successful, {failed} failed)"

    if interval > 7:
        target = "2-3 articles per week"
        return f"The current average is {interval:.1f}, one message is sent every day, and the frequency is low. It is recommended to increase it to {target} (successful {successful}/failure {failed})"
    if interval < 0.5:
        rate = 1 / interval if interval > 0 else 0
        return f"Currently, approximately {rate:.0f} are posted every day, and the pace is too dense. Pay attention to ensuring content quality and review pass rate (successful {successful}/failure {failed})"
    if interval <= 3:
        return f"The current average {interval:.1f} is one per day, the rhythm is healthy, it is recommended to maintain (successful {successful}/failure {failed})"
    return f"The current average {interval:.1f} is one piece per day, which can be fine-tuned to 2-3 pieces per week to obtain a more stable algorithm distribution (successful {successful}/failure {failed})"


def _build_summary(
    period_days: int,
    platform_breakdowns: list,
    engagement_rates: list,
    total_videos: int,
    cadence: dict,
    has_hits: bool,
    has_flops: bool,
) -> str:
    """Generate a 2-3 sentence summary."""
    parts = []
    plat_count = len(platform_breakdowns)
    if plat_count:
        plat_names = "、".join(p["label"] for p in platform_breakdowns)
        parts.append(f"{plat_names} total {plat_count} platforms {total_videos} videos analyzed in the past {period_days} days")

    if engagement_rates:
        engagement_rates_sorted = sorted(engagement_rates, key=lambda x: x[2], reverse=True)
        best = engagement_rates_sorted[0]
        parts.append(f"{best[1]} Interaction rate {best[2]}% Top performer")

    cadence_total = cadence.get("total_uploads", 0) or 0
    if cadence_total:
        parts.append(f"Uploaded {cadence_total} times during the cycle")

    if has_hits and has_flops:
        parts.append("The content is polarized. It is recommended to copy popular videos in series + review sluggish videos.")
    elif has_hits:
        parts.append("A popular item has appeared. It is recommended to follow up the series with the same theme immediately.")
    elif has_flops:
        parts.append("The overall performance is low. It is recommended to optimize the title, cover, and first 3 seconds.")
    else:
        parts.append("The data is stable, you can try to increase investment in testing new directions")

    return "；".join(parts) + "。"


def _fmt_num(value) -> str:
    """Formatted numbers: 1234 → 1.2k, 1500000 → 1.5M."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    if n == int(n):
        return str(int(n))
    return f"{n:.1f}"
