"""Multi-account management - Each account corresponds to an independent Chrome user data directory, and the login status does not interfere with each other.

Storage structure:
  ~/.social_uploader/accounts.json — Account registration form
  ~/.social_uploader/chrome_profiles/<name>/ — Chrome data directory for each account

Backwards Compatibility:
  The only data directory of the old version ~/.chrome-social-upload is automatically migrated to the "default" account.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path.home() / ".social_uploader"
_PROFILES_DIR = _BASE_DIR / "chrome_profiles"
_REGISTRY_PATH = _BASE_DIR / "accounts.json"
_LEGACY_DATA_DIR = Path.home() / ".chrome-social-upload"

DEFAULT_ACCOUNT = "default"


def _ensure_dirs():
    _BASE_DIR.mkdir(parents=True, exist_ok=True)
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _load_registry() -> dict:
    _ensure_dirs()
    if _REGISTRY_PATH.exists():
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {"accounts": {}, "last_used": None}


def _save_registry(reg: dict):
    _ensure_dirs()
    _REGISTRY_PATH.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")


def _migrate_legacy():
    """Migrate the old version of ~/.chrome-social-upload to the default account (only execute once)."""
    reg = _load_registry()
    if DEFAULT_ACCOUNT in reg["accounts"]:
        return
    target = _PROFILES_DIR / DEFAULT_ACCOUNT
    if _LEGACY_DATA_DIR.exists() and not target.exists():
        shutil.copytree(str(_LEGACY_DATA_DIR), str(target), symlinks=True)
        logger.info(f"  📦 The old data directory has been migrated to the '{DEFAULT_ACCOUNT}' account")
    elif not target.exists():
        target.mkdir(parents=True, exist_ok=True)
    reg["accounts"][DEFAULT_ACCOUNT] = {
        "data_dir": str(target),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if reg["last_used"] is None:
        reg["last_used"] = DEFAULT_ACCOUNT
    _save_registry(reg)


def get_data_dir(account: str | None = None) -> str:
    """Get the Chrome data directory path of the specified account.

    When account=None, the last used account is used. If there is no account, default will be automatically migrated/created.
    """
    _migrate_legacy()
    reg = _load_registry()

    if account is None:
        account = reg.get("last_used") or DEFAULT_ACCOUNT

    if account not in reg["accounts"]:
        raise ValueError(
            f"Account '{account}' does not exist. Available accounts: {', '.join(reg['accounts'].keys()) or '(none)'}\n"
            f"Created with `social-upload account add {account}`."
        )

    reg["last_used"] = account
    _save_registry(reg)
    return reg["accounts"][account]["data_dir"]


def add_account(name: str) -> tuple[bool, str]:
    """Register a new account. return (success, message)."""
    _migrate_legacy()
    reg = _load_registry()
    if name in reg["accounts"]:
        return False, f"Account '{name}' already exists"

    data_dir = _PROFILES_DIR / name
    data_dir.mkdir(parents=True, exist_ok=True)
    reg["accounts"][name] = {
        "data_dir": str(data_dir),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_registry(reg)
    return True, str(data_dir)


def remove_account(name: str, delete_data: bool = False) -> tuple[bool, str]:
    """Delete account registration. When delete_data=True, the Chrome data directory is also deleted."""
    reg = _load_registry()
    if name not in reg["accounts"]:
        return False, f"Account '{name}' does not exist"
    if name == DEFAULT_ACCOUNT:
        return False, "Cannot delete default account"

    entry = reg["accounts"].pop(name)
    if reg.get("last_used") == name:
        reg["last_used"] = DEFAULT_ACCOUNT
    _save_registry(reg)

    if delete_data:
        data_dir = Path(entry["data_dir"])
        if data_dir.exists():
            shutil.rmtree(str(data_dir), ignore_errors=True)
            return True, f"Account '{name}' and its data directory have been deleted"
    return True, f"Account '{name}' has been deleted (data directory has been retained)"


def list_accounts() -> list[dict]:
    """Returns a list of all account information."""
    _migrate_legacy()
    reg = _load_registry()
    result = []
    for name, info in reg["accounts"].items():
        result.append({
            "name": name,
            "data_dir": info["data_dir"],
            "created_at": info.get("created_at", ""),
            "is_last_used": name == reg.get("last_used"),
        })
    return result


def _find_chrome_path() -> str:
    """Locate the Chrome executable path."""
    if sys.platform == "darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    for p in [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]:
        if os.path.exists(p):
            return p
    return os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe")


def launch_chrome_for_login(account: str | None = None) -> tuple[bool, str]:
    """For backward compatibility, call launch_chrome_for_account directly."""
    return launch_chrome_for_account(account)


def _is_existing_chrome_compatible(port: int, expected_data_dir: str) -> bool:
    """Check whether the Chrome running on the port is the debug Chrome of the target account (user-data-dir matching).

    Matches can be directly reused to avoid accidentally killing already logged-in Chrome instances.
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP:" + str(port), "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p.strip()) for p in (result.stdout or "").splitlines() if p.strip()]
    except Exception:
        return False

    if not pids:
        return False

    expected_marker = expected_data_dir.rstrip("/")
    for pid in pids:
        try:
            ps_out = subprocess.run(
                ["ps", "-o", "command=", "-p", str(pid)],
                capture_output=True, text=True, timeout=3,
            ).stdout or ""
            if expected_marker in ps_out:
                return True
        except Exception:
            continue
    return False


