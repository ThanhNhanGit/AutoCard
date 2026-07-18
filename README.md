# AutoCard — Japanese Anki Sentence Mining with mpv + Yomitan

**AutoCard is an open-source, portable Windows toolkit for Japanese sentence mining with Anki, mpv, Yomitan, and Japanese subtitles.** It turns anime and video subtitle lines into Anki flashcards with sentence audio, screenshots, known-word highlighting, N+1 detection, frequency coloring, batch selection, and multi-line mining.

Use your normal Yomitan → AnkiConnect workflow, keep AnkiConnect on `http://127.0.0.1:8765`, and let AutoCard enrich mined notes with the current subtitle sentence and media. Everything runs locally—no proxy, cloud account, subscription, or application-wide endpoint change.

**Use cases:** anime sentence mining, Japanese subtitle mining, Anki flashcard creation, Yomitan mining, mpv immersion, N+1 sentence discovery, known-word tracking, and post-episode batch mining.

[Features](#what-this-build-adds) · [Quick start](#quick-start) · [Configuration](#configuration) · [Mining workflows](#mining-workflows) · [FAQ](#frequently-asked-questions) · [Troubleshooting](#troubleshooting)

This enhanced distribution is based on Autocards by かにふぁん and the [One-Click Anime Cards guide](https://learnjapanese.moe/autocards/). Its cache-first highlighting design was inspired by [SubMiner](https://github.com/ksyasuda/SubMiner). It offers some Migaku/SubMiner-style mining conveniences in a small local Autocards workflow, but is not affiliated with Migaku, SubMiner, Yomitan, Anki, mpv, or FFmpeg.

## What this build adds

- **Known-word highlighting** — expressions already present in configured Anki decks are muted green.
- **Immediate cache updates** — a word mined in the current session becomes known without a full deck scan.
- **Dictionary-form matching** — kuromoji tokenization matches inflected subtitle text against cached headwords.
- **N+1 detection** — lines containing exactly one unknown word are marked automatically.
- **Focus N+1 mode** — collapses and fades non-N+1 lines so you can review only useful mining candidates.
- **Frequency bands** — optional Yomitan-format frequency dictionaries tint unknown words by rank.
- **Selectable batch mining** — choose exactly which lines and target expressions should become cards.
- **Multi-line merge** — combine split subtitle cues into one continuous sentence, then mine it normally with Yomitan.
- **Merged media** — merged cards receive concatenated cue audio with gaps removed and a screenshot from the first cue.
- **Robust subtitle input** — external and embedded SRT/ASS/SSA subtitles are supported.
- **No AnkiConnect proxy** — Yomitan, GameSentenceMiner, Manatan, and other tools continue using `http://127.0.0.1:8765`.

Everything runs locally. The browser communicates with AutoCard on port `6969`; AutoCard communicates directly with AnkiConnect on port `8765`.

## Why AutoCard?

AutoCard is designed for learners who watch an episode first and mine useful Japanese sentences afterward without manually scrubbing through every subtitle cue.

| Mining problem | AutoCard workflow |
| --- | --- |
| Every subtitle line looks identical | Known words are muted; unknown and N+1 candidates remain visually prominent. |
| Finding the next useful sentence takes too much scrolling | **Focus N+1** collapses non-N+1 lines with a smooth fade. |
| A spoken sentence is split across subtitle cues | Select the cues, press **Merge**, then mine the continuous sentence with Yomitan. |
| Merged audio contains long silent gaps | Selected cue segments are concatenated while the gaps are removed. |
| Batch mining chooses unwanted words or lines | You select the exact lines and target expressions before creating notes. |
| Full-deck Anki scans would interrupt playback | A persistent local cache handles highlighting and updates newly mined words immediately. |
| Other mining tools already use AnkiConnect | AutoCard leaves the standard `127.0.0.1:8765` endpoint untouched. |

## Requirements

- Windows 10 or 11
- [Anki](https://apps.ankiweb.net/) with [AnkiConnect](https://ankiweb.net/shared/info/2055492159)
- A compatible Anki note type with sentence, expression, picture, and sentence-audio fields
- [Yomitan](https://yomitan.wiki/) for dictionary lookup and normal word mining
- Git LFS when cloning this repository instead of downloading a release

The portable bundle already includes mpv, FFmpeg, yt-dlp, Python, curl, and the browser tokenizer files used by AutoCard.

## Quick start

### Get the complete portable bundle

This repository uses Git LFS for mpv, FFmpeg, Python, tokenizer dictionaries, and other bundled binaries. Install [Git LFS](https://git-lfs.com/), then clone the repository:

```powershell
git lfs install
git clone https://github.com/ThanhNhanGit/AutoCard.git
cd AutoCard
git lfs pull
```

Do not use a clone that contains small text-pointer files in place of `mpv.exe` or `ffmpeg.exe`; run `git lfs pull` first.

### Start Japanese sentence mining

1. Install AnkiConnect and keep its standard endpoint at `http://127.0.0.1:8765`.
2. Open Anki.
3. Run `mpv.exe` and open a video containing Japanese subtitles.
4. AutoCard starts with mpv and opens `http://127.0.0.1:6969` in your browser.
5. Open the settings button in the AutoCard page and map the fields to your Anki note type.
6. Hover a word with Yomitan and create a note normally; AutoCard adds the subtitle sentence, cropped audio, and screenshot.

Keep the directory structure intact. `mpv.exe`, `ffmpeg.exe`, and `portable_config` must remain siblings:

```text
Autocards/
├── mpv.exe
├── ffmpeg.exe
├── yt-dlp.exe
└── portable_config/
    ├── mpv.conf
    ├── scripts/autocards.lua
    └── autocards/
        ├── server.py
        └── index.html
```

## Configuration

Open the gear button in the AutoCard page. Local settings are stored in `portable_config/autocards/options.json`; this file is intentionally ignored by Git because it can contain deck names and absolute paths from your machine. See `options.example.json` for a clean template.

| Setting | Meaning |
| --- | --- |
| Mining Deck | Anki deck receiving mined notes. Quoted deck queries such as `"Mining"` are supported. |
| Sentence Field | Field that receives the subtitle sentence. |
| Expression Field | Field containing the mined dictionary expression. |
| Picture Field | Field receiving the captured video frame. |
| Sentence Audio Field | Field receiving the cropped audio clip. |
| Previous / Next Sentences | Number of neighboring subtitle cues included as context. |
| Known-word Decks | One entry per line in the form `Deck Name: Field, Field`. The mining deck is always included. |
| Note Type | Optional override. Leave empty to auto-detect from the mining deck. |
| Frequency Dictionary | Path to a Yomitan frequency dictionary ZIP, extracted folder, or compatible JSON source. |

After changing known-word sources, press **↻** to rebuild the cache. Frequency data rebuilds automatically after updating its path.

## Mining workflows

### Normal Yomitan mining

1. Hover an unknown word and create the note with Yomitan as usual.
2. AutoCard detects the new note through the existing AnkiConnect workflow.
3. It fills the sentence, screenshot, and subtitle audio, then immediately adds the expression to the known-word cache.

No additional proxy or Yomitan endpoint is involved.

### Review only N+1 lines

Use **Focus N+1** to fade and collapse every line that is not N+1. Click the `N+1` counter to select all currently eligible lines, or select individual lines manually.

### Batch mine selected lines

Select the lines you actually want, choose the highlighted unknown target on each line, and press **Mine**. This creates one note per selected line and crops its media.

Batch-created notes do not receive dictionary definitions because AutoCard does not bundle a dictionary database. Use normal Yomitan mining when you need Yomitan's selected definitions on the new note.

### Merge subtitle cues, then mine with Yomitan

Use this when one spoken sentence is split across two or more subtitle cues:

1. Select the relevant cues.
2. Press **Merge**.
3. AutoCard renders them as one continuous text run and registers their combined timestamps.
4. Hover the desired word in the merged line and mine with Yomitan normally.
5. AutoCard enriches that note with the full merged sentence and concatenated cue audio.

The rendered merge intentionally contains no `<br>` boundary; Yomitan otherwise stops sentence scanning at the line break and captures only one cue.

## Highlighting legend

- **Muted green** — known word found in the local Anki cache.
- **N+1 line marker** — exactly one unknown dictionary-form word remains.
- **Frequency colors** — unknown words are grouped from common to rare according to the loaded frequency dictionary.
- **Target ring** — expression that batch mining will place in the Expression field. Click another unknown token to change it.

## Cache behavior

Known words are cached in `portable_config/autocards/known-words-cache.json`. The cache is loaded immediately at startup and rebuilt in the background when absent or stale. Newly mined expressions are appended from AutoCard's existing card-detection response, so subtitle rendering does not repeatedly query Anki.

Frequency ranks are cached separately in `portable_config/autocards/frequency-cache.json`. Both cache files are runtime data and are excluded from Git.

## Troubleshooting

### mpv starts but the browser shows no subtitles

- Select the Japanese subtitle track in mpv.
- Fully close and reopen mpv after changing `server.py`, `index.html`, or `autocards.lua`.
- Inspect `http://127.0.0.1:6969/subtitle-debug` for the detected source, parser, line count, and error.

### Frequency dictionary is not detected

- Use a Yomitan frequency dictionary containing `term_meta_bank_*.json` files.
- ZIP files, extracted folders, and compatible JSON files are accepted.
- Paste the full local path and press **Update**. AutoCard strips invisible Unicode direction markers that Windows can add when copying a path.
- A normal Yomitan term dictionary containing only `term_bank_*.json` definitions is not a frequency dictionary.

### A merged mine contains only one subtitle cue

Fully close mpv, reopen it, and hard-refresh the browser with `Ctrl+Shift+R`. Older loaded frontend code inserted a `<br>` between merged cues, which caused Yomitan to stop at the first line.

### AutoCard does not enrich the new Anki note

- Keep Anki open.
- Confirm AnkiConnect responds on `127.0.0.1:8765`.
- Confirm the configured deck and field names exactly match Anki.
- Ensure the new note's sentence comes from the currently loaded subtitle line.

### The page still runs old code

The Python server is launched once per mpv session. Fully close every mpv window, reopen mpv, and use `Ctrl+Shift+R` in the browser.

## Frequently asked questions

### What is Japanese sentence mining?

Sentence mining is the practice of saving useful words in sentences encountered during immersion—such as anime, dramas, movies, or YouTube—to personal Anki flashcards. AutoCard automates the subtitle sentence, audio, and screenshot portions of that workflow.

### Does AutoCard work with Yomitan and AnkiConnect?

Yes. Yomitan continues sending notes directly to AnkiConnect at `http://127.0.0.1:8765`. AutoCard detects the new note and enriches it; it does not replace or proxy AnkiConnect.

### Is AutoCard an open-source Migaku or SubMiner replacement?

AutoCard covers a narrower workflow: local mpv subtitle review, known-word highlighting, N+1 filtering, frequency bands, selected batch mining, and multi-line subtitle merging. Migaku and SubMiner have different architectures and broader feature sets. AutoCard is independent and is not a drop-in replacement for either project.

### How does N+1 detection work?

The browser tokenizes Japanese subtitle text with kuromoji/IPADIC, converts tokens to dictionary forms, and compares them with the local known-word cache. A line is marked N+1 when exactly one eligible unknown expression remains.

### Can I show only N+1 subtitle lines?

Yes. Press **Focus N+1** to smoothly fade and collapse the other lines. Press it again to restore the full subtitle history.

### Can I batch mine an anime episode after watching it?

Yes. Select only the lines you want, confirm or change each target expression, and press **Mine**. AutoCard creates one note per selected line with cropped media. Batch-created notes do not include Yomitan dictionary definitions; use normal Yomitan mining when selected definitions are required.

### Can AutoCard merge two subtitle lines into one Anki sentence?

Yes. Select two or more cues and press **Merge**, then hover-mine the merged text with Yomitan. AutoCard stores the full combined sentence and concatenates the selected audio segments without the silence between cues.

### Does AutoCard upload subtitles or Anki data?

No. Subtitle processing, tokenization, cache storage, media capture, and AnkiConnect communication happen locally. AutoCard itself has no telemetry or cloud service.

### Which frequency dictionaries are supported?

Use a Yomitan-format frequency dictionary containing `term_meta_bank_*.json` entries. AutoCard accepts the dictionary ZIP, an extracted folder, or a compatible JSON source.

## Get help and contribute

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a code change.
- Use a [bug report](https://github.com/ThanhNhanGit/AutoCard/issues/new?template=bug_report.yml) for reproducible failures.
- Use a [feature request](https://github.com/ThanhNhanGit/AutoCard/issues/new?template=feature_request.yml) for mining-workflow improvements.
- Include the output of `http://127.0.0.1:6969/subtitle-debug` when reporting subtitle-loading problems.

## Development

The application is intentionally small:

- `portable_config/autocards/server.py` — local HTTP server, AnkiConnect integration, subtitle parsing, media capture, and caches.
- `portable_config/autocards/index.html` — subtitle UI, token highlighting, N+1 filtering, selection, and merge behavior.
- `portable_config/autocards/vendor/tokenizer-worker.js` — background kuromoji initialization and tokenization.
- `portable_config/scripts/autocards.lua` — mpv integration.

Basic checks:

```powershell
.\portable_config\autocards\python\python.exe -m py_compile .\portable_config\autocards\server.py

# Extract the inline script from index.html, then run Node's parser if Node.js is installed.
node --check inline.js
```

Do not test development changes against a valuable live collection when a simulated AnkiConnect instance will cover the behavior.

## Limitations

- Tokenization uses kuromoji/IPADIC and cannot resolve every modern expression, proper noun, reading, or homograph perfectly.
- Reading-aware disambiguation is limited compared with products that ship a dedicated dictionary and morphological pipeline.
- Frequency colors reflect the chosen dictionary, not an objective difficulty or learning priority.
- Deleting or editing old Anki notes requires a known-word cache rebuild.
- Batch mining intentionally does not invent dictionary definitions.

## License and credits

Project-authored Autocards code and modifications are distributed under **GPL-3.0-or-later**. See [LICENSE](LICENSE).

The portable package also redistributes independent third-party programs and data under their own licenses. Those components are not relicensed by the project-wide GPL notice. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the license files stored beside each component.

Key credits:

- Autocards and the original mpv integration — かにふぁん
- Cache-first known-word architecture inspiration — [SubMiner](https://github.com/ksyasuda/SubMiner)
- Japanese tokenizer — [kuromoji.js](https://github.com/takuyaa/kuromoji.js)
- Playback and media processing — [mpv](https://mpv.io/) and [FFmpeg](https://ffmpeg.org/)
- Dictionary lookup and Anki note creation — [Yomitan](https://yomitan.wiki/)
