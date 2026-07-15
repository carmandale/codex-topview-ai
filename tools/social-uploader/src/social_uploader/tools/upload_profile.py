"""
Upload configuration file loader

Responsibilities: Load, verify, and merge users' uploaded profiles.
The upload script obtains the value of the configurable item through the profile instead of hard-coding it in the code.

Configuration priority: user profile > platform default > common default
"""

import json
import os
import logging
import copy

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PROFILE_PATH = os.path.join(_DIR, '..', 'profiles', 'default.json')


def _deep_merge(base, override):
    """Merge two dictionaries recursively, override covering the fields of base with the same name."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def load_profile(profile_path=None):
    """
    Load upload configuration.

    - profile_path=None → Return to the default configuration (the behavior is exactly the same as before the change)
    - profile_path=path → load user configuration and merge with default configuration (user's overrides default)

    Returns the complete profile dictionary.
    """
    with open(_DEFAULT_PROFILE_PATH, 'r', encoding='utf-8') as f:
        default = json.load(f)

    if profile_path is None:
        return default

    if not os.path.exists(profile_path):
        logger.error(f"Configuration file does not exist: {profile_path}")
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with open(profile_path, 'r', encoding='utf-8') as f:
        user_profile = json.load(f)

    merged = _deep_merge(default, user_profile)

    known_top_keys = {"common", "tiktok", "instagram", "youtube"}
    unknown = set(user_profile.keys()) - known_top_keys
    if unknown:
        logger.warning(f"⚠️ There is an unrecognized top-level field in the configuration file: {unknown}, ignored")

    return merged


def get_platform_config(profile, platform):
    """
    Get the complete configuration of a platform.

    Merge logic: common as base → platform-specific configuration overrides fields of common with the same name.
    For example common.visibility="public" but youtube.visibility="unlisted" → ultimately visibility="unlisted"

    Returns a flat dictionary, and the upload script directly uses config["field name"] to obtain the value.
    """
    common = profile.get("common", {})
    platform_specific = profile.get(platform, {})
    return _deep_merge(common, platform_specific)


_PLATFORM_CONSTRAINTS = [
    {
        "platform": "instagram",
        "check": lambda c: c.get("schedule") is not None,
        "message": "Instagram does not support scheduled posting and has been automatically removed. The video will be posted immediately.",
        "strip_keys": ["schedule"],
    },
    {
        "platform": "instagram",
        "check": lambda c: c.get("visibility") is not None,
        "message": "Instagram doesn't support visibility settings and has been automatically removed",
        "strip_keys": ["visibility"],
    },
    {
        "platform": "tiktok",
        "check": lambda c: c.get("visibility") == "only_me" and c.get("schedule") is not None,
        "message": "TikTok videos that are only visible to you cannot be published at a scheduled time. The timing setting has been automatically removed and the video will be published immediately.",
        "strip_keys": ["schedule"],
    },
]


def validate_platform_config(platform, config):
    """Verify platform configuration, automatically remove incompatible options and return warning list.

    Only intercept "dangerous silent ignores" - that is, do not intercept scenarios that will cause actual losses to the user
    (For example, the user thought the video was timed but it was actually released immediately).
    Do not maintain the full support matrix to avoid accidental killing when adding new configuration items.

    Return (config, warnings), config has been corrected in place, and warnings is a list of strings.
    """
    warnings = []
    for rule in _PLATFORM_CONSTRAINTS:
        if rule["platform"] != platform:
            continue
        if rule["check"](config):
            warnings.append(rule["message"])
            for key in rule["strip_keys"]:
                config[key] = None
    return config, warnings
