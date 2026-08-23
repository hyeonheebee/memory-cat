# Memory Cat 🐱

*메모리 뚱냥이 — an OpenAI Build Week project*

> Your disk usage, visualized as a cat that gets chonkier as your drive fills up.

<p align="center">
  <img src="./docs/chonk-loop.gif" alt="A cat getting rounder as the disk fills up" width="300">
</p>

Memory Cat is a desktop pet for macOS, with a lightweight Windows version. It
turns an invisible system metric into something you can understand at a glance:
the fuller your drive gets, the rounder your cat becomes.

The killer demo feature makes that cat personal. Give Memory Cat one photo of
your pet, and **gpt-image-2** creates a six-stage chonk progression that the app
automatically converts into a custom 40-frame desktop theme.

## Screenshots

<table>
  <tr>
    <td align="center">
      <img src="./cute.png" width="260"><br>
      <sub>The default cat gets rounder as disk usage rises</sub>
    </td>
    <td align="center">
      <img src="./simple.png" width="260"><br>
      <sub>Built-in themes give each chonk a different style</sub>
    </td>
  </tr>
  <tr>
    <td align="center" colspan="2">
      <img src="./context-menu.png" width="400"><br>
      <sub>The chonk stage, disk, RAM, swap, top memory apps, the diagnosis, themes, personality, and language — all on right-click</sub>
    </td>
  </tr>
</table>

<p align="center">
  <img src="./docs/screenshots/01-desktop-pet.png" alt="Memory Cat on the desktop" width="48%">
  <img src="./docs/screenshots/02-diagnosis.png" alt="GPT-5.6 diagnosis result" width="48%">
  <img src="./docs/screenshots/03-photo-to-sprite.png" alt="Pet photo to chonk sprite sheet" width="48%">
  <img src="./docs/screenshots/04-safe-cleanup.png" alt="Safe cleanup confirmation" width="48%">
</p>

## Highlights

- **One pet photo → one custom animated theme:** gpt-image-2 preserves your
  pet's distinctive colors, markings, face, and ears while generating a
  six-stage horizontal sprite sheet. Memory Cat segments it and builds the full
  40-frame theme automatically.
- **The complete chonk chart:** disk usage moves your cat through **A fine boi →
  He chomnk → A heckin' chonker → HEFTYCHONK → MEGACHONKER → OH LAWD HE
  COMIN**.
- **“🐾 What did you eat?” diagnosis:** GPT-5.6 (`gpt-5.6-luna`) explains why the
  computer feels slow, recommends safe cleanup targets, estimates reclaimable
  space, and gives one concise piece of advice. The Korean menu label is
  “🐾 뭘 먹은 거야?”.
- **Safety-first cleanup:** only allowlisted browser caches, Trash contents,
  downloads older than 30 days, and Xcode DerivedData can be suggested. Every
  item requires confirmation and is moved through macOS Trash—never permanently
  deleted.
- **A cat with a personality:** choose a sassy, warm, or stoic voice, or describe
  a custom personality in natural language. The selected voice shapes the
  diagnosis.
- **English and Korean:** macOS language is detected automatically, with a
  manual language override in the context menu.
- **Useful at a glance:** disk, RAM, swap, and top memory-consuming apps appear
  in the right-click menu. The cat can be dragged, resized, and rethemed.

