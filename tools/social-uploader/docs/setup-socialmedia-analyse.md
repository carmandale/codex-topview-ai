# Social media data analysis and creation guidance—complete workflow document

Collect creator data dashboards on various social platforms through the OpenCLI adapter, generate data briefings and give AI-driven content creation suggestions. Supports three major platforms: YouTube, TikTok, and Instagram.

---

## 1. Core concepts

This Skill consists of 4 sub-modules, which are executed in sequence:

```
BROWSER（Browser management）→ COLLECT（Data collection）→ ANALYZE（Analysis engine）→ REPORT（Report export）
```

The entire process is completed in 3 rounds of dialogue:
1. **Round 1:** Open browser and ask user to log in
2. **Round 2:** Verify login + confirm account
3. **Round 3:** Collect data + generate reports

---

## 2. Execution environment

| Configuration items | macOS | Windows |
|--------|-------|---------|
| CLI commands | `.venv/bin/social-upload` | `.venv\Scripts\social-upload` |
| working_directory | Project root directory (including `pyproject.toml`) | Same as left |
| Chrome User Data | `~/.social_uploader/chrome_profiles/<account>/` | Same as left |
| Debug port | 9222 | Same as left |

Platform detection: `python -c "import sys; print(sys.platform)"` → `darwin` = macOS, `win32` = Windows.

> ⚠️ **All `<CLI>` below represent the CLI command paths in the above table. ** `.venv/bin/social-upload` for macOS, `.venv\Scripts\social-upload` for Windows. Please replace it with the actual path before copying the command.

---

## 3. Hard rules

1. The collection command only uses `monitor collect`, **forbidden** `monitor run`
2. **Prohibit output of technical details** (execution plan, command code blocks, etc.), only display natural language and final report
3. After each round, you must stop and wait for the user to reply. You cannot execute multiple rounds in a row.
4. This skill has nothing to do with the uploaded skill. It is prohibited to borrow the output format of the uploaded skill.

---

## 4. Complete execution process

### Round 1: Open browser

#### perform operations

```bash
<CLI> account login
```

#### Output example

```
🌐 Debug browser is ready (port 9222）。

⚠️ Please log in to the platform account you want to view data in the debugging browser：

  1. YouTube Studio → studio.youtube.com
  2. TikTok Studio → tiktok.com/tiktokstudio
  3. Instagram → instagram.com

Please open the above links one by one, confirm your login and then reply"Logged in"。
```

**Then stop and wait for the user to reply. **

#### Browser status check (for troubleshooting)

```bash
lsof -i :9222 2>/dev/null | head -3
```
- There is output → Chrome debug mode is running
- No output → need to start

#### Browser Bridge inspection (for troubleshooting)

```bash
opencli doctor 2>&1 | head -5
```
- `[OK] Extension: connected` → The connection is normal
- Failed → OpenCLI Browser Bridge extension needs to be enabled at `chrome://extensions`

---

### Round 2: Verify login + confirm account

After the user says "logged in", verify platform by platform:

```bash
opencli tiktok creator-stats -f json 2>&1 | head -20
opencli instagram creator-stats -f json 2>&1 | head -20
```

#### Judgment rules

| Output | Meaning | Processing |
|------|------|------|
| Return JSON data (exit_code=0) | Logged in | Mark ✅ |
| `Not logged in` or `missing cookie` | Not logged in | Request to log in again |
| `No tab with id` / Connection error | Tab problem | Page refresh required |
| Other non-zero exit codes | Other errors | Display error message |

YouTube does not perform full adapter verification (which takes too long), it only checks that the browser has a YouTube tab open.

#### Output example

```
🔍 Verify login status of each platform：
  ✅ YouTube: Logged in
  ✅ TikTok: Logged in (user: @example_tiktok）
  ❌ Instagram: Not logged in (missing ds_user_id cookie)

⚠️ Instagram Login has not been successful. Please open it in a debugging browser instagram.com and log in to reply"alright"。
```

**After all are passed, the detected user name will be displayed, ask "Is this your account?", and then stop and wait for the user to confirm. **

---

### Round 3: Collection + Reporting

Execute after user confirmation:

```bash
<CLI> monitor collect
```

Executed in the background with `block_until_ms: 0`, polling every 10-15 seconds.

#### completion signal

| Terminal Output | Meaning | Next Step |
|---------|------|--------|
| `✅ youtube: ... (user: @xxx)` | Single-platform collection successful | Continue to wait |
| `❌ youtube: ...` | Single platform collection failed | Record error |
| `🎉 Data collection complete` | All completed | Collection ended |
| `exit_code: 0` | Normal exit | End of collection |
| `exit_code: 1` | Abnormal exit | Enter error handling |

