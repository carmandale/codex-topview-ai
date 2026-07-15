# Automated uploading of social media videos — project planning document

> Last updated: 2026-04-05
> Current version: v0.2.0

---

## 1. What is the project?

A command line tool that connects to your locally opened Chrome browser and automatically completes all operations of uploading videos to TikTok / Instagram / YouTube (fill in the title, fill in the description, and click publish).

Core features:
- **No password**: Use your own logged-in browser, the tool does not touch any account information
- **AI self-healing**: When the button cannot be found due to platform revision, AI can automatically analyze the page, repair the configuration, and retry the upload.
- **New window isolation**: Each upload is performed in a separate new window and does not affect the browser tab you are using.

---

## 2. Project file structure

```
Project root directory/
├── pyproject.toml                       # Python package configuration (dependencies, entry commands)
├── README.md                            # Project Description
├── .venv/                               # Python virtual environment
│
├── src/social_uploader/                 # 【Core code】
│   ├── command_entry.py                 # ① Command entrance: receives user instructions and distributes them to the corresponding platform
│   ├── button_config.json               # ② Button configuration table: Record how to find the buttons for each platform
│   ├── error_classifier.py              # ③ Error classifier: determine error type and processing method
│   ├── repair_engine.py                # ④ Log and repair engine: record logs + take snapshots + recommend repairs
│   │
│   ├── uploaders/                       # 【Upload script】
│   │   ├── video_check.py               # ⑤ Video verification: Check whether the file is legal
│   │   ├── tiktok.py                    # ⑥The whole TikTok upload process
│   │   ├── instagram.py                 # ⑦ Full Instagram upload process
│   │   └── youtube.py                   # ⑧Full YouTube upload process
│   │
│   └── tools/                           # 【Toolbox】
│       ├── browser_manager.py           # ⑨ Browser management: connect Chrome, open new windows, clear pop-up windows
│       ├── element_finder.py            # ⑩ Double-track element search: Track A quick selector → Track B AI semantic positioning
│       ├── ai_locator.py             # ⑪ AI Navigator: UltimateLocator (page warm-up + semantic query + visual verification)
│       ├── platform_semantics.py       # ⑫ Platform semantic configuration: container + target description of each button
│       ├── agentql_client.py            # ⑬ AgentQL API call: REST API semantic positioning + attribute extraction
│       ├── pattern_checker.py          # ⑭ Status mode check: page status detection + pop-up window cleaning
│       ├── recipe_runner.py            # ⑮ Interactive recipe execution: complex processes such as scheduled release and visibility
│       └── dom_heuristic.py           # ⑯ DOM heuristic discovery: semantic keyword search for alternative elements
│
├── scripts/                             # helper script
│   ├── install.sh / install.bat         # One click installation
│   └── start_chrome_debug.sh / .bat     # Enable Chrome debugging mode
│
├── docs/                                # document
│   ├── Project planning document.md                    # this document
│   └── Automatic repair mechanism description.md                # A layman’s explanation of the repair mechanism
│
├── tests/                               # test material
│   ├── sample_video.mp4
│   └── sample_cover.jpg
│
├── vendor_wheels/                       # Offline installation package (for use when there is no network)
│
└── .cursor/skills/social-media-uploader/ # AI Agent Operation Manual
    ├── SKILL.md                          # Agent’s complete operation guide
    ├── examples.md                       # Usage example
    └── troubleshooting.md                # Troubleshooting
```

---

## 3. What is responsible for each file (detailed explanation)

### ① `command_entry.py` — command entry

**What to do**: Receive the commands entered by the user in the terminal and distribute them to the corresponding upload script according to the platform name.

**Included subcommands**:
| Subcommand | Function |
|--------|------|
| `social-upload tiktok --video ... --title ... --description ...` | Upload to TikTok |
| `social-upload instagram --video ... --caption ...` | Upload to Instagram |
| `social-upload youtube --video ... --title ... --description ...` | Upload to YouTube |
| `social-upload diag` | Extract the condensed DOM of the current page (for debugging) |
| `social-upload suggest-selectors --run-id xxx` | Recommended repair commands from failed snapshots |
| `social-upload fix-selector --target xxx --key xxx --selector "..."` | Add a new button to the button configuration table |

