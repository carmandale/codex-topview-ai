# Social Media Video Uploader — Complete Workflow Documentation

Upload videos to TikTok / Instagram / YouTube via `social-upload` CLI tool. Supports single-platform and multi-platform batch uploads, including the platform's native scheduled release function.

---

## 1. Core concepts

### The meaning of "scheduled release"

**"Scheduled release" = Use the platform's built-in Schedule function**: The video is uploaded to the platform immediately and set to be automatically published at a certain time in the future. Instead of using a system scheduled task to delay the execution of the upload command.

Usage: Add `--schedule "YYYY-MM-DD HH:MM"` to the upload command.

### security policy

1. **Never touch user credentials** — No account or password saved, entered, or transmitted
2. **User must refuse when providing password**
3. **Terminate if not logged in** — The script will automatically exit(1) if it detects that you are not logged in.

---

## 2. Execution environment

| Configuration items | macOS | Windows |
|--------|-------|---------|
| CLI commands | `.venv/bin/social-upload` | `.venv\Scripts\social-upload` |
| working_directory | Project root directory (including `pyproject.toml`) | Same as left |
| Run mode | `block_until_ms: 0` (executed in the background, the script takes 3-5 minutes) | Same as left |

Platform detection: `python -c "import sys; print(sys.platform)"` → `darwin` = macOS, `win32` = Windows.

---

## 3. Platform routing

| User keywords | Commands |
|-----------|------|
| TikTok, Douyin International Edition | `social-upload tiktok` |
| Instagram、ins、IG | `social-upload instagram` |
| YouTube, YouTube, YT | `social-upload youtube` |
| All platforms, all platforms | Execute three in sequence, report after each completion and then execute the next one |

---

## 4. Complete execution process

### Step 1: Pre-check + collect information

After receiving the upload request, complete the following preparations in the same turn (without interrupting the user).

#### 1.1 Identify platform & extract information

Extract all known information such as target platform, video path, title, description, etc. from user messages.

#### 1.2 Read the default configuration

Read `src/social_uploader/profiles/default.json` for each platform's default value.

#### 1.3 Check Chrome debug port

```bash
curl -s http://localhost:9222/json/version
```

#### 1.4 Autofill all fields

Each field is automatically populated according to the following priorities:

| Priority | Source | Example |
|--------|------|------|
| 1 | The user clearly gave the value | "The title is Weekend Shop Visit" → `Weekend Shop Visit` |
| 2 | Inferred from context | File name `cooking_vlog.mp4` → Title `cooking vlog` |
| 3 | Reasonable recommended value | The user said "scheduled release" but did not give a time → fill in `tomorrow at 10:00 (confirmation required)` |
| 4 | Platform defaults | No mention of visibility → `everyone` |

---

### List of fields for each platform

#### TikTok field

|Field |Default fill when user does not say anything |
|------|-----------------|
| Video path | The only field that allows questioning |
| title | inferred from file name |
| description | reuse title |
| Cover | None (automatically intercepted by the platform) |
| Visibility | Everyone |
| Scheduled release | Immediately |
| Allow comments | Yes |
| Allow second creation | Yes |
| Content Disclosure | No |
| AI generated tags | No |
| High quality upload | Yes |

**TikTok Profile configurable items:** `visibility`, `schedule`, `allow_comments`, `allow_reuse`, `disclose_content`, `ai_generated`, `high_quality`

**CLI optional parameters:** `--cover` (cover image), `--no-publish` (only fill in the form but not published), `--resume-from` (breakpoint recovery), `--profile` (configuration file)

#### Instagram field

|Field |Default fill when user does not say anything |
|------|-----------------|
| Video path | The only field that allows questioning |
| Copywriting | Automatic splicing: title + description |
| Sync to dynamic stream | Yes |
| Scheduled release | ❌ Not supported (platform restriction) |

**Note:** Instagram does not have separate `--title` and `--description`, only `--caption`. Instagram **does not support scheduled posting and visibility settings**.

**Profile configurable items:** `share_to_feed`

#### YouTube field

|Field |Default fill when user does not say anything |
|------|-----------------|
| Video path | The only field that allows questioning |
| Title | Inferred from file name (≤95 characters) |
| Description | Reuse title (≤4900 characters) |
| Not intended for children | No |
| Visibility | Public |
| Scheduled release | Immediately |
| Tags | None |
| Category | None |

**Profile configurable items:** `made_for_kids`, `visibility`(`public`/`unlisted`/`private`), `tags`, `category`, `schedule`