#### Identity confirmation after collection

```
📊 Collection completed, the following logged in accounts were detected：

| platform | Account detected | Collection results |
|------|------------|---------|
| YouTube | channel: Example Channel | ✅ 3 indicators, 20 videos (Automatically detect channels) |
| TikTok | user: @example_tiktok | ✅ 14 indicators, 7 videos (4-tab full amount) |
| Instagram | user: @example_instagram | ✅ 9 indicators, 20 videos |

Are these the accounts you want to view?？
```

After confirmation, the complete report output by the terminal (creation suggestions + data briefing) is displayed to the user.

---

## 5. Fast path

| User needs | Practice |
|---------|------|
| "Look at my video data" | Complete 3 rounds of conversation |
| "Reanalyze based on last data" | Direct `monitor report` |
| "Export HTML report" | Direct `monitor report --format html` |
| "Export Markdown Report" | Direct `monitor report --format md` |

Only "Reanalyze" and "Export" can skip rounds 1-2.

---

## 6. Detailed explanation of sub-modules

### 6.1 SM-Browser — Debug browser management

Manage the lifecycle of a debugged Chrome instance.

| Function | Command | Description |
|------|------|------|
| Check status | `lsof -i :9222` | Output = Running |
| Start browser | `<CLI> account login` | Specify account: `<CLI> account login myaccount` |
| Alternate startup | `bash scripts/start_chrome_debug.sh` | Script mode |
| Check Bridge | `opencli doctor 2>&1 \| head -5` | Requires OpenCLI extension |
| Restart the browser | `<CLI> restart-browser` | You need to log in again after restarting |

**Key Documents:**
| Files | Roles |
|------|------|
| `src/social_uploader/account_manager.py` | Chrome Profile management, instance startup |
| `src/social_uploader/tools/browser_manager.py` | Port detection, kill_browser |
| `scripts/start_chrome_debug.sh` | Alternate startup script |

---

### 6.2 SM-Collect — Data collection

Call the OpenCLI adapter through `social-upload monitor collect` to collect data on each platform.

#### Preconditions (all must be met before execution)
1. Debug browser is running (port 9222)
2. The user has manually logged in to each platform in the browser
3. Login verification passed
4. Platform configuration is ready

#### Support platform

| Platform | OpenCLI command | Collection method | Time consumption |
|------|-------------|---------|------|
| YouTube | `opencli youtube creator-stats` | Automatic channel detection + DOM parsing | ~40s |
| TikTok | `opencli tiktok creator-stats` | 4-tab full collection + content management page | ~30s |
| Instagram | `opencli instagram creator-stats` | REST API direct tune | ~9s |
| Douyin | `opencli douyin stats <aweme_id>` | REST API direct adjustment | ~5s |

#### Collection process technical details

**YouTube (auto detection of channels + DOM parsing):**

The adapter does not need to provide the channel ID in advance, the whole process is completed automatically:

| Steps | Page | Collect content | Method |
|------|------|---------|------|
| 1 | `studio.youtube.com` | Channel ID + Channel Name | Wait for Studio to automatically redirect to `/channel/UCxxx/`, extracted from the URL |
| 2 | Analytics overview page | Views, watch time, subscribers | Direct navigation → DOM text parsing |
| 3 | Content management page | Title, duration, visibility, date, number of views, number of comments for each video | Direct navigation → DOM text parsing |

Things to note:
- The channel ID can also be passed in manually: `opencli youtube creator-stats UCxxx -f json`
- Auto-detection may fail if the account has multiple channels and Studio displays the channel selector
- Drafts and broken videos do not include view/comment data

**Instagram：**
1. Extract `ds_user_id` and `csrftoken` from cookies
2. Call `/api/v1/users/{userId}/info/` → number of fans, etc.
3. Call `/api/v1/feed/user/{userId}/?count=20` → video data
4. Automatically calculate interaction rate, video/image distribution

**TikTok (4-tab full collection):**

The adapter will access the 4 analysis tabs + content management page of TikTok Studio in sequence, collecting a total of 5 dimensions of data:

```
Analytics → Overview → Content → Viewers → Followers → Content Management page
```