**Calling relationship**: User → `command_entry.py` → `uploaders/tiktok.py` or `instagram.py` or `youtube.py`

---

### ② `button_config.json` — button configuration table

**What to do**: Record "how to find" each key button on each platform. This is the only file that will be modified during AI repair.

**Structure Example**:
```json
{
  "tiktok": {
    "post_button": ["@data-e2e=upload-btn", "text:publish", "text:Post"],
    "file_input": ["tag:input@type=file"]
  },
  "youtube": {
    "upload_icon": ["@id=upload-icon", "@aria-label=Upload video"],
    "post_button": ["#done-button", "text:publish"]
  }
}
```

Each button corresponds to a list. There are multiple "finding methods" in the list. The script will try them from front to back and use the first one found.

**Who reads it**: `element_finder.py` reads → leaves it to the upload script to use
**Who changed it**: `add_selector()` function of `element_finder.py` (called by `fix-selector` command)

---

### ③ `error_classifier.py` — Error Classifier

**What to do**: Define how to handle each error.

```
selector_not_found  →  AI Fix it yourself（agent_fix）
login_required      →  Notify users to log in（notify_user）
timeout             →  Wait for a while and try again（wait_retry）
unknown             →  tell user（escalate_user）
```

**Who uses it**: Agent determines through the process in SKILL.md. Currently, Agent only handles `selector_not_found` independently, other types notify the user.

---

### ④ `repair_engine.py` — Logging and repair engine ⭐ The core of AI repair

This is the most important file of the entire automatic repair mechanism. It is responsible for three things:

**(A) Record the execution log of each step**

The upload script calls `log_step()` after each step:
```
success → {"step":"login","status":"ok"}           Output to stderr
fail → {"step":"publish","status":"fail","error":"selector_not_found"}
```
At the same time, output a readable terminal log such as `✅ [login] complete` or `❌ [publish] failed`.

**(B) "Take snapshot" + write log file on failure**

When the button is not found, the `report_failure()` function does three things:
1. Run a JS script to extract information about all interactive elements on the page ("take a snapshot")
2. Write two log files to `~/.social_uploader/`:
   - `summary.jsonl`: One-line summary (<500 words), recording which platform, which step failed, and what error
   - `detail_{run_id}.jsonl`: Detailed information (≤ 1500 words), including DOM snapshot
3. Terminal output `DIAG|run_id=xxx|platform=xxx|step=xxx|error=xxx` (alarm signal to AI)

**(C) Analyze snapshots and recommend repair commands**

The `suggest_selectors()` function is called by the `suggest-selectors` subcommand:
1. Read the DOM snapshot saved in the detail file
2. Use the `STEP_KEYWORDS` dictionary for semantic matching (such as "publish button" → find elements containing "post", "publish", "release")
3. Convert the matched elements into a directly executable `fix-selector` command and output it to AI

**Information word limit mechanism (to prevent AI context overflow)**:
| Restriction layer | What was done | How much is the limit |
|--------|---------|---------|
| JS extracts only buttons | Ignore all decoration tags, only extract button/input/a, etc. | The entire page is hundreds of KB → several KB |
| Only keep key attributes | Only keep 11 attributes such as id, class (the first 3), aria-label, etc. for each element, and only take the first 15 characters of the text | Cut it in half |
| Hard limit of total characters | `MAX_SNIPPET_CHARS = 1500`, truncated directly if exceeded | **≤ 1.5KB** |
| Hierarchical file | summary (< 500 words) + detail (≤ 1500 words), AI reads the summary first and then details as needed | Each round **~2.5KB** |
| Each round is independent | Only the latest log will be viewed for each repair, no history will be accumulated | No unlimited growth |

---

### ⑤ `uploaders/video_check.py` — Video verification

**What to do**: Check whether the video file is legal before uploading (whether the file exists, whether the format is supported, and whether the size is normal). Also provides a unified "not logged in" error prompt.

**Called by whom**: Called by tiktok.py / instagram.py / youtube.py at the beginning.

