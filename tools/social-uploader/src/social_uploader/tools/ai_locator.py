"""AI Navigator — a highly stable semantic positioning class based on AgentQL.

Locate page elements through structured semantic query (container + target),
Contains enhancement mechanisms such as page warm-up, coordinate calibration, and visual verification.

AgentQL API Key is silently degraded when not configured and returns (None, None).
"""

import logging
import time

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


class UltimateLocator:
    """High stability AI element locator.

    Workflow:
    1. prepare_page() — Preheat the page, activate lazy loading, and clear pop-ups
    2. find_element(query_dict, platform) — structured semantic query
    3. _verify_clickable(element) — visual verification + coordinate calibration
    """

    def __init__(self, page):
        self.page = page

    def prepare_page(self):
        """Warm up page: scroll to activate lazy loading + wait for DOM to stabilize + clean up pop-ups."""
        try:
            self.page.scroll.to_location(0, 500)
            time.sleep(0.3)
            self.page.scroll.to_location(0, 0)
            time.sleep(0.2)
        except Exception:
            pass

        try:
            self.page.wait.doc_loaded(timeout=5)
        except Exception:
            pass

        time.sleep(0.5)

        try:
            from social_uploader.tools.pattern_checker import sweep_modals
            sweep_modals(self.page, max_rounds=1)
        except Exception:
            pass

    def _get_dpr(self):
        """Get window.devicePixelRatio, used for coordinate calibration. Get it in real time every time without caching."""
        try:
            dpr = self.page.run_js("return window.devicePixelRatio || 1;")
            return float(dpr) if dpr else 1.0
        except Exception:
            return 1.0

    def find_element(self, query_dict, platform=""):
        """Structured semantic query entry.

        Args:
            query_dict: {"container": "...", "target": "..."}
            platform: platform name (tiktok/instagram/youtube)

        Returns:
            (element, selector) or (None, None)
        """
        try:
            from social_uploader.tools.agentql_client import (
                _extract_relevant_html,
                _agentql_identify,
                _extract_best_selector,
                _is_safe_element,
                _API_KEY,
            )
        except ImportError:
            logger.debug("agentql_client is not available, skip AI positioning")
            return None, None

        if not _API_KEY:
            logger.debug("AGENTQL_API_KEY is not set, skip AI positioning")
            return None, None

        container = query_dict.get("container", "page")
        target = query_dict.get("target", "")
        if not target:
            return None, None

        description = f"{target} inside {container}"

        for attempt in range(_MAX_RETRIES):
            if attempt > 0:
                logger.info(f"  🔄 AI positioning retry ({attempt + 1}/{_MAX_RETRIES})...")
                self.prepare_page()

            context_hint = ""
            if container and container != "page":
                context_hint = f"@role=dialog"

            html = _extract_relevant_html(self.page, context_hint)
            if not html:
                logger.debug("Unable to extract page HTML")
                continue

            logger.info(
                f"  🧠 AI semantic positioning: '{target}' in '{container}'"
                f"(HTML {len(html) // 1024}KB)"
            )
            candidates = _agentql_identify(html, description, platform)
            if not candidates:
                logger.info("  🧠 AgentQL did not return valid candidates")
                continue

            logger.info(f"  🧠 Get {len(candidates)} candidates: {candidates}")

            for sel in candidates:
                try:
                    el = self.page.ele(sel, timeout=2)
                    if not el:
                        continue
                    if not _is_safe_element(el, target):
                        continue
                    if not self._verify_clickable(el):
                        logger.debug(f"    Candidate {sel} not clickable, skip")
                        continue

                    best = _extract_best_selector(self.page, el)
                    final_sel = best if best else sel
                    logger.info(f"  🧠 AI positioning successful: {final_sel}")
                    return el, final_sel
                except Exception:
                    continue

        logger.info("  🧠 AI positioning did not find available elements")
        return None, None

    def _verify_clickable(self, element):
        """Visual validation: check element visibility + mouse movement validation."""
        try:
            if not element.states.has_rect:
                return False
        except Exception:
            return False

        try:
            rect = element.rect.location
            if not rect:
                return False
            x, y = rect
            dpr = self._get_dpr()
            phys_x = int(x * dpr)
            phys_y = int(y * dpr)

            self.page.actions.move_to(phys_x, phys_y)
            time.sleep(0.2)
        except Exception:
            pass

        try:
            is_enabled = element.states.is_enabled
            if is_enabled is False:
                return False
        except Exception:
            pass

        return True
