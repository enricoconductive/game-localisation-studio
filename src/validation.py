"""Validation of translations and game translation files (CONTRACTS §5, §13).

The rules here must agree with the JavaScript validator in ``game/validator.js``.
Every issue carries a plain-English ``message`` and ``fix_hint`` for students.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

FORMAT_NAME = "lantern-mystery-translation"
MAX_FILE_BYTES = 100 * 1024
MAX_CHARACTER_NAME = 20
ALLOWED_LOCALES = ("en-GB", "en-US", "en")
FILE_LOCALES = ALLOWED_LOCALES + ("zh-Hant-HK",)       # locales a game file may declare
ALLOWED_SOURCES = ("live", "replay", "mixed", "original", "reference")
ID_RE = re.compile(r"^[a-z]+\.[a-z_]+\.[a-z0-9_]+$")
PLACEHOLDER_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")

CRITICAL = "CRITICAL"
WARNING = "WARNING"

_TYPE_LABELS = {
    "ui": "The button/interface text",
    "narration": "The narration",
    "dialogue": "The line",
    "choice": "The choice",
    "ending": "The ending text",
}


def repo_path(path: str | Path) -> Path:
    """Resolve a path relative to the current directory, else the repo root."""
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p
    return REPO_ROOT / p


# --------------------------------------------------------------------------- data


@dataclass
class StringSpec:
    id: str
    type: str = "dialogue"
    speaker: str | None = None
    placeholders: list[str] = field(default_factory=list)
    max_len: int | None = None
    allow_newlines: bool = False
    source: str = ""
    context: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StringSpec":
        return cls(
            id=d["id"],
            type=d.get("type") or "dialogue",
            speaker=d.get("speaker"),
            placeholders=[normalise_placeholder(x) for x in d.get("placeholders") or []],
            max_len=d.get("max_len"),
            allow_newlines=bool(d.get("allow_newlines", False)),
            source=d.get("source") or "",
            context=d.get("context") or "",
        )


@dataclass
class Issue:
    severity: str
    code: str
    string_id: str | None
    message: str
    fix_hint: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def critical(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == CRITICAL]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.critical

    def codes(self, severity: str | None = None) -> list[str]:
        return [i.code for i in self.issues if severity is None or i.severity == severity]

    def add(self, severity, code, string_id, message, fix_hint) -> None:
        self.issues.append(Issue(severity, code, string_id, message, fix_hint))

    def extend(self, other: "ValidationReport") -> None:
        self.issues.extend(other.issues)

    def summary(self) -> str:
        if not self.issues:
            return "All checks passed: no problems found."
        c, w = len(self.critical), len(self.warnings)
        head = (f"{c} blocking problem(s) must be fixed before export" if c
                else "No blocking problems")
        return f"{head}; {w} warning(s) to review."

    def to_dict(self) -> dict:
        return {"ok": self.ok, "summary": self.summary(),
                "issues": [i.to_dict() for i in self.issues]}


class DuplicateKeyError(ValueError):
    """Raised by :func:`parse_json_strict` when an object repeats a key."""

    def __init__(self, keys: list[str]):
        self.keys = keys
        super().__init__("The same key appears more than once: " + ", ".join(keys))


# --------------------------------------------------------------------------- loading


def load_manifest(path: str | Path = "game/strings_manifest.json") -> dict:
    with open(repo_path(path), encoding="utf-8") as f:
        return parse_json_strict(f.read())


def spec_from_manifest(manifest: dict, mission: str | None = None) -> dict[str, StringSpec]:
    """Specs for one mission (or every string when ``mission`` is None)."""
    out: dict[str, StringSpec] = {}
    for sid, entry in (manifest.get("strings") or {}).items():
        if mission is not None and entry.get("mission") != mission:
            continue
        out[sid] = StringSpec.from_dict({**entry, "id": sid})
    return out


def spec_from_challenge(challenge: dict) -> dict[str, StringSpec]:
    return {s["id"]: StringSpec.from_dict(s) for s in challenge.get("strings", [])}


def _collect_pairs(dups: list[str]):
    def hook(pairs):
        obj: dict = {}
        for k, v in pairs:
            if k in obj:
                dups.append(k)
            obj[k] = v
        return obj
    return hook


def parse_json_strict(text: str | bytes) -> Any:
    """``json.loads`` that raises :class:`DuplicateKeyError` on repeated keys."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    if text.startswith("﻿"):
        text = text[1:]
    dups: list[str] = []
    obj = json.loads(text, object_pairs_hook=_collect_pairs(dups))
    if dups:
        raise DuplicateKeyError(dups)
    return obj