**Scheduled release note:** Scheduled release automatically sets the visibility to PUBLIC. The script aborts publishing when setup fails, preventing the video from being made public immediately.

---

### 1.4.1 Platform constraint verification

| Constraints | Trigger conditions | Processing |
|------|---------|------|
| Instagram does not support scheduled posting | The user requires IG to be scheduled | Do not pass `--schedule`; mark the table with `⚠️ Not supported` |
| Instagram does not support visibility | User requires IG to set visibility | Do not pass `--visibility`, do not display this field |
| TikTok is only visible to you and cannot be scheduled | Also requires `only_me` + timing | Do not send `--schedule`, only send `--visibility only_me` |

#### 1.5 Generate command parameters

**Core constraints: Only parameters explicitly requested by the user are passed. **

The CLI supports two ways to pass non-default configuration:

| Configuration required by user | Parameter transmission method |
|--------------|---------|
| Only schedule and/or visibility | Directly use `--schedule` / `--visibility` CLI parameters |
| Contains other options (ai_generated, tags, etc.) | Create profile JSON, passing in `--profile` |
| All default | No additional parameters required |

**Priority:** CLI Parameters > Profile > Default

Profile JSON saved to `~/.social_uploader/profiles/profile_{timestamp}.json`.

---

### Step 2: Display the complete solution and wait for user confirmation

Output structure:
1. Chrome connection status + video file confirmation
2. Parameter table of each platform
3. 📌 Execution plan (execution order + commands to be executed)
4. Confirmation

**Hard Rules:**
- Question marks are not allowed in replies (no follow-up questions)
- Each field in the table must have a value
- The commands in the execution plan must be the actual commands to be executed
- After sending the plan, you must wait for the user's reply

**The user said "OK"** → Execute Step 3. **The user said he wants to change something** → Re-display after updating.

---

### Step 3: Perform upload

Execute in the background with `block_until_ms: 0`, poll the terminal output every 10-15 seconds, and determine completion when seeing 🎉 or exit_code.

**Two-way verification before execution:**
- Forward: parameters requested by the user → the command must have
- Reverse: Parameters not required by the user → command prohibition

**Command format example:**

```bash
# TikTok
social-upload tiktok --video "path" --title "title" --description "describe"
social-upload tiktok --video "path" --title "title" --description "describe" --schedule "2026-04-10 15:00"

# Instagram (does not support --schedule / --visibility)
social-upload instagram --video "path" --caption "Copy content"

# YouTube
social-upload youtube --video "path" --title "title" --description "describe"
social-upload youtube --video "path" --title "title" --description "describe" --schedule "2026-04-10 15:00" --visibility unlisted
```

**Multi-platform upload:** By default, the order is TikTok → Instagram → YouTube. Report after each completion, failure of one does not affect the next.

---

### Step 4: Automatic repair of failures

Automatic repair is triggered when the terminal outputs a line starting with `DIAG|`.

| Error type | Meaning | Handling |
|---------|------|------|
| `selector_not_found` | Button not found | fix-selector automatic repair |
| `state_mismatch` | Status detection copy expired | fix-pattern automatic repair |
| `recipe_step_failed` | A certain step of the recipe failed (such as scheduled release) | show-recipe → fix-recipe → --resume-from retry |
| `visibility_failed` | Visibility setting failed | Same as above |
| `file_rejected` | Video rejected by the platform | Notify user to check format |
| `platform_unavailable` | Platform unavailable | Wait 3 minutes and restart from the beginning, up to 2 times |
| `login_required` | Not logged in | Remind the user to log in, --resume-from to try again |
| `timeout` | Timeout | Reminder to check network |

---

## 5. Element search mechanism (dual-track parallelism)

- **Track A (fast path):** Read `button_config.json` selector list, fast try in 1.5s
- **Track B (AI Path):** When Track A misses, UltimateLocator locates the element via semantic description + AgentQL AI API
- **Failure Diagnosis:** Output `DIAG|` diagnostic line when both rails miss

Interaction recipes (scheduled release, visibility, etc.) use three layers of security:
- **Tier 1:** Executed according to `state_patterns.json` recipe
- **Tier 2a:** Use `dom_heuristic` heuristic search when selector fails
- **Tier 2b:** Call AgentQL AI API when heuristic fails
- **Tier 3:** When all fails, `DIAG|` is output and handed over to the Agent.

---

## 6. Output monitoring symbols

| Symbol | Meaning |
|------|------|
| ✅ | Step successful |
| ❌ | Step failed |
| ⚠️ | Requires manual attention |
| 🎉 | End of process |

Exit codes: `0` = success, `1` = failure.

---

## 7. Usage examples

