"""Data storage layer - account mapping management, snapshot access, and historical timing reading.

Storage structure (isolated by account):
  ~/.social_uploader/analytics/
    accounts_map.json — Account → Platform switch mapping (global, only true/false)
    <account>/ — like default/
      snapshots/ — A complete JSON snapshot of each collection
        {timestamp}_{platform}.json
      history.jsonl — Time series append, collecting one line of summary each time
      reports/ — Generated report files
        {date}_report.md / .html
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path.home() / ".social_uploader"
_ANALYTICS_DIR = _BASE_DIR / "analytics"
_ACCOUNTS_MAP_PATH = _ANALYTICS_DIR / "accounts_map.json"

_OLD_SNAPSHOTS_DIR = _ANALYTICS_DIR / "snapshots"
_OLD_REPORTS_DIR = _ANALYTICS_DIR / "reports"
_OLD_HISTORY_PATH = _ANALYTICS_DIR / "history.jsonl"


def _account_dir(account: str = "default") -> Path:
    return _ANALYTICS_DIR / account


def _ensure_account_dirs(account: str = "default"):
    base = _account_dir(account)
    for sub in ("snapshots", "reports"):
        (base / sub).mkdir(parents=True, exist_ok=True)


def _ensure_dirs():
    _ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_data():
    """Migrate the old flat directory data to the default/account subdirectory when running for the first time."""
    target = _account_dir("default")
    migrated = False

    if _OLD_SNAPSHOTS_DIR.exists() and not (target / "snapshots").exists():
        _ensure_account_dirs("default")
        for f in _OLD_SNAPSHOTS_DIR.glob("*.json"):
            shutil.move(str(f), str(target / "snapshots" / f.name))
        if not any(_OLD_SNAPSHOTS_DIR.iterdir()):
            _OLD_SNAPSHOTS_DIR.rmdir()
        migrated = True

    if _OLD_REPORTS_DIR.exists() and not (target / "reports").exists():
        _ensure_account_dirs("default")
        for f in _OLD_REPORTS_DIR.iterdir():
            shutil.move(str(f), str(target / "reports" / f.name))
        if not any(_OLD_REPORTS_DIR.iterdir()):
            _OLD_REPORTS_DIR.rmdir()
        migrated = True

    if _OLD_HISTORY_PATH.exists() and not (target / "history.jsonl").exists():
        _ensure_account_dirs("default")
        shutil.move(str(_OLD_HISTORY_PATH), str(target / "history.jsonl"))
        migrated = True

    if migrated:
        logger.info("  📦 Old version data has been migrated to default/account directory")


_migrate_legacy_data()


# ---------------------------------------------------------------------------
# accounts_map management (global, not divided into directories by account)
# ---------------------------------------------------------------------------

def load_accounts_map() -> dict:
    _ensure_dirs()
    if _ACCOUNTS_MAP_PATH.exists():
        try:
            return json.loads(_ACCOUNTS_MAP_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read accounts_map.json: {e}")
    return {}


def save_accounts_map(mapping: dict):
    _ensure_dirs()
    _ACCOUNTS_MAP_PATH.write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"  accounts_map saved: {_ACCOUNTS_MAP_PATH}")


def _sanitize_platforms(platforms: dict) -> dict:
    """Make sure that the platform value is only True/False and does not contain identification information such as channel ID."""
    sanitized = {}
    for k, v in platforms.items():
        if isinstance(v, bool):
            sanitized[k] = v
        elif isinstance(v, str) and v.lower() in ("true", "false"):
            sanitized[k] = v.lower() == "true"
        elif v:
            sanitized[k] = True
        else:
            sanitized[k] = False
    return sanitized


def get_account_platforms(account: str = "default") -> dict:
    """Returns the platform mapping of the specified account. If it does not exist, an empty dict is returned.

    Automatically normalize old formats (with string values ​​such as channel IDs) to true/false.
    """
    mapping = load_accounts_map()
    raw = mapping.get(account, {})
    sanitized = _sanitize_platforms(raw)
    if raw != sanitized:
        mapping[account] = sanitized
        save_accounts_map(mapping)
    return sanitized


def set_account_platforms(account: str, platforms: dict):
    """Set the platform mapping for the specified account. Platform values ​​only allow true/false."""
    mapping = load_accounts_map()
    mapping[account] = platforms
    save_accounts_map(mapping)


# ---------------------------------------------------------------------------
# Snapshot storage (isolated by account)
# ---------------------------------------------------------------------------

_SNAPSHOT_RETAIN_DAYS = 90


def save_snapshot(platform: str, data: dict, account: str = "default") -> Path:
    """Save a complete data snapshot collected once and return the file path. Automatically clean up overaged snapshots after saving."""
    _ensure_account_dirs(account)
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"{ts}_{platform}.json"
    path = _account_dir(account) / "snapshots" / filename
    data_with_meta = {
        "platform": platform,
        "collected_at": datetime.now().isoformat(),
        **data,
    }
    sanitized = (
        json.dumps(data_with_meta, indent=2, ensure_ascii=False)
        .encode("utf-8", errors="replace")
        .decode("utf-8")
    )
    path.write_text(sanitized, encoding="utf-8")
    logger.info(f"  Snapshot saved: {path.name}")
    _cleanup_old_snapshots(account)
    return path


def _cleanup_old_snapshots(account: str = "default"):
    """Delete snapshot files older than _SNAPSHOT_RETAIN_DAYS days."""
    snap_dir = _account_dir(account) / "snapshots"
    if not snap_dir.exists():
        return
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=_SNAPSHOT_RETAIN_DAYS)
    removed = 0
    for f in snap_dir.glob("*.json"):
        try:
            ts_str = f.name.split("_")[0]
            file_time = datetime.strptime(ts_str, "%Y-%m-%dT%H-%M-%S")
            if file_time < cutoff:
                f.unlink()
                removed += 1
        except (ValueError, IndexError):
            continue
    if removed:
        logger.info(f"  🧹 Cleaned {removed} old snapshots older than {_SNAPSHOT_RETAIN_DAYS} days")


def load_latest_snapshot(platform: str, account: str = "default") -> dict | None:
    """Load the latest snapshot of the specified platform."""
    _ensure_account_dirs(account)
    snap_dir = _account_dir(account) / "snapshots"
    candidates = sorted(
        snap_dir.glob(f"*_{platform}.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    if not candidates:
        return None
    try:
        return json.loads(candidates[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Snapshot read failed {candidates[0]}: {e}")
        return None


def load_previous_snapshot(platform: str, account: str = "default") -> dict | None:
    """Load the penultimate snapshot of the specified platform (for trend comparison)."""
    _ensure_account_dirs(account)
    snap_dir = _account_dir(account) / "snapshots"
    candidates = sorted(
        snap_dir.glob(f"*_{platform}.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    if len(candidates) < 2:
        return None
    try:
        return json.loads(candidates[1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Snapshot read failed {candidates[1]}: {e}")
        return None


def list_snapshots(platform: str | None = None, limit: int = 20, account: str = "default") -> list[dict]:
    """Lists snapshot summaries, filterable by platform."""
    _ensure_account_dirs(account)
    snap_dir = _account_dir(account) / "snapshots"
    pattern = f"*_{platform}.json" if platform else "*.json"
    candidates = sorted(
        snap_dir.glob(pattern),
        key=lambda p: p.name,
        reverse=True,
    )[:limit]
    result = []
    for p in candidates:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            result.append({
                "file": p.name,
                "platform": data.get("platform", "?"),
                "collected_at": data.get("collected_at", "?"),
            })
        except (json.JSONDecodeError, OSError):
            pass
    return result


# ---------------------------------------------------------------------------
# Historical time series (isolated by account)
# ---------------------------------------------------------------------------

def append_history(entry: dict, account: str = "default"):
    """Append a line of collection summary to history.jsonl."""
    _ensure_account_dirs(account)
    entry.setdefault("ts", datetime.now().isoformat())
    history_path = _account_dir(account) / "history.jsonl"
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_history(limit: int = 100, account: str = "default") -> list[dict]:
    """Read the latest N history records."""
    history_path = _account_dir(account) / "history.jsonl"
    if not history_path.exists():
        return []
    lines = history_path.read_text(encoding="utf-8").strip().splitlines()
    result = []
    for line in lines[-limit:]:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


# ---------------------------------------------------------------------------
# Report files (isolated by account)
# ---------------------------------------------------------------------------

def save_report(content: str, fmt: str = "md", account: str = "default") -> Path:
    """Save the report file and return the path."""
    _ensure_account_dirs(account)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}_report.{fmt}"
    path = _account_dir(account) / "reports" / filename
    path.write_text(content, encoding="utf-8")
    logger.info(f"  Report saved: {path}")
    return path


def get_reports_dir(account: str = "default") -> Path:
    _ensure_account_dirs(account)
    return _account_dir(account) / "reports"