def launch_chrome_for_account(account: str | None = None, port: int = 9222) -> tuple[bool, str]:
    """Launch the Chrome debugging browser for the specified account for user login and data collection.

    Security policy (to prevent accidental killing of daily Chrome or logged-in debug Chrome):
      1. If Chrome is already running on port 9222, and its user-data-dir matches the target account
         → Direct reuse, no killing or restarting, login status retained
      2. If Chrome is already running on port 9222, but the user-data-dir does not match (it means other accounts or daily Chrome)
         → The internal safety guardrail of kill_browser will refuse to terminate; a prompt will be returned requiring the user to handle it manually
      3. If port 9222 is free → Start new debug Chrome normally
    """
    data_dir = get_data_dir(account)
    account = account or _load_registry().get("last_used", DEFAULT_ACCOUNT)
    chrome_path = _find_chrome_path()

    if _is_existing_chrome_compatible(port, data_dir):
        logger.info(f"  ✅ There is already a matching debugging Chrome running on port {port}, so you can reuse it directly.")
        return True, (
            f"✅ Detected that debug Chrome for account '{account}' is already running (port {port})\n"
            f"   Data directory: {data_dir}\n"
            f"   No restart operation has been performed, and the login status is retained. \n"
            f"   If you need to switch accounts, please run: social-upload restart-browser --port {port}"
        )

    killed, kill_msg = _kill_existing_chrome_safely(port)
    if not killed and kill_msg.startswith("FOREIGN_CHROME:"):
        return False, (
            f"⚠️Port {port} is already occupied by a Chrome instance **not for this project** and cannot be started automatically\n"
            f"   {kill_msg}\n"
            f"   Recommended Action:\n"
            f"     1. Manually close that Chrome instance (does not affect the Chrome you use daily)\n"
            f"     2. Or start with another debugging port:"
            f" social-upload account login --port 9223"
        )

    try:
        subprocess.Popen(
            [
                chrome_path,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={data_dir}",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--excludeSwitches=enable-automation",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
                "--restore-last-session",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        return True, (
            f"✅ Chrome has been launched for account '{account}' (port {port})\n"
            f"   Data directory: {data_dir}\n"
            f"   Please log in to TikTok / Instagram / YouTube in your browser and let me know when the login is complete."
        )
    except FileNotFoundError:
        return False, f"❌ Chrome not found, please confirm the installation path: {chrome_path}"
    except Exception as e:
        return False, f"❌ Failed to start Chrome: {e}"


def _kill_existing_chrome_safely(port: int) -> tuple[bool, str]:
    """Chrome termination with safety guardrails: Kill only the debugging Chrome for this project."""
    from social_uploader.tools.browser_manager import kill_browser
    killed, msg = kill_browser(port=port)
    if killed:
        logger.info(f"  🔄 The old debugging Chrome for this project has been closed (port {port})")
        time.sleep(1)
    return killed, msg
