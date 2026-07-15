# Usage example

## Single platform upload (default configuration)

### TikTok
```bash
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"
```

### TikTok (with cover image)
```bash
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip" --cover "/Users/xxx/cover.jpg"
```

### Instagram
```bash
.venv/bin/social-upload instagram --video "/Users/xxx/vlog.mp4" --caption "Weekend store visit 🍜 #food #vlog"
```

### YouTube
```bash
.venv/bin/social-upload youtube --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"
```

## Scheduled publishing and visibility (--schedule/--visibility)

### TikTok scheduled release
```bash
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip" --schedule "2026-04-10 15:00"
```

### Visible to TikTok friends + scheduled publishing
```bash
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip" --schedule "2026-04-10 15:00" --visibility friends
```

### YouTube scheduled releases
```bash
.venv/bin/social-upload youtube --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip" --schedule "2026-04-10 15:00"
```

### Unlisted on YouTube
```bash
.venv/bin/social-upload youtube --video "/Users/xxx/draft.mp4" --title "draft" --description "for testing" --visibility unlisted
```

### YouTube private mode
```bash
.venv/bin/social-upload youtube --video "/Users/xxx/draft.mp4" --title "draft" --description "for testing" --visibility private
```

## Use custom configuration (--profile, for complex configuration)

### YouTube for kids + tagged

First create the configuration file `kids.json`:
```json
{
  "youtube": {
    "made_for_kids": true,
    "tags": "toys, unboxing, review"
  }
}
```

Then upload (can use --visibility and --profile together):
```bash
.venv/bin/social-upload youtube --video "/Users/xxx/toy_review.mp4" --title "Toy unboxing" --description "What I unboxed today is..." --visibility unlisted --profile kids.json
```

### TikTok AI generated tags + content disclosure

```json
{
  "tiktok": {
    "ai_generated": true,
    "disclose_content": true
  }
}
```

```bash
.venv/bin/social-upload tiktok --video "/Users/xxx/ai_video.mp4" --title "AI creation" --description "AI-generated content" --schedule "2026-04-10 10:00" --profile ai_config.json
```

## Just fill in the form without publishing

```bash
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "test" --description "Test description" --no-publish
```

## Resume from breakpoint (used when AI automatically repairs)

```bash
.venv/bin/social-upload youtube --video "/Users/xxx/vlog.mp4" --title "title" --description "describe" --resume-from publish
```

## Restart the browser after switching accounts

```bash
# Terminate the old debug browser and restart with the new account
.venv/bin/social-upload restart-browser

# Restart the debug browser (macOS)
bash scripts/start_chrome_debug.sh

# Restart the debug browser (Windows)
scripts\start_chrome_debug.bat
```

## All platforms are uploaded sequentially

Execute three commands in sequence, report the results after each is completed, and then execute the next one:

```bash
# 1. TikTok
.venv/bin/social-upload tiktok --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"

# 2. Instagram
.venv/bin/social-upload instagram --video "/Users/xxx/vlog.mp4" --caption "Weekend shop visit 🍜 Record your weekend food trip"

# 3. YouTube
.venv/bin/social-upload youtube --video "/Users/xxx/vlog.mp4" --title "Weekend store visit" --description "Record your weekend food trip"
```