# --------------------------------------------------------------------------- helpers


def normalise_placeholder(p) -> str:
    """Manifest entries may be written "{name}" or "name"; return "{name}"."""
    p = str(p)
    return p if p.startswith("{") else "{" + p + "}"


def extract_placeholders(text: str) -> list[str]:
    """Well-formed ``{snake_case}`` placeholders, in order of appearance."""
    return PLACEHOLDER_RE.findall(text or "")


def _short(text: str, n: int = 40) -> str:
    text = text.replace("\n", "\\n")
    return text if len(text) <= n else text[: n - 1] + "…"


def _label(spec: StringSpec | None) -> str:
    return _TYPE_LABELS.get(spec.type if spec else "", "The text")


def _is_bad_char(ch: str) -> bool:
    cp = ord(ch)
    if 0xD800 <= cp <= 0xDFFF or cp == 0xFFFD:
        return True
    if cp == 0x0A:
        return False
    return cp <= 0x1F or 0x7F <= cp <= 0x9F


def has_bad_encoding(text: str) -> bool:
    return any(_is_bad_char(c) for c in text)


def _has_cjk(text: str) -> bool:
    return any(0x3400 <= ord(c) <= 0x9FFF for c in text)


# Exactly JavaScript's ``\s`` (what validator.js trims and tests), so both validators agree
# on U+FEFF, no-break and other Unicode spaces (Python's own ``str.strip`` differs).
JS_WHITESPACE = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
                 "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")


def _strip(text: str) -> str:
    return text.strip(JS_WHITESPACE)


# --------------------------------------------------------------------------- per-string


def validate_string(sid: str, text: str, spec: StringSpec) -> list[Issue]:
    """All issues for one translated string."""
    rep = ValidationReport()
    label = _label(spec)
    if not isinstance(text, str):
        rep.add(CRITICAL, "bad_structure", sid,
                f"The translation for '{sid}' is not text.",
                "Make sure every translation is written between quotation marks.")
        return rep.issues
    if not _strip(text):
        rep.add(CRITICAL, "empty_text", sid,
                f"{label} '{sid}' is empty.",
                "Write an English translation for this string.")
        return rep.issues

    if has_bad_encoding(text):
        rep.add(CRITICAL, "bad_encoding", sid,
                f"{label} '{sid}' contains invisible or broken characters "
                "(control characters, a damaged character or the replacement symbol �).",
                "Retype the text by hand instead of pasting it, then check again.")

    # Placeholders: well-formed tokens versus anything else with braces.
    found = extract_placeholders(text)
    leftover = PLACEHOLDER_RE.sub("", text)
    if "{" in leftover or "}" in leftover:
        rep.add(CRITICAL, "placeholder_broken", sid,
                f"{label} '{sid}' has a broken placeholder: '{_short(text)}'. "
                "A curly bracket is unmatched, or the name inside it was changed or translated.",
                "Copy placeholders exactly as in the source, e.g. {player_name} — "
                "lower-case English letters and underscores, no spaces.")
    want, have = Counter(spec.placeholders), Counter(found)
    for ph in sorted((want - have).elements()):
        rep.add(CRITICAL, "placeholder_missing", sid,
                f"{label} '{sid}' is missing the placeholder {ph}. "
                "The game puts a value there at runtime.",
                f"Add {ph} back into the sentence exactly once.")
    for ph in sorted((have - want).elements()):
        rep.add(CRITICAL, "placeholder_extra", sid,
                f"{label} '{sid}' has an extra placeholder {ph} that the source does not have "
                "(or has it more than once).",
                f"Remove the extra {ph}; each placeholder must appear exactly as often as in the source.")

    n = len(text)
    if spec.max_len is not None:
        if n > spec.max_len:
            rep.add(CRITICAL, "too_long", sid,
                    f"{label} '{_short(text)}' is {n} characters, but the limit is {spec.max_len}.",
                    "Shorten it — try fewer words or a shorter synonym.")
        elif n >= 0.9 * spec.max_len:
            rep.add(WARNING, "near_limit", sid,
                    f"{label} '{sid}' uses {n} of {spec.max_len} characters.",
                    "It fits, but check it does not look cramped in the game.")

    if not spec.allow_newlines and ("\n" in text or "\r" in text):
        rep.add(CRITICAL, "newline_not_allowed", sid,
                f"{label} '{sid}' contains a line break, but this string must stay on one line.",
                "Remove the line break and join the text into one line.")

    if _has_cjk(text):
        rep.add(WARNING, "untranslated_cjk", sid,
                f"{label} '{sid}' still contains Chinese characters: '{_short(text)}'.",
                "Check whether something was left untranslated.")
    if text != _strip(text) or "  " in text:
        rep.add(WARNING, "whitespace", sid,
                f"{label} '{sid}' has a space (or an invisible space-like character) at the start "
                "or end, or a double space.",
                "Remove the extra spaces.")
    if "<" in text or ">" in text:
        rep.add(WARNING, "angle_brackets", sid,
                f"{label} '{sid}' contains < or >. The game shows them literally, not as formatting.",
                "Remove them unless you really want the symbols to appear.")
    return rep.issues