---

### ⑥⑦⑧ `uploaders/tiktok.py` / `instagram.py` / `youtube.py` — Upload script

**What to do**: Complete upload automation process for each platform. They are the code that actually operates the browser.

**Internal Process (Take TikTok as an example)**:
```
Verification video → Connect browser → Open upload page → Check login status
→ Clear pop-ups → Inject video files → Wait for upload to complete
→ Fill in title and description → Waiting for copyright check
→ Click to publish → Waiting for confirmation of successful release
```

**After each step is executed**:
- Success → Call `log_step("step_name", "ok")`
- Failure → Call `log_step("step_name", "fail", error="error_type")`
- The button cannot be found → additionally call `report_failure()` to take a snapshot and write a log

**How ​​to find the button**: Instead of writing it directly, call `find_element(page, "tiktok", "post_button")` of `element_finder.py`, and the latter goes to `button_config.json` to check the button list.

---

### ⑨ `tools/browser_manager.py` — Browser management

**do what**:
- `connect_browser()`: Connect to the local Chrome debugging port (9222), **open a new independent window** to perform the task
- `dismiss_interfering_overlays()`: Clean up distracting pop-ups on the page (browser extensions, notifications, etc.)
- `cleanup_tabs()`: Close the task window after the task is completed and retain the user's original label
- `find_first()`: Given multiple selectors, try them in sequence and return the first element found.

**Return value**: `(ctrl, work, baseline_tab_ids, work_tab_id)`
- `ctrl`: Browser master control, used to manage tabs
- `work`: The tab where the task is located (newly opened window)
- `baseline_tab_ids`: The tab ID that existed before the connection (cannot be closed)
- `work_tab_id`: ID of the task tab

---

### ⑩ `tools/element_finder.py` — Find button

**do what**:
- `find_element(page, "tiktok", "post_button")`: Go to `button_config.json` to check all the "finding methods" of tiktok.post_button, try them one by one, and return the found elements.
- `add_selector("tiktok", "post_button", "new_selector")`: insert the new selector at the front of the configuration table (called by `fix-selector`).
- `load_selectors("tiktok")`: Read `button_config.json` (with cache, read only once)

---

## 4. Complete information flow: from uploading to AI repair

### 4.1 Normal upload process (no errors)

```
User input command
    │
    ▼
① command_entry.py Receive commands and generate run_id，Distribute to corresponding platforms
    │
    ▼
⑤ video_check.py Check video file legality
    │
    ▼
⑨ browser_manager.py connect Chrome，Open a new window
    │
    ▼
⑥ tiktok.py（or⑦⑧）Start uploading steps：
    │
    │   Called at every step ④ repair_engine.py of log_step() Record results
    │   Called when finding the button ⑩ element_finder.py → read ② button_config.json
    │
    ▼
Upload successful → Close task window → return exit(0)
```

### 4.2 AI automatic repair process when the button cannot be found

This is the core mechanism of the entire project. When the platform changes and the button cannot be found:

```
Phase 1: The script finds the problem and reports it
═══════════════════════════

⑥ tiktok.py call ⑩ element_finder.py try to find"publish button"
    │
    │  element_finder go ② button_config.json Check all"Find a way"
    │  → None found
    │
    ▼
⑥ tiktok.py call ④ repair_engine.py of report_failure()
    │
    │  report_failure() Three things were done internally：
    │  ├─ 1. run JS，Extract all button information on the page（"Take a snapshot"，≤1500Character）
    │  ├─ 2. Write summary.jsonl（500word summary）+ detail_{run_id}.jsonl（With snapshot）
    │  └─ 3. Terminal output DIAG|run_id=abc12|platform=tiktok|step=publish|error=selector_not_found
    │
    ▼
script exit（exit 1），terminal display：
    ❌ [publish] fail — selector_not_found
    DIAG|run_id=abc12|platform=tiktok|step=publish|error=selector_not_found


second stage：AI Read key information ⭐ AI intervention point
═══════════════════════════════════

AI（Cursor Agent / OpenClaw）See the terminal output DIAG| OK
    │
    │  Step 1: Read the abstract and determine the type of error
    │  run: tail -1 ~/.social_uploader/summary.jsonl
    │  get: {"run_id":"abc12","platform":"tiktok","failed_at":"publish","error":"selector_not_found",...}
    │  → The judgment is selector_not_found → Can be repaired automatically
    │
    │  Step Two: Get Repair Suggestions
    │  run: social-upload suggest-selectors --run-id abc12
    │
    ▼
④ repair_engine.py of suggest_selectors() function is called：
    │
    │  1. read detail_abc12.jsonl saved in DOM Snapshot
    │  2. use STEP_KEYWORDS Dictionary for semantic matching：
    │     "publish" step → Find contains "post"、"release"、"submit" elements of
    │  3. Convert matched elements into repair commands
    │
    ▼
Terminal output（~200Character，AI Just look at these）：
    STEP: post_button
    PLATFORM: tiktok
    RUN_ONE:
      1. social-upload fix-selector --target tiktok --key post_button --selector "@data-e2e=publish_btn"
      2. social-upload fix-selector --target tiktok --key post_button --selector "text:Post video"


The third stage：AI Perform repair ⭐ AI Modification point
═══════════════════════════════

AI Copy No. 1 command to run：
    social-upload fix-selector --target tiktok --key post_button --selector "@data-e2e=publish_btn"
    │
    ▼
① command_entry.py route to ⑩ element_finder.py of add_selector() function
    │
    │  add_selector() things to do：
    │  1. read ② button_config.json
    │  2. exist tiktok.post_button Insert at the front of the list "@data-e2e=publish_btn"
    │  3. write back ② button_config.json
    │
    ▼
② button_config.json was modified (this is the only file that was modified）：
    "post_button": ["@data-e2e=publish_btn", ...The original way to find...]
                     ↑ The newly added ones are listed first and will be used first next time.


Stage 4：AI Retry from breakpoint
═══════════════════════

AI run:
    social-upload tiktok --video "..." --title "..." --description "..." --resume-from publish
    │
    ▼
⑥ tiktok.py Skip completed steps from publish Step start
    │
    │  try to find"publish button"→ ⑩ element_finder.py → ② button_config.json
    │  → The first one was just added "@data-e2e=publish_btn" → Found it！
    │
    ▼
Upload successful 🎉
```

### 4.3 Constraint rules for AI repair

| Rules | Description |
|------|------|
| **Zero Code** | AI only runs commands throughout the process, without writing code or directly editing files |
| **Only change one file** | Only change `button_config.json`, the Python code does not change a line |
| **Up to 3 rounds** | Repair failed 3 times in a row → Stop, notify user |
| **Each round is independent** | Only the latest round of logs will be viewed for each repair, and the context will not be accumulated |
| **Each round ~2.5KB** | summary(500 words) + detail(1500 words) + repair output(500 words) |

---

## 5. Call relationship diagram between files

```
user
 │
 ▼
command_entry.py ─────────────────────────────────────┐
 │                                                     │
 ├─→ uploaders/tiktok.py ──┐                           │
 ├─→ uploaders/instagram.py ├─→ video_check.py         │
 └─→ uploaders/youtube.py ─┘                           │
       │        │        │                              │
       │        │        └─→ repair_engine.py          │
       │        │             │ log_step()              │
       │        │             │ report_failure()        │
       │        │             │   ├─ Write summary.jsonl   │
       │        │             │   ├─ Write detail.jsonl    │
       │        │             │   └─ output DIAG|         │
       │        │             │                         │
       │        │             └─→ suggest_selectors()  ←┤ (suggest-selectors Order)
       │        │                  read detail → Recommended fix  │
       │        │                                       │
       │        └─→ element_finder.py ─────────────────→┤ (fix-selector Order)
       │             │ find_element()                    │  add_selector()
       │             │   read button_config.json           │  Write button_config.json
       │             │                                   │
       │             └─→ browser_manager.py              │
       │                  connect_browser()              │
       │                  find_first()                   │
       │                  dismiss_overlays()             │
       │                                                │
       └─→ error_classifier.py                          │
            classify_error()                            │
            is_agent_fixable()                          │
                                                        │
AI Agent ←── See DIAG| ──→ run suggest-selectors ────┘
         └──────────────→ run fix-selector ────────────┘
         └──────────────→ run --resume-from Try again
```

