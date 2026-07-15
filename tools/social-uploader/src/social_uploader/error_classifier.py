"""Automated repair - Error classification: deciding which errors the AI ​​can fix itself and which ones the user should be notified of

[What is this file responsible for]
Define all error types and corresponding handling methods:
- agent_fix: AI can fix it by itself (for example, the button name has changed)
- notify_user: requires user intervention (for example, not logged in)
- wait_retry: wait for a while and try again (such as frequency limit)
- escalate_user: If you can’t figure it out, tell the user (unknown error)

【Things you may want to change】
- ERROR_TYPES dictionary: add or delete error types or adjust processing strategies
"""

ERROR_TYPES = {
    "selector_not_found": "agent_fix",
    "element_stale":      "agent_fix",
    "intercepted_click":  "agent_fix",
    "timeout":            "notify_user",
    "file_rejected":      "notify_user",
    "state_mismatch":     "agent_fix",
    "recipe_step_failed": "agent_fix",
    "visibility_failed":  "agent_fix",
    "dialog_not_open":    "wait_retry",
    "login_required":     "notify_user",
    "captcha_detected":   "notify_user",
    "platform_unavailable": "wait_retry",
    "rate_limit":         "wait_retry",
    "unknown":            "escalate_user",
}


def classify_error(error_code):
    """Returns the processing policy label corresponding to the error code."""
    return ERROR_TYPES.get(error_code, "escalate_user")


def is_agent_fixable(error_code):
    """Determine whether the error type can be repaired by the Agent autonomously."""
    return classify_error(error_code) == "agent_fix"