| Steps | Page/Tab | Collect content | Method |
|------|---------|---------|------|
| 1 | Enter analytics | User information (fans, followers, likes, number of videos) | `/tiktokstudio/api/web/user` JSON API |
| 2 | **Overview tab** | Video views, Profile views, Likes, Comments, Shares, Est. rewards + Trend changes | SSR DOM text parsing |
| 3 | **Content tab** | Popular posts ranking (by Most views / Most likes, etc.) | Click tab → DOM text parsing |
| 4 | **Viewers tab** | Total viewers, New viewers + gender/age/region portrait | Click tab → DOM text analysis |
| 5 | **Followers tab** | Total followers, Net followers + fan gender/age/region portrait | Click tab → DOM text analysis |
| 6 | Content management page | Views/likes/comments, release date, duration, privacy status of each video | Navigate to `/tiktokstudio/content` → DOM parsing |

Things to note:
- Viewers portrait (gender/age/region) needs to reach 100 viewers to be displayed
- Followers portrait needs to reach 100 followers to be displayed
- Popular posts in the Content tab will only appear if they have playback data.
- The video list includes scheduled and private (Only me) videos.

#### Initial configuration

```bash
<CLI> monitor config --youtube true --tiktok true --instagram true   # set up
<CLI> monitor config                                                  # Check
```

#### data storage

```
~/.social_uploader/analytics/<account>/snapshots/<timestamp>_<platform>.json
```

**Key Documents:**
| Files | Roles |
|------|------|
| `src/social_uploader/analytics/collector.py` | Collection arrangement |
| `src/social_uploader/analytics/store.py` | Snapshot access |

---

### 6.3 SM-Analyze — Data Analysis + AI Creation Suggestions

#### Rule Analysis Engine (`analyzer.py`)

Built-in analysis rules without relying on LLM:

| Analysis dimensions | Calculation method |
|---------|---------|
| Interaction rate | (Likes + Comments + Shares) / Views |
| Trend change | Percentage change of current snapshot vs last snapshot |
| Popularity detection | A certain video indicator > Average value of all videos × 2.0 |
| Downturn detection | A certain video indicator < mean value of all videos × 0.3 |
| Release rhythm | Daily/weekly frequency statistics by release time |

#### AI creation suggestions (`advisor.py`)

Moonshot LLM receives **desensitized data** (the video title is replaced with "Video 1" and "Video 2") and generates:

1. **Content Direction Suggestions** — Analysis of popular directions based on popular videos
2. **Format and Length Recommendations** — Best video length, cover style
3. **Release strategy** — optimal release time and frequency
4. **Hag Suggestions** — Popular tag recommendations

#### AI downgrade strategy

| Situation | Behavior |
|------|------|
| `MOONSHOT_API_KEY` Not configured | Downgraded to rule recommendation, report annotation `source: rules` |
| LLM call failed | Downgraded to rule suggestions, logging errors |
| LLM returns non-standard JSON | Automatic repair (Chinese quotation marks → standard quotation marks), downgrade if failed |

#### Configure API Key

```bash
export MOONSHOT_API_KEY=sk-xxx
```

Can be used without setting, and AI suggestions will be downgraded to rule-based suggestions.

#### data isolation
- Data sent to LLM does not include channel ID, username, video URL
- Video title replaced with anonymous number
- API Key is only loaded from environment variables

**Key Documents:**
| Files | Roles |
|------|------|
| `src/social_uploader/analytics/analyzer.py` | Rule Analysis Engine |
| `src/social_uploader/analytics/advisor.py` | AI suggestion generation |

---

### 6.4 SM-Report — report rendering and export

#### Supported formats

| Format | Command | Output | Applicable scenarios |
|------|------|------|---------|
| Terminal | `<CLI> monitor report --format terminal` | Direct terminal output | Quick view |
| Markdown | `<CLI> monitor report --format md` | Terminal + `.md` File | Document Archive, Feishu/Notion |
| HTML | `<CLI> monitor report --format html` | Terminal + `.html` file | Browser view, share |

#### Advanced usage

```bash
# Custom save path
<CLI> monitor report --format md --output ~/Desktop/my_report.md

# Specify time range
<CLI> monitor report --period 7                 # last 7 days
<CLI> monitor report --period 30 --format md    # Last 30 days

# Specify account
<CLI> monitor report --format md --account myaccount
```

#### Report content structure

```
📊 Social media data briefing
├── 📅 Report date + Covered platforms
├── 🔑 Key findings
│   ├── Highlights（🔥 Popular videos, fans, etc.）
│   └── early warning（⚠️ Downtrend etc.）
├── 📈 Overview of account-level metrics
│   ├── Core indicators of each platform + Trend changes
│   └── Cross-platform comparison table (when multiple platforms）
├── 🎬 Video details
│   ├── Video-by-video metric table with all available fields）
│   └── Hot style/downturn mark（🔥 / ⚠️）
├── 💡 AI creative suggestions
│   ├── content direction
│   ├── Format and length
│   ├── Release strategy
│   └── Tag recommendation
└── 📝 Meta information (generation time, data source）
```

