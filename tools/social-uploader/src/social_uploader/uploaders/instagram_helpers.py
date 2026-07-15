"""Instagram platform-specific auxiliary functions (excluding step arrangement).

[Architecture Agreement]
- `tools/` = Common infrastructure for all platforms
- `uploaders/instagram_helpers.py` = Instagram exclusive assistant (only instagram.py can be imported)
- `uploaders/instagram.py` = Step arranger (does not write underlying logic)

Cross-platform import is prohibited: tiktok.py / youtube.py This module is not allowed to be imported.

【status quo】
The Instagram upload process currently does not include schedule/visibility and other aspects that require complex recipes.
(IG Web does not support schedule and has no visibility control), the main process can be used `find_element` + directly
click to complete all steps, so there is no need to migrate functions in this module.

[When to add functions here]
- Requires JS injection to operate Instagram-specific UI (such as Reels exclusive button, Story editing panel)
- Introduce IG exclusive recipe (if Meta goes online in the future, IG will release it regularly)
- Instagram Shadow DOM / iframe adaptation appears (such as embedded components integrated with Threads)
- Platform-specific status detection or retry strategies

[It is forbidden to add here]
- General tools (should be placed in tools/)
- TikTok/YouTube shared logic (should put tools/ or keep their respective helpers)
- Step arrangement (should stay in instagram.py)
"""

import logging

logger = logging.getLogger(__name__)

# There is no function yet. Please follow the convention above when adding.