def validate_translations(translations: dict, spec: dict[str, StringSpec],
                          require_all: bool = True) -> ValidationReport:
    """Validate ``{id: text}`` against specs (used before approval and export)."""
    rep = ValidationReport()
    if not isinstance(translations, dict):
        rep.add(CRITICAL, "bad_structure", None,
                "The translations are not a list of id → text pairs.",
                "Re-run the translator or restore an earlier version.")
        return rep
    for sid, text in translations.items():
        if sid not in spec:
            rep.add(CRITICAL, "unknown_id", sid,
                    f"'{sid}' is not a string id used by this mission.",
                    "Remove it, or check the id for typos.")
            continue
        rep.issues.extend(validate_string(sid, text, spec[sid]))
    if require_all:
        for sid in spec:
            if sid not in translations:
                rep.add(CRITICAL, "missing_id", sid,
                        f"There is no translation for '{sid}'.",
                        "Translate this string (or re-run the translator) before exporting.")
    return rep


# --------------------------------------------------------------------------- game file


def _validate_characters(chars: Any, manifest: dict, rep: ValidationReport) -> None:
    known = manifest.get("characters") or {}
    if not isinstance(chars, dict):
        rep.add(CRITICAL, "bad_structure", None,
                "The 'characters' section is not a list of character → name pairs.",
                "Remove the 'characters' section or fix its format.")
        return
    for key, name in chars.items():
        if key not in known:
            rep.add(CRITICAL, "bad_structure", None,
                    f"'{key}' is not a character in this game.",
                    "Remove it from the 'characters' section.")
        elif not isinstance(name, str) or not _strip(name):
            rep.add(CRITICAL, "bad_structure", None,
                    f"The English name for '{key}' is empty or not text.",
                    "Write a name in quotation marks, or remove the entry.")
        elif len(name) > MAX_CHARACTER_NAME or "\n" in name or "\r" in name:
            rep.add(CRITICAL, "bad_structure", None,
                    f"The English name for '{key}' must be one line of at most "
                    f"{MAX_CHARACTER_NAME} characters.",
                    "Shorten the name and remove any line breaks.")
        elif has_bad_encoding(name):
            rep.add(CRITICAL, "bad_encoding", None,
                    f"The English name for '{key}' contains a damaged or invisible character.",
                    "Retype the name and save the file as UTF-8.")
        elif _has_cjk(name):
            rep.add(WARNING, "untranslated_cjk", None,
                    f"The English name for '{key}' still contains Chinese characters.",
                    "Check whether the name should be romanised or translated.")


def _validate_metadata(obj: dict, rep: ValidationReport) -> None:
    """``source`` and ``locale`` (CONTRACTS §5 resolution (f))."""
    if "source" not in obj:
        rep.add(WARNING, "bad_structure", None,
                "The file does not say where the translation came from (no 'source').",
                "Use the file exported by the studio; it sets 'source' for you.")
    elif obj["source"] not in ALLOWED_SOURCES:
        rep.add(CRITICAL, "bad_structure", None,
                f"'source' must be one of {', '.join(ALLOWED_SOURCES)}, not {_short(repr(obj['source']))}.",
                "Re-export the file from the studio instead of editing 'source' by hand.")
    locale = obj.get("locale")
    if not isinstance(locale, str) or locale not in FILE_LOCALES:
        rep.add(WARNING, "bad_structure", None,
                f"The 'locale' should be one of {', '.join(FILE_LOCALES)}"
                + (" but it is missing." if "locale" not in obj else
                   f", not {_short(repr(locale))}."),
                "Use the file exported by the studio; it sets the locale for you.")


def mission_ids(manifest: dict, mission: str) -> list[str]:
    """Ids of a mission: its ``string_ids`` list, else strings tagged with that mission."""
    for m in manifest.get("missions") or []:
        if isinstance(m, dict) and m.get("id") == mission:
            return list(m.get("string_ids") or [])
    return [sid for sid, e in (manifest.get("strings") or {}).items()
            if isinstance(e, dict) and e.get("mission") == mission]