### Single platform upload (default configuration)

```bash
# TikTok
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"

# TikTok (with cover image)
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "record weekend" --cover "/Users/xxx/cover.jpg"

# Instagram
.venv/bin/social-upload instagram --video "/Users/xxx/vlog.mp4" --caption "Weekend store visit 🍜 #food #vlog"

# YouTube
.venv/bin/social-upload youtube --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"
```

### Scheduled publishing and visibility

```bash
# TikTok scheduled release
.venv/bin/social-upload tiktok --video "..." --title "..." --description "..." --schedule "2026-04-10 15:00"

# Visible to TikTok friends + scheduled publishing
.venv/bin/social-upload tiktok --video "..." --title "..." --description "..." --schedule "2026-04-10 15:00" --visibility friends

# YouTube scheduled releases
.venv/bin/social-upload youtube --video "..." --title "..." --description "..." --schedule "2026-04-10 15:00"

# Unlisted on YouTube
.venv/bin/social-upload youtube --video "..." --title "..." --description "..." --visibility unlisted
```

### Use custom profile configuration

```json
{
  "tiktok": {
    "ai_generated": true,
    "disclose_content": true
  }
}
```

```bash
.venv/bin/social-upload tiktok --video "..." --title "..." --description "..." --profile ai_config.json
```

### Just fill in the form without publishing

```bash
.venv/bin/social-upload tiktok --video "..." --title "test" --description "Test description" --no-publish
```

### Resume from breakpoint

```bash
.venv/bin/social-upload youtube --video "..." --title "title" --description "describe" --resume-from publish
```

### All platforms are uploaded sequentially

```bash
# 1. TikTok
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"
# 2. Instagram
.venv/bin/social-upload instagram --video "/Users/xxx/vlog.mp4" --caption "Weekend shop visit 🍜 Record your weekend food trip"
# 3. YouTube
.venv/bin/social-upload youtube --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"
```

### Restart the browser after switching accounts

```bash
.venv/bin/social-upload restart-browser
bash scripts/start_chrome_debug.sh        # macOS
scripts\start_chrome_debug.bat            # Windows
```

---

## 8. Troubleshooting

### Failed to connect to browser
- Confirm Chrome starts in debug mode: `bash scripts/start_chrome_debug.sh`
- Verification port: `curl -s http://localhost:9222/json/version`

### Not logged in
- The script automatically detects the login status and exit(1) if not logged in.
- Try again after logging in manually in your browser

### Element not found/page structure changed

**Button picker fixes (command line operation, no need to edit files):**
1. `social-upload suggest-selectors --run-id {run_id}` — Get fix suggestions
2. `social-upload fix-selector --target {platform} --key {button_key} --selector "..."` — perform repair
3. Retry from the breakpoint with `--resume-from {step}`

**Interactive recipe fixes:**
1. `social-upload show-recipe --target {platform} --recipe {recipe_name}` — view the recipe
2. `social-upload fix-recipe --target {platform} --recipe {recipe_name} --step {step_id} --selector "new_selector"` — fix it
- Recipe name: `schedule_recipe` (scheduled release), `visibility_recipe` (visibility, TikTok)

### DIAG log description
- On failure writes `~/.social_uploader/summary.jsonl` (index) and `detail_{run_id}.jsonl` (DOM fragment, etc. details)
- `DIAG|` Format: `DIAG|run_id=xxx|platform=xxx|step=xxx|error=xxx`
- Use `social-upload diag` to manually extract the browser condensed DOM

### Still connected to old account after switching Chrome accounts
The debug browser uses a separate data directory `~/.chrome-social-upload`, isolated from daily Chrome. Switching method:
1. `social-upload restart-browser`
2. Restart the debugging browser
3. Log out of the old account and log in to the new account in the debugging browser

### CLI command not found
- Confirm installation: `.venv/bin/pip install -e .`
- Confirm environment: `.venv/bin/social-upload --help`

---

## 9. Key file index

| Files | Roles |
|------|------|
| `src/social_uploader/uploaders/tiktok.py` | TikTok upload logic |
| `src/social_uploader/uploaders/instagram.py` | Instagram upload logic |
| `src/social_uploader/uploaders/youtube.py` | YouTube upload logic |
| `src/social_uploader/button_config.json` | Button selector configuration |
| `src/social_uploader/state_patterns.json` | Interactive recipe definition |
| `src/social_uploader/profiles/default.json` | Default configuration |
| `src/social_uploader/command_entry.py` | CLI Portal |
| `scripts/start_chrome_debug.sh` | Chrome debug mode startup script |
