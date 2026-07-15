# Instagram upload configuration items

After AI reads this file, it collects information from the user according to the "Implemented" section.

## CLI required parameters (must be collected)

| Parameters | Description | Collection method | Limitations |
|------|------|---------|------|
| `--video` | Video file path | Dialogue question | mp4/mov/avi/mkv/webm/flv/wmv/3gp |
| `--caption` | Publish copy | If the dialogue asks, if the user does not give it, it will be extracted from the file name | ≤2200 characters |

Note: Instagram does not have separate `--title` and `--description`, only `--caption`.
If the user provides title and description, AI should be spliced ​​into `title + "\n\n" + description` as caption.

## Implemented profile configuration items (you can ask the user)

### Sync to dynamic stream `instagram.share_to_feed`

- **Collection method**: AskQuestion (only when the user actively mentions it)
- **Default**: `true` (sync to dynamic stream)
- **Use the default if the user doesn't mention it, don't ask proactively**

AskQuestion template:
```json
{
  "id": "instagram_share_to_feed",
  "prompt": "Synchronize to dynamic stream?",
  "options": [
    { "id": "yes", "label": "Yes (default)" },
    { "id": "no", "label": "No, published as Reel only" }
  ]
}
```

Mapping: `yes` → `"share_to_feed": true`, `no` → `"share_to_feed": false`

## CLI optional parameters

| Parameters | Description |
|------|------|
| `--no-publish` | Just fill in the form without posting |
| `--resume-from` | Resume from breakpoint |
| `--profile` | Configuration file path |

## Generated profile JSON example

Generated when the user says "Upload to Instagram, not synced to feed":
```json
{
  "instagram": {
    "share_to_feed": false
  }
}
```

When the user says nothing (all defaults are used): do not pass `--profile`, and the code automatically uses default.json.

## Unsupported features

- `schedule` — **Scheduled posting: Instagram web version does not support scheduled posting function. ** If the user requests scheduled posting on Instagram, they should be clearly informed that "the web version of Instagram does not support scheduled posting, and the video will be posted immediately." This is a platform limitation, not a problem with this tool.

## Under planning (the code has not been implemented yet, don’t ask users)

- `location` — geolocation tag