The AI-powered items above are macOS only. See
[Install on Windows](#install-on-windows) for what the Windows build covers.

## Privacy

Memory Cat does not phone home. Disk, RAM, and swap numbers are measured and
drawn entirely on your machine, and nothing is collected or sent anywhere in
the background. There is no analytics, telemetry, or crash reporting in the
codebase. (The macOS installer does route the app's own stdout and stderr to a
local `cat.log` under `~/Library/Logs/Memory Cat/`, which never leaves your
machine.)

Two features reach the network, and only when you click them yourself:

- **🐾 What did you eat? diagnosis** sends the usage numbers, the names of the apps
  using the most memory, and per-category cleanup totals. If you wrote your own
  personality description, that text is sent as well, since it shapes the reply.
  **File names and paths are never sent** — the payload is assembled without
  them, and a test enforces it. The request also sets `store=False`.
- **Make a theme from my pet…** uploads the photo you pick. A consent dialog
  naming OpenAI appears first, and nothing is uploaded until you approve it.

Both features need your own `OPENAI_API_KEY`. **Without a key the app still
works**: the diagnosis falls back to a local, rules-based explanation and only
custom theme generation is unavailable.

Cleanup can only ever touch four allowlisted locations — browser caches, the
Trash, downloads older than 30 days, and Xcode DerivedData. That list is fixed
in code and the model cannot extend it. Every item is confirmed individually
with its full path shown, and items are moved to the macOS Trash rather than
deleted.

## Runtime models

- Performance diagnosis: **GPT-5.6** (`gpt-5.6-luna`)
- Custom pet theme generation: **gpt-image-2**

## Built-in themes

| Theme | Description |
|---|---|
| Cute | A soft 3D-toy cat whose eyes get sleepier as it gets rounder |
| Simple | A clean, minimal illustrated chonk |
| Madness | A sparkly, wide-eyed chibi cat |
| Wake-up call | An intentionally derpy reminder to check your drive |

## Install on macOS

```bash
git clone https://github.com/hyeonheebee/memory-cat.git
cd memory-cat
./install_mac.command        # You can also double-click this file
```

The installer requires Python 3.9 or later. It builds a real application
bundle at `~/Applications/Memory Cat.app`, installs the dependencies into a
virtual environment inside that bundle, launches Memory Cat, and configures it
to start at login.

Because everything the app needs lives in the bundle, **you can delete the
cloned repository afterwards** and Memory Cat keeps working.

On a Mac that has never had developer tools installed, `python3` is only a stub
that prompts you to install them. Run `xcode-select --install` first, then run
the installer again. The installer checks for this and tells you what to do.

### Where your files live

| What | Where |
| --- | --- |
| The app | `~/Applications/Memory Cat.app` |
| Settings (`config.json`) | `~/Library/Application Support/Memory Cat/` |
| Themes you generated | `~/Library/Application Support/Memory Cat/frames/` |
| `OPENAI_API_KEY` (`.env`) | `~/Library/Application Support/Memory Cat/` |
| Log | `~/Library/Logs/Memory Cat/cat.log` |
| Login item | `~/Library/LaunchAgents/com.memorycat.desktop.plist` |

The four built-in themes ship inside the bundle and are replaced on every
install. Anything you made stays in Application Support and is never
overwritten.

**Upgrading from an older install?** The installer copies your existing
`config.json`, `.env`, and any custom `frames/<name>/` folders out of the
repository and into Application Support on first run. It copies rather than
moves, so the originals in your clone are left untouched, and it never
overwrites a file that is already there.

### Removing it

```bash
./uninstall_mac.command
```

If you already deleted the repository, the same script is kept inside the app:

```bash
"$HOME/Applications/Memory Cat.app/Contents/Resources/uninstall_mac.command"
```

Either way it stops the app, removes the login item and the bundle, and leaves
your settings and custom themes alone. It prints the one command that deletes
those too, if that is what you want.

### Updating

Pull, then run `./install_mac.command` again. It stops the running app,
rebuilds the bundle, and restarts it.

Store `OPENAI_API_KEY` in `~/Library/Application Support/Memory Cat/.env` to
enable GPT-5.6 diagnosis and custom pet theme generation. When you run from a
clone for development, a `.env` in the project root still works.

## Install on Windows

> **What the Windows build includes.** The disk-driven cat, RAM and swap
> readouts, top memory consumers, theme and size switching, and the Korean /
> English language toggle. The AI features are macOS only: the 🐾 What did you
> eat? diagnosis, custom pet themes, safe cleanup, and personalities. In
> exchange the Windows build has no OpenAI dependency and makes no network
> requests at all.

See [`windows/README.txt`](windows/README.txt) for the full instructions. In
short:

```bat
pip install -r windows\requirements.txt
pythonw windows\windows_cat.pyw
```

To build a standalone executable, install PyInstaller and run `build_exe.bat`.
It works from any working directory — the script switches to its own folder
before building, so `windows\build_exe.bat` from the repository root is fine:

```bat
pip install -r windows\requirements.txt
pip install pyinstaller
windows\build_exe.bat
```

> **The executable it produces is unsigned — expect security warnings.** This is
> a personal project with no code-signing certificate, so the first launch of
> `MemoryCat.exe` triggers a Windows SmartScreen "unknown publisher" prompt, and
> antivirus engines sometimes flag PyInstaller `--onefile` builds as a false
> positive (a `--onefile` binary unpacks itself into a temp folder at startup,
> which resembles malware behaviour). That is expected here, but **please do not
> learn to click through unsigned-binary warnings in general** — it is a
> genuinely dangerous habit. Do not run a `MemoryCat.exe` you got from anyone
> else; there is no way to verify it was built from this repository. If you want
> assurance, skip the executable and run the Python script directly:
> `windows/windows_cat.pyw` is a single readable file you can inspect before
> running it. Building the `.exe` yourself, on your own machine, is the only
> use it is recommended for.

## Make your own theme 🎨

### From one pet photo with gpt-image-2

On macOS, right-click the cat and choose **Make a theme from my pet…**. After
you select a photo and approve sending it to OpenAI, the app generates, imports,
and immediately applies the new theme in a background thread.

The same pipeline is available from the command line:

```bash
# install_mac.command builds its virtual environment inside the app bundle.
# For a development environment in the clone, make your own:
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip   # stock pip cannot resolve pyobjc-core
./.venv/bin/python -m pip install -r requirements.txt

# Keep OPENAI_API_KEY in the project root .env file
./.venv/bin/python vision_theme.py my-pet.jpg my-pet --quality medium
```

`vision_theme.py` asks gpt-image-2 for six clearly separated versions of the
same pet, from slim to extremely round. It then reuses the existing import
pipeline to produce `cat_00.png` through `cat_39.png` under
`~/Library/Application Support/Memory Cat/frames/my-pet/`, plus preview and raw
debug images. Set `MEMORY_CAT_HOME` to write somewhere else.

### From an existing sprite sheet

If you already have a horizontal image with multiple stages from slim to round,
import it directly:

```bash
./.venv/bin/python import_theme.py my-sprite-sheet.png my-theme
```

Themes are discovered automatically from two places: the four built-in themes
inside the app bundle, and your own themes in
`~/Library/Application Support/Memory Cat/frames/<name>/`. Newly generated
themes always go to the second one, so reinstalling the app never deletes them.
Reopen the right-click **Theme** menu to select a newly imported theme.
Code-generated built-in themes can be rebuilt with `python generate_frames.py`.

## Project structure

```text
desktop_cat.py      macOS desktop app and menus (PyObjC)
apppaths.py         where bundled assets end and user data begins
macos/build_app.py  assembles Memory Cat.app and the LaunchAgent plist
brain.py            GPT-5.6 performance diagnosis and safe Trash workflow
personality.py      personality presets and custom prompt compiler
i18n.py             English/Korean UI strings and chonk-stage names
metrics.py          shared disk and memory measurements
vision_theme.py     one pet photo -> gpt-image-2 custom theme
import_theme.py     sprite sheet segmentation and frame generation
generate_frames.py  built-in theme generator
windows/            lightweight Windows app (PySide6)
frames/<theme>/     generated PNG frames for each theme
tests/              mocked, regression, and optional live API tests
```

## Developer demo and test overrides

- `MEMORY_CAT_CONFIG=demo_config.json`: use a separate config file for demos or
  tests so personal settings are not read or modified.
- `MEMORY_CAT_DEMO_DISK_PERCENT=92`: replace measured disk usage with a demo or
  test value, clamped to 0–100; displayed and diagnostic values stay consistent.
- `MEMORY_CAT_HOME=/tmp/cat-home`: relocate everything under
  `~/Library/Application Support/Memory Cat/` — settings, custom themes, and
  `.env` — so a test run cannot touch your real data.
- `MEMORY_CAT_APPS_DIR=/tmp/apps`: install the bundle somewhere other than
  `~/Applications`. Used by `install_mac.command` and `uninstall_mac.command`.

Example:

```bash
MEMORY_CAT_CONFIG=demo_config.json \
MEMORY_CAT_DEMO_DISK_PERCENT=92 \
.venv/bin/python desktop_cat.py
```

## How I collaborated with Codex

All application code in this project was written by **Codex** (GPT-5.6-Codex) in a
single continuous session in the ChatGPT desktop app, working directly on this
repository. My workflow for every feature:

1. **Spec first** — I wrote a detailed spec for each module (goals, design
   decisions, safety constraints, test requirements, done criteria) and handed
   it to Codex as one prompt.
2. **Codex implements** — Codex wrote the code, tests, and commits: the GPT-5.6
   diagnosis engine (`brain.py`), the safety-first trash pipeline (`safe_trash`
   with an allowlist + macOS Trash only), i18n, the personality system, and the
   killer feature — `vision_theme.py`, which turns one photo of your pet into a
   40-frame chonk-progression theme via gpt-image-2.
3. **Verify against the real API** — mocked tests all passed, but my review
   partner (Claude, which I used for planning, code review, and demo prep —
   never for the code itself) ran a live API call and caught a real bug:
   gpt-image-2 rejects the `response_format` parameter. I reported it back to
   Codex with the error, Codex verified it against the API reference and shipped
   the fix with a regression test (`assertNotIn("response_format", kwargs)`).

Models used at runtime: **GPT-5.6** (`gpt-5.6-luna`) powers the cat's
personality-driven performance diagnosis; **gpt-image-2** generates the custom
pet sprite sheets.

## Author and license

Built by Hyeonhee Shim (@hyeonheebee). Code by Codex; planning, review, and demo by Claude. MIT License.
