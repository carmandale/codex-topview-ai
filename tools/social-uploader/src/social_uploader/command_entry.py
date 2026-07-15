import argparse
import sys
import logging

from social_uploader.repair_engine import generate_run_id


def main():
    parser = argparse.ArgumentParser(
        prog='social-upload',
        description='Social media video automatic upload tool (TikTok / Instagram / YouTube)',
    )
    subparsers = parser.add_subparsers(dest='platform', required=True, help='target platform')

    # ---Public account parameters ---
    _account_help = 'Use the specified account to upload (if not uploaded, the last account used will be used)'

    # --- TikTok ---
    p_tk = subparsers.add_parser('tiktok', help='Upload to TikTok')
    p_tk.add_argument('--video', required=True, help='Video file path')
    p_tk.add_argument('--title', required=True, help='video title')
    p_tk.add_argument('--description', required=True, help='Video description')
    p_tk.add_argument('--cover', default=None, help='Cover image path (optional, supports jpg/png)')
    p_tk.add_argument('--no-publish', action='store_true', help='Fill out the form but don’t click publish')
    p_tk.add_argument('--resume-from', default=None, help='Resume execution from specified step')
    p_tk.add_argument('--profile', default=None, help='Upload the configuration file path (JSON). If not uploaded, the default configuration will be used.')
    p_tk.add_argument('--schedule', default=None, help='Scheduled release time (format: "YYYY-MM-DD HH:MM"), if not passed, it will be released immediately')
    p_tk.add_argument('--visibility', default=None, help='Visibility: everyone / friends / only_me (default everyone)')
    p_tk.add_argument('--account', default=None, help=_account_help)

    # --- Instagram ---
    p_ig = subparsers.add_parser('instagram', help='Upload to Instagram')
    p_ig.add_argument('--video', required=True, help='Video file path')
    p_ig.add_argument('--caption', required=True, help='Post copy')
    p_ig.add_argument('--no-publish', action='store_true', help='Fill out the form but don’t click share')
    p_ig.add_argument('--resume-from', default=None, help='Resume execution from specified step')
    p_ig.add_argument('--profile', default=None, help='Upload the configuration file path (JSON). If not uploaded, the default configuration will be used.')
    p_ig.add_argument('--schedule', default=None, help='Instagram does not support scheduled posting, and incoming messages will be automatically ignored.')
    p_ig.add_argument('--visibility', default=None, help='Instagram does not support visibility settings, incoming messages are automatically ignored')
    p_ig.add_argument('--account', default=None, help=_account_help)

    # --- YouTube ---
    p_yt = subparsers.add_parser('youtube', help='Upload to YouTube')
    p_yt.add_argument('--video', required=True, help='Video file path')
    p_yt.add_argument('--title', required=True, help='video title')
    p_yt.add_argument('--description', required=True, help='Video description')
    p_yt.add_argument('--no-publish', action='store_true', help='Fill out the form but don’t click publish')
    p_yt.add_argument('--resume-from', default=None, help='Resume execution from specified step')
    p_yt.add_argument('--profile', default=None, help='Upload the configuration file path (JSON). If not uploaded, the default configuration will be used.')
    p_yt.add_argument('--schedule', default=None, help='Scheduled release time (format: "YYYY-MM-DD HH:MM"), if not passed, it will be released immediately')
    p_yt.add_argument('--visibility', default=None, help='Visibility: public / unlisted / private (default public)')
    p_yt.add_argument('--account', default=None, help=_account_help)

    # --- Account account management ---
    p_acc = subparsers.add_parser('account', help='Manage upload account')
    acc_sub = p_acc.add_subparsers(dest='account_action', required=True, help='Account operation')
    acc_add = acc_sub.add_parser('add', help='Add new account')
    acc_add.add_argument('name', help='Account name')
    acc_add.add_argument('--login', action='store_true', help='Start browser login immediately after creation')
    acc_rm = acc_sub.add_parser('remove', help='Delete account')
    acc_rm.add_argument('name', help='Account name')
    acc_rm.add_argument('--delete-data', action='store_true', help='Also delete the Chrome data directory')
    acc_sub.add_parser('list', help='List all accounts')
    acc_login = acc_sub.add_parser('login', help='Start the browser to log in to the specified account')
    acc_login.add_argument('name', nargs='?', default=None, help='Account name (if not passed, the current account will be used)')
    acc_login.add_argument('--debug', action='store_true', help='(Deprecated, with debug port by default)')

    # --- Diag ---
    p_diag = subparsers.add_parser('diag', help='Diagnosis: Extract the condensed DOM of the current browser page')
    p_diag.add_argument('--area', default=None, help='Target area CSS selector (optional)')

    # --- Suggest Selectors ---
    p_suggest = subparsers.add_parser('suggest-selectors', help='Recommend candidate selectors from recently failed DOM fragments')
    p_suggest.add_argument('--run-id', required=True, help='failed run_id (obtained from DIAG| line)')

    # --- Fix Selector ---
    p_fix = subparsers.add_parser('fix-selector', help='Safely add new selectors to button_config.json')
    p_fix.add_argument('--target', required=True, dest='target_platform', help='Target platform (youtube/tiktok/instagram)')
    p_fix.add_argument('--key', required=True, help='Selector key (such as post_button)')
    p_fix.add_argument('--selector', required=True, help='New DrissionPage selector string')

    # --- Suggest Patterns ---
    p_sp = subparsers.add_parser('suggest-patterns', help='Recommend candidate state signals from recently failed DOM snapshots')
    p_sp.add_argument('--run-id', required=True, help='failed run_id (obtained from DIAG| line)')

    # --- Fix Pattern ---
    p_fp = subparsers.add_parser('fix-pattern', help='Safely add new state signals to state_patterns.json')
    p_fp.add_argument('--target', required=True, dest='target_platform', help='Target platform (youtube/tiktok/instagram)')
    p_fp.add_argument('--step', required=True, help='Step name (such as confirm / wait_upload)')
    p_fp.add_argument('--signal', required=True, help='Signal type, such as success_signals or error_signals')
    p_fp.add_argument('--value', required=True, help='New selector string, such as "text:Published"')

    # --- Show Recipe ---
    p_sr = subparsers.add_parser('show-recipe', help='View the current configuration of interactive recipes')
    p_sr.add_argument('--target', required=True, dest='target_platform', help='Target platform (youtube/tiktok/instagram)')
    p_sr.add_argument('--recipe', required=True, help='Recipe name (such as schedule_recipe)')

    # --- Fix Recipe ---
    p_fr = subparsers.add_parser('fix-recipe', help='Update the selector of a step in an interactive recipe')
    p_fr.add_argument('--target', required=True, dest='target_platform', help='Target platform (youtube/tiktok/instagram)')
    p_fr.add_argument('--recipe', required=True, help='Recipe name (such as schedule_recipe)')
    p_fr.add_argument('--step', required=True, help='Step ID (such as set_date)')
    p_fr.add_argument('--selector', required=True, help='New CSS selectors')

    # --- Restart Browser ---
    p_rb = subparsers.add_parser('restart-browser', help='Terminate Chrome on the debug port to reconnect after switching accounts')
    p_rb.add_argument('--port', type=int, default=9222, help='Debug port number (default 9222)')

    # ---Monitor data monitoring ---
    p_mon = subparsers.add_parser('monitor', help='Social media data monitoring and analysis (collected via OpenCLI)')
    mon_sub = p_mon.add_subparsers(dest='monitor_action', required=True, help='Monitor operations')

    mon_config = mon_sub.add_parser('config', help='Configure account platform mapping')
    mon_config.add_argument('--account', default='default', help='Account name (default default)')
    mon_config.add_argument('--youtube', default=None, help='YouTube: true/false (channel ID is obtained by the browser in real time)')
    mon_config.add_argument('--tiktok', default=None, help='TikTok: true/false')
    mon_config.add_argument('--instagram', default=None, help='Instagram: true/false')
    mon_config.add_argument('--douyin', default=None, help='TikTok: true/false')

    _platforms_help = (
        'Only execute on specified platforms (comma separated, optional youtube/tiktok/instagram/douyin),'
        'If not passed, all configured platforms of the account will be overwritten. Example: --platforms tiktok or --platforms youtube,tiktok'
    )

    mon_collect = mon_sub.add_parser('collect', help='Collect data dashboards from each platform (via opencli)')
    mon_collect.add_argument('--account', default='default', help='Account name (default default)')
    mon_collect.add_argument('--no-report', action='store_true', help='Only collect but do not generate reports')
    mon_collect.add_argument('--format', default='terminal', choices=['md', 'html', 'terminal'], help='Report format (default terminal)')
    mon_collect.add_argument('--period', type=int, default=28, help='Analysis cycle number of days (default 28)')
    mon_collect.add_argument('--platforms', default=None, help=_platforms_help)

    mon_report = mon_sub.add_parser('report', help='Generate data analysis reports')
    mon_report.add_argument('--format', default='md', choices=['md', 'html', 'terminal'], help='Output format (default md)')
    mon_report.add_argument('--period', type=int, default=28, help='Analysis cycle number of days (default 28)')
    mon_report.add_argument('--account', default='default', help='Account name (default default)')
    mon_report.add_argument('--output', default=None, help='Customized report save path')
    mon_report.add_argument('--platforms', default=None, help=_platforms_help)

    mon_run = mon_sub.add_parser('run', help='One-click collection + report generation')
    mon_run.add_argument('--format', default='md', choices=['md', 'html', 'terminal'], help='Output format (default md)')
    mon_run.add_argument('--period', type=int, default=28, help='Analysis cycle number of days (default 28)')
    mon_run.add_argument('--account', default='default', help='Account name (default default)')
    mon_run.add_argument('--output', default=None, help='Customized report save path')
    mon_run.add_argument('--platforms', default=None, help=_platforms_help)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    # ---Data monitoring branch ---
    if args.platform == 'monitor':
        _handle_monitor(args)
        sys.exit(0)

    # ---Account Management Branch ---
    if args.platform == 'account':
        from social_uploader.account_manager import (
            add_account, remove_account, list_accounts,
            launch_chrome_for_account, launch_chrome_for_login, get_data_dir,
        )  # launch_chrome_for_login reserved for backward compatibility
        if args.account_action == 'add':
            ok, msg = add_account(args.name)
            if ok:
                print(f"✅ Account '{args.name}' has been created")
                print(f"   Data directory: {msg}")
                if args.login:
                    ok2, msg2 = launch_chrome_for_login(args.name)
                    print(msg2)
            else:
                print(f"❌ {msg}")
            sys.exit(0 if ok else 1)
        elif args.account_action == 'remove':
            ok, msg = remove_account(args.name, delete_data=args.delete_data)
            print(msg)
            sys.exit(0 if ok else 1)
        elif args.account_action == 'list':
            accounts = list_accounts()
            if not accounts:
                print("There are no accounts yet. Create one with `social-upload account add <name>`.")
            else:
                for acc in accounts:
                    marker = " ← current" if acc["is_last_used"] else ""
                    print(f"  {'●' if acc['is_last_used'] else '○'} {acc['name']}{marker}")
                    print(f"    Creation time: {acc['created_at']}")
            sys.exit(0)
        elif args.account_action == 'login':
            ok, msg = launch_chrome_for_account(args.name)
            print(msg)
            sys.exit(0 if ok else 1)

    run_id = generate_run_id()
    resume_from = getattr(args, 'resume_from', None)
    profile_path = getattr(args, 'profile', None)
    account = getattr(args, 'account', None)

    profile = None
    if args.platform in ('tiktok', 'instagram', 'youtube'):
        from social_uploader.tools.upload_profile import load_profile
        profile = load_profile(profile_path)

        schedule_cli = getattr(args, 'schedule', None)
        visibility_cli = getattr(args, 'visibility', None)
        if schedule_cli or visibility_cli:
            if args.platform not in profile:
                profile[args.platform] = {}
            if schedule_cli:
                profile[args.platform]["schedule"] = schedule_cli
            if visibility_cli:
                profile[args.platform]["visibility"] = visibility_cli

    if args.platform == 'tiktok':
        from social_uploader.uploaders.tiktok import upload_tiktok
        success = upload_tiktok(args.video, args.title, args.description, args.no_publish,
                                cover_path=args.cover, run_id=run_id, resume_from=resume_from,
                                profile=profile, account=account)
    elif args.platform == 'instagram':
        from social_uploader.uploaders.instagram import upload_instagram
        success = upload_instagram(args.video, args.caption, args.no_publish,
                                   run_id=run_id, resume_from=resume_from,
                                   profile=profile, account=account)
    elif args.platform == 'youtube':
        from social_uploader.uploaders.youtube import upload_youtube
        success = upload_youtube(args.video, args.title, args.description, args.no_publish,
                                 run_id=run_id, resume_from=resume_from,
                                 profile=profile, account=account)
    elif args.platform == 'diag':
        from social_uploader.tools.browser_manager import connect_browser
        from social_uploader.repair_engine import get_dom_snippet
        _, work, _, _ = connect_browser(new_window=False)
        print(get_dom_snippet(work, area_selector=args.area))
        sys.exit(0)
    elif args.platform == 'suggest-selectors':
        from social_uploader.repair_engine import suggest_selectors
        print(suggest_selectors(args.run_id))
        sys.exit(0)
    elif args.platform == 'fix-selector':
        from social_uploader.tools.element_finder import add_selector
        ok, msg = add_selector(args.target_platform, args.key, args.selector)
        print(msg)
        sys.exit(0 if ok else 1)
    elif args.platform == 'suggest-patterns':
        from social_uploader.repair_engine import suggest_patterns
        print(suggest_patterns(args.run_id))
        sys.exit(0)
    elif args.platform == 'fix-pattern':
        from social_uploader.tools.pattern_checker import add_pattern
        ok, msg = add_pattern(args.target_platform, args.step, args.signal, args.value)
        print(msg)
        sys.exit(0 if ok else 1)
    elif args.platform == 'restart-browser':
        from social_uploader.tools.browser_manager import kill_browser
        killed, msg = kill_browser(port=args.port)
        print(msg)
        if killed:
            print(f"\n✅ Chrome is closed. Please restart the debugging browser:")
            if sys.platform == 'darwin':
                print(f"   bash scripts/start_chrome_debug.sh")
            elif sys.platform == 'win32':
                print(f"   scripts\\start_chrome_debug.bat")
            else:
                print(f"   google-chrome --remote-debugging-port={args.port}")
            print(f"\n After startup, log in to the target platform account in the debugging browser, and then re-execute the upload command.")
        else:
            print(f"\n💡 If the browser is still running, please manually close all Chrome windows and restart it.")
        sys.exit(0)

    elif args.platform == 'show-recipe':
        from social_uploader.tools.recipe_runner import show_recipe
        print(show_recipe(args.target_platform, args.recipe))
        sys.exit(0)
    elif args.platform == 'fix-recipe':
        from social_uploader.tools.recipe_runner import fix_recipe_step
        ok, msg = fix_recipe_step(args.target_platform, args.recipe, args.step, args.selector)
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


