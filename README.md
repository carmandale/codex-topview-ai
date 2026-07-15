# TopView AI Codex Plugin

TopView AI for Codex covers the complete marketing-content workflow: public-source research, video strategy and scripting, TopView media generation, Storyboard previews, and optional publishing to TikTok, Instagram, and YouTube.

## Included Skills

- `topview-skill`: generate videos, images, avatars, product visuals, voice, and Storyboard previews with TopView AI.
- `video-script-writer`: develop hooks, scripts, shot lists, storyboards, and model-ready video prompts.
- `multi-platform-content-collector`: collect structured public web and social research.
- `social-media-uploader`: dry-run, schedule, and publish finished videos through a logged-in Chrome debug session.

## Requirements

Core TopView generation requires:

- Codex Desktop or Codex CLI with plugin support.
- Python 3.10 or newer.
- A TopView account with available generation credits.
- Network access to `https://www.topview.ai`.

Install the core Python dependencies from the plugin root:

```bash
python -m pip install -r skills/topview-skill/scripts/requirements.txt
```

Optional capabilities have additional dependencies:

- Content collection: `opencli`, `curl`, and existing browser login sessions for platforms that require authentication.
- Social publishing: Chrome, Python 3.9 or newer, and the packages declared by `tools/social-uploader/pyproject.toml`.

Install the bundled uploader only when social publishing is needed:

```bash
python -m pip install -e tools/social-uploader
```

## Install as a Personal Plugin

The simplest installation is to ask Codex to use the built-in `plugin-creator` workflow:

```text
Use @plugin-creator to install the plugin from
https://github.com/topviewai/codex-topview-ai.git
as a personal plugin named topview-ai. Validate it, install it from the personal
marketplace, and tell me to start a new task when installation is complete.
```

For a manual personal installation, clone the repository into the personal plugin source directory:

macOS/Linux:

```bash
mkdir -p ~/plugins
git clone https://github.com/topviewai/codex-topview-ai.git ~/plugins/topview-ai
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\plugins" | Out-Null
git clone https://github.com/topviewai/codex-topview-ai.git "$env:USERPROFILE\plugins\topview-ai"
```

Add this plugin entry to `~/.agents/plugins/marketplace.json`. Merge it into an existing `plugins` array instead of overwriting other personal plugins:

```json
{
  "name": "personal",
  "interface": {
    "displayName": "Personal"
  },
  "plugins": [
    {
      "name": "topview-ai",
      "source": {
        "source": "local",
        "path": "./plugins/topview-ai"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

Restart the ChatGPT desktop app, open the plugin directory, select the Personal marketplace, and install TopView AI. Start a new task after installation so Codex loads the bundled skills and tools.

Do not copy this plugin into Codex's internal cache manually, and do not edit plugin entries in `~/.codex/config.toml` by hand.

## Update

Pull the latest plugin source:

macOS/Linux:

```bash
git -C ~/plugins/topview-ai pull --ff-only
```

Windows PowerShell:

```powershell
git -C "$env:USERPROFILE\plugins\topview-ai" pull --ff-only
```

For a released version, restart the desktop app, reinstall or update TopView AI from the Personal marketplace, and start a new task.

For local development, ask `@plugin-creator` to apply a Codex cachebuster, reinstall `topview-ai@personal`, and validate the updated plugin. Do not hand-edit the marketplace or cache during this update loop.

## Verify

From the plugin root, validate the package with the built-in plugin validator:

```bash
python <plugin-creator-skill>/scripts/validate_plugin.py .
```

Then start a new Codex task and try one of these prompts:

```text
Use TopView AI to write a short-form product video script, show me the draft,
then ask whether I want a Storyboard preview before generation.
```

```text
Collect recent competitor content ideas from YouTube and Reddit and turn them
into three video briefs.
```

```text
Dry-run a private YouTube upload for this finished video and ask me before publishing.
```

## Safety and Credentials

- TopView login credentials are stored locally in `%USERPROFILE%\.topview\credentials.json` on Windows or `~/.topview/credentials.json` on macOS/Linux.
- Social publishing reuses a Chrome debug browser. Users must log in to target platforms themselves; the plugin must never request passwords.
- Always dry-run social uploads before publishing and require explicit confirmation before the final publish action.

## Repository Layout

- `.codex-plugin/plugin.json`: Codex plugin manifest.
- `skills/topview-skill/`: TopView generation client and references.
- `skills/video-script-writer/`: video strategy and script workflow.
- `skills/multi-platform-content-collector/`: public-source research workflow.
- `skills/social-media-uploader/`: safe social publishing workflow.
- `tools/social-uploader/`: local uploader CLI implementation.

## License

The plugin package is licensed under the MIT License. The bundled `skills/topview-skill` component is licensed separately under Apache-2.0; see `THIRD_PARTY_NOTICES.md` and `skills/topview-skill/LICENSE.txt`.
