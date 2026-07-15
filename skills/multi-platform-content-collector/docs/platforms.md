# Platform search configuration

This document is a platform search reference for `search_all.py`. The script is responsible for candidate search, deduplication, and sorting; the Agent reads details on demand during the verification phase.

---

## Search mode

| Mode | Purpose |
|---|---|
| `--mode general` | General collection: search by user keywords, without binding prompt suffix |
| `--mode prompt` | AI work prompt word collection: additional search for suffixes such as `prompt` / `提示词` |

`search_all.py` will expand user keywords into common variations, for example `seedance 2.0` will expand to `seedance 2.0 / seedance2 / seedance2.0 / seedance 2 / Seedance / seedance`.

---

## Candidate sorting

After the search is completed, sort by interaction indicators from high to low:

| Platform | Sort fields |
|---|---|
| X/Twitter | `likes` |
| TikTok | `likes` |
| YouTube | `views` |
| Reddit | `score` |
| Bilibili | `score` |

These indicators are just priorities and do not equal whether they are qualified or not; final inclusion is still verified based on user goals.

---

## X / Twitter

Requires Browser Bridge + x.com login. X/Twitter is only enabled if the user explicitly requests it.

Return fields: `id`, `author`, `text`, `created_at`, `likes`, `views`, `url`

Get details:

```bash
opencli twitter thread "<tweet-id>" -f json
```

Suitable for: hot discussions, creators’ opinions, work release, short text feedback, link clues.

---

## TikTok

Requires Browser Bridge + login to tiktok.com. TikTok is only enabled when the user explicitly requests it.

Return fields: `desc`, `author`, `url`, `plays`, `likes`

Note: Each TikTok search will refresh the browser page, which is slow; it is recommended to run alone when there are a small number of targets.

Suitable for: popular short videos, oral broadcast scripts, creator samples, comments/trend clues.

---

## YouTube

Return fields: `title`, `channel`, `views`, `duration`, `published`, `url`

Get details:

```bash
opencli youtube video "<url>" -f json
opencli youtube transcript "<url>" -f json
```

Suitable for: long video cases, channels/creators, tutorial content, comments and feedback, subtitle information.

---

## Reddit

Return fields: `title`, `subreddit`, `author`, `score`, `comments`, `url`

Get details:

```bash
SKILL_DIR="$HOME/.codex/skills/multi-platform-content-collector"
python3 "$SKILL_DIR/scripts/fetch_reddit_post.py" <subreddit> <post_id>
```

Suitable for: user feedback, pain points, product discussions, prompt sharing, and real community reviews.

---

## Bilibili

Return fields: `title`, `author`, `score`, `url`

Get details:

```bash
SKILL_DIR="$HOME/.codex/skills/multi-platform-content-collector"
python3 "$SKILL_DIR/scripts/fetch_bilibili_video.py" <BVNumber>
```

Suitable for: Chinese video cases, tutorials, creators, comment area clues, AI work materials.

---

## Other platforms

OpenCLI adapter extensions are available when explicitly requested by the user:

| Platform | Command | Remarks |
|---|---|---|
| Xiaohongshu | `opencli xiaohongshu search` | Login required |
| Weibo | `opencli weibo search` | Login required |
| Douyin | `opencli douyin hashtag search` | Login required creator.douyin.com |

---

## Command quick check

```bash
opencli twitter thread "<tweet-id>" -f json
opencli youtube video "<url>" -f json
opencli youtube transcript "<url>" -f json
python3 "$SKILL_DIR/scripts/fetch_reddit_post.py" <subreddit> <post_id>
python3 "$SKILL_DIR/scripts/fetch_bilibili_video.py" <BVNumber>
opencli doctor
```
