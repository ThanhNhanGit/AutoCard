import json
import threading
import time
import bisect
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import html
import mimetypes
import random
import os
import re
import unicodedata
import zipfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = Path(__file__).parent.resolve()


def to_ms(h=0, m=0, s=0, ms=0):
    return ms + 1000 * (s + 60 * (m + 60 * h))


def parse_srt(srt):
    """Parse SRT subtitles without assuming a specific newline style or that
    every cue has a numeric sequence line.

    The original parser split only on ``\n\n`` and unpacked every block as
    ``index, timestamp, text``. A slightly unusual FFmpeg/Windows SRT export
    could therefore parse as zero cues or raise on the whole file.
    """

    def parse_ts(ts):
        ts = ts.strip().replace(".", ",")
        hh, mm, rest = ts.split(":", 2)
        ss, fraction = rest.split(",", 1)
        # Normalize 1/2/3+ fractional digits to milliseconds.
        fraction = re.sub(r"\D.*$", "", fraction)
        ms = int((fraction + "000")[:3])
        hh, mm, ss = int(hh), int(mm), int(ss)
        return to_ms(hh, mm, ss, ms), f"{hh}:{mm:02}:{round(ss + ms / 1000):02}"

    normalized = (
        str(srt)
        .replace("\ufeff", "")
        .replace("\x00", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    cues = []
    blocks = re.split(r"\n[ \t]*\n+", normalized.strip())
    tag_re = re.compile(r"\{\\[^}]*\}")

    for block in blocks:
        raw_lines = block.split("\n")
        timing_index = next(
            (i for i, line in enumerate(raw_lines) if "-->" in line),
            None,
        )
        if timing_index is None:
            continue

        try:
            start_raw, end_raw = raw_lines[timing_index].split("-->", 1)
            end_raw = end_raw.strip().split()[0]
            start_ms, start_str = parse_ts(start_raw)
            end_ms, end_str = parse_ts(end_raw)
        except (ValueError, IndexError):
            continue

        text_lines = raw_lines[timing_index + 1 :]
        text_lines = [
            tag_re.sub("", line).replace("\\N", "\n").replace("\\n", "\n")
            for line in text_lines
        ]
        flattened = []
        for line in text_lines:
            flattened.extend(line.split("\n"))

        if not flattened:
            flattened = [""]

        cues.append([flattened, start_ms, start_str, end_ms, end_str])

    cues.sort(key=lambda cue: cue[1])
    return cues


def parse_ass(ass):
    """Parse ASS/SSA subtitle events robustly.

    Only an Events-section ``Format:`` line is used. The old implementation
    also consumed the Styles-section ``Format:`` line; with some ASS variants
    that leaves Dialogue rows mapped against the wrong columns and silently
    produces no subtitle cues.
    """

    def parse_ts(ts):
        ts = ts.strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid ASS timestamp: {ts}")
        h = int(parts[0])
        m = int(parts[1])
        sec_parts = parts[2].split(".", 1)
        s = int(sec_parts[0])
        fraction = sec_parts[1] if len(sec_parts) == 2 else "0"
        fraction = re.sub(r"\D.*$", "", fraction)
        ms = int((fraction + "000")[:3])
        return to_ms(h, m, s, ms), f"{h}:{m:02}:{round(s + ms / 1000):02}"

    normalized = (
        str(ass)
        .replace("\ufeff", "")
        .replace("\x00", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    lines = []
    format_cols = []
    section = ""

    default_event_cols = [
        "layer",
        "start",
        "end",
        "style",
        "name",
        "marginl",
        "marginr",
        "marginv",
        "effect",
        "text",
    ]

    tag_re = re.compile(r"\{[^}]*\}")

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        section_match = re.fullmatch(r"\[([^\]]+)\]", line)
        if section_match:
            section = section_match.group(1).strip().lower()
            continue

        lower = line.lower()

        if lower.startswith("format:"):
            if section in ("events", ""):
                format_cols = [
                    x.strip().lower()
                    for x in line.split(":", 1)[1].split(",")
                ]
            continue

        if not lower.startswith("dialogue:"):
            continue

        cols = format_cols or default_event_cols
        payload = line.split(":", 1)[1].lstrip()
        parts = payload.split(",", len(cols) - 1)
        if len(parts) != len(cols):
            continue

        row = dict(zip(cols, parts))
        try:
            start_ms, start_str = parse_ts(row.get("start", ""))
            end_ms, end_str = parse_ts(row.get("end", ""))
        except (ValueError, IndexError):
            continue

        subtitle_text = row.get("text", "")
        subtitle_text = tag_re.sub("", subtitle_text)
        subtitle_text = (
            subtitle_text
            .replace("\\N", "\n")
            .replace("\\n", "\n")
            .replace("\\h", " ")
        )

        lines.append([
            subtitle_text.split("\n"),
            start_ms,
            start_str,
            end_ms,
            end_str,
        ])

    lines.sort(key=lambda cue: cue[1])
    return lines


def token():
    return random.randbytes(8).hex()


DELIM = re.compile(r"(「|」|『|』|\"|\'|\.|!|\?|．|。|…|︒|！|？|︙|\s|<b>|</b>|\uFEFF)")


def normalize_str(s):
    return DELIM.sub("", s)


def strip_invisible_chars(s):
    """Drop Unicode "format" characters (bidi/joining control marks like
    U+202A LEFT-TO-RIGHT EMBEDDING, zero-width joiners, etc.) that some
    clipboard/IME paste flows silently prepend or embed in copied text.
    They're invisible in every UI the value passes through (browser input,
    Explorer's address bar, this file printed in a terminal) but break
    exact-match lookups — a Path that looks right won't resolve, a deck/field
    name that looks right won't match. None of them can legitimately appear
    in a real file path, deck name, or field name."""
    return "".join(ch for ch in s if unicodedata.category(ch) != "Cf")


ID = ""
FILE = ""
AID = None
LINES = []
NORMALIZED = []
IGNORE = set()
DELAY = 0

SUB_DEBUG = {
    "source": "",
    "content_chars": 0,
    "parser": "",
    "line_count": 0,
    "error": "",
}

OPTIONS = {
    "deck": "",
    "sentence": "",
    "expression": "",
    "picture": "",
    "audio": "",
    "prev_lines": 0,
    "next_lines": 0,
    "known_decks": "",
    "model": "",
    "freq_path": "",
}

# Option keys that are allowed to be empty without disabling the /check
# card-enrichment flow.
OPTIONAL_KEYS = {"prev_lines", "next_lines", "known_decks", "model", "freq_path"}

# Keys expected to be integers; every other key is coerced to a string.
OPTION_INT_KEYS = {"prev_lines", "next_lines"}


def normalize_options_payload(body):
    """Coerce an incoming /options POST body to the types the rest of the file
    assumes (int for OPTION_INT_KEYS, str for everything else) before merging
    it onto OPTIONS. A field that can't be coerced is dropped rather than
    poisoning OPTIONS with a value that breaks a later arithmetic/string op
    (e.g. build_card_body's `idx - prev_lines` on a string or null). String
    values also get invisible-character-stripped so a path/deck/field name
    pasted with a stray bidi-control character (a real, observed failure —
    it looks identical to the clean value everywhere it's displayed) matches
    on the filesystem / in Anki instead of silently never resolving."""
    clean = {}
    for key, value in body.items():
        if key in OPTION_INT_KEYS:
            try:
                clean[key] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            clean[key] = strip_invisible_chars("" if value is None else str(value))
    return clean

CHECK_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Known-word highlighting.
#
# A local cache of dictionary-form words the user already knows. Populated from
# Anki only on initial/daily/manual rebuild; newly mined words are appended from
# Autocards' existing /check workflow and from the batch miner below. Everything
# stays on the local Autocards port, so Yomitan / GameSentenceMiner / Manatan and
# every other app keep using the normal AnkiConnect endpoint at :8765 untouched.
# Subtitle tokenization + headword matching + N+1 detection happen in the browser
# (kuromoji.js), so the known cache only needs to ship a flat word list.
# ---------------------------------------------------------------------------
ANKI_CONNECT_URL = "http://127.0.0.1:8765"
KNOWN_CACHE_PATH = BASE / "known-words-cache.json"

KNOWN_LOCK = threading.RLock()
KNOWN_CONDITION = threading.Condition(KNOWN_LOCK)
KNOWN_NOTES = {}          # note id -> [words] pulled from Anki decks
KNOWN_MANUAL = set()      # words the user marked known/ignored by hand
KNOWN_WORDS = set()       # deduped union exposed to the browser
KNOWN_VERSION = 0
KNOWN_READY = False
KNOWN_LAST_SYNC = 0
KNOWN_LAST_ERROR = ""
KNOWN_REBUILD_LOCK = threading.Lock()

MINING_MODEL = ""         # auto-detected Anki note type for batch mining


def deck_query(deck):
    deck = str(deck).strip()
    if not deck:
        return ""
    if len(deck) >= 2 and deck[0] == '"' and deck[-1] == '"':
        return f"deck:{deck}"
    escaped = deck.replace("\\", "\\\\").replace('"', '\\"')
    return f'deck:"{escaped}"'


def parse_known_decks():
    """Return [(deck, [fields])]. Always includes the mining deck + Expression
    field first (so mined words survive a rebuild), then any user-configured
    "Deck: Field, Field" lines from the known_decks setting."""
    entries = []
    seen = set()

    def add(deck, fields):
        deck = deck.strip()
        if deck and deck not in seen:
            seen.add(deck)
            entries.append((deck, [f for f in fields if f]))

    mining = str(OPTIONS.get("deck", "")).strip()
    expression = str(OPTIONS.get("expression", "")).strip()
    if mining and expression:
        add(mining, [expression])

    raw = OPTIONS.get("known_decks", "")
    if isinstance(raw, str):
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                deck, fields = line.split(":", 1)
                add(deck, [f.strip() for f in fields.split(",")])
            else:
                # deck name only -> reuse the Expression field name
                add(line, [expression] if expression else [])

    return entries


def known_field_names():
    fields = set()
    for _deck, flds in parse_known_decks():
        fields.update(flds)
    expression = str(OPTIONS.get("expression", "")).strip()
    if expression:
        fields.add(expression)
    return fields


def current_known_scope():
    return {
        "deck": str(OPTIONS.get("deck", "")).strip(),
        "expression": str(OPTIONS.get("expression", "")).strip(),
        "known_decks": str(OPTIONS.get("known_decks", "")).strip(),
    }


def clean_known_word(value):
    if not isinstance(value, str):
        return ""
    # Preserve visible ruby base text while dropping readings and other markup.
    value = re.sub(r"<rt\b[^>]*>[\s\S]*?</rt>", "", value, flags=re.I)
    value = re.sub(r"<rp\b[^>]*>[\s\S]*?</rp>", "", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"[\u200b-\u200d\uFEFF]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def should_include_known_word(word):
    if not word or len(word) > 128:
        return False
    # Reject sentence-like values (real words never contain spaces).
    if " " in word:
        return False
    # Avoid painting single-kana particles/interjections as known words.
    if len(word) == 1 and re.fullmatch(r"[ぁ-ゖァ-ヺー]", word):
        return False
    return bool(re.search(r"[一-龯々〆ヵヶぁ-ゖァ-ヺー]", word))


def words_from_note_info(note_info, field_names):
    if not isinstance(note_info, dict):
        return []
    fields = note_info.get("fields")
    if not isinstance(fields, dict):
        return []
    words = []
    for name in field_names:
        field = fields.get(name)
        if isinstance(field, dict):
            word = clean_known_word(field.get("value", ""))
            if should_include_known_word(word):
                words.append(word)
    return list(dict.fromkeys(words))


def rebuild_known_word_set_locked():
    global KNOWN_WORDS
    words = {
        word
        for note_words in KNOWN_NOTES.values()
        for word in note_words
        if should_include_known_word(word)
    }
    words.update(w for w in KNOWN_MANUAL if should_include_known_word(w))
    KNOWN_WORDS = words


def persist_known_cache_locked():
    payload = {
        "format": 2,
        "scope": current_known_scope(),
        "version": KNOWN_VERSION,
        "refreshed_at": KNOWN_LAST_SYNC,
        "manual": sorted(KNOWN_MANUAL),
        "notes": {str(note_id): words for note_id, words in KNOWN_NOTES.items()},
    }
    temp_path = KNOWN_CACHE_PATH.with_suffix(".tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(temp_path, KNOWN_CACHE_PATH)
    except Exception as e:
        print(f"Known-word cache write failed: {e}")
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def load_known_cache():
    global KNOWN_NOTES, KNOWN_MANUAL, KNOWN_VERSION, KNOWN_READY
    global KNOWN_LAST_SYNC, KNOWN_LAST_ERROR
    try:
        with open(KNOWN_CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("scope") != current_known_scope():
            return
        raw_notes = payload.get("notes", {})
        notes = {}
        if isinstance(raw_notes, dict):
            for raw_id, raw_words in raw_notes.items():
                try:
                    note_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if not isinstance(raw_words, list):
                    continue
                words = [clean_known_word(v) for v in raw_words]
                words = [v for v in words if should_include_known_word(v)]
                if words:
                    notes[note_id] = list(dict.fromkeys(words))
        raw_manual = payload.get("manual", [])
        manual = set()
        if isinstance(raw_manual, list):
            for v in raw_manual:
                w = clean_known_word(v)
                if should_include_known_word(w):
                    manual.add(w)
        with KNOWN_CONDITION:
            KNOWN_NOTES = notes
            KNOWN_MANUAL = manual
            rebuild_known_word_set_locked()
            KNOWN_VERSION = max(1, int(payload.get("version", 1)))
            KNOWN_LAST_SYNC = int(payload.get("refreshed_at", 0) or 0)
            KNOWN_READY = True
            KNOWN_LAST_ERROR = ""
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Known-word cache read failed: {e}")


def clear_known_cache():
    global KNOWN_NOTES, KNOWN_WORDS, KNOWN_VERSION, KNOWN_READY, KNOWN_LAST_SYNC
    with KNOWN_CONDITION:
        KNOWN_NOTES = {}
        # KNOWN_MANUAL is intentionally kept across scope changes.
        KNOWN_VERSION += 1
        KNOWN_READY = False
        KNOWN_LAST_SYNC = 0
        rebuild_known_word_set_locked()
        persist_known_cache_locked()
        KNOWN_CONDITION.notify_all()


def replace_known_notes(note_infos, field_names):
    global KNOWN_NOTES, KNOWN_VERSION, KNOWN_READY, KNOWN_LAST_SYNC, KNOWN_LAST_ERROR
    next_notes = {}
    for note_info in note_infos:
        if not isinstance(note_info, dict):
            continue
        note_id = note_info.get("noteId")
        if not isinstance(note_id, int) or note_id <= 0:
            continue
        words = words_from_note_info(note_info, field_names)
        if words:
            next_notes[note_id] = words

    with KNOWN_CONDITION:
        KNOWN_NOTES = next_notes
        rebuild_known_word_set_locked()
        KNOWN_VERSION += 1
        KNOWN_READY = True
        KNOWN_LAST_SYNC = int(time.time())
        KNOWN_LAST_ERROR = ""
        persist_known_cache_locked()
        KNOWN_CONDITION.notify_all()


def append_known_expression(note_id, expression):
    """Append the exact Expression already present in cardsInfo. Piggybacks on
    Autocards' existing new-card detector — no extra AnkiConnect request."""
    global KNOWN_VERSION, KNOWN_READY, KNOWN_LAST_SYNC, KNOWN_LAST_ERROR

    if not isinstance(note_id, int) or note_id <= 0:
        return False

    word = clean_known_word(expression)
    if not should_include_known_word(word):
        return False

    with KNOWN_CONDITION:
        words = [word]
        if KNOWN_NOTES.get(note_id) == words:
            return False

        KNOWN_NOTES[note_id] = words
        rebuild_known_word_set_locked()
        KNOWN_VERSION += 1
        KNOWN_READY = True
        KNOWN_LAST_SYNC = int(time.time())
        KNOWN_LAST_ERROR = ""
        persist_known_cache_locked()
        KNOWN_CONDITION.notify_all()
        return True


def mark_known_word(word, known):
    """Manually add/remove a word from the known set (Migaku-style word status).
    Also used to 'ignore' character names so they stop breaking N+1 counts."""
    global KNOWN_VERSION, KNOWN_LAST_ERROR
    word = clean_known_word(word)
    if not should_include_known_word(word):
        return False

    with KNOWN_CONDITION:
        if known:
            if word in KNOWN_MANUAL:
                return False
            KNOWN_MANUAL.add(word)
        else:
            if word not in KNOWN_MANUAL:
                return False
            KNOWN_MANUAL.discard(word)
        rebuild_known_word_set_locked()
        KNOWN_VERSION += 1
        KNOWN_LAST_ERROR = ""
        persist_known_cache_locked()
        KNOWN_CONDITION.notify_all()
        return True


def full_sync_known_words():
    global KNOWN_LAST_ERROR
    entries = parse_known_decks()
    field_names = known_field_names()
    if not entries or not field_names:
        with KNOWN_CONDITION:
            KNOWN_LAST_ERROR = "Set Mining Deck and Expression Field first"
            KNOWN_CONDITION.notify_all()
        return

    all_ids = []
    seen = set()
    for deck, _fields in entries:
        query = deck_query(deck)
        if not query:
            continue
        note_ids = invoke("findNotes", query=query)
        if note_ids is None or isinstance(note_ids, Exception):
            raise RuntimeError(str(note_ids or "AnkiConnect is unavailable"))
        for note_id in note_ids:
            if note_id not in seen:
                seen.add(note_id)
                all_ids.append(note_id)

    note_infos = []
    chunk_size = 100
    for i in range(0, len(all_ids), chunk_size):
        chunk = all_ids[i : i + chunk_size]
        result = invoke("notesInfo", notes=chunk)
        if result is None or isinstance(result, Exception):
            raise RuntimeError(str(result or "Unable to read notes from Anki"))
        note_infos.extend(result)

    replace_known_notes(note_infos, field_names)
    print(f"Known-word cache rebuilt: {len(KNOWN_WORDS)} words from {len(all_ids)} notes")


def start_known_rebuild():
    if KNOWN_REBUILD_LOCK.locked():
        return False

    def worker():
        global KNOWN_LAST_ERROR, KNOWN_VERSION
        if not KNOWN_REBUILD_LOCK.acquire(blocking=False):
            return
        try:
            full_sync_known_words()
        except Exception as e:
            with KNOWN_CONDITION:
                KNOWN_LAST_ERROR = str(e)
                KNOWN_VERSION += 1
                KNOWN_CONDITION.notify_all()
            print(f"Known-word rebuild failed: {e}")
        finally:
            KNOWN_REBUILD_LOCK.release()

    threading.Thread(target=worker, name="known-word-rebuild", daemon=True).start()
    return True


def known_snapshot(include_words=True):
    with KNOWN_LOCK:
        payload = {
            "version": KNOWN_VERSION,
            "ready": KNOWN_READY,
            "count": len(KNOWN_WORDS),
            "last_sync": KNOWN_LAST_SYNC,
            "error": KNOWN_LAST_ERROR,
            # Headword matching + N+1 happen browser-side via kuromoji.js.
            "match_mode": "headword",
        }
        if include_words:
            payload["words"] = sorted(KNOWN_WORDS, key=lambda v: (-len(v), v))
        return payload


def wait_for_known_version(version, timeout=25.0):
    with KNOWN_CONDITION:
        if KNOWN_VERSION == version:
            KNOWN_CONDITION.wait(timeout)
        return KNOWN_VERSION


def known_cache_is_stale(max_age_seconds=24 * 60 * 60):
    with KNOWN_LOCK:
        return (
            not KNOWN_READY
            or KNOWN_LAST_SYNC <= 0
            or time.time() - KNOWN_LAST_SYNC >= max_age_seconds
        )


# ---------------------------------------------------------------------------
# Frequency-band coloring.
#
# Parses a Yomitan frequency dictionary (a .zip, a folder of term_meta_bank_*.json
# files, or a single such .json) into term -> rank (1 = most common) and ships it
# to the browser, which tints unknown words by how common they are so the most
# worthwhile mining candidates stand out. Rank-based dicts keep their own ranks;
# occurrence-count dicts are converted to positional ranks. Purely local — no
# network or Anki calls.
# ---------------------------------------------------------------------------
FREQ_CACHE_PATH = BASE / "frequency-cache.json"
FREQ_TOPX = 30000

FREQ_LOCK = threading.RLock()
FREQ_RANKS = {}
FREQ_VERSION = 0
FREQ_READY = False
FREQ_LAST_ERROR = ""
FREQ_SCOPE = ""            # freq_path this cache was built from
FREQ_REBUILD_LOCK = threading.Lock()

# Common words used to detect whether a dict's values are ranks (small = common)
# or occurrence counts (large = common).
FREQ_SENTINELS = ["の", "する", "いる", "ない", "これ", "人", "事", "思う",
                  "見る", "時", "なる", "言う", "私", "自分"]


def current_freq_scope():
    path = strip_invisible_chars(str(OPTIONS.get("freq_path", ""))).strip()
    # Windows "Copy as path" wraps the path in double quotes; strip surrounding
    # quotes (and any leftover whitespace) so the file actually resolves.
    if len(path) >= 2 and path[0] in "\"'" and path[-1] == path[0]:
        path = path[1:-1].strip()
    return path


def _extract_freq_value(data):
    """Pull an integer frequency/rank out of a Yomitan term-meta value, which may
    be a number, a numeric string, or a nested object with value/frequency keys."""
    if isinstance(data, bool):
        return None
    if isinstance(data, (int, float)):
        v = int(data)
        return v if v >= 0 else None
    if isinstance(data, str):
        m = re.search(r"\d[\d,]*", data)
        return int(m.group().replace(",", "")) if m else None
    if isinstance(data, dict):
        for key in ("value", "frequency", "freq", "rank"):
            if key in data:
                v = _extract_freq_value(data[key])
                if v is not None:
                    return v
        if "displayValue" in data:
            return _extract_freq_value(data["displayValue"])
    return None


def _iter_term_meta_payloads(path):
    p = Path(path)
    if p.is_dir():
        for f in sorted(p.glob("term_meta_bank_*.json")):
            try:
                yield f.read_bytes()
            except OSError:
                continue
    elif p.is_file() and p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if re.search(r"term_meta_bank_[^/]*\.json$", name):
                    yield z.read(name)
    elif p.is_file() and p.suffix.lower() == ".json":
        yield p.read_bytes()
    else:
        raise FileNotFoundError(f"No frequency dictionary at {path}")


def parse_frequency_source(path):
    """Return {term: [min_value, max_value]} from a Yomitan frequency dict."""
    raw = {}
    found_any = False
    for payload in _iter_term_meta_payloads(path):
        try:
            entries = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            # Yomitan term-meta frequency row: [term, "freq", data]
            if not isinstance(entry, (list, tuple)) or len(entry) < 3:
                continue
            if entry[1] != "freq":
                continue
            term = entry[0]
            if not isinstance(term, str) or not term:
                continue
            value = _extract_freq_value(entry[2])
            if value is None:
                continue
            found_any = True
            cur = raw.get(term)
            if cur is None:
                raw[term] = [value, value]
            else:
                if value < cur[0]:
                    cur[0] = value
                if value > cur[1]:
                    cur[1] = value
    if not found_any:
        raise ValueError(
            "No frequency entries found (is this a Yomitan frequency dictionary?)"
        )
    return raw


def _median(values):
    values = sorted(values)
    n = len(values)
    if n == 0:
        return 0
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


def normalize_freq_ranks(raw, topx=FREQ_TOPX):
    """Convert raw {term: [min, max]} into {term: rank} (rank 1 = most common),
    capped at topx. Auto-detects rank-based vs occurrence-count dictionaries."""
    if not raw:
        return {}

    all_mins = sorted(v[0] for v in raw.values())
    sentinel_mins = [raw[t][0] for t in FREQ_SENTINELS if t in raw]
    ascending = True
    if sentinel_mins and all_mins:
        sent_med = _median(sentinel_mins)
        below = bisect.bisect_left(all_mins, sent_med)
        # Rank-based: common sentinels sit near the small-value end.
        ascending = (below / len(all_mins)) < 0.5

    ranks = {}
    if ascending:
        # Value is already a rank; keep each term's best (smallest) value.
        for term, (mn, _mx) in raw.items():
            if mn <= topx:
                ranks[term] = mn if mn >= 1 else 1
    else:
        # Occurrence counts; assign positional ranks by descending count.
        ordered = sorted(raw.items(), key=lambda kv: -kv[1][1])
        for pos, (term, _v) in enumerate(ordered, 1):
            if pos > topx:
                break
            ranks[term] = pos
    return ranks


def persist_freq_cache_locked():
    payload = {
        "format": 1,
        "scope": FREQ_SCOPE,
        "version": FREQ_VERSION,
        "topx": FREQ_TOPX,
        "ranks": FREQ_RANKS,
    }
    tmp = FREQ_CACHE_PATH.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, FREQ_CACHE_PATH)
    except Exception as e:
        print(f"Frequency cache write failed: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def load_freq_cache():
    global FREQ_RANKS, FREQ_VERSION, FREQ_READY, FREQ_SCOPE, FREQ_LAST_ERROR
    try:
        with open(FREQ_CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"Frequency cache read failed: {e}")
        return
    if payload.get("scope") != current_freq_scope():
        return
    ranks = payload.get("ranks")
    if not isinstance(ranks, dict):
        return
    clean = {}
    for term, rank in ranks.items():
        if isinstance(term, str) and isinstance(rank, int) and rank >= 1:
            clean[term] = rank
    with FREQ_LOCK:
        FREQ_RANKS = clean
        FREQ_SCOPE = str(payload.get("scope", ""))
        FREQ_VERSION = max(1, int(payload.get("version", 1)))
        FREQ_READY = True
        FREQ_LAST_ERROR = ""


def full_sync_frequency():
    global FREQ_RANKS, FREQ_VERSION, FREQ_READY, FREQ_SCOPE, FREQ_LAST_ERROR
    path = current_freq_scope()
    if not path:
        with FREQ_LOCK:
            FREQ_RANKS = {}
            FREQ_READY = False
            FREQ_SCOPE = ""
            FREQ_LAST_ERROR = ""
            FREQ_VERSION += 1
            persist_freq_cache_locked()
        return

    raw = parse_frequency_source(path)          # may raise
    ranks = normalize_freq_ranks(raw)
    with FREQ_LOCK:
        FREQ_RANKS = ranks
        FREQ_SCOPE = path
        FREQ_READY = True
        FREQ_LAST_ERROR = ""
        FREQ_VERSION += 1
        persist_freq_cache_locked()
    print(f"Frequency dictionary loaded: {len(ranks)} ranked terms (topX {FREQ_TOPX}) from {path}")


def start_freq_rebuild():
    if FREQ_REBUILD_LOCK.locked():
        return False

    def worker():
        global FREQ_LAST_ERROR, FREQ_VERSION, FREQ_READY
        if not FREQ_REBUILD_LOCK.acquire(blocking=False):
            return
        try:
            full_sync_frequency()
        except Exception as e:
            with FREQ_LOCK:
                FREQ_LAST_ERROR = str(e)
                FREQ_READY = False
                FREQ_VERSION += 1
            print(f"Frequency load failed: {e}")
        finally:
            FREQ_REBUILD_LOCK.release()

    threading.Thread(target=worker, name="frequency-rebuild", daemon=True).start()
    return True


def freq_snapshot(include_ranks=False):
    with FREQ_LOCK:
        payload = {
            "version": FREQ_VERSION,
            "ready": FREQ_READY,
            "building": FREQ_REBUILD_LOCK.locked(),
            "enabled": bool(current_freq_scope()),
            "count": len(FREQ_RANKS),
            "topx": FREQ_TOPX,
            "error": FREQ_LAST_ERROR,
        }
        if include_ranks:
            # FREQ_RANKS is only ever replaced (never mutated in place), so
            # returning the reference is safe to serialize outside the lock.
            payload["ranks"] = FREQ_RANKS
        return payload


def _decode_subtitle_bytes(data):
    """Decode subtitle bytes using practical Windows/Japanese fallbacks."""
    if not isinstance(data, (bytes, bytearray)):
        return str(data) if data is not None else ""

    for encoding in ("utf-8-sig", "utf-16", "cp932"):
        try:
            return bytes(data).decode(encoding)
        except UnicodeDecodeError:
            continue
    return bytes(data).decode("utf-8", errors="replace")


def read_subtitle_file(path):
    try:
        return _decode_subtitle_bytes(Path(path).read_bytes())
    except Exception as e:
        print(f"Error reading subtitle file {path}: {e}")
        return None


def _write_subtitle_debug_copy(content):
    try:
        debug_path = BASE / "autocards-subtitle-debug.txt"
        with open(debug_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(content or "")
        return str(debug_path)
    except Exception:
        return ""


def load_subs_content(content, source="unknown"):
    global ID, LINES, NORMALIZED, SUB_DEBUG

    decoded = _decode_subtitle_bytes(content)
    decoded = (
        decoded
        .replace("\ufeff", "")
        .replace("\x00", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    ID = ""
    LINES = []
    NORMALIZED = []
    clear_merges()
    SUB_DEBUG = {
        "source": source,
        "content_chars": len(decoded),
        "parser": "",
        "line_count": 0,
        "error": "",
    }

    if not decoded.strip():
        SUB_DEBUG["error"] = "Subtitle content was empty"
        print(f"Subtitle load failed ({source}): content was empty")
        return False

    looks_ass = bool(
        re.search(r"(?im)^\s*\[(script info|events)\]\s*$", decoded)
        or re.search(r"(?im)^\s*dialogue\s*:", decoded)
    )
    parsers = (
        [("ass", parse_ass), ("srt", parse_srt)]
        if looks_ass
        else [("srt", parse_srt), ("ass", parse_ass)]
    )

    errors = []
    for parser_name, parser in parsers:
        try:
            parsed = parser(decoded)
        except Exception as e:
            errors.append(f"{parser_name}: {e}")
            continue

        if parsed:
            ID = token()
            LINES = parsed
            NORMALIZED = [normalize_str("".join(line[0])) for line in LINES]
            SUB_DEBUG.update({
                "parser": parser_name,
                "line_count": len(LINES),
                "error": "",
            })
            print(
                f"Loaded {len(LINES)} subtitle lines "
                f"with {parser_name.upper()} parser from {source}"
            )
            return True

        errors.append(f"{parser_name}: parsed 0 cues")

    debug_copy = _write_subtitle_debug_copy(decoded)
    detail = "; ".join(errors)
    if debug_copy:
        detail += f"; payload saved to {debug_copy}"
    SUB_DEBUG["error"] = detail
    print(f"Subtitle load failed ({source}): {detail}")
    return False


def request(action, **params):
    return {"action": action, "params": params, "version": 6}


def invoke(action, **params):
    req_json = json.dumps(request(action, **params)).encode("utf-8")
    try:
        r = json.load(
            urllib.request.urlopen(
                urllib.request.Request(ANKI_CONNECT_URL, req_json), timeout=15
            )
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # ValueError covers json.JSONDecodeError from a malformed response body,
        # so callers always get None instead of an uncaught parse exception
        # skipping their temp-file cleanup (take_screenshot/take_audio).
        return None

    if len(r) != 2:
        return None
    if "error" not in r:
        return None
    if "result" not in r:
        return None
    if r["error"] is not None:
        return Exception(r["error"])

    return r["result"]


def invoke_status(action, **params):
    """Like invoke(), but returns (ok, result) so a SUCCESSFUL call whose
    result is legitimately null can be told apart from a FAILED one.

    invoke() collapses both into None: AnkiConnect returns {"result": null,
    "error": null} on success for actions like updateNote, and invoke() also
    returns None for a network error / malformed response. Anything that
    needs to know whether a write actually landed must use this instead —
    treating success-null as failure (or failure as success) is what left
    mined cards either stuck retrying forever or silently un-enriched."""
    req_json = json.dumps(request(action, **params)).encode("utf-8")
    try:
        r = json.load(
            urllib.request.urlopen(
                urllib.request.Request(ANKI_CONNECT_URL, req_json), timeout=15
            )
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return False, e

    if not isinstance(r, dict) or "error" not in r or "result" not in r:
        return False, Exception(f"Malformed AnkiConnect response: {r!r}")
    if r["error"] is not None:
        return False, Exception(r["error"])

    return True, r["result"]


MPV_PATH = BASE / "../../mpv.exe"
MPV = str(MPV_PATH) if MPV_PATH.exists() else "mpv"

FFMPEG_PATH = BASE / "../../ffmpeg.exe"
FFMPEG = str(FFMPEG_PATH) if FFMPEG_PATH.exists() else "ffmpeg"


def extract_internal_subs(video_path, stream_index, fmt="srt"):
    """Extract one embedded subtitle stream as text."""
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        cmd = [
            FFMPEG,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-map",
            f"0:{stream_index}",
            "-f",
            fmt,
            "-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            startupinfo=startupinfo,
            timeout=CAPTURE_TIMEOUT,
        )
        stderr = _decode_subtitle_bytes(result.stderr).strip()

        if result.returncode != 0:
            print(f"FFmpeg subtitle extraction failed ({fmt}, stream {stream_index}): {stderr}")
            return None

        output = _decode_subtitle_bytes(result.stdout)
        print(
            f"FFmpeg extracted {len(output)} subtitle characters "
            f"as {fmt} from stream {stream_index}"
        )
        return output
    except Exception as e:
        print(f"Subtitle extraction failed ({fmt}, stream {stream_index}): {e}")
        return None


# A single frame grab or a few seconds of audio takes ~1-3s; anything past
# this is mpv wedged (an unreadable stream, a network path that stalled, a
# seek that never completes), not slow progress.
CAPTURE_TIMEOUT = 60


def run_capture(cmd, what):
    """Run an mpv/ffmpeg capture with a hard timeout.

    Without one, a wedged mpv blocks its caller forever. Since captures run
    inside check() while it holds CHECK_LOCK, a single hung mpv permanently
    stops ALL card enrichment for the rest of the session — silently, since
    every later check() just sees the lock held and returns. Killing the
    capture instead turns that into one failed card that gets retried."""
    try:
        subprocess.run(cmd, timeout=CAPTURE_TIMEOUT)
        return True
    except subprocess.TimeoutExpired:
        debug_log(f"run_capture: {what} timed out after {CAPTURE_TIMEOUT}s, killed")
        return False
    except Exception as e:
        debug_log(f"run_capture: {what} failed: {e!r}")
        return False


def _store_media(file, path, kind):
    """Upload a just-captured media file to Anki and clean up the temp copy.

    Returns the stored filename, or None if the capture or the upload failed.
    Callers MUST treat None as "no media" and refuse to write it into a note:
    formatting None into '<img src="{}">' produces a literal <img src="None">,
    which is a non-empty field, which drops the card out of the
    "Picture: SentenceAudio:" retry query forever — a card left permanently
    with no image and no audio, never looked at again. That is exactly the
    failure this whole path has to avoid."""
    if not os.path.exists(path):
        # mpv exited without producing a file (bad seek, unreadable source,
        # codec failure). os.remove() below would raise FileNotFoundError.
        debug_log(f"_store_media: mpv produced no {kind} at {path}")
        return None

    try:
        if os.path.getsize(path) == 0:
            debug_log(f"_store_media: {kind} at {path} is empty")
            return None

        ok, result = invoke_status("storeMediaFile", filename=file, path=path)
        if not ok:
            debug_log(f"_store_media: storeMediaFile failed for {kind} {file}: {result!r}")
            return None
        if not isinstance(result, str) or not result:
            debug_log(f"_store_media: storeMediaFile gave no filename for {kind} {file}: {result!r}")
            return None
        return result
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def take_screenshot(src, start, end):
    file = f"autocards-{token()}.webp"
    path = str(BASE / file)

    run_capture(
        [
            MPV,
            src,
            "--no-config",
            "--audio=no",
            "--no-ocopy-metadata",
            "--no-sub",
            "--frames=1",
            "--dscale=box",
            "--window-scale=0.5",
            "--screenshot-webp-quality=70",
            "--screenshot-webp-compression=3",
            f"--start={0.75 * start + 0.25 * end:.3f}",
            "-o",
            path,
        ],
        "screenshot",
    )

    return _store_media(file, path, "screenshot")


def take_audio(src, start, end, aid=None):
    file = f"autocards-{token()}.mp3"
    path = str(BASE / file)

    cmd = [
        MPV,
        src,
        "--no-config",
        "--video=no",
        "--no-ocopy-metadata",
        "--no-sub",
        "--audio-channels=1",
        f"--start={start:.3f}",
        f"--length={end - start:.3f}",
    ]
    if aid is not None:
        cmd.append(f"--aid={aid}")
    cmd.extend(["-o", path])

    run_capture(cmd, "audio")

    return _store_media(file, path, "audio")


def _extract_audio_segment(src, start, end, aid, out_path):
    cmd = [
        MPV, src, "--no-config", "--video=no", "--no-ocopy-metadata", "--no-sub",
        "--audio-channels=1", f"--start={start:.3f}", f"--length={max(0.05, end - start):.3f}",
    ]
    if aid is not None:
        cmd.append(f"--aid={aid}")
    cmd.extend(["-o", out_path])
    run_capture(cmd, "audio segment")


def take_audio_merged(src, segments, aid=None):
    """Extract each (start, end) segment and concatenate them, dropping the
    silence/gaps between subtitle cues so a merged multi-line clip stays tight."""
    segments = [(s, e) for s, e in segments if e > s]
    if not segments:
        return None
    if len(segments) == 1:
        return take_audio(src, segments[0][0], segments[0][1], aid=aid)

    temp_files = []
    for start, end in segments:
        tmp = BASE / f"autocards-seg-{token()}.mp3"
        _extract_audio_segment(src, start, end, aid, str(tmp))
        if tmp.exists() and tmp.stat().st_size > 0:
            temp_files.append(tmp)

    if not temp_files:
        return None

    final = temp_files[0]
    cleanup = list(temp_files)
    if len(temp_files) > 1:
        final = BASE / f"autocards-{token()}.mp3"
        inputs = []
        for tf in temp_files:
            inputs += ["-i", str(tf)]
        n = len(temp_files)
        filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            subprocess.run(
                [FFMPEG, "-y", "-hide_banner", *inputs, "-filter_complex", filt, "-map", "[out]", "-ac", "1", str(final)],
                startupinfo=startupinfo,
                timeout=CAPTURE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            debug_log("take_audio_merged: ffmpeg concat timed out, killed")
        cleanup.append(final)

    result = None
    if final.exists() and final.stat().st_size > 0:
        result = invoke("storeMediaFile", filename=final.name, path=str(final))

    for tf in cleanup:
        try:
            tf.unlink()
        except OSError:
            pass
    return result


def build_card_body(idx, expression=None, original_sentence=None, lines=None, file=None, aid=None, delay=None):
    """Build the sentence HTML (with bolded target) and capture screenshot +
    audio for the line window around idx. Shared by the /check enricher and the
    batch miner.

    `lines`/`file`/`aid`/`delay` default to the live globals, but /check passes
    its own snapshot taken at the start of the request: LINES/FILE/AID/DELAY are
    all reassigned wholesale (never mutated in place) by a concurrent /init or
    /update, so idx — computed earlier against that snapshot — stays valid, and
    the screenshot/audio come from the right video, only if we keep using the
    same snapshot instead of re-reading the globals after the AnkiConnect round
    trips in between."""
    if lines is None:
        lines = LINES
    prev_lines = OPTIONS.get("prev_lines", 0)
    next_lines = OPTIONS.get("next_lines", 0)

    start_idx = max(0, idx - prev_lines)
    end_idx = min(len(lines) - 1, idx + next_lines)

    lines_subset = lines[start_idx : end_idx + 1]

    sentence = "<br/>".join("<br/>".join(line[0]) for line in lines_subset)

    words_to_bold = set()
    if expression:
        words_to_bold.add(expression)

    if original_sentence:
        words_to_bold.update(
            filter(None, re.findall(r"<b>(.*?)</b>", original_sentence))
        )

    if words_to_bold:
        sorted_words = sorted(words_to_bold, key=len, reverse=True)
        pattern_str = "|".join(re.escape(w) for w in sorted_words)
        sentence = re.sub(pattern_str, lambda m: f"<b>{m.group(0)}</b>", sentence)

    delay = DELAY if delay is None else delay
    start = lines_subset[0][1] / 1000 + delay
    end = lines_subset[-1][3] / 1000 + delay

    src = FILE if file is None else file
    aid = AID if aid is None else aid
    picture = take_screenshot(src, start, end)
    sound = take_audio(src, start, end, aid=aid)

    return sentence, picture, sound


def update_note(note_id, idx, expression=None, original_sentence=None, lines=None, file=None, aid=None, delay=None):
    """Returns True on a confirmed AnkiConnect write, False otherwise (e.g. a
    transient failure while Anki's Browse editor has this exact note open,
    observed in practice). Callers must check this before treating the card
    as done — invoke() can silently return None/Exception on failure, and
    blindly treating that as success left cards permanently stuck with only
    their original Yomitan-mined text and no audio/screenshot, never retried
    again since nothing signaled the enrichment hadn't actually happened."""
    sentence, picture, sound = build_card_body(idx, expression, original_sentence, lines=lines, file=file, aid=aid, delay=delay)

    if not picture or not sound:
        # Leave the fields EMPTY so this card stays in the retry query and
        # gets another attempt, instead of being written as <img src="None">
        # and silently dropping out of it forever.
        debug_log(f"update_note({note_id}): missing media (picture={picture!r} sound={sound!r}), not writing")
        return False

    ok, result = invoke_status(
        "updateNote",
        note={
            "id": note_id,
            "fields": {
                OPTIONS["sentence"]: sentence,
                OPTIONS["picture"]: f'<img src="{picture}">',
                OPTIONS["audio"]: f"[sound:{sound}]",
            },
        },
    )
    if not ok:
        debug_log(f"update_note({note_id}): updateNote failed: {result!r}")
        return False

    print("updated note:", note_id)
    return True


def detect_mining_model():
    """Auto-detect the note type used in the mining deck so the batch miner can
    addNote without extra configuration. A manual `model` option overrides."""
    global MINING_MODEL

    configured = str(OPTIONS.get("model", "")).strip()
    if configured:
        MINING_MODEL = configured
        return MINING_MODEL
    if MINING_MODEL:
        return MINING_MODEL

    query = deck_query(OPTIONS.get("deck", ""))
    if not query:
        return ""
    ids = invoke("findCards", query=query)
    if not ids or isinstance(ids, Exception):
        return ""
    info = invoke("cardsInfo", cards=[ids[0]])
    if not info or isinstance(info, Exception):
        return ""
    MINING_MODEL = info[0].get("modelName", "")
    return MINING_MODEL


def build_merged_card_body(indices, expression=None, lines=None, file=None, aid=None, delay=None):
    """Build ONE card body spanning several subtitle lines: their text joined,
    plus a screenshot + audio covering the first line's start to the last line's
    end. Used when a sentence is split across cues (Migaku multi-select).

    See build_card_body's docstring for why `lines`/`file`/`aid`/`delay` accept
    an explicit snapshot instead of always reading the live globals."""
    if lines is None:
        lines = LINES
    sorted_idx = sorted({i for i in indices if 0 <= i < len(lines)})
    if not sorted_idx:
        return None

    lines_subset = [lines[i] for i in sorted_idx]
    sentence = "<br/>".join("<br/>".join(line[0]) for line in lines_subset)
    if expression:
        sentence = re.sub(re.escape(expression), lambda m: f"<b>{m.group(0)}</b>", sentence)

    delay = DELAY if delay is None else delay
    # One clip per selected line, concatenated — so gaps between cues are dropped
    # and the audio matches the joined sentence instead of spanning dead air.
    segments = [(lines[i][1] / 1000 + delay, lines[i][3] / 1000 + delay) for i in sorted_idx]

    src = FILE if file is None else file
    aid = AID if aid is None else aid
    # Screenshot from the first selected line (where the target word usually sits).
    picture = take_screenshot(src, segments[0][0], segments[0][1])
    sound = take_audio_merged(src, segments, aid=aid)
    return sentence, picture, sound


def mine_lines(items, merge=False):
    """Create Anki cards for the selected subtitle lines (Migaku-style batch).

    Each item is {index, expression}, where expression is the intended card
    front (the line's chosen / most-common unknown word). With merge=True the
    selected lines become a single card with a combined sentence + audio."""
    if not ID or not LINES:
        return {"error": "No subtitles loaded"}
    if not FILE:
        return {"error": "No video loaded"}

    deck = str(OPTIONS.get("deck", "")).strip()
    sentence_field = str(OPTIONS.get("sentence", "")).strip()
    expression_field = str(OPTIONS.get("expression", "")).strip()
    picture_field = str(OPTIONS.get("picture", "")).strip()
    audio_field = str(OPTIONS.get("audio", "")).strip()
    if not (deck and sentence_field and picture_field and audio_field):
        return {"error": "Configure deck and fields first"}

    model = detect_mining_model()
    if not model:
        return {"error": "Could not detect note type — mine one card normally first, or set the Note Type option"}

    # Strip surrounding quotes for addNote's deckName (it wants a plain name).
    deck_name = deck[1:-1] if len(deck) >= 2 and deck[0] == '"' and deck[-1] == '"' else deck

    # Collect valid (index, expression) pairs, preserving request order.
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(LINES):
            valid.append((idx, clean_known_word(item.get("expression", ""))))
    if not valid:
        return {"error": "No valid lines selected"}

    created = 0
    skipped = 0
    errors = []
    mined_words = []

    def add_note(expression, sentence, picture, sound, is_word):
        nonlocal created, skipped
        if not picture or not sound:
            # Never create a card carrying <img src="None"> / [sound:None]:
            # the fields would look populated, so /check would never revisit
            # it, leaving a permanently image-less and audio-less card.
            msg = f"Capture failed for {expression or sentence!r} (no {'image' if not picture else 'audio'})"
            debug_log(f"mine_lines: {msg}")
            errors.append(msg)
            return
        fields = {
            sentence_field: sentence,
            picture_field: f'<img src="{picture}">',
            audio_field: f"[sound:{sound}]",
        }
        if expression_field:
            fields[expression_field] = expression
        result = invoke(
            "addNote",
            note={
                "deckName": deck_name,
                "modelName": model,
                "fields": fields,
                "tags": ["autocards", "autocards-batch"],
                "options": {"allowDuplicate": False},
            },
        )
        if isinstance(result, Exception):
            if "duplicate" in str(result).lower():
                skipped += 1
            else:
                errors.append(str(result))
        elif result is None:
            errors.append("AnkiConnect unavailable")
        else:
            created += 1
            # Only real target words become "known"; never a whole-sentence fallback.
            if is_word and should_include_known_word(expression):
                mined_words.append((result, expression))

    if merge:
        indices = [idx for idx, _ in valid]
        target = next((e for _, e in valid if e), "")
        expression = target or "".join(LINES[min(indices)][0])
        body = build_merged_card_body(indices, expression)
        if body:
            add_note(expression, *body, bool(target))
    else:
        for idx, expr in valid:
            expression = expr or "".join(LINES[idx][0])
            add_note(expression, *build_card_body(idx, expression), bool(expr))

    # Newly mined targets become known immediately (dim on the next re-highlight).
    for note_id, word in mined_words:
        note_id = note_id if isinstance(note_id, int) else 0
        append_known_expression(note_id or int(time.time() * 1000) + created, word)

    return {"created": created, "skipped": skipped, "errors": errors, "merged": merge, "model": model}


# Lines the user has merged for mining: normalized combined text -> a FIFO list
# of pending line-index groups. When a card is mined (via Yomitan) whose sentence
# matches a merged group, /check enriches it with the combined sentence +
# gap-dropped audio spanning those lines. Keyed by text (the only thing /check
# can match a card against) rather than by indices, so it's a list per key, not
# a single value: two merges whose combined text happens to collide (repeated
# dialogue) each get their own pending entry instead of the second silently
# clobbering the first.
MERGE_LOCK = threading.Lock()
MERGES = {}


def merge_key(indices):
    idx = sorted({i for i in indices if isinstance(i, int) and 0 <= i < len(LINES)})
    key = normalize_str("".join("".join(LINES[i][0]) for i in idx))
    return key, idx


def register_merge(indices):
    key, idx = merge_key(indices)
    if len(idx) < 2 or not key:
        return None
    with MERGE_LOCK:
        group = MERGES.setdefault(key, [])
        if idx not in group:
            group.append(idx)
    return idx


def unregister_merge(indices):
    key, idx = merge_key(indices)
    with MERGE_LOCK:
        group = MERGES.get(key)
        if not group:
            return
        try:
            group.remove(idx)
        except ValueError:
            pass
        if not group:
            MERGES.pop(key, None)


def clear_merges():
    with MERGE_LOCK:
        MERGES.clear()


def update_note_merged(note_id, indices, expression=None, lines=None, file=None, aid=None, delay=None):
    """Returns True on a confirmed AnkiConnect write, False otherwise — see
    update_note's docstring for why this must be checked rather than assumed."""
    body = build_merged_card_body(indices, expression, lines=lines, file=file, aid=aid, delay=delay)
    if not body:
        return False
    sentence, picture, sound = body
    if not picture or not sound:
        debug_log(f"update_note_merged({note_id}): missing media (picture={picture!r} sound={sound!r}), not writing")
        return False

    ok, result = invoke_status(
        "updateNote",
        note={
            "id": note_id,
            "fields": {
                OPTIONS["sentence"]: sentence,
                OPTIONS["picture"]: f'<img src="{picture}">',
                OPTIONS["audio"]: f"[sound:{sound}]",
            },
        },
    )
    if not ok:
        debug_log(f"update_note_merged({note_id}): updateNote failed: {result!r}")
        return False

    print("updated merged note:", note_id)
    return True


DEBUG_LOG_PATH = BASE / "check-debug.log"
DEBUG_LOG_MAX_BYTES = 1024 * 1024
DEBUG_LOG_LOCK = threading.Lock()


def debug_log(msg):
    """Append a diagnostic line about the mining/enrichment path.

    Only ever called on unusual outcomes (a no-match, a failed capture, a
    failed write) — never on the normal per-poll happy path — so a healthy
    session writes almost nothing. Rotated at 1MB so a long session, or a
    card that keeps failing, can't grow this without bound."""
    try:
        with DEBUG_LOG_LOCK:
            if (
                DEBUG_LOG_PATH.exists()
                and DEBUG_LOG_PATH.stat().st_size > DEBUG_LOG_MAX_BYTES
            ):
                DEBUG_LOG_PATH.replace(DEBUG_LOG_PATH.with_suffix(".log.old"))
            with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{time.time():.3f} {msg}\n")
    except Exception:
        pass


# Enrichment retry bookkeeping: card id -> [attempts, last_attempt_ts].
# Retrying is what rescues a card from a transient failure, but retrying an
# unconditionally-broken one (misconfigured field name, unreadable video)
# every 1.5s would respawn two mpv captures per tick forever, so attempts
# back off and eventually stop.
ENRICH_ATTEMPTS = {}
ENRICH_MAX_ATTEMPTS = 6
ENRICH_BACKOFF_BASE = 3.0

# Card id -> the video that was loaded when this pending card was first seen.
# /check finds candidates with "added:1" (added today), which spans every
# episode watched today, so a card left unenriched when you move to the next
# episode would otherwise be matched against the NEW episode's subtitles and
# given a screenshot and audio from the wrong video entirely.
CARD_VIDEO = {}



def should_attempt_enrich(card_id):
    state = ENRICH_ATTEMPTS.get(card_id)
    if not state:
        return True
    attempts, last = state
    if attempts >= ENRICH_MAX_ATTEMPTS:
        return False
    # 3s, 6s, 12s, 24s, ... since the previous failed attempt.
    wait = ENRICH_BACKOFF_BASE * (2 ** (attempts - 1))
    return (time.time() - last) >= wait


def note_enrich_failed(card_id):
    attempts, _ = ENRICH_ATTEMPTS.get(card_id, (0, 0.0))
    attempts += 1
    ENRICH_ATTEMPTS[card_id] = (attempts, time.time())
    if attempts >= ENRICH_MAX_ATTEMPTS:
        debug_log(
            f"enrich: card {card_id} failed {attempts}x, giving up until restart "
            f"(check Anki field config / that the video is readable)"
        )


_BAIL_LOG_AT = {}


def debug_log_throttled(key, msg, every=30.0):
    """Log a recurring condition at most once per `every` seconds.

    check() runs ~every 1.5s, so its early-exit paths can't be logged
    unconditionally without flooding the file — but they can't be silent
    either: a silently-bailing check() is indistinguishable from a working
    one that has nothing to do, which makes 'my card never got its audio'
    impossible to diagnose."""
    now = time.time()
    if now - _BAIL_LOG_AT.get(key, 0.0) >= every:
        _BAIL_LOG_AT[key] = now
        debug_log(msg)


def check(t, focus=None):
    global IGNORE

    if not CHECK_LOCK.acquire(blocking=False):
        # Another check() is still running. Brief overlap is normal; a lock
        # held for a long time means a previous pass is wedged (a capture
        # that never returned), and nothing will be enriched until it clears.
        debug_log_throttled("lock", "check(): skipped, a previous pass still holds the lock")
        return

    try:
        if not ID:
            debug_log_throttled("noid", "check(): no subtitles loaded (ID empty) — mpv never sent /init?")
            return

        for k, v in OPTIONS.items():
            if k in OPTIONAL_KEYS:
                continue
            if not v:
                debug_log(f"check(): OPTIONS['{k}'] is empty, bailing")
                return

        # Snapshot the globals /init and /update can reassign mid-request, so
        # this call stays internally consistent end to end: idx/merged_indices
        # get computed against these local names below, and are only ever used
        # against these SAME names later (after the AnkiConnect round trips),
        # never against whatever the globals have become by then.
        lines = LINES
        normalized = NORMALIZED
        file = FILE
        aid = AID
        delay = DELAY

        BASE_QUERY = (
            f"{deck_query(OPTIONS['deck'])} added:1 {OPTIONS['picture']}: {OPTIONS['audio']}: "
        )

        ids = invoke("findCards", query=BASE_QUERY)
        if not ids or isinstance(ids, Exception):
            if isinstance(ids, Exception) or ids is None:
                debug_log(f"check(): findCards failed for query {BASE_QUERY!r}: {ids!r}")
            else:
                debug_log_throttled(
                    "nocards", f"check(): no cards awaiting media for query {BASE_QUERY!r}"
                )
            return

        end_idx = bisect.bisect_left(lines, to_ms(s=t), key=lambda v: v[1])

        # Queue of occurrences per normalized text, oldest first, so a repeated
        # subtitle line resolves each matching card to a DISTINCT occurrence
        # instead of every card colliding on whichever occurrence came last.
        subs_queue = {}
        for i, v in enumerate(normalized[:end_idx]):
            subs_queue.setdefault(v, []).append(i)

        def claim_cue(norm):
            """Find the subtitle cue a mined card came from, and claim it.

            Considers exact matches and containing matches TOGETHER, and among
            all candidates picks the one closest to the playhead. Two reasons
            they can't be separate steps with exact winning outright:

              * Yomitan captures only the sentence around the clicked word, so
                a card mined from a multi-row or multi-sentence cue holds just
                a FRAGMENT of it — the cue it belongs to contains the text
                rather than equalling it.
              * normalize_str() strips punctuation, so a fragment can exactly
                equal some unrelated cue elsewhere in the episode (「ん？」and
                「ん…」collapse to the same key). Letting that exact match win
                attached a screenshot from the wrong scene entirely.

            Preferring the latest candidate at or before the playhead resolves
            both: while watching, that is the line just played; after
            scrolling back to mine an older line, it is that older line, since
            everything after it is past the playhead. Popping the occurrence
            keeps repeated dialogue mapping distinct cards to distinct cues.
            """
            if not norm:
                return None

            # Gather every cue whose text contains this card's text.
            cands = []
            for key, idxs in subs_queue.items():
                if not idxs or norm not in key:
                    continue
                cands.extend((i, key) for i in idxs)
            if not cands:
                return None

            if focus is not None:
                # The browser told us which line the user was pointing at, so
                # take the candidate nearest it. This is the only reliable
                # signal when the user scrolls back to mine an older line:
                # the playhead is then far past it, and picking by playhead
                # would grab a later repeat of the same words instead.
                best_idx, best_key = min(cands, key=lambda c: (abs(c[0] - focus), -c[0]))
            else:
                # No hint (older page still open): fall back to the latest
                # candidate at or before the playhead, i.e. the line most
                # recently played.
                best_idx, best_key = max(cands, key=lambda c: c[0])

            subs_queue[best_key].remove(best_idx)
            return best_idx

        # Merged groups whose lines are all already revealed, as a queue per
        # key too (two merges with colliding combined text are now distinct
        # pending entries instead of one clobbering the other).
        with MERGE_LOCK:
            merged_queue = {k: list(v) for k, v in MERGES.items() if v}
        for k in list(merged_queue.keys()):
            merged_queue[k] = [g for g in merged_queue[k] if g and g[-1] < end_idx]
            if not merged_queue[k]:
                del merged_queue[k]

        notes = invoke("cardsInfo", cards=ids)
        if not notes or isinstance(notes, Exception):
            debug_log(f"check(): cardsInfo returned {notes!r} for ids {ids}")
            return

        filtered_cards = []
        consumed_groups = []
        for id, info in zip(ids, notes):
            if id in IGNORE:
                # Already enriched this session. If the card still looks
                # unenriched to Anki we would otherwise skip it forever with
                # no trace, so say so (throttled).
                debug_log_throttled("ign-%s" % id,
                    f"check(): card {id} skipped, already marked done this session")
                continue

            note_id = info.get("note")
            if not isinstance(note_id, int):
                debug_log(f"check(): card {id} info has no int note id: {info!r}")
                continue

            # Bind this pending card to the video it belongs to, and never
            # enrich it from a different one.
            first_video = CARD_VIDEO.setdefault(id, file)
            if first_video != file:
                debug_log(f"check(): card {id} belongs to {first_video!r}, not {file!r}; skipping")
                IGNORE.add(id)
                continue

            # A note whose model lacks the configured Sentence/Expression
            # field (a stray card in the mining deck, a renamed field) used
            # to raise KeyError here — outside the per-card try/except below
            # — aborting the whole pass, so every OTHER pending card in the
            # same batch silently stopped being enriched too.
            try:
                fields = info["fields"]
                sentence = fields[OPTIONS["sentence"]]["value"]
                expression = None
                if OPTIONS["expression"]:
                    expression = fields[OPTIONS["expression"]]["value"]
            except (KeyError, TypeError) as e:
                debug_log(f"check(): card {id} missing configured field ({e!r}), skipping")
                IGNORE.add(id)
                continue

            norm = normalize_str(sentence)

            # A registered merge is an explicit user intent and matches the
            # combined text exactly, so it is checked before single cues.
            merged_indices = None
            groups = merged_queue.get(norm)
            if groups:
                merged_indices = groups.pop(0)
                consumed_groups.append(merged_indices)

            idx = None
            if merged_indices is None:
                idx = claim_cue(norm)

            if idx is None and merged_indices is None:
                debug_log(f"check(): card {id} note {note_id} sentence={sentence!r} norm={norm!r} NO MATCH (end_idx={end_idx})")
                continue

            filtered_cards.append((id, note_id, idx, merged_indices, expression, sentence))

        # NOTE: consumed_groups are NOT unregistered here. A merge is only
        # forgotten once its card has actually been enriched (below) — if the
        # write fails, the group must still be in MERGES for the retry to be
        # able to rebuild the merged sentence/audio. A merged sentence spans
        # several cues, so it is not a substring of any single cue either:
        # dropping the group early would make the card unrecoverable.

        for id, note_id, idx, merged_indices, expression, sentence in filtered_cards:
            if not should_attempt_enrich(id):
                debug_log_throttled("bo-%s" % id,
                    f"check(): card {id} waiting on retry backoff "
                    f"(attempts={ENRICH_ATTEMPTS.get(id, (0, 0))[0]})")
                continue

            # cardsInfo already gave us Expression AND the note id (under
            # "note"), so update the local known-word cache and enrich the
            # note without any further AnkiConnect round trip per card.
            append_known_expression(note_id, expression)
            try:
                if merged_indices:
                    ok = update_note_merged(note_id, merged_indices, expression, lines=lines, file=file, aid=aid, delay=delay)
                else:
                    ok = update_note(note_id, idx, expression, sentence, lines=lines, file=file, aid=aid, delay=delay)
            except Exception:
                import traceback
                debug_log(f"check(): enrichment for card {id} note {note_id} raised:\n{traceback.format_exc()}")
                note_enrich_failed(id)
                continue

            # Only mark this card done once AnkiConnect confirmed the write.
            # A card whose update silently failed (e.g. a transient error, or
            # a capture that produced no media) must NOT be added here, or it
            # would never be retried again — exactly what left cards
            # permanently stuck with no audio or screenshot.
            if ok:
                IGNORE.add(id)
                ENRICH_ATTEMPTS.pop(id, None)
                # Safe to forget the merge only now that its card is written.
                if merged_indices:
                    unregister_merge(merged_indices)
            else:
                note_enrich_failed(id)
                debug_log(f"check(): card {id} note {note_id} update did not confirm, will retry")
    finally:
        CHECK_LOCK.release()


OPTIONS_PATH = BASE / "options.json"
if OPTIONS_PATH.exists():
    with open(OPTIONS_PATH, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    # Merge onto defaults so new optional keys always exist.
    OPTIONS = {**OPTIONS, **loaded}

TIME = 0, time.time()


def clock():
    return TIME[0] + min(time.time() - TIME[1], 1.0)


def find_sub(path):
    path = Path(path)
    dir = path.parent
    stem = path.stem

    return next(
        (
            f
            for f in dir.iterdir()
            if f.suffix in [".srt", ".ass"] and f.stem.startswith(stem)
        ),
        None,
    )


VENDOR_ROOT = (BASE / "vendor").resolve()


def resolve_vendor_path(url_path):
    rel = url_path[len("/vendor/") :].strip("/")
    if not rel:
        return None
    target = (VENDOR_ROOT / rel).resolve()
    if target != VENDOR_ROOT and VENDOR_ROOT not in target.parents:
        return None
    if not target.is_file():
        return None
    return target


class Server(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        t = clock()
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()

            with open(BASE / "index.html", "rb") as f:
                self.wfile.write(f.read())
        elif path == "/lines":
            self.send_response(200)
            self.send_header("Content-type", "text/json; charset=utf-8")
            self.end_headers()

            self.wfile.write(json.dumps({"id": ID, "lines": LINES}).encode())
        elif path == "/subtitle-debug":
            self._send_json({
                **SUB_DEBUG,
                "id": ID,
                "line_count": len(LINES),
                "video": FILE,
            })
        elif path == "/options":
            self.send_response(200)
            self.send_header("Content-type", "text/json; charset=utf-8")
            self.end_headers()

            self.wfile.write(json.dumps(OPTIONS).encode())
        elif path == "/update":
            self.send_response(200)
            self.send_header("Content-type", "text/json")
            self.end_headers()

            self.wfile.write(json.dumps([ID, to_ms(s=t)]).encode())
        elif path == "/known-words":
            self._send_json(known_snapshot())
        elif path == "/known-words/wait":
            params = urllib.parse.parse_qs(parsed_path.query)
            try:
                version = int(params.get("version", ["0"])[0])
            except (TypeError, ValueError):
                version = 0
            next_version = wait_for_known_version(version)
            self._send_json({"version": next_version, "changed": next_version != version})
        elif path == "/frequency":
            # Lightweight status (no ranks) — safe to poll while building.
            self._send_json(freq_snapshot(include_ranks=False))
        elif path == "/frequency/ranks":
            # Heavy payload (the full term -> rank map); fetched once when ready.
            self._send_json(freq_snapshot(include_ranks=True))
        elif path.startswith("/vendor/"):
            target = resolve_vendor_path(path)
            if target is None:
                self.send_response(404)
                self.end_headers()
                return
            ctype, _ = mimetypes.guess_type(str(target))
            if target.suffix == ".gz":
                # Serve raw gzip bytes; kuromoji.js inflates them itself, so we
                # must NOT set Content-Encoding (that would double-decompress).
                ctype = "application/octet-stream"
            elif target.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-type", ctype or "application/octet-stream")
            self.send_header("Cache-Control", "max-age=604800")
            self.end_headers()
            with open(target, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global OPTIONS, TIME, ID, FILE, DELAY, AID, MINING_MODEL, IGNORE

        sz = int(self.headers.get("Content-Length", "0") or 0)
        if sz:
            raw_body = self.rfile.read(sz)
            try:
                body = json.loads(raw_body)
            except UnicodeDecodeError:
                try:
                    # Try CP932 (Shift-JIS) which is common for Japanese Windows and uses 0x82
                    body = json.loads(raw_body.decode("cp932"))
                except Exception:
                    # Last resort: ignore errors to prevent crash
                    body = json.loads(raw_body.decode("utf-8", "ignore"))
        else:
            body = {}

        t = clock()
        path = urllib.parse.urlparse(self.path).path

        if path == "/init":
            video_path = ""
            loaded = False
            source = "no subtitle selected"

            if isinstance(body, str):
                video_path = body
                sub_file = find_sub(video_path)
                if sub_file:
                    source = f"external:{sub_file}"
                    loaded = load_subs_content(
                        read_subtitle_file(sub_file),
                        source=source,
                    )
            elif isinstance(body, dict):
                video_path = body.get("video", "")
                sub_info = body.get("sub")
                if isinstance(sub_info, dict):
                    sub_type = str(sub_info.get("type", "")).lower()

                    if sub_type == "external":
                        sub_path = sub_info.get("path")
                        source = f"external:{sub_path or 'missing path'}"
                        if sub_path and os.path.exists(sub_path):
                            loaded = load_subs_content(
                                read_subtitle_file(sub_path),
                                source=source,
                            )
                        else:
                            load_subs_content(None, source=source)

                    elif sub_type == "internal":
                        stream_index = sub_info.get("index")
                        codec = str(sub_info.get("codec", "")).lower()
                        preferred_fmt = "ass" if codec in ("ass", "ssa") else "srt"
                        source = f"internal:{stream_index}:{codec or preferred_fmt}"

                        if stream_index is not None:
                            content = extract_internal_subs(
                                video_path,
                                stream_index,
                                preferred_fmt,
                            )
                            loaded = load_subs_content(content, source=source)

                            # Some FFmpeg/codec combinations produce an odd ASS
                            # export even though conversion to SRT is valid (or
                            # vice versa). Retry the alternate text muxer before
                            # giving up.
                            if not loaded:
                                alternate_fmt = "srt" if preferred_fmt == "ass" else "ass"
                                alternate_source = (
                                    f"internal:{stream_index}:{codec or preferred_fmt}"
                                    f":retry-{alternate_fmt}"
                                )
                                alternate_content = extract_internal_subs(
                                    video_path,
                                    stream_index,
                                    alternate_fmt,
                                )
                                loaded = load_subs_content(
                                    alternate_content,
                                    source=alternate_source,
                                )
                        else:
                            load_subs_content(
                                None,
                                source=f"internal:missing-index:{codec}",
                            )
                else:
                    load_subs_content(None, source=source)
            else:
                load_subs_content(None, source="invalid /init payload")

            FILE = video_path
            AID = body.get("aid") if isinstance(body, dict) else None

            # Per-card enrichment state belongs to the video that was loaded,
            # not to the process. Without this, a card marked done (or backed
            # off, or bound to a video) stays that way across an mpv restart
            # or a switch to the next episode, and is then skipped forever
            # with the card left holding no image or audio.
            IGNORE.clear()
            ENRICH_ATTEMPTS.clear()
            CARD_VIDEO.clear()
            _BAIL_LOG_AT.clear()

            self._send_json({
                "loaded": loaded,
                "id": ID,
                "line_count": len(LINES),
                "debug": SUB_DEBUG,
            })
        elif path == "/aid":
            self.send_response(200)
            self.end_headers()

            AID = body.get("aid") if isinstance(body, dict) else None
        elif path == "/update":
            self.send_response(200)
            self.end_headers()

            TIME = body.get('time'), time.time()
            DELAY = body.get('delay')
        elif path == "/check":
            self.send_response(200)
            self.end_headers()

            focus = body.get("focus") if isinstance(body, dict) else None
            if not isinstance(focus, int) or focus < 0:
                focus = None
            check(t, focus=focus)
        elif path == "/mine":
            items = body.get("items") if isinstance(body, dict) else None
            merge = bool(body.get("merge")) if isinstance(body, dict) else False
            if not isinstance(items, list) or not items:
                self._send_json({"error": "No lines selected"}, status=400)
            else:
                self._send_json(mine_lines(items, merge=merge))
        elif path == "/merge":
            indices = body.get("indices") if isinstance(body, dict) else None
            if isinstance(indices, list):
                idx = register_merge(indices)
                self._send_json({"ok": bool(idx), "indices": idx or []})
            else:
                self._send_json({"ok": False}, status=400)
        elif path == "/unmerge":
            indices = body.get("indices") if isinstance(body, dict) else None
            if isinstance(indices, list):
                unregister_merge(indices)
            self._send_json({"ok": True})
        elif path == "/options":
            old_scope = current_known_scope()
            old_freq_scope = current_freq_scope()
            self.send_response(200)
            self.end_headers()

            OPTIONS = {**OPTIONS, **normalize_options_payload(body)} if isinstance(body, dict) else OPTIONS
            MINING_MODEL = str(OPTIONS.get("model", "")).strip()
            with open(OPTIONS_PATH, "w", encoding="utf-8") as f:
                json.dump(OPTIONS, f, ensure_ascii=False)
            if current_known_scope() != old_scope:
                clear_known_cache()
                start_known_rebuild()
            if current_freq_scope() != old_freq_scope:
                start_freq_rebuild()
        elif path == "/known-words/mark":
            word = body.get("word", "") if isinstance(body, dict) else ""
            known = bool(body.get("known", True)) if isinstance(body, dict) else True
            changed = mark_known_word(word, known)
            self._send_json({"changed": changed, "known": known})
        elif path == "/known-words/rebuild":
            started = start_known_rebuild()
            self._send_json({"started": started}, status=202 if started else 200)
        elif path == "/frequency/rebuild":
            started = start_freq_rebuild()
            self._send_json({"started": started}, status=202 if started else 200)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        _ = format
        _ = args


class SingleInstanceServer(ThreadingHTTPServer):
    # http.server's HTTPServer sets allow_reuse_address = 1 (for a quick
    # restart past TIME_WAIT), but on Windows SO_REUSEADDR also lets an
    # entirely separate process bind the SAME port while an older instance
    # is still alive and listening — mpv spawns a fresh server.py on every
    # launch without checking whether a previous one (e.g. one orphaned by
    # a crash or force-close) is still running, so both would end up bound
    # at once with requests split unpredictably between them, silently
    # starving whichever process actually holds the live video/subtitle
    # state. Disabling reuse makes a second bind attempt fail loudly at
    # startup instead, leaving whichever instance bound first as the sole,
    # deterministic listener.
    allow_reuse_address = False


if __name__ == "__main__":
    load_known_cache()
    if known_cache_is_stale():
        start_known_rebuild()
    load_freq_cache()
    if current_freq_scope() and not FREQ_READY:
        start_freq_rebuild()
    with SingleInstanceServer(("127.0.0.1", 6969), Server) as server:
        server.serve_forever()
