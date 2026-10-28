"""Custom uploads (CONTRACTS §14): .txt, .csv and .json become a custom challenge.

Uploaded text is always treated as plain text; anything that looks like HTML or
script is kept verbatim (and flagged) but never executed or rendered as HTML.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import PurePath

from .validation import DuplicateKeyError, extract_placeholders, has_bad_encoding, parse_json_strict

MAX_BYTES = 200 * 1024
MAX_STRINGS = 200
MAX_CHARS = 500
HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>|javascript:|on[a-z]+\s*=", re.I)
_SLUG_RE = re.compile(r"[^a-z0-9_]+")


class ImportRejected(Exception):
    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def _decode(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise ImportRejected("The upload could not be read as a file.")
    if len(data) > MAX_BYTES:
        raise ImportRejected(f"The file is {len(data) // 1024} KB; the limit is {MAX_BYTES // 1024} KB. "
                             "Split it into smaller files.")
    try:
        return bytes(data).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportRejected("The file is not saved as UTF-8 text. In Excel use 'Save As → CSV UTF-8'; "
                             "in a text editor choose the UTF-8 encoding.") from None


def _rows_from_txt(text: str) -> list[dict]:
    return [{"source": line.strip()} for line in text.splitlines() if line.strip()]


def _rows_from_csv(text: str) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        if "source" not in header:
            raise ImportRejected("The CSV needs a header row with a column called 'source' "
                                 "(optional columns: id, context, max_len, speaker).")
        rows = []
        for raw in reader:
            row = {(k or "").strip().lower(): (v or "") for k, v in raw.items() if k is not None}
            if (row.get("source") or "").strip():
                rows.append(row)
            if len(rows) > MAX_STRINGS:
                break
        return rows
    except csv.Error:
        raise ImportRejected("The CSV file could not be read. Check that it is a normal "
                             "comma-separated file.") from None


def _rows_from_json(text: str):
    try:
        obj = parse_json_strict(text)
    except DuplicateKeyError as e:
        raise ImportRejected(f"The JSON file repeats a key ({', '.join(e.keys[:3])}).") from None
    except (ValueError, RecursionError):
        raise ImportRejected("The JSON file is not valid JSON.") from None
    if isinstance(obj, dict) and isinstance(obj.get("strings"), list):
        return obj.get("strings"), obj
    if isinstance(obj, list):
        return obj, None
    raise ImportRejected("The JSON file must be a challenge file or a list of "
                         '{"source": "..."} entries.')


def _max_len(value, n: int):
    if value in (None, ""):
        return None
    try:
        v = int(str(value).strip())
    except ValueError:
        raise ImportRejected(f"Row {n}: max_len must be a whole number.") from None
    if not 1 <= v <= MAX_CHARS:
        raise ImportRejected(f"Row {n}: max_len must be between 1 and {MAX_CHARS}.")
    return v


def _slug(name: str) -> str:
    s = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    return s[:30] or "speaker"


def import_upload(filename: str, data: bytes) -> dict:
    """Return a custom challenge dict, or raise :class:`ImportRejected`."""
    ext = PurePath(filename or "").suffix.lower()
    if ext not in (".txt", ".csv", ".json"):
        raise ImportRejected("Please upload a .txt, .csv or .json file.")
    text = _decode(data)
    base = None
    if ext == ".txt":
        rows = _rows_from_txt(text)
    elif ext == ".csv":
        rows = _rows_from_csv(text)
    else:
        rows, base = _rows_from_json(text)
    if not rows:
        raise ImportRejected("No strings were found in the file.")
    if len(rows) > MAX_STRINGS:
        raise ImportRejected(f"The file has more than {MAX_STRINGS} strings. Split it into smaller files.")

    strings, warnings, speakers = [], [], {}
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ImportRejected(f"Entry {n} is not an object with a 'source' field.")
        source = row.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ImportRejected(f"Entry {n} has no source text.")
        source = source.strip().replace("\r\n", "\n")
        if len(source) > MAX_CHARS:
            raise ImportRejected(f"Entry {n} is {len(source)} characters; the limit is {MAX_CHARS}.")
        if has_bad_encoding(source):
            raise ImportRejected(f"Entry {n} contains invisible control characters or broken "
                                 "characters. Retype it and upload again.")
        if HTML_RE.search(source):
            warnings.append(f"Entry {n} looks like HTML or script. It is kept as plain text and "
                            "will never be run.")
        speaker_name = str(row.get("speaker") or "").strip()[:40]
        speaker = None
        if speaker_name:
            speaker = speakers.setdefault(speaker_name, _slug(speaker_name))
        context = str(row.get("context") or "").strip()[:MAX_CHARS]
        original_id = str(row.get("id") or "").strip()[:80]
        if original_id:
            context = (context + " " if context else "") + f"(original id: {original_id})"
        strings.append({
            "id": f"custom.text.{n:03d}", "source": source,
            "type": "dialogue" if speaker else "narration", "speaker": speaker,
            "context": context, "intended_meaning": "", "constraints": [],
            "placeholders": extract_placeholders(source), "max_len": _max_len(row.get("max_len"), n),
            "allow_newlines": "\n" in source, "focus": [],
        })
        if strings[-1]["max_len"]:
            strings[-1]["constraints"].append(f"Maximum {strings[-1]['max_len']} characters")

    base = base or {}
    characters = [{"id": slug, "name_zh": name, "name_en_suggestion": "", "profile": "",
                   "voice": "", "relationships": ""} for name, slug in speakers.items()]
    glossary = [g for g in (base.get("glossary") or []) if isinstance(g, dict)
                and isinstance(g.get("source"), str) and isinstance(g.get("target"), str)][:100]
    return {
        "schema_version": "1.0", "id": "custom", "mission": "custom",
        "title": str(base.get("title") or f"Custom upload — {PurePath(filename).name}")[:120],
        "title_zh": "", "estimated_minutes": None,
        "brief": str(base.get("brief") or "Your own uploaded text.")[:1000],
        "teaching_objectives": [],
        "scene_context": str(base.get("scene_context") or "")[:2000],
        "source_language": "the source language of the uploaded text",
        "characters": characters, "glossary": glossary, "strings": strings,
        "import_warnings": warnings,
    }
