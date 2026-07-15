# YouTube upload configuration items

After AI reads this file, it collects information from the user and generates profile JSON based on the "Implemented" part.

## CLI required parameters (must be collected)

| Parameters | Description | Collection method | Limitations |
|------|------|---------|------|
| `--video` | Video file path | Dialogue question | mp4/mov/avi/mkv/webm/flv/wmv/3gp |
| `--title` | Video title | Dialogue question, if the user does not give it, it will be extracted from the file name | ≤95 characters |
| `--description` | Video description | Dialogue question, reuse title if user does not provide one | ≤4900 characters |

## Implemented profile configuration items (you can ask the user)

### For children `youtube.made_for_kids`

- **Collection method**: AskQuestion
- **Default**: `false` (not for children)
- **Use the default if the user doesn't mention it, don't ask proactively**

AskQuestion template:
```json
{
  "id": "youtube_kids",
  "prompt": "Is this video intended for children?",
  "options": [
    { "id": "no", "label": "No (default)" },
    { "id": "yes", "label": "Yes, for children" }
  ]
}
```

Mapping: `yes` → `"made_for_kids": true`, `no` → `"made_for_kids": false`

### Visibility `youtube.visibility`

- **Collection method**: AskQuestion
- **Default**: `"public"`
- **Use the default if the user doesn't mention it, don't ask proactively**

AskQuestion template:
```json
{
  "id": "youtube_visibility",
  "prompt": "Video visibility settings?",
  "options": [
    { "id": "public", "label": "Public (visible to everyone, default)" },
    { "id": "unlisted", "label": "Not listed publicly (can only be viewed with a link)" },
    { "id": "private", "label": "Private (visible only to you)" }
  ]
}
```

Mapping: directly use option id as the value of `"visibility"`.

### Tag `youtube.tags`

- **Collection method**: Ask in dialogue
- **Default value**: `null` (no label set)
- **Use the default if the user doesn't mention it, don't ask proactively**
- **Format**: comma-separated string, such as `"travel,vlog,food"`

### Category `youtube.category`

- **Collection method**: Ask in dialogue
- **Default value**: `null` (no classification set)
- **Use the default if the user doesn't mention it, don't ask proactively**
- **Optional values**: Entertainment, Education, Science & Technology, People & Blogs, Music, Gaming, etc.

## CLI optional parameters

| Parameters | Description |
|------|------|
| `--no-publish` | Just fill in the form without publishing, add it when the user says "Preview" or "Don't publish" |
| `--resume-from` | Recovery from breakpoints, used when AI automatically repairs, no need to ask the user |
| `--profile` | Configuration file path, automatically passed in after AI is generated |

## Generated profile JSON example

Generated when user says "Upload to YouTube, made for kids, private, tagged travel and food":
```json
{
  "youtube": {
    "made_for_kids": true,
    "visibility": "unlisted",
    "tags": "travel, food"
  }
}
```

When the user says "Upload to YouTube, it will be published at 10 am tomorrow":
```json
{
  "youtube": {
    "schedule": "2026-04-08 10:00"
  }
}
```

When the user says nothing (all defaults are used): do not pass `--profile`, and the code automatically uses default.json.

### Regular release `youtube.schedule`

- **Collection method**: Ask in dialogue
- **Default**: `null` (for immediate release)
- **Use the default if the user doesn't mention it, don't ask proactively**
- **Format**: `"YYYY-MM-DD HH:MM"`, such as `"2026-04-08 10:00"`
- **Precondition**: Scheduled press conferences automatically set visibility to PUBLIC (public)
- **Security Gating**: If the timing setting fails, the script will abort publishing, preventing the video from being made public immediately

AskQuestion template (only used when the user actively mentions scheduled publishing):
```json
{
  "id": "youtube_schedule",
  "prompt": "YouTube scheduled release time?",
  "options": [
    { "id": "now", "label": "Publish immediately (default)" },
    { "id": "custom", "label": "Specify time (please add YYYY-MM-DD HH:MM in the conversation)" }
  ]
}
```

Mapping: `now` → no schedule, `custom` → `"schedule": "user-provided time"`

## Under planning (the code has not been implemented yet, don’t ask users)

The following functions have no corresponding fields in default.json, and the code has no processing logic.
**AI may not question users or generate configurations about these options. ** If the user actively mentions it, they should reply "This function has not been implemented yet".

- `playlist` — Playlist
- `license` — authorization type