def _verify_login_before_collect(platforms: dict) -> dict[str, bool]:
    """Verify the login status on a platform-by-platform basis before collection, and return the login status of each platform.

    Platforms that are not logged in will print an eye-catching reminder and be excluded from the collection list.
    If all platforms are not logged in, log out directly and ask the user to log in first.
    """
    import shutil
    import subprocess as _sp

    opencli = shutil.which("opencli")
    if not opencli:
        for candidate in ("/usr/local/bin/opencli", "/opt/homebrew/bin/opencli"):
            if shutil.which(candidate):
                opencli = candidate
                break
    if not opencli:
        print("❌ opencli not found, login verification skipped")
        return {p: True for p in platforms}

    print("🔍 Verifying the login status of each platform...")
    login_status = {}
    for platform in platforms:
        if not platforms[platform]:
            continue
        if platform == "youtube":
            import urllib.request, urllib.error, json as _json
            try:
                raw = urllib.request.urlopen("http://localhost:9222/json", timeout=3).read()
                tabs = _json.loads(raw)
                has_yt = any("youtube.com" in t.get("url", "") for t in tabs)
                login_status[platform] = has_yt
                if has_yt:
                    print(f"  ✅ {platform}: YouTube tab detected")
                else:
                    print(f"  ⚠️ {platform}: YouTube tab not detected, will automatically navigate when collecting")
                    login_status[platform] = True
            except Exception:
                login_status[platform] = True
                print(f"  ⚠️ {platform}: Unable to detect browser status, skip preflight")
            continue
        cmd_map = {
            "tiktok": [opencli, "tiktok", "creator-stats", "-f", "json"],
            "instagram": [opencli, "instagram", "creator-stats", "-f", "json"],
        }
        cmd = cmd_map.get(platform)
        if not cmd:
            login_status[platform] = True
            continue
        try:
            result = _sp.run(cmd, capture_output=True, text=True, timeout=30)
            output = (result.stdout + result.stderr).lower()
            if result.returncode == 0 and "not logged in" not in output and "missing" not in output:
                login_status[platform] = True
                print(f"  ✅ {platform}: logged in")
            else:
                login_status[platform] = False
                print(f"  ❌ {platform}: Not logged in")
        except Exception:
            login_status[platform] = True
            print(f"  ⚠️ {platform}: Verification timeout, skip")

    logged_in = [p for p, ok in login_status.items() if ok]
    not_logged_in = [p for p, ok in login_status.items() if not ok]

    if not logged_in and not_logged_in:
        print("\n" + "=" * 50)
        print("⛔ All platforms are not logged in and data cannot be collected.")
        print("Please log in to each platform account in the debugging browser first:")
        print("  1. YouTube Studio → studio.youtube.com")
        print("  2. TikTok Studio → tiktok.com/tiktokstudio")
        print("  3. Instagram → instagram.com")
        print("=" * 50)
        sys.exit(1)

    if not_logged_in:
        print(f"\n⚠️ If you are not logged in to the following platforms, collection will be skipped: {', '.join(not_logged_in)}")
        print(f"   Continue collecting logged-in platforms: {', '.join(logged_in)}\n")

    return login_status