#### template system

| Template file | Purpose |
|---------|------|
| `src/social_uploader/analytics/templates/report.md` | Markdown template |
| `src/social_uploader/analytics/templates/report.html` | HTML template (including styles) |

The terminal format is directly generated by `render_terminal()` of `reporter.py` without using a template.

#### report storage

```
~/.social_uploader/analytics/
├── <account>/
│   ├── reports/
│   │   ├── 2026-04-14_report.md
│   │   ├── 2026-04-14_report.html
│   │   └── ...
│   ├── snapshots/       ← Raw collected data
│   └── history.jsonl    ← Collection history
└── accounts_map.json    ← Platform switch configuration
```

**Key Documents:**
| Files | Roles |
|------|------|
| `src/social_uploader/analytics/reporter.py` | Report Rendering Core |
| `src/social_uploader/analytics/templates/report.md` | Markdown template |
| `src/social_uploader/analytics/templates/report.html` | HTML Template |
| `src/social_uploader/analytics/store.py` | Save report |

---

## 7. Error handling summary

| Error | Terminal Behavior | Processing |
|------|---------|------|
| Chrome startup failed | — | Manual: `bash scripts/start_chrome_debug.sh` |
| Port occupied | — | `<CLI> restart-browser` |
| Browser Bridge disconnected | `exit code 69` | `chrome://extensions` Enable extension |
| OpenCLI not installed | `opencli command not found` | `npm install -g @jackwener/opencli` |
| Not logged in | `Not logged in (missing cookie)` | Users need to log in in the browser |
| Missing YouTube channel ID | `channel ID not detected` | Open studio.youtube.com in your browser and log in |
| Tab ID invalid | `No tab with id: xxx` | `<CLI> restart-browser` |
| Timeout | >3 minutes of no output | Check network |

---

## 8. Debugging skills

### Call OpenCLI directly (skipping social-upload)

```bash
opencli youtube creator-stats -f json              # Automatic channel detection, about 40 seconds
opencli youtube creator-stats UCxxxx -f json       # Manually specify channel ID
opencli tiktok creator-stats -f json               # 4-tab full collection, about 25 seconds
opencli instagram creator-stats -f json
opencli instagram creator-stats --count 50 -f json
```

### Use opencli browser to manually view TikTok Studio data

When you need to troubleshoot TikTok data collection issues, you can use browser control commands to operate step by step:

```bash
# 1. Open TikTok Studio
opencli browser open "https://www.tiktok.com/tiktokstudio"

# 2. Check the page status (find the index number N of the Analytics button)
opencli browser state 2>&1 | grep -E "Analytics|Content|Viewers|Followers"

# 3. Click the Analytics button
opencli browser click N

# 4. Wait for loading and then take a screenshot
sleep 5 && opencli browser screenshot ~/Desktop/tiktok_overview.png

# 5. Extract the page text to see the actual data
opencli browser eval "document.querySelector('#root').innerText.substring(0, 2000)"

# 6. Click the Content / Viewers / Followers tab one by one (find the index number first)
opencli browser state 2>&1 | grep -E "\[.*\].*Content|Viewers|Followers"
opencli browser click <Contentindex>
opencli browser click <Viewersindex>
opencli browser click <Followersindex>

# 7. View the Posts management page
opencli browser open "https://www.tiktok.com/tiktokstudio/content"
sleep 5 && opencli browser eval "document.querySelector('#root').innerText.substring(0, 3000)"
```

### View snapshots and reports

```bash
ls -la ~/.social_uploader/analytics/default/snapshots/ | tail -5
ls -la ~/.social_uploader/analytics/default/reports/
```

### Open the HTML report in a browser

```bash
open ~/.social_uploader/analytics/default/reports/2026-04-14_report.html   # macOS
```

### Test analysis modules individually

```python
from social_uploader.analytics.store import load_latest_snapshot
from social_uploader.analytics.analyzer import analyze
snapshot = load_latest_snapshot(account="default")
result = analyze(snapshot)
```

### Test AI recommendations

```python
from social_uploader.analytics.advisor import generate_advice
advice = generate_advice(analysis_result)
```

---

## 9. OpenCLI adapter output structure

The `creator-stats` adapter on each platform returns a unified `[{metric, value, trend}, ...]` format, and the data area is divided by the `---` delimiter.

### YouTube adapter output (auto-detection of channels + DOM parsing)

