# Third-party notices

AutoCard is distributed as a portable bundle. The top-level GPL license applies to project-authored Autocards code and modifications; it does not replace the licenses of the independent programs, libraries, scripts, fonts, or data listed below.

The corresponding full license texts and required notices are included in the repository at the paths shown.

| Component | Bundled location | License / notice | Upstream |
| --- | --- | --- | --- |
| Original Autocards code by かにふぁん | `portable_config/autocards/`, `portable_config/scripts/autocards.lua` | GPL-3.0-or-later — `LICENSE` and `portable_config/autocards/LICENSE` | [One-Click Anime Cards](https://learnjapanese.moe/autocards/) |
| mpv | `mpv.exe`, `mpv.com` | License text supplied with this build — `mpv.LICENSE` | [mpv](https://mpv.io/) |
| FFmpeg | `ffmpeg.exe` | License text supplied with this build — `ffmpeg.LICENSE` | [FFmpeg](https://ffmpeg.org/) |
| yt-dlp | `yt-dlp.exe` | The Unlicense — `yt-dlp.LICENSE`; official release executables may include separately licensed bundled components described by yt-dlp upstream | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| yt-dlp HiAnime extractor plugin | `yt-dlp-plugins/yt-dlp-hianime-master/` | The Unlicense — `yt-dlp-plugins/yt-dlp-hianime-master/LICENSE` | [yt-dlp-hianime](https://github.com/pratikpatel8982/yt-dlp-hianime) |
| Python embedded distribution | `portable_config/autocards/python/` | Python Software Foundation License and bundled notices — `portable_config/autocards/python/LICENSE.txt` | [Python](https://www.python.org/) |
| curl | `portable_config/autocards/curl.exe` | curl license — `portable_config/autocards/CURL_LICENSE.txt` | [curl](https://curl.se/) |
| kuromoji.js | `portable_config/autocards/vendor/kuromoji.js`, tokenizer dictionary data | Apache License 2.0 — `portable_config/autocards/vendor/LICENSE-2.0.txt`; IPADIC attribution — `portable_config/autocards/vendor/NOTICE.md` | [kuromoji.js](https://github.com/takuyaa/kuromoji.js) |
| mecab-ipadic dictionary data | `portable_config/autocards/vendor/dict/` | Attribution and redistribution terms in `portable_config/autocards/vendor/NOTICE.md` | [mecab-ipadic](https://sourceforge.net/projects/mecab/files/mecab-ipadic/) |
| uosc and its bundled icon/texture fonts and helper binaries | `portable_config/scripts/uosc/`, `portable_config/fonts/uosc_*` | LGPL-2.1 — `portable_config/scripts/uosc/LICENSE.LGPL` | [uosc](https://github.com/tomasklaen/uosc) |
| thumbfast | `portable_config/scripts/thumbfast.lua` | MPL-2.0 — `portable_config/scripts/thumbfast.LICENSE` | [thumbfast](https://github.com/po5/thumbfast) |

## Source and build offers

This repository contains the source files for the project-authored Python, HTML/JavaScript, and Lua integration code. For independently built third-party executables, use the upstream links above to obtain their corresponding source and build instructions for the exact version you redistribute. When replacing a bundled executable, update its adjacent license text and this notice if the applicable terms change.

## No endorsement

Third-party project names and trademarks identify compatibility or redistributed components only. Their inclusion does not imply endorsement of AutoCard.
