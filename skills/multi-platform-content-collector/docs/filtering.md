# Filter secondary references

This file is used for any "data collection on demand" task. The core is not keyword matching, but determining whether the candidate can serve the user's collection goals.

---

## Judgment method: target → evidence → field

1. **Target matching**: Whether the candidate really belongs to the object the user wants to collect.
2. **Sufficient Evidence**: Is there a public link, author/source, text, or verifiable metrics.
3. **Field can be extracted**: Whether the field required by the user can be extracted from the source; if not, mark `N/A`.
4. **Clear value**: Why this item is worth collecting; use `summary` / `insight` / `reason` to briefly explain.

Don’t rely solely on keyword filtering. The title hits the keywords but the content is irrelevant, so you should skip it; the title is ordinary but the text is valuable, so you can accept it.

---

## Generic keep/skip rules

| Reserve | Skip |
|---|---|
| Directly related to user goals | Just the same name, rubbish, and advertising noise |
| There is a traceable link to the source | The source is not accessible or cannot be located |
| There is at least some information about the author, publication time, and interaction data | All key fields are missing |
| Ability to distill clear findings or uses | Unable to explain why it is relevant |
| Edge-related items when the user explicitly asks to "collect as much as possible" | Privacy, permission bypassing, paywall content |

If it is uncertain but may be valuable, it can be kept and marked with "reason for uncertainty" in `note`.

---

## Scene reference

### Competing products/topics

Keep: popular videos, title structure, review pain points, selling point expression, and content format.
Skip: pure tutorials, general news, repeated forwarding without interaction or content details.

### Creator list

Keep: account homepage, clear categories, recent content samples, and data that can determine influence.
Skip: moving number, empty homepage, and accounts whose platform identity cannot be confirmed.

### Comments/Feedback

Reserved: Comments that express specific needs, pain points, compliments, objections, or purchase/use experiences.
Skip: Emoticons, meaningless comments, and obvious robots that spam the screen.

### AI works + prompt words

Reserved: Demonstrate AI work and share complete or targetable prompts publicly.
Skip: only works but no public prompts; tutorials/reviews/news; paid guides to obtain prompts.

Prompt words must be recorded in the original text and must not be rewritten, translated, or completed.

---

## Anti-truncation quick check

| Risk | Resolution |
|---|---|
| Reddit body truncated | Use `fetch_reddit_post.py` or Reddit JSON API |
| TikTok description truncated | Try OCR, or annotate information in the screen |
| YouTube description is incomplete | `youtube video` gets description, `youtube transcript` gets subtitles |
| Command line parameter too long | Save JSON with `save_verified.py --from-file` |
| Missing rows after table writing | Use the `start_index` breakpoint of `write_rows.py` to continue writing |
