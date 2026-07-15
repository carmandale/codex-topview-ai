# social-uploader

CLI for uploading videos to TikTok, Instagram, and YouTube through a local Chrome debug session.

It uses [DrissionPage](https://drissionpage.cn) browser automation and never handles platform passwords.

---

## Quick installation

### macOS

```bash
cd <project-root>/tools/social-uploader
bash scripts/install.sh
```

### Windows

```cmd
cd <project-root>\tools\social-uploader
scripts\install.bat
```

> **Windows Note**: The offline wheel package is the macOS version. When installing Windows, you need to be online to download the dependencies (the script will automatically download it from PyPI).

<details>
<summary>Manual installation (such as one-click script error)</summary>

**macOS:**
```bash
cd <project-root>/tools/social-uploader
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install ./DrissionPage
.venv/bin/pip install -e .
.venv/bin/social-upload --help
```

**Windows:**
```cmd
cd <project-root>\tools\social-uploader
python -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install .\DrissionPage
.venv\Scripts\pip install -e .
.venv\Scripts\social-upload --help
```
</details>

## Preconditions

1. **Google Chrome** browser is installed
2. **Python 3.9+**
   - macOS: `brew install python@3.10` or download from python.org
   - Windows: Download from [python.org](https://www.python.org/downloads/) and check **Add Python to PATH** during installation.

## Usage

### Step 1: Enable Chrome debugging mode

| System | Commands |
|------|------|
| macOS | `bash scripts/start_chrome_debug.sh` |
| Windows | Double-click `scripts\start_chrome_debug.bat` or execute it from the command line |

### Step 2: Manually log in to the target platform in the browser

This tool does not touch any account password and requires you to log in first.

### Step 3: Upload the video

**macOS:**
```bash
# TikTok
.venv/bin/social-upload tiktok --video "video.mp4" --title "title" --description "describe"

# TikTok scheduled release
.venv/bin/social-upload tiktok --video "video.mp4" --title "title" --description "describe" --schedule "2026-04-10 15:00"

# Instagram
.venv/bin/social-upload instagram --video "video.mp4" --caption "Copywriting #hashtag"

# YouTube
.venv/bin/social-upload youtube --video "video.mp4" --title "title" --description "describe"

# YouTube Scheduled + Unlisted
.venv/bin/social-upload youtube --video "video.mp4" --title "title" --description "describe" --schedule "2026-04-10 15:00" --visibility unlisted

# Just fill in the form without publishing
.venv/bin/social-upload tiktok --video "video.mp4" --title "title" --description "describe" --no-publish
```

**Windows:**
```cmd
:: TikTok
.venv\Scripts\social-upload tiktok --video "video.mp4" --title "title" --description "describe"

:: TikTok scheduled release
.venv\Scripts\social-upload tiktok --video "video.mp4" --title "title" --description "describe" --schedule "2026-04-10 15:00"

:: Instagram
.venv\Scripts\social-upload instagram --video "video.mp4" --caption "Copywriting #hashtag"

:: YouTube
.venv\Scripts\social-upload youtube --video "video.mp4" --title "title" --description "describe"

:: YouTube Scheduled + Unlisted
.venv\Scripts\social-upload youtube --video "video.mp4" --title "title" --description "describe" --schedule "2026-04-10 15:00" --visibility unlisted

:: Just fill in the form without publishing
.venv\Scripts\social-upload tiktok --video "video.mp4" --title "title" --description "describe" --no-publish
```

> **Scheduled release instructions**: `--schedule` uses the platform's built-in scheduled release function (the video is uploaded immediately and automatically published at the set time), not a system-level scheduled task.

## Used in Cursor (Skill mode)

This project contains the Cursor Agent Skill definition (`.cursor/skills/social-media-uploader/SKILL.md`).

After opening this project in Cursor, say directly to the AI:

> "Help me upload the vlog.mp4 on my desktop to TikTok with the title 'Weekend Store Visit'"

AI will automatically detect the operating system and call the corresponding command to complete the upload.

## Project structure

```
Project root directory/
├── pyproject.toml                      # Package definition + dependencies
├── README.md                           # this document
│
├── src/social_uploader/                # [Official code] CLI package
│   ├── command_entry.py                # Command entrance (receive instructions, distribute tasks)
│   ├── repair_engine.py              # Logging + Auto-repair engine
│   ├── error_classifier.py            # Error classification (determining whether the AI ​​can teach itself)
│   ├── button_config.json             # Button configuration table (only change this here when repairing)
│   ├── state_patterns.json            # Status signal + interactive recipe (recipe)
│   ├── profiles/
│   │   └── default.json               # Default upload configuration
│   ├── uploaders/                      # Upload logic for each platform
│   │   ├── __init__.py                 # Public utility functions (should_skip, etc.)
│   │   ├── video_check.py              # Video file verification + login prompt
│   │   ├── tiktok.py
│   │   ├── instagram.py
│   │   └── youtube.py
│   └── tools/
│       ├── browser_manager.py          # Browser management (connection + new window + clear pop-up window)
│       ├── element_finder.py           # Find button + add button
│       ├── upload_profile.py           # Upload configuration loading, merging and constraint verification
│       ├── pattern_checker.py          # Status signal detection (success/failure/pop-up window)
│       ├── recipe_runner.py            # Interactive recipe executor (three layers of security)
│       ├── agentql_client.py            # AgentQL AI semantic element discovery (Tier 2b)
│       └── dom_heuristic.py           # Heuristic DOM element discovery (Tier 2a)
│
├── scripts/                            # All scripts
│   ├── install.sh                      # macOS one-click installation
│   ├── install.bat                     # Windows one-click installation
│   ├── start_chrome_debug.sh           # macOS Chrome debug mode starts
│   ├── start_chrome_debug.bat          # Windows Chrome debug mode starts
│   ├── verify_code.py                  # Automated verification after code modification (P0+P1 check)
│   └── test_logic.py                   # Full-link simulation testing (117 checkpoints)
│
├── docs/                               # document
│   ├── Project planning document.md                   # Project planning and structure description
│   └── Automatic repair mechanism description.md               # Automatic repair principle (popular version)
│
├── DrissionPage/                       # DrissionPage library source code (only for dependency installation, do not run scripts here)
│   ├── DrissionPage/                   # Library ontology
│   └── setup.py
│
├── .cursor/rules/                      # AI Agent global rules
│   └── task-orchestration.mdc          # Task scheduling (intent routing + multi-skill orchestration)
│
└── .cursor/skills/                     # AI Agent Commands
    ├── social-media-uploader/          # Social Media Upload Skill
    │   ├── SKILL.md
    │   ├── examples.md
    │   ├── troubleshooting.md
    │   └── platforms/                  # Description of configuration items for each platform
    ├── auto-repair/                    # Automatic repair skill
    │   └── SKILL.md
    ├── code-rules/                     # Code Standard Skill
    │   └── SKILL.md
    ├── code-review/                    # Verification Skill after code modification
    │   └── SKILL.md
    └── topview-skill/                  # AI content generation skill (video/picture/dubbing)
        ├── SKILL.md
        └── scripts/                    # Topview API script
```

## Troubleshooting

| Questions | macOS | Windows |
|------|-------|---------|
| Python not found | `brew install python@3.10` | Download from python.org, check Add to PATH during installation |
| Chrome connection failed | `bash scripts/start_chrome_debug.sh` | Double-click `scripts\start_chrome_debug.bat` |
| Dependency installation failed | Check the network, or manually `pip install ./DrissionPage` | Make sure you are connected to the Internet, Windows needs to install dependencies online |
| Upload button not found | Platform UI may be updated, use `social-upload suggest-selectors` to fix | Same as left |
| `python3` command does not exist (Windows) | — | Windows uses `python` instead of `python3` |
