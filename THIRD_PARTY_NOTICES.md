# Third-party notices

AutoCard is a portable aggregate containing project-authored code and independent third-party
programs, libraries, scripts, fonts, and data. The top-level GPL-3.0-or-later license covers the
original Autocards code and AutoCard modifications; it does not relicense independent components.

The complete source/provenance record for distributed binaries is in
[CORRESPONDING_SOURCE.md](CORRESPONDING_SOURCE.md).

## Bundled components

| Component | Bundled location | Version / provenance | License and notice |
| --- | --- | --- | --- |
| Original Autocards by かにふぁん | `portable_config/autocards/`, `portable_config/scripts/autocards.lua` | [One-Click Anime Cards](https://learnjapanese.moe/autocards/) | GPL-3.0-or-later — `LICENSE` and `portable_config/autocards/LICENSE` |
| mpv and statically linked dependencies | `mpv.exe`, `mpv.com` | mpv `v0.41.0-60-g85bf9f4ff`; source/build record in `CORRESPONDING_SOURCE.md` | mpv source is GPL-2.0-or-later; this distributed combined build contains GPLv3 components and is provided under GPL-3.0-or-later — `mpv.LICENSE` |
| FFmpeg and statically linked dependencies | `ffmpeg.exe` | `N-121764-g88b676105`; configured with `--enable-gpl --enable-version3` | **GPL-3.0-or-later** — `ffmpeg.LICENSE` |
| yt-dlp | `yt-dlp.exe` | `2025.12.08` | The Unlicense — `yt-dlp.LICENSE` |
| yt-dlp HiAnime extractor | `yt-dlp-plugins/yt-dlp-hianime-master/` | `3.0.0` | The Unlicense — bundled `LICENSE` |
| Python embedded distribution | `portable_config/autocards/python/` | `3.13.2` | Python Software Foundation License and bundled notices — `portable_config/autocards/python/LICENSE.txt` |
| curl | `portable_config/autocards/curl.exe` | `8.12.1` | curl license — `portable_config/autocards/CURL_LICENSE.txt` |
| kuromoji.js | `portable_config/autocards/vendor/kuromoji.js` | Upstream: [takuyaa/kuromoji.js](https://github.com/takuyaa/kuromoji.js) | Apache-2.0 — `portable_config/autocards/vendor/LICENSE-2.0.txt` |
| mecab-ipadic dictionary data | `portable_config/autocards/vendor/dict/` | Distributed with kuromoji.js | Attribution and redistribution terms — `portable_config/autocards/vendor/NOTICE.md` |
| uosc, fonts, and helper binaries | `portable_config/scripts/uosc/`, `portable_config/fonts/uosc_*` | `5.8.0` | LGPL-2.1 — `portable_config/scripts/uosc/LICENSE.LGPL` |
| thumbfast | `portable_config/scripts/thumbfast.lua` | Upstream: [po5/thumbfast](https://github.com/po5/thumbfast) | MPL-2.0 — `portable_config/scripts/thumbfast.LICENSE` |
| mpv installer scripts and icon | `installer/mpv-install.bat`, `installer/mpv-uninstall.bat`, `installer/mpv-icon.ico` | Derived from [rossy/mpv-install](https://github.com/rossy/mpv-install), packaged by [shinchiro/mpv-packaging](https://github.com/shinchiro/mpv-packaging) | ISC — `installer/LICENSE` |
| mpv manual | `doc/manual.pdf` | Generated from mpv documentation; source commit is recorded in `CORRESPONDING_SOURCE.md` | GPL-2.0-or-later; distributed combined materials use `mpv.LICENSE` |

## FFmpeg correction

Earlier AutoCard revisions placed the LGPL-2.1 text in `ffmpeg.LICENSE`. Inspection of the bundled
binary shows both `--enable-gpl` and `--enable-version3`, including GPL libraries such as x264 and
x265. The resulting FFmpeg binary is GPL-3.0-or-later, so the adjacent license has been corrected.

## Source availability

AutoCard publishes immutable source commits, build information, and hashes in
`CORRESPONDING_SOURCE.md`. Anyone redistributing or replacing a binary must update that record and
preserve equivalent access to the exact corresponding source for as long as the binary is offered.

Project-authored Python, HTML/JavaScript, and Lua source is included in this repository. Source for
bundled uosc, thumbfast, the extractor plugin, and the project modifications is also included.

## Removed unlicensed extras

The current distribution omits the former `installer/updater.ps1`, root `updater.bat`, and
`doc/mpbindings.png`. Their public upstream locations did not contain a clear redistribution
license. They are not required to run AutoCard. Historical repository revisions containing those
files should not be redistributed without permission from their respective authors.

## No endorsement

Third-party names identify compatibility, provenance, or bundled components only. Their inclusion
does not imply sponsorship or endorsement. See [TRADEMARKS.md](TRADEMARKS.md).
