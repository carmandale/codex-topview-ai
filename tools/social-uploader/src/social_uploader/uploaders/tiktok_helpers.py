"""TikTok platform-specific auxiliary functions (excluding step arrangement).

[Architecture Agreement]
- `tools/` = Common infrastructure for all platforms
- `uploaders/tiktok_helpers.py` = TikTok exclusive auxiliary (only tiktok.py can be imported)
- `uploaders/tiktok.py` = Step arranger (does not write underlying logic)

Cross-platform import is prohibited: youtube.py / instagram.py This module is not allowed to be imported.

[This module includes]
- `_set_toggle` sets the switch state of button[role="switch"] based on the label text
- `_set_checkbox` Set [role="checkbox"] / input[type="checkbox"] status based on label text
- `_set_tiktok_visibility` Set visibility drop-down (everyone/friends/only_me), go to visibility_recipe
- `_set_tiktok_schedule` to set scheduled release, go to schedule_recipe
- `_set_tiktok_options` aggregates the above option settings and returns (changed, recipe_diag)
"""

import logging

from social_uploader.tools.recipe_runner import run_recipe

logger = logging.getLogger(__name__)


def _set_toggle(page, label_keywords, desired_state):
    """Find the TikTok toggle switch via the label text and set it to the target state."""
    for kw in label_keywords:
        safe_kw = kw.replace("\\", "\\\\").replace("'", "\\'")
        result = page.run_js(f"""
            var kw = '{safe_kw}';
            var switches = document.querySelectorAll('button[role="switch"]');
            for (var sw of switches) {{
                var row = sw;
                for (var i = 0; i < 8; i++) {{
                    row = row.parentElement;
                    if (!row) break;
                    if (row.textContent.includes(kw)) {{
                        var isOn = sw.getAttribute('aria-checked') === 'true';
                        var want = {'true' if desired_state else 'false'};
                        if (isOn !== want) {{ sw.click(); return 'toggled'; }}
                        return 'ok';
                    }}
                }}
            }}
            return 'not_found';
        """)
        if result in ('toggled', 'ok'):
            action = 'turn on' if desired_state else 'closure'
            status = 'Switched' if result == 'toggled' else 'No changes required'
            logger.info(f"  ✅ {kw}: {action} ({status})")
            return True
    return False


def _set_checkbox(page, label_keywords, desired_state):
    """Find the TikTok custom checkbox by label text and set it to the target state."""
    for kw in label_keywords:
        safe_kw = kw.replace("\\", "\\\\").replace("'", "\\'")
        result = page.run_js(f"""
            var kw = '{safe_kw}';
            var targets = document.querySelectorAll(
                '[role="checkbox"], input[type="checkbox"], [role="switch"]'
            );
            for (var el of targets) {{
                var row = el;
                for (var i = 0; i < 8; i++) {{
                    row = row.parentElement;
                    if (!row) break;
                    if (row.textContent.includes(kw)) {{
                        var isChecked = el.checked
                            || el.getAttribute('aria-checked') === 'true'
                            || el.classList.contains('checked');
                        var want = {'true' if desired_state else 'false'};
                        if (isChecked !== want) {{ el.click(); return 'toggled'; }}
                        return 'ok';
                    }}
                }}
            }}
            return 'not_found';
        """)
        if result in ('toggled', 'ok'):
            action = 'Check' if desired_state else 'Uncheck'
            status = 'Switched' if result == 'toggled' else 'No changes required'
            logger.info(f"  ✅ {kw}: {action} ({status})")
            return True
    return False


def _set_tiktok_visibility(page, visibility):
    """Set TikTok visibility dropdown (everyone/friends/only_me).

    Use the recipe recipe system (three layers of coverage):
    - Tier 1: Execute by state_patterns.json → tiktok.visibility_recipe
    - Tier 2: Heuristically discovers alternative elements when the selector fails, and automatically writes back the recipe when successful.
    - Tier 3: When all fails, enhanced DIAG is output and handed over to Agent for intervention.

    Return (success: bool, diag: dict|None).
    """
    visibility_map = {
        "everyone": ["Everyone", "所有人"],
        "friends": ["Friends", "好友"],
        "only_me": ["Only you", "Only me", "仅自己", "Only Me"],
    }
    option_texts = visibility_map.get(visibility, ["Everyone", "所有人"])

    variables = {
        "option_text": "|".join(option_texts),
        "option_hint": option_texts[0],
    }

    success, failed_step, hint = run_recipe(
        page, "tiktok", "visibility_recipe", variables,
    )

    if success:
        logger.info(f"  ✅ Visibility: {visibility}")
        return True, None
    logger.warning(
        f"  ⚠️ Visibility setting failed (step={failed_step}, hint={hint})"
    )
    return False, {
        "failed_step": failed_step or "",
        "semantic_hint": hint or "",
        "recipe_key": "visibility_recipe",
    }


