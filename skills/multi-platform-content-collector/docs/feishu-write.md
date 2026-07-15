# Feishu form writing

This step writes the verified data in `/tmp/collector_verified.jsonl` into the Feishu table. The fields are not fixed, and the header and column order must be determined according to the user's current collection goal.

---

## 1. Generate row data

Example: Universal collection form.

```bash
SKILL_DIR="$HOME/.codex/skills/multi-platform-content-collector"

python3 - <<'PY'
import json
rows = []
with open('/tmp/collector_verified.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        rows.append([
            d.get('platform', 'N/A'),
            d.get('title') or d.get('source') or d.get('author', 'N/A'),
            d.get('author') or d.get('creator', 'N/A'),
            d.get('date', 'N/A'),
            d.get('metric') or d.get('likes') or d.get('views') or d.get('score') or 'N/A',
            d.get('url', 'N/A'),
            d.get('summary') or d.get('insight') or d.get('reason') or d.get('prompt') or '',
        ])
print(f'Loaded {len(rows)} verified rows')
with open('/tmp/rows.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False)
PY
```

If the user wants a prompt word library, the last column can be replaced by `prompt`, and the header uses "complete prompt word".

---

## 2. Create a table

Create a header based on this field, for example:

```bash
lark-cli sheets +create --as user \
  --title "<Keywords> Multi-platform data collection" \
  --headers '["Platform","Title/Source","Author","Published","Metrics","Link","Abstract/Findings"]'
```

Log the returned `url`, and then obtain `sheet_id`:

```bash
lark-cli sheets +info --url "<URL>" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data['data']['sheets']['sheets'][0]['sheet_id'])"
```

---

## 3. Write data

```bash
python3 "$SKILL_DIR/scripts/write_rows.py" "<URL>" "<sheet_id>" /tmp/rows.json
```

The script is written line by line to avoid truncation of long text and supports retry on failure.

---

## 4. Verify after writing

```bash
lark-cli sheets +read --as user --url "<URL>" --sheet-id "<sheet_id>"
```

examine:

- Number of rows = number of rows in `/tmp/rows.json`.
- Key field is not empty.
- Long text is not truncated at the end.

If there are missing lines, use the `start_index` parameter breakpoint to continue writing:

```bash
python3 "$SKILL_DIR/scripts/write_rows.py" "<URL>" "<sheet_id>" /tmp/rows.json <Failed row index>
```