```
┌─ User profile ────────────────────────────────────
│  username (username)        bill s（or channel ID）
├─ Overview (past 28 sky) ───────────────────────
│  views (views)         145
│  Viewing time (hours） (watch_time_hours)  0.1
│  Number of subscribers (subscribers)   +1
├─ Top Videos (N videos) ──────────────────────
│  🎬 Public video title          views=X comments=Y   date
│  ⏰ Publish videos regularly          views=0 comments=0   date
│  📝 Draft video              views=0 comments=0
│  🔒 Private video              views=X comments=Y   date
│  🔗 Unlist video        views=X comments=Y   date
└──────────────────────────────────────────────
```

### TikTok adapter output (4-tab full size)

```
┌─ User profile ────────────────────────────────────
│  username (username)        spicychicke2
│  Number of fans (followers)       0
│  Number of followers (following)       0
│  Total number of likes (hearts)        0
│  Number of videos (videos)          0
├─ Overview Overview (past 7 sky) ───────────────────
│  Video views (views)      0          (--)
│  Profile views            0          (--)
│  Likes (likes)            0          (--)
│  Comments (comments)      0          (--)
│  Shares (shares)          0          (--)
│  Est. rewards             $0         (0.0%)
├─ content Content ───────────────────────────────
│  Popular posts                 None yet / Video ranking list
├─ audience Viewers (past 7 sky) ───────────────────
│  Total viewers            0          (--)
│  New viewers              0          (--)
│  Gender distribution / Age distribution / Regional distribution (required 100 viewer）
├─ fan Followers ─────────────────────────────
│  Total followers          0          All time
│  Net followers            0          (--)
│  fan gender / age / Region (required 100 fan）
├─ Top Videos (N videos) ──────────────────────
│  🎬 video title              views=X likes=Y comments=Z   date
│  🔒 Private video title          views=X likes=Y comments=Z   date
└──────────────────────────────────────────────
```

### Instagram adapter output

```
┌─ User profile ────────────────────────────────────
│  Number of fans / Number of followers / Number of posts / username / Account type
├─ Summary of recent content (N posts) ─────────────────────
│  Total likes / Total comments / total plays / Number of videos / Number of pictures / interaction rate
├─ Single post data (top 10) ─────────────────────────
│  🎬 video title    likes=X comments=Y plays=Z   date
└──────────────────────────────────────────────
```

### How collector.py digests adapter output

`collector.py`'s `_normalize_flat_output()` routes data by delimiter:

| separator value keyword | mapped to section | data destination |
|---|---|---|
| `Top Video` / `Single Post` / `Top Content` | `videos` | `video_metrics[]` |
| `Recent Content` / `content` | `summary` | `account_metrics{}` |
| `Analytics Data` / `analytics` | `analytics` | `account_metrics{}` |
| `Overview` | `analytics` | `account_metrics{}` |
| `Viewers` | `analytics` | `account_metrics{}` |
| `Followers` | `analytics` | `account_metrics{}` |
| `Content` | `summary` | `account_metrics{}` |

The `value` format (`views=X likes=Y comments=Z`) of the video line is extracted through the regular `(\w+)=(\d+)`.

---

## 10. Expand new platforms

Create the `creator-stats.js` adapter under `~/.opencli/clis/<new-platform>/`, return the `[{metric, value, trend}, ...]` format, and then execute:

```bash
<CLI> monitor config --new platform true
```

---

## 11. Key file index

| Files | Roles |
|------|------|
| `src/social_uploader/analytics/__init__.py` | Module entrance |
| `src/social_uploader/analytics/collector.py` | Collection arrangement (calling opencli) |
| `src/social_uploader/analytics/analyzer.py` | Rule Analysis Engine |
| `src/social_uploader/analytics/advisor.py` | AI suggestion generation |
| `src/social_uploader/analytics/reporter.py` | Report Rendering |
| `src/social_uploader/analytics/store.py` | Data Access |
| `src/social_uploader/analytics/templates/report.md` | Markdown template |
| `src/social_uploader/analytics/templates/report.html` | HTML Template |
| `src/social_uploader/account_manager.py` | Chrome Profile Management |
| `src/social_uploader/tools/browser_manager.py` | Browser Management |
| `src/social_uploader/command_entry.py` | CLI Portal |
| `~/.social_uploader/analytics/accounts_map.json` | Platform switch configuration |
| `~/.opencli/clis/tiktok/creator-stats.js` | TikTok 4-tab full collection adapter |
| `~/.opencli/clis/instagram/creator-stats.js` | Instagram REST API Collection Adapter |
| `~/.opencli/clis/youtube/creator-stats.js` | YouTube automatic channel detection + DOM parsing collection adapter |
