"""Step-level intelligent retry engine — Leverages AI to diagnose and intelligently recover when steps fail.

Design principles:
1. Each step can be retried max_retries times at most.
2. Use AI to diagnose the cause of failure before each retry, and perform recovery actions based on recommendations
3. Irreversible steps (such as publish) have special idempotence protection
4. Downgrade to simple delayed retry when AI is unavailable
"""

import logging
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)

_NON_RETRYABLE_RECOVERIES = {"abort"}
_NEEDS_DISMISS = {"dismiss_and_retry"}
_NEEDS_WAIT = {"wait_and_retry"}
_NEEDS_SCROLL = {"scroll_and_retry"}
_NEEDS_REFRESH = {"refresh_and_retry"}
_NEEDS_NAV_BACK = {"navigate_back"}


class StepResult:
    """Step execution result."""
    def __init__(self, success: bool, value: Any = None, error: str = ""):
        self.success = success
        self.value = value
        self.error = error

    def __bool__(self):
        return self.success


def retry_step(
    page,
    platform: str,
    step_name: str,
    step_fn: Callable,
    max_retries: int = 3,
    is_irreversible: bool = False,
    pre_retry_check: Callable | None = None,
) -> StepResult:
    """Execute steps and intelligently retry if they fail.

    Args:
        page: DrissionPage page object
        platform: platform name
        step_name: step name (for logs and AI diagnosis)
        step_fn: step execution function, signature () -> StepResult
        max_retries: Maximum number of retries
        is_irreversible: Is it an irreversible step (such as publish)? If so, do an idempotent check before retrying.
        pre_retry_check: idempotent check function before retry, signature () -> bool (True=completed without retrying)

    Returns:
        StepResult
    """
    last_error = ""

    for attempt in range(1 + max_retries):
        if attempt > 0:
            logger.info(f"  🔄 Retry {step_name} ({attempt}/{max_retries} times)")

            if is_irreversible and pre_retry_check:
                try:
                    already_done = pre_retry_check()
                    if already_done:
                        logger.info(f"  ✅ Idempotent check: {step_name} completed, no need to retry")
                        return StepResult(True, error="idempotent_skip")
                except Exception as e:
                    logger.debug(f"  Idempotent check exception: {e}")

            recovery = _get_recovery_advice(page, platform, step_name, last_error)
            if recovery:
                action = recovery.get("recovery", "retry_same")
                if action in _NON_RETRYABLE_RECOVERIES:
                    logger.warning(f"  AI suggests giving up: {recovery.get('diagnosis', '')}")
                    return StepResult(False, error=f"ai_abort: {recovery.get('diagnosis', '')}")

                _execute_recovery(page, action, recovery)
            else:
                time.sleep(min(2 * attempt, 8))

        try:
            result = step_fn()
            if result.success:
                if attempt > 0:
                    logger.info(f"  ✅ {step_name} Successful after {attempt+1}st attempt")
                return result
            last_error = result.error or "step returned failure"
        except Exception as e:
            err_name = type(e).__name__
            last_error = f"{err_name}: {str(e)[:200]}"
            if "Disconnected" in err_name or "disconnected" in str(e).lower():
                logger.warning(f"  ⚠️ {step_name} The page connection is disconnected and cannot be retried.")
                return StepResult(False, error=last_error)
            logger.warning(f"  ⚠️ {step_name} Exception: {last_error}")

    logger.error(f"  ❌ {step_name} still failed after {1+max_retries} attempts: {last_error}")
    return StepResult(False, error=f"exhausted_{max_retries}_retries: {last_error}")


def _get_recovery_advice(page, platform: str, step_name: str, error_msg: str) -> dict | None:
    """Call AI to diagnose the cause of failure. Return None if the AI ​​is unavailable (downgrade to simple retry)."""
    try:
        from social_uploader.tools.ai_judge import diagnose_failure
        return diagnose_failure(page, platform, step_name, error_msg)
    except Exception as e:
        logger.debug(f"  AI diagnostics not available: {e}")
        return None


def _execute_recovery(page, action: str, advice: dict):
    """Perform recovery actions based on AI recommendations."""
    logger.info(f"  🔧 Perform recovery: {action}")

    if action in _NEEDS_DISMISS:
        sel = advice.get("dismiss_selector")
        if sel:
            try:
                btn = page.ele(sel, timeout=1)
                if btn and btn.states.has_rect:
                    btn.click()
                    logger.info(f"  Occluded element turned off: {sel}")
                    time.sleep(1)
                    return
            except Exception:
                pass
        try:
            page.handle_alert(accept=True, timeout=0.5)
        except Exception:
            pass
        for fallback_sel in ["[aria-label='Close']", "[aria-label='关闭']", "text:OK", "text:Cancel"]:
            try:
                el = page.ele(fallback_sel, timeout=0.3)
                if el and el.states.has_rect:
                    el.click()
                    time.sleep(0.5)
                    break
            except Exception:
                pass
        time.sleep(1)

    elif action in _NEEDS_WAIT:
        wait_s = advice.get("wait_seconds", 5)
        wait_s = max(2, min(wait_s, 15))
        logger.info(f"  Wait {wait_s} seconds...")
        time.sleep(wait_s)

    elif action in _NEEDS_SCROLL:
        try:
            page.scroll.to_bottom()
            time.sleep(1)
        except Exception:
            pass

    elif action in _NEEDS_REFRESH:
        try:
            page.refresh()
            time.sleep(3)
        except Exception:
            pass

    elif action in _NEEDS_NAV_BACK:
        try:
            page.back()
            time.sleep(2)
        except Exception:
            pass

    elif action == "skip":
        logger.info("  AI recommends skipping this step")

    else:
        time.sleep(2)