def _set_tiktok_schedule(page, schedule_str):
    """Set TikTok scheduled release (format: 'YYYY-MM-DD HH:MM').

    Use the recipe recipe system (three layers of coverage):
    - Tier 1: Execute by state_patterns.json → tiktok.schedule_recipe
    - Tier 2: Heuristically discovers alternative elements when the selector fails, and automatically writes back the recipe when successful.
    - Tier 3: When all fails, enhanced DIAG is output and handed over to Agent for intervention.

    Return (success: bool, diag: dict|None).
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

    time_parts = time_str.split(':')
    if len(time_parts) != 2:
        logger.warning(f"  ⚠️ Incorrect time format (requires 'HH:MM'): {time_str}")
        return False, _format_diag(f"time_str format error: {time_str}")
    try:
        hour_int = int(time_parts[0])
        minute_int = int(time_parts[1])
    except ValueError:
        logger.warning(f"  ⚠️ The time contains non-numeric characters: {time_str}")
        return False, _format_diag(f"time_str contains non-digits: {time_str}")
    target_hour = str(hour_int).zfill(2)
    target_minute = str(minute_int - (minute_int % 5)).zfill(2)

    date_parts = date_str.split('-')
    if len(date_parts) != 3:
        logger.warning(f"  ⚠️ Wrong date format (requires 'YYYY-MM-DD'): {date_str}")
        return False, _format_diag(f"date_str format error: {date_str}")
    try:
        day = str(int(date_parts[2]))
    except ValueError:
        logger.warning(f"  ⚠️ The day in the date cannot be parsed as a number: {date_str}")
        return False, _format_diag(f"date_str date field non-numeric: {date_str}")

    variables = {
        "date": date_str,
        "time": f"{target_hour}:{target_minute}",
        "hour": target_hour,
        "minute": target_minute,
        "day": day,
    }

    success, failed_step, hint = run_recipe(page, "tiktok", "schedule_recipe", variables)

    if success:
        logger.info(f"  ✅ Regular releases: {date_str} {target_hour}:{target_minute}")
        return True, None
    logger.warning(f"  ⚠️ Scheduled release setting failed (step={failed_step}, hint={hint})")
    return False, {
        "failed_step": failed_step or "",
        "semantic_hint": hint or "",
        "recipe_key": "schedule_recipe",
    }


def _set_tiktok_options(page, config):
    """Set all options of the TikTok upload page according to the profile configuration.

    Return (changed, recipe_diag):
      changed — List of options that have been successfully changed
      recipe_diag — {"visibility": diag|None, "schedule": diag|None}，
                    Used by the upper layer to put failed_step / semantic_hint / recipe_key when failure occurs
                    Transparently passed to report_failure to facilitate subsequent diagnosis.
    """
    changed = []
    recipe_diag = {"visibility": None, "schedule": None}

    ai_generated = config.get("ai_generated", False)
    if ai_generated:
        if _set_toggle(page, ["AI-generated content", "AI generated content", "AI-generated"], True):
            changed.append("ai_generated")

    disclose = config.get("disclose_content", False)
    if disclose:
        if _set_toggle(page, ["Disclose post content", "Disclose post content", "Disclose"], True):
            changed.append("disclose_content")

    high_quality = config.get("high_quality", True)
    if not high_quality:
        if _set_toggle(page, ["High-quality uploads", "High quality upload", "High-quality"], False):
            changed.append("high_quality=off")

    allow_comments = config.get("allow_comments", True)
    if not allow_comments:
        if _set_checkbox(page, ["Comment", "Comment"], False):
            changed.append("comments=off")

    allow_reuse = config.get("allow_reuse", True)
    if not allow_reuse:
        if _set_checkbox(page, ["Reuse of content", "Quotes allowed", "Reuse"], False):
            changed.append("reuse=off")

    visibility = config.get("visibility", "everyone")
    if visibility != "everyone":
        ok, diag = _set_tiktok_visibility(page, visibility)
        if ok:
            changed.append(f"visibility={visibility}")
        else:
            recipe_diag["visibility"] = diag

    schedule = config.get("schedule")
    if schedule:
        if visibility == "only_me":
            logger.warning("  ⚠️TikTok platform restrictions: Videos that are only visible to you cannot be published at a scheduled time. The timing setting has been automatically skipped and the video will be published immediately.")
            changed.append("schedule=skipped(private)")
        else:
            ok, diag = _set_tiktok_schedule(page, schedule)
            if ok:
                changed.append(f"schedule={schedule}")
            else:
                recipe_diag["schedule"] = diag

    return changed, recipe_diag