---

## 6. Safety principles

1. **Never touch user credentials** — No account or password saved, entered, or transmitted
2. **Login is completed by the user** — The tool is only responsible for uploading, and the login process is completed manually by the user
3. **Credential Denial Mechanism** — The Agent must refuse to use a password provided by the user
4. **Terminate without logging in** — Output a security prompt and exit(1) when no logging in is detected
5. **New window isolation** — Each task is performed in a newly opened independent window, without affecting the user's existing tabs

---

## 7. CLI command specifications

### 7.1 Installation method

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

### 7.2 Command format

```bash
# upload
social-upload tiktok    --video "path" --title "title" --description "describe" [--cover "cover"] [--no-publish]
social-upload instagram --video "path" --caption "copywriting" [--no-publish]
social-upload youtube   --video "path" --title "title" --description "describe" [--no-publish]

# Breakpoint recovery
social-upload tiktok --video "..." --title "..." --description "..." --resume-from publish

# Diagnosis and repair
social-upload diag [--area "CSS selector"]
social-upload suggest-selectors --run-id {run_id}
social-upload fix-selector --target {platform} --key {Button name} --selector "Find a way"
```

### 7.3 Exit codes

| Exit code | Meaning |
|--------|------|
| `0` | Success |
| `1` | Failed |

### 7.4 Terminal output format

**For human viewing (stdout)**:
```
10:30:01 [INFO]   ✅ [login] Finish
10:30:05 [INFO]   ✅ [file_inject] Finish
10:30:12 [ERROR]  ❌ [publish] fail — selector_not_found
DIAG|run_id=abc12345|platform=tiktok|step=publish|error=selector_not_found
```

**Parsed by AI (stderr)**:
```json
{"step":"login","status":"ok"}
{"step":"file_inject","status":"ok"}
{"step":"publish","status":"fail","error":"selector_not_found","detail":"post_button not found"}
```

---

## 8. Upload steps for each platform

### TikTok（`uploaders/tiktok.py`）

```
Video verification → Connect browser → Open upload page → Login detection
→ Clear pop-ups → Inject video files → Wait for upload to complete (including error detection）
→ Fill in the title+describe → Set cover (optional)）→ scroll to bottom → Waiting for copyright check
→ [no_publish examine] → Click to publish → Handle secondary confirmation → Waiting for confirmation of successful release
```

### Instagram（`uploaders/instagram.py`）

```
Video verification → Connect browser → Open home page → Login detection
→ Close distracting pop-ups → Click"new post"button → Inject video files
→ Waiting for cutting interface → Select original scale
→ Next step (crop→filter）→ Next step (filter→Fill in information）
→ Fill in the copy → [no_publish examine] → Click to share → Wait for publishing to complete
```

### YouTube（`uploaders/youtube.py`）

```
Video verification → Connect browser → Open YouTube Studio → Login detection
→ Close remaining pop-ups → Call up the upload pop-up window (shortcut icon/Create menu downgrade）
→ Inject video files → Fill in the title+describe
→ set up"Not for children"（5strategy rotation+verify）→ Cycle through and click Next×3
→ [no_publish examine] → Set public visibility → Click to publish → Waiting for confirmation of successful release
```

---

## 9. Dependence

### Python packages

```toml
[project]
name = "social-uploader"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = ["DrissionPage>=4.0"]
```

### System requirements

- macOS or Windows + Google Chrome
- Python >= 3.9
- Chrome starts in debug mode (port 9222)
- The user has manually logged into the target platform in the browser

---

## 10. Location of AI Agent Operation Manual

The complete instructions for the Agent are at `.cursor/skills/social-media-uploader/SKILL.md`, which tells the Agent:
- When to execute the upload command
- How to initiate repair when you see `DIAG|`
- Which commands to run during repair and in what order
- How many rounds can be repaired at most and when will it be given up? Notify the user

This file itself is not code, it is an "operation manual" for AI.
