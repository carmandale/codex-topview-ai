# Description of the automatic repair mechanism (version for human viewing)

## What's this?

When TikTok / Instagram / YouTube updates the web interface and the upload script cannot find the button,
The system will automatically try to fix it, **no need for people to change the code**.

---

## In plain English, the repair process consists of three steps:

### Step 1: The script finds "button not found"

For example, TikTok changed the code of the publish button from `post_video_button` to `publish_btn`.

The script looks for the old name → Not Found → The script does three things:
1. **Take snapshot**: Write down the information of all buttons on the current page (like taking a photo)
2. **Take notes**: Write "Which button am I looking for" (`selectors_tried`) into the log, so that you will know which button to match when analyzing the snapshot later?
3. **Shout**: Output a line in the terminal `DIAG|...`, which means "I have a problem here"

### Step 2: The AI ​​sees an error and asks the system "How to fix it"

The AI ​​runs a command:
```
social-upload suggest-selectors --run-id xxx
```

The system automatically does these things:
1. Pull out the snapshot you just took
2. Find "Which button am I looking for" from the log (`selectors_tried`, such as `post_button`)
3. Look at which button in the snapshot looks like the "publish button" (for example, it says "publish" on it)
4. Translate the found button information** into a format that can be used by scripts**
5. Directly output a repair command that can be copied and run

### Step 3: AI runs the repair command and tries again

```
social-upload fix-selector --target tiktok --key post_button --selector "@data-e2e=publish_btn"
social-upload tiktok --video "..." --title "..." --resume-from publish
```

The repair command will write the new button name into the configuration file, and then the script will continue running from the breakpoint.

---

## What documents are involved? What are each doing?

```
src/social_uploader/
│
├── button_config.json      ← 📋 "Address book"：Record how to find each button on each platform
│                              The only file that was changed during the repair
│                              You can also change this manually.
│
├── tools/
│   ├── element_finder.py   ← 🔍 "The person looking for the button"（Dual-track parallel）：
│   │                          - find_element(): track A Quick selector → track B AI Semantic positioning
│   │                          - find_and_click(): Find and click, with post-click status check
│   │                          - add_selector(): Add a new button name to the address book (for CLI for repair）
│   │
│   ├── ai_locator.py     ← 🧠 "AI brain"（track B core）：
│   │                          - UltimateLocator: Page warm-up + Structured semantic query + Visual verification
│   │                          - call agentql_client.py of API，Do not write back results
│   │
│   └── platform_semantics.py ← 📖 "semantic dictionary"：
│                                Structured description of every button for every platform（container + target）
│                                for UltimateLocator improve AI Positioning accuracy
│
├── repair_engine.py       ← 📸 "The person who takes the photo + analyzes the photo"：
│                              - report_failure(): Take page snapshots and write logs when errors occur (including selectors_tried）
│                              - suggest_selectors(): read selectors_tried → Analyze Snapshot → Recommended fixes
│                              - get_dom_snippet(): How to take a snapshot
│                              - STEP_KEYWORDS: "What does the publish button look like?"knowledge base (using selectors_tried Find）
│
├── error_classifier.py     ← 🏷️ "Classification tags"：
│                              Determine whether this error is AI Can be repaired by oneself，
│                              Users still need to be notified
│
└── command_entry.py        ← 🚪 "receptionist"：
                               - suggest-selectors Command entry
                               - fix-selector Command entry
```

---

## If you want to change something, where should you change it?

### Scenario 1: A new button has been added to the platform and you want to add it in advance

Change **`button_config.json`** and add one under the corresponding platform:

```json
"tiktok": {
    "New button name": ["How to find it"]
}
```

### Scenario 2: The automatically recommended fix is ​​inaccurate and you want to adjust the judgment of "what does the publish button look like"

Change the `STEP_KEYWORDS` dictionary in **`repair_engine.py`**:

```python
STEP_KEYWORDS = {
    "post_button": ["post", "publish", "release", "submit"],  ← Add keywords
    ...
}
```

Meaning: If the text/attributes of a button on the page contain these words, it is considered to be a publish button.

### Scenario 3: Want to add a new error type

Change **`error_classifier.py`**:

```python
ERROR_TYPES = {
    "new error name": "agent_fix",      # AI fixes itself
    "another error": "notify_user",  # Notify user
}
```

### Scenario 4: Want to change the output format of the repair command

Change the end of the `suggest_selectors()` function in **`repair_engine.py`** and splice the output text there.

### Scenario 5: Want to change the logic of "how to write the new button name into the configuration"

Change the `add_selector()` function in **`tools/element_finder.py`**.

---

## One picture of the entire process

```
TikTok/Instagram/YouTube Changed the interface
         │
         ▼
button_config.json the old button name in → track A not found
         │
         ▼
element_finder.py Automatically switch to track B（AI Semantic positioning）
         │
         ├─→ ai_locator.py Warm up page + Structured semantic query
         ├─→ platform_semantics.py supply container + target constraint
         └─→ agentql_client.py call AgentQL API position
                │
         ┌──── ▼ ────┐
         │ track B success │ → Return the element directly without writing back the configuration
         └──── │ ────┘
               │
         ┌──── ▼ ────┐
         │ track B fail │ → Enter DIAG Repair process
         └──── │ ────┘
               │
               ▼
tiktok.py call repair_engine.py of report_failure()
         │
         ├─→ Take a page snapshot（get_dom_snippet）
         ├─→ Write log file to ~/.social_uploader/
         └─→ Terminal output DIAG| Signal
                │
                ▼
         AI See DIAG|
                │
                ▼
         AI run suggest-selectors Order
                │
                ▼
         repair_engine.py Analyze Snapshot + Recommended fixes
                │
                ▼
         AI run fix-selector Order
                │
                ▼
         element_finder.py Enter the new button name button_config.json
                │
                ▼
         AI use --resume-from Try again → success！
```

## Where are the log files?

```
~/.social_uploader/
├── summary.jsonl           ← One line summary for each failure (which platform, which step, what error）
└── detail_abc12345.jsonl   ← Details of this failure (including page snapshots）
```

These files are automatically generated and do not require you to create them manually.