def validate_game_file(text_or_obj: Any, manifest: dict,
                       require_all_for_mission: str | None = None) -> ValidationReport:
    """Validate an exported/imported game translation file (CONTRACTS §5).

    With ``require_all_for_mission`` every id of that mission is required (CRITICAL
    ``missing_id``, the Python export rule). Otherwise missing ids are WARNINGs, for every
    mission the file touches plus its ``mission`` field (the game import rule).
    """
    rep = ValidationReport()
    obj = text_or_obj
    if isinstance(obj, (bytes, str)):
        raw = obj if isinstance(obj, bytes) else obj.encode("utf-8", "surrogatepass")
    else:
        try:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8", "surrogatepass")
        except (TypeError, ValueError):
            raw = b""
    if len(raw) > MAX_FILE_BYTES:
        rep.add(CRITICAL, "file_too_large", None,
                f"The file is {-(-len(raw) // 1024)} KB, but the limit is {MAX_FILE_BYTES // 1024} KB.",
                "Use the file exported by the studio; do not add extra content.")
        return rep
    if isinstance(obj, (bytes, str)):
        if isinstance(obj, bytes):
            try:
                obj = obj.decode("utf-8-sig")
            except UnicodeDecodeError:
                rep.add(CRITICAL, "bad_encoding", None,
                        "The file is not saved as UTF-8 text.",
                        "Save the file as UTF-8 (the studio export always is).")
                return rep
        dups: list[str] = []
        try:
            obj = json.loads(obj[1:] if obj.startswith("\ufeff") else obj,
                             object_pairs_hook=_collect_pairs(dups))
        except (ValueError, RecursionError) as e:
            rep.add(CRITICAL, "invalid_json", None,
                    f"The file is not valid JSON ({getattr(e, 'msg', 'unreadable')}).",
                    "Re-export the file from the studio instead of editing it by hand.")
            return rep
        for key in dups:
            rep.add(CRITICAL, "duplicate_id", key if ID_RE.match(key) else None,
                    f"'{key}' appears more than once in the file; only the last one would be used.",
                    "Keep exactly one entry for each id.")

    if not isinstance(obj, dict):
        rep.add(CRITICAL, "wrong_format", None, "This is not a Lantern Mystery translation file.",
                "Use the game translation file exported by the studio.")
        return rep
    if obj.get("format") != FORMAT_NAME:
        rep.add(CRITICAL, "wrong_format", None,
                "This is not a Lantern Mystery translation file (the 'format' is wrong or missing).",
                "Use the game translation file exported by the studio.")
    version = obj.get("schema_version")
    if not isinstance(version, (str, int, float)) or isinstance(version, bool) \
            or str(version).split(".")[0] != "1":
        rep.add(CRITICAL, "wrong_format", None,
                f"This file uses schema version {version!r}, but the game reads version 1.x.",
                "Export the file again from the current studio.")
    _validate_metadata(obj, rep)
    strings = obj.get("strings")
    if not isinstance(strings, dict):
        rep.add(CRITICAL, "bad_structure", None,
                "'strings' must map each string id to a piece of text.",
                "Re-export the file from the studio.")
        return rep
    if "characters" in obj:
        _validate_characters(obj["characters"], manifest, rep)

    spec = spec_from_manifest(manifest)
    touched: list[str] = []
    rep.extend(validate_translations(strings, spec, require_all=False))
    for sid in strings:
        m = (manifest.get("strings") or {}).get(sid, {}).get("mission")
        if m and m not in touched:
            touched.append(m)
    if require_all_for_mission is not None:
        check, severity = [require_all_for_mission], CRITICAL
    else:
        check, severity = touched, WARNING
        if isinstance(obj.get("mission"), str) and obj["mission"] not in check \
                and mission_ids(manifest, obj["mission"]):
            check = check + [obj["mission"]]
    for mission in check:
        for sid in mission_ids(manifest, mission):
            if sid not in strings:
                if severity == CRITICAL:
                    rep.add(CRITICAL, "missing_id", sid,
                            f"There is no translation for '{sid}'.",
                            "Translate every string of the mission before exporting.")
                else:
                    rep.add(WARNING, "missing_id", sid,
                            f"'{sid}' is not in this file, so the game will show it in Chinese.",
                            "Add a translation for this id if you want the whole mission in English.")
    return rep
