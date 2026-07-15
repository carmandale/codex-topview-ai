# Troubleshooting

## Failed to connect to browser
- Confirm Chrome is started in debug mode: `bash scripts/start_chrome_debug.sh`
- Verification port: `curl -s http://localhost:9222/json/version`

## Not logged in
- The script will automatically detect the login status and exit(1) if not logged in.
- Please manually access the corresponding platform in the browser to complete the login and try again.
- This tool will not process any account passwords

## Element not found/page structure changes (dual-track parallelism + three-layer recipe)

Element search uses dual-rail parallelism:
- **Track A (Fast Path)**: Read `button_config.json` selector list, fast try in 1.5s
- **Track B (AI path)**: When track A misses, `ai_locator.py`'s UltimateLocator passes `platform_semantics.py`'s structured semantic description + AgentQL AI API to locate the element (no write-back results, each time based on real-time page status)
- **Failure Diagnosis**: When both tracks miss, the `DIAG|` diagnostic line is output and handed over to the Agent for manual intervention.

Interaction recipes (scheduled release, visibility, etc.) still use three layers of security:
- **Tier 1**: Execute according to the recipe in `state_patterns.json`, using the predefined selector
- **Tier 2a**: `dom_heuristic` Heuristic search for alternative elements with semantic keywords when selector fails (native, free)
- **Tier 2b**: When the heuristic fails, `agentql_client` calls AgentQL AI API semantic positioning element (requires API Key)
- **Tier 3**: When all failures occur, the `DIAG|` diagnostic line will be output and handed over to the Agent for manual intervention.

### Button selector fixes
- The entire Agent repair process only requires running the command and does not require editing any files:
  1. `social-upload suggest-selectors --run-id {run_id}` — Get a list of candidate repair commands
  2. `social-upload fix-selector --target {platform} --key {button_key} --selector "..."` — apply the recommended fix
  3. Retry from the breakpoint with `--resume-from {step}`
- The selector is configured at `src/social_uploader/button_config.json`

### Interactive Recipe fixes
- Complex interactions such as visibility and scheduled release use the Recipe recipe system:
  1. `social-upload show-recipe --target {platform} --recipe {recipe_name}` — view the current recipe
  2. `social-upload fix-recipe --target {platform} --recipe {recipe_name} --step {step_id} --selector "new_selector"` — update a step selector
- The recipe is defined in `src/social_uploader/state_patterns.json`
- Commonly used recipe names: `schedule_recipe` (scheduled release), `visibility_recipe` (visibility, TikTok only)

## DIAG log description
- Each step of the script outputs structured JSON to stderr (for automated parsing)
- On failure, write the two-layer file to `~/.social_uploader/`:
  - `summary.jsonl`: One-line index containing error type and detail file path
  - `detail_{run_id}.jsonl`: Contains detailed context such as DOM fragments
- The `DIAG|` line in the terminal is a trigger signal to the Agent. The format is: `DIAG|run_id=xxx|platform=xxx|step=xxx|error=xxx`
- Use the `social-upload diag` subcommand to manually extract the condensed DOM of the current browser page

## About the code
- `src/social_uploader/uploaders/` is the official version (called by CLI) and has log and automatic repair capabilities.
- An earlier standalone script has been archived in `DrissionPage/_archive/` and should no longer be used
- **Always use the `social-upload` CLI command**

## Still connected to old account after switching Chrome accounts

The debug browser uses a separate data directory (`~/.chrome-social-upload`), completely isolated from daily Chrome. Switching between Google accounts in daily Chrome will not affect the login status of the debug browser.

**Solution:**
```bash
# 1. Terminate the old debugging browser
.venv/bin/social-upload restart-browser

# 2. Restart the debugging browser
bash scripts/start_chrome_debug.sh          # macOS
scripts\start_chrome_debug.bat              # Windows

# 3. Log out of the old account in the debugging browser, log in to the new account, and then re-execute the upload command.
```

**Root Cause**: `connect_browser()` connected to the debug browser through `127.0.0.1:9222`. This browser has independent cookies and login status (stored in `~/.chrome-social-upload`) and is not affected by daily Chrome Profile switching. To change accounts, you must operate within the debugging browser.

## Upload timed out
- Check network connection
- Check video file size (oversized files will take longer to upload)
- The script waits for 60-120 seconds by default. Please check the browser manually after the timeout.

## CLI command not found
- Confirm installed: `.venv/bin/pip install -e .`
- Make sure you are using the correct Python environment: `.venv/bin/social-upload --help`
