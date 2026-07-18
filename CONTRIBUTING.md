# Contributing to AutoCard

Thank you for helping improve Japanese sentence mining with AutoCard. Bug reports, reproducible subtitle samples, documentation fixes, and focused pull requests are welcome.

## Before opening an issue

1. Fully close every mpv window and reopen the video.
2. Hard-refresh the AutoCard browser page with `Ctrl+Shift+R`.
3. Confirm Anki is open and AnkiConnect responds on `http://127.0.0.1:8765`.
4. Check `http://127.0.0.1:6969/subtitle-debug` for subtitle parser details.
5. Search existing issues for the same symptom.

## A useful bug report includes

- Windows version
- AutoCard commit or release
- mpv version and video container
- Subtitle source: external or embedded
- Subtitle format: SRT, ASS, or SSA
- Browser and Yomitan versions
- Anki and AnkiConnect versions
- Exact steps to reproduce
- Expected and actual behavior
- Relevant server console output
- `/subtitle-debug` output when subtitles are involved
- A minimal subtitle sample when licensing permits it

Remove personal deck content, local usernames, API keys, and copyrighted media before attaching logs or screenshots.

## Development setup

The portable bundle contains the runtime needed by AutoCard. The main project files are:

- `portable_config/autocards/server.py`
- `portable_config/autocards/index.html`
- `portable_config/autocards/vendor/tokenizer-worker.js`
- `portable_config/scripts/autocards.lua`

Run the Python syntax check:

```powershell
.\portable_config\autocards\python\python.exe -c "from pathlib import Path; p=Path('portable_config/autocards/server.py'); compile(p.read_text(encoding='utf-8'), str(p), 'exec')"
```

If Node.js is installed, extract and syntax-check the inline JavaScript from `index.html` before browser testing.

## Pull-request guidelines

- Keep AnkiConnect on the standard `127.0.0.1:8765` endpoint. Do not introduce a mandatory proxy.
- Preserve compatibility with the portable Windows layout.
- Do not commit `portable_config/autocards/options.json`, cache files, debug output, or personal Anki data.
- Avoid adding large binaries unless the change genuinely requires them; applicable binaries must use Git LFS.
- Include focused tests or a reproducible simulated-AnkiConnect check for backend behavior.
- Run Python and JavaScript syntax checks before submitting.
- Update README documentation when user-visible behavior changes.
- Keep third-party license and attribution files with redistributed components.

## License

By contributing project-authored code or documentation, you agree that your contribution may be distributed under GPL-3.0-or-later. Third-party components remain under their respective licenses documented in `THIRD_PARTY_NOTICES.md`.