def _format_identity(platform: str, identity: dict) -> str:
    """Extract the human-readable account ID from account_identity."""
    username = identity.get("username", "")
    if username:
        prefix = "@" if not username.startswith("@") else ""
        return f"User: {prefix}{username}"
    channel_hint = identity.get("channel_hint", "")
    if channel_hint and platform == "youtube":
        return f"Channel first video: {channel_hint[:30]}"
    return ""


_PLATFORM_ALIAS = {
    "yt": "youtube",
    "youtube": "youtube",
    "tk": "tiktok",
    "tiktok": "tiktok",
    "ig": "instagram",
    "insta": "instagram",
    "instagram": "instagram",
    "dy": "douyin",
    "douyin": "douyin",
    "Tik Tok": "douyin",
}


def _parse_platforms_filter(raw: str | None) -> list[str] | None:
    """Parse the --platforms string into a normalized list of platforms.

    Return value semantics:
      - None: The user has not passed --platforms, and all configured platforms of the account will be used.
      - []: The user passed in all unrecognizable aliases (the caller should exit directly)
      - ["xxx", ...]: The user passed and parsed out at least one legal platform
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    cleaned: list[str] = []
    for token in raw.replace(";", ",").split(","):
        key = token.strip().lower()
        if not key:
            continue
        norm = _PLATFORM_ALIAS.get(key)
        if not norm:
            print(f"⚠️ Ignore unknown platform: {token.strip()} (support: youtube/tiktok/instagram/douyin)")
            continue
        if norm not in cleaned:
            cleaned.append(norm)
    return cleaned


def _apply_platforms_filter(platforms: dict, only: list[str] | None) -> dict:
    """Filter the account_platforms dictionary based on --platforms.

    Returns unchanged when only is None; otherwise only retains the intersection and returns the result for unconfigured but explicitly requested platforms
    Temporarily add a True so that subsequent collectors can still try to collect (suitable for users who are logged in but are still
    I have never run the monitor config scenario).
    """
    if not only:
        return platforms
    result: dict = {}
    for p in only:
        if p in platforms:
            val = platforms[p]
            if val:
                result[p] = val
            else:
                print(f"⚠️ Platform '{p}' has been closed in the account configuration, --platforms will temporarily enable this collection")
                result[p] = True
        else:
            print(f"ℹ️ Platform '{p}' is not in the account configuration, --platforms will temporarily enable this collection")
            result[p] = True
    return result


def _handle_monitor(args):
    """Handles the monitor subcommand."""
    action = args.monitor_action

    _PLATFORM_ARGS = ['youtube', 'tiktok', 'instagram', 'douyin']

    if action == 'config':
        from social_uploader.analytics.store import get_account_platforms, set_account_platforms
        current = get_account_platforms(args.account)
        updated = dict(current)

        has_update = False
        for p in _PLATFORM_ARGS:
            val = getattr(args, p, None)
            if val is not None:
                updated[p] = val.lower() == 'true'
                has_update = True

        if not has_update:
            if current:
                print(f"📋 Platform mapping for account '{args.account}':")
                for k, v in current.items():
                    display = 'Enabled' if v else '(not configured)'
                    print(f"   {k}: {display}")
            else:
                print(f"⚠️Account '{args.account}' has not configured platform mapping")
                print(f"\nUsage example:")
                print(f"  social-upload monitor config --youtube true --tiktok true --instagram true")
            return

        set_account_platforms(args.account, updated)
        print(f"✅ The platform mapping of account '{args.account}' has been updated:")
        for k, v in updated.items():
            display = v if isinstance(v, str) and v else ('Enabled' if v else '(not configured)')
            print(f"   {k}: {display}")

    elif action == 'collect':
        from social_uploader.analytics.store import (
            get_account_platforms, save_snapshot, append_history,
            load_latest_snapshot, load_previous_snapshot,
        )
        from social_uploader.analytics.collector import run_collect

        platforms = get_account_platforms(args.account)
        only = _parse_platforms_filter(getattr(args, 'platforms', None))
        if only == []:
            print("❌ No recognized platforms in the --platforms parameter, exited")
            sys.exit(1)
        if not platforms and not only:
            print(f"❌ The account '{args.account}' has not been configured with platform mapping, please run:")
            print(f"   social-upload monitor config --youtube true --tiktok true --instagram true")
            sys.exit(1)

        platforms = _apply_platforms_filter(platforms or {}, only)
        if not platforms:
            print("❌ After filtering by --platforms, there are no platforms that can be collected, so we have exited.")
            sys.exit(1)

        if only:
            print(f"🎯 Only collect designated platforms: {', '.join(platforms.keys())}")

        login_status = _verify_login_before_collect(platforms)
        verified_platforms = {p: v for p, v in platforms.items() if login_status.get(p, True)}

        print(f"\n🔄 Start collecting data (Account: {args.account}, via OpenCLI)...")
        results = run_collect(verified_platforms)

        success_count = 0
        for platform, data in results.items():
            if data.get("error"):
                print(f"  ❌ {platform}: {data['error']}")
            else:
                metric_count = len(data.get("account_metrics", {}))
                video_count = len(data.get("video_metrics", []))
                save_snapshot(platform, data, account=args.account)
                append_history({
                    "action": "collect",
                    "platform": platform,
                    "metrics_count": metric_count,
                    "videos_count": video_count,
                }, account=args.account)
                identity = data.get("account_identity", {})
                identity_label = _format_identity(platform, identity)
                if identity_label:
                    print(f"  ✅ {platform}: {metric_count} indicators, {video_count} video data ({identity_label})")
                else:
                    print(f"  ✅ {platform}: {metric_count} indicators, {video_count} video data")
                success_count += 1

                top_metrics = data.get("account_metrics", {})
                if top_metrics:
                    summary_parts = []
                    for key in ("views", "likes", "comments", "followers", "new_followers"):
                        val = top_metrics.get(key)
                        if val is not None:
                            from social_uploader.analytics.reporter import _format_number
                            summary_parts.append(f"{key}={_format_number(val)}")
                    if summary_parts:
                        print(f"     📈 {', '.join(summary_parts[:5])}")

        print(f"\n🎉 Data collection completed ({success_count}/{len(results)} platforms successful)")

        collected_identities = []
        for platform, data in results.items():
            if not data.get("error"):
                identity = data.get("account_identity", {})
                label = _format_identity(platform, identity)
                collected_identities.append((platform, label or "(Account name not detected)"))
        if collected_identities:
            print("\n" + "=" * 50)
            print("⚠️ Please confirm whether the account collected below is correct:")
            print("-" * 50)
            for plat, label in collected_identities:
                print(f"  {plat}: {label}")
            print("=" * 50)
            print("If the account is incorrect, please switch accounts in the browser and collect again. \n")

        if not getattr(args, 'no_report', False) and success_count > 0:
            from social_uploader.analytics.analyzer import analyze
            from social_uploader.analytics.advisor import generate_advice
            from social_uploader.analytics.reporter import generate_report

            current_snapshots = {}
            previous_snapshots = {}
            for platform in verified_platforms:
                snap = load_latest_snapshot(platform, account=args.account)
                if snap:
                    current_snapshots[platform] = snap
                    prev = load_previous_snapshot(platform, account=args.account)
                    if prev:
                        previous_snapshots[platform] = prev

            if current_snapshots:
                fmt = getattr(args, 'format', 'terminal')
                period = getattr(args, 'period', 28)
                print(f"\n📊 Analyzing data (Period: {period} days)...")
                analysis = analyze(current_snapshots, previous_snapshots, period_days=period, account=args.account)

                print("📝 Generating creative suggestions based on rules...")
                advice = generate_advice(analysis)

                content, saved_path = generate_report(analysis, advice, fmt=fmt, account=args.account)
                print(content)
                if saved_path:
                    print(f"\n📄 Report file: {saved_path}")

    elif action == 'report':
        from social_uploader.analytics.store import (
            get_account_platforms, load_latest_snapshot, load_previous_snapshot,
        )
        from social_uploader.analytics.analyzer import analyze
        from social_uploader.analytics.advisor import generate_advice
        from social_uploader.analytics.reporter import generate_report

        platforms = get_account_platforms(args.account)
        only = _parse_platforms_filter(getattr(args, 'platforms', None))
        if only == []:
            print("❌ No recognized platforms in the --platforms parameter, exited")
            sys.exit(1)
        all_platform_keys = list(platforms.keys()) if platforms else _PLATFORM_ARGS
        if only:
            all_platform_keys = [p for p in only if p in all_platform_keys] or list(only)
            print(f"🎯 Generate reports only based on the following platforms: {', '.join(all_platform_keys)}")

        current_snapshots = {}
        previous_snapshots = {}
        for platform in all_platform_keys:
            snap = load_latest_snapshot(platform, account=args.account)
            if snap:
                current_snapshots[platform] = snap
                prev = load_previous_snapshot(platform, account=args.account)
                if prev:
                    previous_snapshots[platform] = prev

        if not current_snapshots:
            print("❌ No collected data found, please run:")
            print("   social-upload monitor collect")
            sys.exit(1)

        print(f"📊 Analyzing data (Period: {args.period} days)...")
        analysis = analyze(current_snapshots, previous_snapshots, period_days=args.period, account=args.account)

        print("📝 Generating creative suggestions based on rules...")
        advice = generate_advice(analysis)

        fmt = getattr(args, 'format', 'md')
        output_path = getattr(args, 'output', None)
        content, saved_path = generate_report(analysis, advice, fmt=fmt, output_path=output_path, account=args.account)

        print(content)
        if saved_path:
            print(f"\n📄 Report file: {saved_path}")

    elif action == 'run':
        from social_uploader.analytics.store import (
            get_account_platforms, save_snapshot, append_history,
            load_latest_snapshot, load_previous_snapshot,
        )
        from social_uploader.analytics.collector import run_collect
        from social_uploader.analytics.analyzer import analyze
        from social_uploader.analytics.advisor import generate_advice
        from social_uploader.analytics.reporter import generate_report

        platforms = get_account_platforms(args.account)
        only = _parse_platforms_filter(getattr(args, 'platforms', None))
        if only == []:
            print("❌ No recognized platforms in the --platforms parameter, exited")
            sys.exit(1)
        if not platforms and not only:
            print(f"❌ The account '{args.account}' has not been configured with platform mapping, please run:")
            print(f"   social-upload monitor config --youtube true --tiktok true --instagram true")
            sys.exit(1)

        platforms = _apply_platforms_filter(platforms or {}, only)
        if not platforms:
            print("❌ After filtering by --platforms, there are no platforms that can be collected, so we have exited.")
            sys.exit(1)

        if only:
            print(f"🎯 Only collect designated platforms: {', '.join(platforms.keys())}")

        login_status = _verify_login_before_collect(platforms)
        verified_platforms = {p: v for p, v in platforms.items() if login_status.get(p, True)}

        print(f"\n🔄 Start collecting data (Account: {args.account}, via OpenCLI)...")
        results = run_collect(verified_platforms)

        for platform, data in results.items():
            if data.get("error"):
                print(f"  ❌ {platform}: {data['error']}")
            else:
                save_snapshot(platform, data, account=args.account)
                append_history({
                    "action": "collect",
                    "platform": platform,
                    "metrics_count": len(data.get("account_metrics", {})),
                    "videos_count": len(data.get("video_metrics", [])),
                }, account=args.account)
                identity = data.get("account_identity", {})
                identity_label = _format_identity(platform, identity)
                suffix = f" ({identity_label})" if identity_label else ""
                print(f"  ✅ {platform}: Collection completed {suffix}")

        all_platform_keys = list(verified_platforms.keys())
        current_snapshots = {}
        previous_snapshots = {}
        for platform in all_platform_keys:
            snap = load_latest_snapshot(platform, account=args.account)
            if snap:
                current_snapshots[platform] = snap
                prev = load_previous_snapshot(platform, account=args.account)
                if prev:
                    previous_snapshots[platform] = prev

        if not current_snapshots:
            print("❌ Collection failed on all platforms and reports cannot be generated")
            sys.exit(1)

        print(f"\n📊 Analyzing data (Period: {args.period} days)...")
        analysis = analyze(current_snapshots, previous_snapshots, period_days=args.period, account=args.account)

        print("📝 Generating creative suggestions based on rules...")
        advice = generate_advice(analysis)

        fmt = getattr(args, 'format', 'md')
        output_path = getattr(args, 'output', None)
        content, saved_path = generate_report(analysis, advice, fmt=fmt, output_path=output_path, account=args.account)

        print(content)
        if saved_path:
            print(f"\n📄 Report file: {saved_path}")
        print("\n🎉 Collection + reporting completed with one click")


if __name__ == '__main__':
    main()
