"""Translator, reviewer and reviser agents (CONTRACTS §7, §11).

Every prompt is built from visible parts: role text, the team's editable
instructions, ``settings_to_text`` lines, glossary, project memory, context and the
strings. Nothing is hidden from students; every request is stored as a snapshot.
"""
from __future__ import annotations

import inspect
import json
import re

from .project_state import ProjectState, StudioError, Finding, Version
from .providers import DEFAULT_MAX_TOKENS, ProviderError, find_secrets
from .providers import _error as _provider_error

BATCH_SIZE = 8
MAX_TOKENS = DEFAULT_MAX_TOKENS   # 4000; providers.json "limits.max_tokens" overrides it
RAW_LIMIT = 4000
CATEGORIES = ("accuracy", "fluency", "terminology", "cultural", "character_voice", "technical")
SEVERITIES = ("minor", "major", "critical")
REPAIR_MARK = "## Your previous reply could not be read"
REPAIR_TEXT = ("Your previous reply was not valid JSON in the required shape. Reply again with ONLY "
               "the JSON object described under 'Output format' — no explanations and no code "
               "fences. Keep notes very short.")
TRUNCATED_REPAIR_TEXT = ("Your previous reply was cut off because it was too long. Reply again "
                         "with ONLY the JSON object described under 'Output format', as compact "
                         "as possible: leave every note empty, write no explanations and no code "
                         "fences.")

LOCALE_LINES = {
    "en-GB": "British English (en-GB): use British spelling (colour, realise, centre, travelling), "
             "British vocabulary and British punctuation conventions.",
    "en-US": "American English (en-US): use American spelling (color, realize, center, traveling), "
             "American vocabulary and American punctuation conventions.",
    "en": "International English (en): use neutral, widely understood vocabulary for a global "
          "audience; avoid strongly regional idioms and slang; keep spelling consistent throughout.",
}

# --------------------------------------------------------------------------- settings

_STRATEGY = {
    1: "very faithful — stay as close to the source wording and sentence structure as English "
       "allows; do not add or drop ideas.",
    2: "faithful — keep the source wording where it reads naturally; rephrase only to fix "
       "awkward English.",
    3: "balanced — keep the meaning and function exact, but rephrase freely where a literal "
       "rendering would sound unnatural.",
    4: "free — put the effect on the player first; you may restructure sentences and replace "
       "images or jokes with English equivalents of similar effect.",
    5: "very creative — recreate the experience for English-speaking players; wordplay and "
       "humour may be rewritten completely, as long as plot facts and constraints are kept.",
}
_CULTURE = {
    1: "keep the source culture — keep Hong Kong names, food, places and customs; do not "
       "explain or replace them.",
    2: "mostly keep — keep cultural references; add a light hint only where English players "
       "would be lost.",
    3: "balanced — keep references that create the setting; adapt ones that would only confuse.",
    4: "mostly adapt — replace references English players would not get with familiar "
       "equivalents, while keeping the Hong Kong setting.",
    5: "fully adapt for the target audience — make every reference feel natural to them, "
       "keeping only plot facts and the setting.",
}
_VOICE = {
    1: "minimal — keep dialogue plain and neutral.",
    2: "light — small touches of personality where the source shows them.",
    3: "clear — each character should sound recognisably like their profile.",
    4: "strong — make speech patterns, vocabulary and rhythm distinctive for each character.",
    5: "very strong — give each character an unmistakable voice (word choice, rhythm, "
       "catchphrases) based on their profile, within the constraints.",
}
_REGISTER = {
    "match_source": "match the register of each source string",
    "neutral": "neutral and clear",
    "casual": "casual and conversational",
    "formal": "formal and polite",
    "playful": "playful and light-hearted",
    "dramatic": "dramatic and atmospheric",
}
_GLOSSARY = {
    "must_use": "you MUST use the glossary target term whenever the source term appears.",
    "prefer": "use the glossary target term unless it clearly does not fit; if you choose "
              "something else, say why in the note.",
    "ignore": "treat the glossary as background information only; you may choose other terms.",
}
_STRICTNESS = {
    1: "lenient — report only serious errors (wrong meaning, broken game text).",
    2: "relaxed — report serious and clearly noticeable problems.",
    3: "standard — report problems a typical player would notice; ignore personal style "
       "preferences.",
    4: "demanding — also report smaller problems of naturalness and consistency.",
    5: "very strict — report every problem you can justify, including minor polish.",
}
_TEMPERATURE = {1: 0.1, 2: 0.2, 3: 0.4, 4: 0.6, 5: 0.8}
REVIEWER_TEMPERATURE = 0.1
BASELINE_TEMPERATURE = 0.3


def _slider(key, label, default, help_, levels):
    return {"key": key, "label": label, "kind": "slider", "range": [1, 5], "default": default,
            "help": help_, "levels": {str(k): v for k, v in levels.items()}}


TRANSLATOR_SETTINGS_SPEC = [
    _slider("strategy", "Translation strategy (1 faithful → 5 creative)", 3,
            "How closely the translation follows the source wording.", _STRATEGY),
    _slider("cultural_adaptation", "Cultural adaptation (1 keep source culture → 5 adapt)", 3,
            "Whether cultural references stay Hong Kong or become familiar to the audience.",
            _CULTURE),
    {"key": "register", "label": "Register / tone", "kind": "dropdown",
     "options": list(_REGISTER), "default": "match_source",
     "help": "The overall tone of the English text.", "levels": _REGISTER},
    _slider("voice_strength", "Character voice strength", 3,
            "How distinctive each character's way of speaking should be.", _VOICE),
    {"key": "glossary_strictness", "label": "Glossary strictness", "kind": "dropdown",
     "options": list(_GLOSSARY), "default": "prefer",
     "help": "How strictly the glossary must be followed.", "levels": _GLOSSARY},
]

REVIEWER_SETTINGS_SPEC = [
    *[{"key": f"check_{c}", "label": f"Check {c.replace('_', ' ')}", "kind": "checkbox",
       "default": True, "help": f"Report {c.replace('_', ' ')} problems."} for c in CATEGORIES],
    _slider("strictness", "Review strictness", 3, "How small a problem must be to be reported.",
            _STRICTNESS),
    {"key": "max_findings", "label": "Maximum findings", "kind": "slider", "range": [1, 10],
     "default": 6, "help": "The most suggestions the reviewer may make in one round."},
]

TRANSLATOR_ROLE = (
    "You are the TRANSLATOR agent in a game localisation team. You translate game text for a "
    "short narrative mystery game into English. A separate reviewer agent and a human "
    "localisation director will check your work. You reply with JSON only."
)
REVIEWER_ROLE = (
    "You are the REVIEWER agent in a game localisation team. You check an English translation "
    "of game text against the source. You do not change the translation yourself: your findings "
    "are suggestions for a human localisation director, who decides whether to accept, edit or "
    "reject each one. You reply with JSON only."
)
DEFAULT_TRANSLATOR_INSTRUCTIONS = (
    "Translate each string into natural, idiomatic English for players of a story-driven "
    "mystery game.\n"
    "- Keep the meaning, tone and purpose of every string; never add plot information that "
    "is not in the source.\n"
    "- Interface text must be short and clear; choices must read as actions the player can pick.\n"
    "- Dialogue must sound like the character who speaks it.\n"
    "- Respect every constraint: character limits, placeholders and line-break rules.\n"
    "- Use the note to explain any non-obvious choice in one short sentence."
)
DEFAULT_REVIEWER_INSTRUCTIONS = (
    "Review the English translation of each string against its source, context, constraints "
    "and the glossary.\n"
    "- Report only real problems: meaning errors or omissions, unnatural English, wrong "
    "terminology, cultural references that will confuse the audience, characters who do not "
    "sound like themselves, and technical faults (placeholders, length limits, line breaks).\n"
    "- Be specific: cite the string id, say what is wrong and explain why it matters.\n"
    "- Give a complete replacement string that fixes the problem and respects every constraint.\n"
    "- Do not invent problems. If a string is fine, say nothing about it. It is fine to report "
    "no findings at all."
)


def default_settings(role: str) -> dict:
    spec = TRANSLATOR_SETTINGS_SPEC if role == "translator" else REVIEWER_SETTINGS_SPEC
    return {s["key"]: s["default"] for s in spec}


# --------------------------------------------------------------------------- presets (§15)

FAITHFUL_TRANSLATOR_INSTRUCTIONS = (
    "Translate each string accurately and completely, staying as close to the source wording "
    "and sentence structure as correct English allows.\n"
    "- Accuracy comes first: render every idea in the source, in the same order where possible. "
    "Do not add, drop, soften or explain information.\n"
    "- Keep Hong Kong names, food, places and customs as they are, and use the glossary target "
    "term every time the source term appears.\n"
    "- Translate idioms, sayings and wordplay closely enough that the original image is still "
    "recognisable; do not replace them with English idioms.\n"
    "- Keep each character's register as the source shows it, but do not invent slang, "
    "catchphrases or jokes that are not there.\n"
    "- Interface text must still work in the game: respect every character limit, placeholder "
    "and line-break rule exactly.\n"
    "- In the note, flag any place where a close rendering may sound unusual to English players, "
    "so the director can decide."
)
CREATIVE_TRANSLATOR_INSTRUCTIONS = (
    "Recreate the experience of the scene for English-speaking players: they should smile, "
    "wonder and care about the characters where the original audience does.\n"
    "- Put the effect on the player first. Rewrite jokes, puns and sayings as English ones that "
    "work as well as the original, keeping the key image (the rabbit, the moon, the lanterns) "
    "where you can.\n"
    "- Give every character a distinctive, consistent voice based on their profile: word "
    "choice, rhythm and attitude should tell the player who is speaking without a name tag.\n"
    "- Adapt references that would puzzle international players, but keep the Hong Kong "
    "setting, the required glossary terms and every plot fact. Do not add events, clues or "
    "details that are not in the source.\n"
    "- Linked strings (a riddle, its answer and its pay-off) must be adapted together so the "
    "scene still works.\n"
    "- Technical constraints are not negotiable: copy placeholders such as {player_name} exactly, "
    "stay within character limits, and use a line break only where the string allows one.\n"
    "- Use the note to explain each adaptation in one short sentence, so the director can "
    "judge it."
)

TRANSLATOR_PRESETS = {
    "faithful": {
        "label": "Faithful",
        "description": "Stay close to the source wording and structure.",
        "settings": {"strategy": 1, "cultural_adaptation": 1, "register": "match_source",
                     "voice_strength": 2, "glossary_strictness": "must_use"},
        "instructions": FAITHFUL_TRANSLATOR_INSTRUCTIONS,
    },
    "balanced": {
        "label": "Balanced",
        "description": "Natural English that keeps the meaning and function of every string.",
        "settings": default_settings("translator"),
        "instructions": DEFAULT_TRANSLATOR_INSTRUCTIONS,
    },
    "creative": {
        "label": "Creative",
        "description": "Recreate the player's experience: strong voices, recreated humour, "
                       "adapted references.",
        "settings": {"strategy": 5, "cultural_adaptation": 4, "register": "match_source",
                     "voice_strength": 5, "glossary_strictness": "prefer"},
        "instructions": CREATIVE_TRANSLATOR_INSTRUCTIONS,
    },
}
PRESET_ORDER = ("faithful", "balanced", "creative")
DEFAULT_PRESET = "balanced"


def _preset_name(agent_cfg: dict | None) -> str:
    name = (agent_cfg or {}).get("preset") or DEFAULT_PRESET
    return name if name in TRANSLATOR_PRESETS else DEFAULT_PRESET


def apply_preset(agent_cfg: dict, name: str) -> dict:
    """Load a translator preset into ``agent_cfg`` (in place; also returned)."""
    if name not in TRANSLATOR_PRESETS:
        raise StudioError(f"Unknown preset '{name}'. Choose one of: " + ", ".join(PRESET_ORDER) + ".")
    p = TRANSLATOR_PRESETS[name]
    agent_cfg["settings"] = dict(p["settings"])
    agent_cfg["instructions"] = p["instructions"]
    agent_cfg.setdefault("default_instructions", DEFAULT_TRANSLATOR_INSTRUCTIONS)
    agent_cfg["preset"] = name
    agent_cfg["edited"] = False
    return agent_cfg


def mark_edited(agent_cfg: dict) -> dict:
    """Set ``edited`` to whether settings/instructions now differ from the chosen preset."""
    p = TRANSLATOR_PRESETS[_preset_name(agent_cfg)]
    try:
        settings = normalise_settings("translator", agent_cfg.get("settings"))
    except StudioError:
        settings = None
    agent_cfg["preset"] = _preset_name(agent_cfg)
    agent_cfg["edited"] = (settings != normalise_settings("translator", p["settings"])
                           or (agent_cfg.get("instructions") or "").strip() != p["instructions"].strip())
    return agent_cfg


def replay_variant_note(agent_cfg: dict | None) -> str:
    """Plain-English label of the prepared Replay output for this translator config."""
    label = TRANSLATOR_PRESETS[_preset_name(agent_cfg)]["label"]
    if (agent_cfg or {}).get("edited"):
        return (f"Prepared output for the ‘{label}’ preset. Your own edits are saved in your "
                "prompt and report, but Replay Mode cannot generate a new response — switch to "
                "Live Mode to test them.")
    return f"Prepared output for the ‘{label}’ preset (Replay Mode, not generated live)."


def default_agent_config(role: str) -> dict:
    if role not in ("translator", "reviewer"):
        raise StudioError("The agent role must be 'translator' or 'reviewer'.")
    instr = DEFAULT_TRANSLATOR_INSTRUCTIONS if role == "translator" else DEFAULT_REVIEWER_INSTRUCTIONS
    cfg = {"settings": default_settings(role), "instructions": instr, "default_instructions": instr}
    if role == "translator":
        cfg.update(preset=DEFAULT_PRESET, edited=False)
    return cfg


def normalise_settings(role: str, settings: dict | None) -> dict:
    """Fill defaults and check values; raises StudioError with a plain message."""
    spec = TRANSLATOR_SETTINGS_SPEC if role == "translator" else REVIEWER_SETTINGS_SPEC
    out = default_settings(role)
    for s in spec:
        if s["key"] not in (settings or {}):
            continue
        v = settings[s["key"]]
        if s["kind"] == "slider":
            lo, hi = s["range"]
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise StudioError(f"'{s['label']}' must be a number from {lo} to {hi}.") from None
            out[s["key"]] = min(hi, max(lo, v))
        elif s["kind"] == "dropdown":
            if v not in s["options"]:
                raise StudioError(f"'{v}' is not an option for '{s['label']}'.")
            out[s["key"]] = v
        else:
            out[s["key"]] = bool(v)
    if role == "reviewer" and not any(out[f"check_{c}"] for c in CATEGORIES):
        raise StudioError("Tick at least one category for the reviewer to check.")
    return out


def settings_to_text(role: str, settings: dict) -> str:
    """The exact lines inserted into the prompt (shown to students)."""
    s = normalise_settings(role, settings)
    if role == "translator":
        return "\n".join([
            f"- Translation strategy {s['strategy']}/5: {_STRATEGY[s['strategy']]}",
            f"- Cultural adaptation {s['cultural_adaptation']}/5: {_CULTURE[s['cultural_adaptation']]}",
            f"- Register and tone: {_REGISTER[s['register']]}.",
            f"- Character voice strength {s['voice_strength']}/5: {_VOICE[s['voice_strength']]}",
            f"- Glossary: {_GLOSSARY[s['glossary_strictness']]}",
        ])
    cats = [c for c in CATEGORIES if s[f"check_{c}"]]
    return "\n".join([
        "- Check only these categories: " + ", ".join(cats) + ".",
        f"- Strictness {s['strictness']}/5: {_STRICTNESS[s['strictness']]}",
        f"- Report at most {s['max_findings']} findings, the most important first.",
    ])


def temperature_for(role: str, settings: dict | None = None) -> float:
    if role in ("translator", "reviser"):
        return _TEMPERATURE[normalise_settings("translator", settings)["strategy"]]
    if role == "reviewer":
        return REVIEWER_TEMPERATURE
    return BASELINE_TEMPERATURE


def temperature_note(role: str, settings: dict | None, provider_name: str,
                     provider_config: dict | None = None) -> str:
    t = temperature_for(role, settings)
    origin = ("from the translation strategy" if role in ("translator", "reviser")
              else "fixed for this agent")
    cfg = (provider_config or {}).get(provider_name, {})
    default_send = provider_name not in ("anthropic", "replay")
    if provider_name == "replay":
        return f"Temperature {t} ({origin}). Replay Mode uses prepared outputs, so it has no effect."
    if not cfg.get("send_temperature", default_send):
        return (f"Temperature {t} ({origin}) is shown for reference only: current Claude models "
                "choose their own sampling, so your settings work through the prompt lines above.")
    return f"Temperature {t} ({origin}) is sent with the request."


# --------------------------------------------------------------------------- prompt parts


def _source_language(challenge: dict) -> str:
    return challenge.get("source_language") or "Traditional Chinese (Hong Kong Cantonese usage)"


def _char_names(challenge: dict) -> dict:
    return {c.get("id"): c.get("name_en_suggestion") or c.get("name_zh") or c.get("id")
            for c in challenge.get("characters", []) if isinstance(c, dict)}


def _glossary_text(challenge: dict) -> str:
    items = challenge.get("glossary") or []
    if not items:
        return "No glossary for this challenge."
    lines = []
    for g in items:
        line = f"- {g.get('source', '')} → {g.get('target', '')} ({g.get('strictness', 'preferred')})"
        if g.get("note"):
            line += f". Note: {g['note']}"
        lines.append(line)
    return "\n".join(lines)


def _memory_text(memory_rules) -> str:
    rules = list(memory_rules or [])
    if not rules:
        return "No rules yet."
    lines = ["Follow these rules; the human director approved them for this project."]
    for r in rules:
        get = r.get if isinstance(r, dict) else (lambda k, _r=r: getattr(_r, k, None))
        terms = ""
        if get("source_term") or get("target_term"):
            terms = f" ({get('source_term') or '…'} → {get('target_term') or '…'})"
        lines.append(f"- {get('rule_id')} [{get('kind')}]{terms}: {get('text')}")
    return "\n".join(lines)


def _characters_text(challenge: dict) -> str:
    chars = challenge.get("characters") or []
    if not chars:
        return "No character profiles."
    lines = []
    for c in chars:
        parts = [f"- {c.get('id')}: {c.get('name_zh', '')} (English name: "
                 f"{c.get('name_en_suggestion') or 'not fixed'})."]
        for k, lab in (("profile", "Profile"), ("voice", "Voice"), ("relationships", "Relationships")):
            if c.get(k):
                parts.append(f"{lab}: {c[k]}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _strings_for(challenge: dict, string_ids=None) -> list[dict]:
    strings = challenge.get("strings", [])
    if string_ids is None:
        return list(strings)
    wanted = set(string_ids)
    return [s for s in strings if s["id"] in wanted]


def _string_block(s: dict, names: dict, translation: str | None = None) -> str:
    q = lambda t: json.dumps(t, ensure_ascii=False)  # noqa: E731 - shows \n and spaces clearly
    speaker = s.get("speaker")
    phs = s.get("placeholders") or []
    lines = [f"[{s['id']}]", f"Source: {q(s.get('source', ''))}",
             f"Type: {s.get('type', 'dialogue')} | Speaker: "
             + (f"{speaker} ({names.get(speaker, speaker)})" if speaker else "none")]
    if s.get("context"):
        lines.append(f"Context: {s['context']}")
    if s.get("constraints"):
        lines.append("Constraints: " + "; ".join(s["constraints"]))
    lines.append("Placeholders: " + (", ".join(phs) + " — copy exactly, each once" if phs else "none"))
    lines.append(f"Max length: {s['max_len']} characters" if s.get("max_len") else "Max length: none")
    lines.append("Line breaks: " + ("allowed (write \\n)" if s.get("allow_newlines") else "not allowed"))
    if translation is not None:
        lines.append(f"Translation under review: {q(translation)}")
    return "\n".join(lines)


TRANSLATION_SCHEMA = (
    "Return ONLY a JSON object, with no text before or after it, in exactly this shape:\n"
    '{"translations": [{"id": "<string id>", "text": "<English translation>", '
    '"note": "<one short sentence, optional>"}]}\n'
    "Include every id listed under 'Strings' exactly once and no other ids. Keep every "
    "placeholder such as {player_name} exactly as written."
)
FINDINGS_SCHEMA = (
    "Return ONLY a JSON object, with no text before or after it, in exactly this shape:\n"
    '{"findings": [{"string_id": "<id>", "category": "accuracy|fluency|terminology|cultural|'
    'character_voice|technical", "severity": "minor|major|critical", "issue": "<what is wrong>", '
    '"reasoning": "<why it matters>", "suggestion": "<the full replacement English string>"}], '
    '"overall_comment": "<one or two sentences>"}\n'
    'Use only string ids listed above. If there is nothing to report, return {"findings": [], '
    '"overall_comment": "..."}.'
)


def _strict_object(properties: dict) -> dict:
    """A JSON Schema object for structured outputs: every field required, nothing extra."""
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def translations_json_schema(ids) -> dict:
    """Strict schema for translator / baseline / reviser replies (CONTRACTS §7).

    ``id`` is limited to the batch's ids; ``note`` is required but may be empty.
    """
    item = _strict_object({"id": {"type": "string", "enum": list(dict.fromkeys(ids))},
                           "text": {"type": "string"},
                           "note": {"type": "string"}})
    return _strict_object({"translations": {"type": "array", "items": item}})


def findings_json_schema(valid_ids) -> dict:
    """Strict schema for reviewer replies (CONTRACTS §7)."""
    item = _strict_object({"string_id": {"type": "string", "enum": list(dict.fromkeys(valid_ids))},
                           "category": {"type": "string", "enum": list(CATEGORIES)},
                           "severity": {"type": "string", "enum": list(SEVERITIES)},
                           "issue": {"type": "string"},
                           "reasoning": {"type": "string"},
                           "suggestion": {"type": "string"}})
    return _strict_object({"findings": {"type": "array", "items": item},
                           "overall_comment": {"type": "string"}})


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}"


def build_baseline_prompt(challenge: dict, locale: str) -> tuple[str, str]:
    """Deliberately minimal: no context, glossary or constraints."""
    items = {s["id"]: s.get("source", "") for s in challenge.get("strings", [])}
    system = "You are a translator."
    user = (f"Translate into English ({locale}). Return JSON in this shape: "
            '{"translations": [{"id": "...", "text": "..."}]}\n\n'
            + json.dumps(items, ensure_ascii=False, indent=2))
    return system, user


def build_translator_prompt(challenge: dict, agent_cfg: dict, locale: str, memory_rules,
                            string_ids=None) -> tuple[str, str]:
    names = _char_names(challenge)
    parts = [
        _section("Task", f"Translate from {_source_language(challenge)} into English."),
        _section("Your instructions (written by the localisation team)", agent_cfg.get("instructions", "")),
        _section("Settings chosen by the team", settings_to_text("translator", agent_cfg.get("settings", {}))),
        _section("Target English variant", LOCALE_LINES.get(locale, LOCALE_LINES["en"])),
        _section("Glossary", _glossary_text(challenge)),
        _section("Project memory (approved by the human director)", _memory_text(memory_rules)),
        _section("Scene context", challenge.get("scene_context") or "Not given."),
        _section("Characters", _characters_text(challenge)),
        _section("Strings", "\n\n".join(_string_block(s, names)
                                        for s in _strings_for(challenge, string_ids))),
        _section("Output format", TRANSLATION_SCHEMA),
    ]
    return TRANSLATOR_ROLE, "\n\n".join(parts)


def build_reviewer_prompt(challenge: dict, agent_cfg: dict, locale: str, memory_rules,
                          translations: dict, string_ids=None) -> tuple[str, str]:
    names = _char_names(challenge)
    strings = [s for s in _strings_for(challenge, string_ids) if s["id"] in translations]
    parts = [
        _section("Task", f"Review an English translation of {_source_language(challenge)} game text."),
        _section("Your instructions (written by the localisation team)", agent_cfg.get("instructions", "")),
        _section("Settings chosen by the team", settings_to_text("reviewer", agent_cfg.get("settings", {}))),
        _section("Target English variant", LOCALE_LINES.get(locale, LOCALE_LINES["en"])),
        _section("Glossary", _glossary_text(challenge)),
        _section("Project memory (approved by the human director)", _memory_text(memory_rules)),
        _section("Scene context", challenge.get("scene_context") or "Not given."),
        _section("Characters", _characters_text(challenge)),
        _section("Strings under review", "\n\n".join(
            _string_block(s, names, translations.get(s["id"], "")) for s in strings)),
        _section("Output format", FINDINGS_SCHEMA),
    ]
    return REVIEWER_ROLE, "\n\n".join(parts)


def build_revision_prompt(challenge: dict, agent_cfg: dict, locale: str, memory_rules,
                          translations: dict, feedback: list[dict], string_ids,
                          locked: dict | None = None) -> tuple[str, str]:
    """Translator prompt for ``string_ids`` + accepted feedback only + locked context."""
    system, user = build_translator_prompt(challenge, agent_cfg, locale, memory_rules, string_ids)
    q = lambda t: json.dumps(t, ensure_ascii=False)  # noqa: E731
    current = "\n".join(f"- {sid}: {q(translations.get(sid, ''))}" for sid in string_ids)
    fb_lines = []
    for f in feedback:
        line = (f"- [{f['string_id']}] {f.get('finding_id', '')} ({f.get('category', '')}, "
                f"{f.get('severity', '')}): {f.get('issue', '')}\n"
                f"  Reviewer suggestion: {q(f.get('suggestion', ''))}")
        if f.get("comment"):
            line += f"\n  Director's comment: {f['comment']}"
        fb_lines.append(line)
    extra = [
        _section("Current translations of the strings to revise", current),
        _section("Feedback accepted by the human director", "\n".join(fb_lines) or "None."),
    ]
    if locked:
        extra.append(_section(
            "Locked strings decided by the human director (context only — do not return them)",
            "\n".join(f"- {sid}: {q(t)}" for sid, t in locked.items())))
    extra.append(_section(
        "Revision rules",
        "Revise only the strings listed under 'Strings'. Apply the accepted feedback: you may use "
        "the reviewer's suggestion as written or improve it, but keep every constraint. Do not "
        "change any other string."))
    return system, user + "\n\n" + "\n\n".join(extra)


# --------------------------------------------------------------------------- parsing


class AgentOutputError(StudioError):
    """The model reply could not be used (after one repair attempt)."""


def _brace_candidates(text: str, limit: int = 20):
    starts = [m.start() for m in re.finditer(r"\{", text)][:limit]
    for start in starts:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield text[start:i + 1]
                    break


def extract_json_object(text: str) -> dict:
    """Bare JSON, fenced JSON, or a JSON object surrounded by prose."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty reply")
    t = text.strip()
    candidates = [t] + re.findall(r"```(?:json|JSON)?\s*(.*?)```", t, re.S)
    for c in candidates:
        try:
            obj = json.loads(c.strip())
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    for c in _brace_candidates(t):
        try:
            obj = json.loads(c)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no JSON object found")


def _bad_output(what: str) -> AgentOutputError:
    return AgentOutputError(f"The {what} reply could not be read as the expected JSON.")


def parse_translations(text: str, expected_ids) -> list[dict]:
    """``[{id, text, note}]`` for expected ids only; raises AgentOutputError if unreadable."""
    try:
        obj = extract_json_object(text)
    except ValueError:
        raise _bad_output("translator") from None
    items = obj.get("translations")
    if not isinstance(items, list):
        raise _bad_output("translator")
    expected = set(expected_ids)
    out, seen = [], set()
    for it in items:
        if not isinstance(it, dict):
            continue
        sid, txt = it.get("id"), it.get("text")
        if sid in expected and sid not in seen and isinstance(txt, str):
            note = it.get("note")
            out.append({"id": sid, "text": txt, "note": note if isinstance(note, str) else ""})
            seen.add(sid)
    if expected and not out:
        raise _bad_output("translator")
    return out


_CATEGORY_ALIASES = {"voice": "character_voice", "character": "character_voice",
                     "style": "fluency", "grammar": "fluency", "naturalness": "fluency",
                     "meaning": "accuracy", "mistranslation": "accuracy", "omission": "accuracy",
                     "glossary": "terminology", "consistency": "terminology",
                     "culture": "cultural", "placeholder": "technical", "length": "technical",
                     "formatting": "technical"}


def _norm_category(c) -> str:
    c = str(c or "").strip().lower().replace(" ", "_").replace("-", "_")
    return c if c in CATEGORIES else _CATEGORY_ALIASES.get(c, "accuracy")


def _normalisation_note(raw_category, category, raw_severity, severity) -> str:
    """'category 'style' → fluency' etc. when the reply used a value outside the schema."""
    notes = []
    if str(raw_category or "").strip().lower().replace(" ", "_").replace("-", "_") not in CATEGORIES:
        notes.append(f"category '{raw_category}' → {category}")
    if str(raw_severity or "").strip().lower() not in SEVERITIES:
        notes.append(f"severity '{raw_severity}' → {severity}")
    return "; ".join(notes)


def parse_findings(text: str, valid_ids) -> tuple[list[dict], int]:
    """Normalised findings for known ids, and how many were dropped.

    A finding whose category or severity was outside the schema is kept with the nearest
    value and carries ``normalised`` (e.g. "category 'style' → fluency"); otherwise "".
    """
    try:
        obj = extract_json_object(text)
    except ValueError:
        raise _bad_output("reviewer") from None
    items = obj.get("findings")
    if not isinstance(items, list):
        raise _bad_output("reviewer")
    valid = set(valid_ids)
    out, dropped = [], 0
    for it in items:
        if not isinstance(it, dict) or it.get("string_id") not in valid or not str(it.get("issue") or "").strip():
            dropped += 1
            continue
        sev = str(it.get("severity") or "").strip().lower()
        sev = sev if sev in SEVERITIES else "minor"
        cat = _norm_category(it.get("category"))
        out.append({"string_id": it["string_id"], "category": cat, "severity": sev,
                    "issue": str(it.get("issue")).strip(),
                    "reasoning": str(it.get("reasoning") or "").strip(),
                    "suggestion": it.get("suggestion") if isinstance(it.get("suggestion"), str) else "",
                    "normalised": _normalisation_note(it.get("category"), cat,
                                                      it.get("severity"), sev)})
    return out, dropped


# --------------------------------------------------------------------------- running


def _batches(ids: list[str], size: int = BATCH_SIZE) -> list[list[str]]:
    return [ids[i:i + size] for i in range(0, len(ids), size)]


def _model_for(state: ProjectState, agent: str) -> str:
    p = state.provider
    if agent == "reviewer":
        return p.get("reviewer_model") or p.get("translator_model") or ""
    return p.get("translator_model") or ""


def _source(provider) -> str:
    return "live" if getattr(provider, "is_live", True) else "replay"


def _check_cap(state: ProjectState, provider, n: int) -> None:
    """Refuse a step that would go past the cap: the session meter if the provider has one
    (it survives key reloads and mission changes), else this project's own counter."""
    if n <= 0 or not getattr(provider, "is_live", True):
        return
    meter = getattr(provider, "usage_meter", None)
    if meter is not None:
        cap, used, where = meter.request_cap, meter.requests, " in this session"
    else:
        cap, used, where = state.usage.get("request_cap", 40), state.usage.get("requests", 0), ""
    if used + n > cap:
        raise _provider_error("cap_reached", cap=cap,
                              extra=f"{used} used{where}, this step needs {n}")


def _record_usage(state: ProjectState, provider, resp, count_request: bool = True) -> None:
    """Add a reply to this project's usage (``state.usage`` is per project, for the report)."""
    u = state.usage
    if resp.simulated:
        u["simulated_requests"] = u.get("simulated_requests", 0) + 1
        return
    if count_request:
        u["requests"] = u.get("requests", 0) + 1
    u["input_tokens"] = u.get("input_tokens", 0) + (resp.input_tokens or 0)
    u["output_tokens"] = u.get("output_tokens", 0) + (resp.output_tokens or 0)
    meter = getattr(provider, "usage_meter", None)
    price = (meter.pricing.get(resp.model) if meter else None) or {}
    if price:
        cost = ((resp.input_tokens or 0) * price.get("input_per_mtok", 0)
                + (resp.output_tokens or 0) * price.get("output_per_mtok", 0)) / 1e6
        u["est_cost_usd"] = round((u.get("est_cost_usd") or 0.0) + cost, 6)


def _refuse_if_key(system: str, user: str) -> None:
    """A prompt that contains a loaded API key is never sent (nor stored as a snapshot)."""
    if find_secrets(f"{system}\n{user}"):
        raise StudioError("Not sent: the prompt contains your API key (or something like one). "
                          "Remove it from your instructions, rules, comments or upload, then retry.")


def _complete_counted(state, provider, system, prompt, **kw):
    """``provider.complete`` that adds every HTTP attempt it makes (retries included, failed
    ones too) to this project's ``usage["requests"]``, read from the session meter."""
    meter = getattr(provider, "usage_meter", None)
    before = meter.requests if meter is not None else None
    try:
        resp = provider.complete(system, prompt, **kw)
    finally:
        if before is not None:
            state.usage["requests"] = state.usage.get("requests", 0) + meter.requests - before
    _record_usage(state, provider, resp, count_request=before is None)
    return resp


def max_tokens_for(provider) -> int:
    """The output limit per request: providers.json ``limits.max_tokens``, else 4000."""
    limits = getattr(provider, "limits", None)
    try:
        return int((limits or {}).get("max_tokens") or MAX_TOKENS)
    except (TypeError, ValueError, AttributeError):
        return MAX_TOKENS


def _takes_json_schema(provider) -> bool:
    """Only pass ``json_schema`` to providers whose ``complete`` accepts it."""
    if not getattr(provider, "accepts_json_schema", False):
        return False
    # follow pass-through wrappers (e.g. the UI's progress wrapper keeps the real one in _inner)
    for _ in range(5):
        try:
            params = list(inspect.signature(provider.complete).parameters.values())
        except (TypeError, ValueError, AttributeError):
            return False
        if any(p.name == "json_schema" for p in params):
            return True
        inner = (vars(provider) if hasattr(provider, "__dict__") else {}).get("_inner")
        if inner is None or not any(p.kind is p.VAR_KEYWORD for p in params):
            return False
        provider = inner
    return False


def _log_provider_notes(state, provider) -> None:
    notes = getattr(provider, "notes", None)
    if isinstance(notes, list):
        while notes:
            state.log("provider_note", str(notes.pop(0)))


def _ask(state, provider, *, agent, rnd, system, user, model, temperature, replay_key, parse,
         json_schema=None):
    """One request + at most one repair request. Returns the parsed result.

    ``json_schema`` (structured outputs) is passed to providers that accept it; the tolerant
    parser and the repair request stay as the safety net for every provider.
    If the reply was cut off at the output limit, the repair request asks for compact output.
    """
    src = _source(provider)
    _refuse_if_key(system, user)
    raws, prompt, cut_off = [], user, False
    extra = {"json_schema": json_schema} if json_schema and _takes_json_schema(provider) else {}
    for attempt in range(2):
        _check_cap(state, provider, 1)
        state.add_snapshot(agent, rnd, system, prompt, model, src)
        try:
            resp = _complete_counted(state, provider, system, prompt, model=model,
                                     max_tokens=max_tokens_for(provider), temperature=temperature,
                                     replay_key=replay_key, **extra)
        finally:
            _log_provider_notes(state, provider)
        raws.append(resp.text or "")
        cut_off = bool(getattr(resp, "truncated", False))
        try:
            return parse(resp.text)
        except AgentOutputError:
            state.log("parse_failed", f"{agent} round {rnd}: reply not readable"
                      + (" (cut off at the output limit)" if cut_off else "")
                      + (" — sending one repair request" if attempt == 0 else ""))
        prompt = user + "\n\n" + _section(REPAIR_MARK[3:],
                                           TRUNCATED_REPAIR_TEXT if cut_off else REPAIR_TEXT)
    for raw in raws:
        state.raw_failures.append({"agent": agent, "round": rnd, "text": raw[:RAW_LIMIT],
                                   "created_at": state.updated_at})
    if cut_off:
        raise AgentOutputError(
            f"The {agent} reply was cut off because it was too long, even after asking for a "
            "shorter reply. Nothing was changed. Try fewer strings or a shorter instruction "
            "(ask for short notes), or switch to Replay Mode. The raw reply is saved in the "
            "project for inspection.")
    raise AgentOutputError(
        f"The {agent} reply could not be read, even after one repair request. Nothing was "
        "changed. Try again, simplify the instructions, or switch to Replay Mode. The raw reply "
        "is saved in the project for inspection.")


def _require_strings(challenge: dict) -> list[str]:
    ids = [s["id"] for s in challenge.get("strings", [])]
    if not ids:
        raise StudioError("This challenge has no strings to translate.")
    return ids


def _translate_all(state, provider, challenge, agent, ids, build, temperature, rnd=0,
                   variant=None):
    """Results per id, and the ids of batches that failed after an earlier batch succeeded.

    If the first batch fails the error is raised (nothing to keep). If a later batch fails,
    the completed batches are kept, no further batches are sent, and the unsent/failed ids
    are returned so the caller keeps their previous text and warns (event ``partial_run``).
    """
    _check_cap(state, provider, len(_batches(ids)))
    model = _model_for(state, "translator")
    results: dict[str, dict] = {}
    batches = _batches(ids)
    for n, batch in enumerate(batches):
        system, user = build(batch)
        key = {"challenge": state.challenge_id, "stage": agent, "round": rnd, "string_ids": batch}
        if variant:
            key["variant"] = variant
        try:
            items = _ask(state, provider, agent=agent, rnd=rnd, system=system, user=user,
                         model=model, temperature=temperature, replay_key=key,
                         parse=lambda t, b=batch: parse_translations(t, b),
                         json_schema=translations_json_schema(batch))
        except (ProviderError, AgentOutputError) as e:
            if not results:
                raise
            failed = [sid for b in batches[n:] for sid in b]
            state.log("partial_run", (
                f"{agent}: request {n + 1} of {len(batches)} failed, so {len(failed)} string(s) "
                f"were not translated this time and keep their previous text: {', '.join(failed)}. "
                f"The other strings were kept. Run this step again to retry them. "
                f"Reason: {e.user_message}"))
            return results, failed
        results.update({it["id"]: it for it in items})
    return results, []


def _merge(state, results: dict, ids, previous: dict, agent: str,
           failed=()) -> tuple[dict, dict]:
    translations, notes, missing = dict(previous), {}, []
    failed = set(failed)
    for sid in ids:
        if sid in results:
            translations[sid] = results[sid]["text"]
            if results[sid].get("note"):
                notes[sid] = results[sid]["note"]
        elif sid in failed:
            notes[sid] = ("Not translated this time (a request failed) — kept the previous text."
                          if sid in previous else
                          "Not translated this time (a request failed) — no text yet.")
        else:
            missing.append(sid)
            notes[sid] = ("Missing from the model reply — kept the previous text."
                          if sid in previous else "Missing from the model reply — not translated.")
    if missing:
        state.log("warning", f"{agent}: the reply did not include {', '.join(missing)}; "
                  "previous text kept where there was one (nothing was invented).")
    return translations, notes


def run_baseline(state: ProjectState, provider, challenge: dict) -> Version:
    ids = _require_strings(challenge)
    sub = lambda b: build_baseline_prompt({"strings": _strings_for(challenge, b)}, state.locale)  # noqa: E731
    results, failed = _translate_all(state, provider, challenge, "baseline", ids, sub,
                                     BASELINE_TEMPERATURE)
    prev = state.baseline_version()
    translations, notes = _merge(state, results, ids, prev.translations if prev else {},
                                 "baseline", failed)
    v = state.add_version("Baseline (minimal prompt)", "baseline", _source(provider), translations,
                          round=0, notes=notes, make_current=False)
    state.baseline_version_id = v.version_id
    if state.stage == "INPUT":
        state.stage = "BASELINE"
    return v


def run_translator(state: ProjectState, provider, challenge: dict) -> Version:
    ids = _require_strings(challenge)
    cfg = state.agents["translator"]
    temp = temperature_for("translator", cfg.get("settings"))
    build = lambda b: build_translator_prompt(challenge, cfg, state.locale, _rules(state), b)  # noqa: E731
    variant = _preset_name(cfg)
    results, failed = _translate_all(state, provider, challenge, "translator", ids, build, temp,
                                     variant=variant)
    cur = state.current_version()
    translations, notes = _merge(state, results, ids, cur.translations if cur else {},
                                 "translator", failed)
    state.invalidate_approval("translator re-run")
    label = "Translator agent"
    if not getattr(provider, "is_live", True):
        label = f"Translator · Replay · {TRANSLATOR_PRESETS[variant]['label']} preset"
        if cfg.get("edited"):
            label += " (your edits not applied)"
        state.log("replay_variant", replay_variant_note(cfg))
    v = state.add_version(label, "translator", _source(provider), translations,
                          round=0, parent_id=cur.version_id if cur else None, notes=notes)
    v.variant = variant
    if state.stage not in ("APPROVED", "EXPORTED"):
        state.stage = "TRANSLATED"
    return v


def _rules(state: ProjectState) -> list[dict]:
    return [r.__dict__ for r in state.memory_rules]


def version_variant(state: ProjectState, version: Version | None) -> str:
    """Prompt variant of a version: its own, else inherited from its parents (§15)."""
    seen = set()
    while version is not None and version.version_id not in seen:
        if getattr(version, "variant", None) in TRANSLATOR_PRESETS:
            return version.variant
        seen.add(version.version_id)
        version = state.version(version.parent_id)
    return DEFAULT_PRESET


def _review_targets(state: ProjectState, string_ids=None) -> list[str]:
    cur = state.current_version()
    if cur is None:
        raise StudioError("Run the translator first; there is nothing to review yet.")
    all_ids = [sid for sid in state.string_ids() if sid in cur.translations] or list(cur.translations)
    if string_ids is not None:
        return [sid for sid in all_ids if sid in set(string_ids)]
    last = state.version(state.revision.get("last_reviewed_version_id"))
    if last is None:
        return all_ids
    return [sid for sid in all_ids if cur.translations.get(sid) != last.translations.get(sid)]


class ReviewResult(list):
    """The findings of one review run (a ``list[Finding]``) plus what happened to the rest.

    ``skipped``: no request was made because no string changed since the last review.
    ``received``: findings in the replies; ``dropped``: unknown string id or no issue text;
    ``off_topic``: outside the ticked categories; ``over_limit``: beyond ``max_findings``;
    ``normalised``: kept findings whose category/severity was mapped to an allowed value.
    """

    def __init__(self, findings=(), *, reviewed_ids=(), skipped=False, received=0, dropped=0,
                 off_topic=0, over_limit=0, normalised=()):
        super().__init__(findings)
        self.reviewed_ids = list(reviewed_ids)
        self.skipped, self.received, self.dropped = skipped, received, dropped
        self.off_topic, self.over_limit = off_topic, over_limit
        self.normalised = list(normalised)

    @property
    def all_dropped(self) -> bool:
        """The reviewer did report findings, but none could be used (a problem, not 'all fine')."""
        return not self and self.dropped > 0 and self.dropped == self.received

    def counts_text(self) -> str:
        parts = []
        if self.dropped:
            parts.append(f"{self.dropped} finding(s) dropped because they named an unknown "
                         "string id or had no issue text")
        if self.off_topic:
            parts.append(f"{self.off_topic} finding(s) outside the ticked categories ignored")
        if self.over_limit:
            parts.append(f"{self.over_limit} finding(s) over the maximum number ignored")
        if self.normalised:
            parts.append(f"{len(self.normalised)} finding(s) with an unknown category or severity mapped to "
                         "the nearest one (" + "; ".join(self.normalised[:3])
                         + ("; …" if len(self.normalised) > 3 else "") + ")")
        return "; ".join(parts)


def run_reviewer(state: ProjectState, provider, challenge: dict, string_ids=None) -> ReviewResult:
    """Review the current version. Later rounds default to the strings changed since.

    Returns a :class:`ReviewResult` (a list of the new findings with counts attached).
    If every finding in the replies had to be dropped, the version is not marked as
    reviewed, so running the reviewer again re-checks the same strings.
    """
    ids = _review_targets(state, string_ids)
    if not ids:
        state.log("review_skipped", "No strings changed since the last review; nothing to review.")
        return ReviewResult(skipped=True)
    cur = state.current_version()
    cfg = state.agents["reviewer"]
    settings = normalise_settings("reviewer", cfg.get("settings"))
    rnd = state.latest_review_round() + 1
    _check_cap(state, provider, len(_batches(ids)))
    model = _model_for(state, "reviewer")
    raw_findings, dropped = [], 0
    for n, batch in enumerate(_batches(ids)):
        system, user = build_reviewer_prompt(challenge, cfg, state.locale, _rules(state),
                                             cur.translations, batch)
        key = {"challenge": state.challenge_id, "stage": "reviewer", "round": rnd,
               "string_ids": batch, "variant": version_variant(state, cur)}
        if n == 0:
            key["known_ids"] = state.string_ids()
        found, d = _ask(state, provider, agent="reviewer", rnd=rnd, system=system, user=user,
                        model=model, temperature=REVIEWER_TEMPERATURE, replay_key=key,
                        parse=lambda t, b=batch: parse_findings(t, b),
                        json_schema=findings_json_schema(batch))
        raw_findings += found
        dropped += d
    allowed = {c for c in CATEGORIES if settings[f"check_{c}"]}
    kept = [f for f in raw_findings if f["category"] in allowed]
    off_topic = len(raw_findings) - len(kept)
    order = {"critical": 0, "major": 1, "minor": 2}
    kept = sorted(kept, key=lambda f: order[f["severity"]])
    extra = max(0, len(kept) - settings["max_findings"])
    kept = kept[: settings["max_findings"]]
    findings = [Finding(f"R{rnd}-{n:02d}", rnd, f["string_id"], f["category"], f["severity"],
                        f["issue"], f["reasoning"], f["suggestion"], cur.version_id,
                        _source(provider)) for n, f in enumerate(kept, 1)]
    normalised = [f"{fd.finding_id}: {f['normalised']}" for fd, f in zip(findings, kept)
                  if f.get("normalised")]
    result = ReviewResult(findings, reviewed_ids=ids, received=len(raw_findings) + dropped,
                          dropped=dropped, off_topic=off_topic, over_limit=extra,
                          normalised=normalised)
    state.findings.extend(findings)
    if not result.all_dropped:
        state.revision["last_reviewed_version_id"] = cur.version_id
    detail = f"Round {rnd}: {len(findings)} finding(s) on {len(ids)} string(s)"
    if result.counts_text():
        detail += "; " + result.counts_text()
    if result.all_dropped:
        detail += ("; every finding was dropped, so these strings still count as not reviewed")
    state.log("review", detail)
    if state.stage not in ("APPROVED", "EXPORTED"):
        state.stage = "REVIEWED"
    return result


def _revision_plan(state: ProjectState):
    rnd = state.latest_review_round()
    if rnd == 0:
        raise StudioError("Run the reviewer first; there is no feedback to apply yet.")
    if any(v.kind == "revision" and v.round == rnd for v in state.versions):
        raise StudioError(f"Review round {rnd} is already applied. Run the reviewer again first.")
    cur = state.current_version()
    reviewed = state.version(state.revision.get("last_reviewed_version_id")) or cur
    decisions = state.latest_decisions()
    human, accepts = {}, {}
    for f in state.findings:
        d = decisions.get(f.finding_id)
        if f.round != rnd or d is None:
            continue
        if d.action in ("accept_edited", "override"):
            human[f.string_id] = d.human_text
        elif d.action == "accept":
            accepts.setdefault(f.string_id, []).append(
                {"finding_id": f.finding_id, "string_id": f.string_id, "category": f.category,
                 "severity": f.severity, "issue": f.issue, "suggestion": f.suggestion,
                 "comment": d.comment})
    locked = dict(human)
    for sid, text in cur.translations.items():
        if reviewed and text != reviewed.translations.get(sid) and sid not in locked:
            locked[sid] = text   # changed by the human since the review (direct edit / restore)
    for sid in list(accepts):
        if sid in locked:
            state.log("warning", f"{sid}: the human text takes priority over the accepted "
                      "reviewer suggestion.")
            del accepts[sid]
    return rnd, human, accepts, locked


def estimate_requests(state: ProjectState, challenge: dict, step: str) -> int:
    """Requests the next step will make (Replay requests are free and not counted)."""
    if step in ("baseline", "translator"):
        return len(_batches([s["id"] for s in challenge.get("strings", [])]))
    if step == "reviewer":
        try:
            return len(_batches(_review_targets(state)))
        except StudioError:
            return 0
    if step == "revision":
        try:
            _, _, accepts, _ = _revision_plan(state)
        except StudioError:
            return 0
        return len(_batches(list(accepts)))
    raise StudioError(f"Unknown step '{step}'.")


def run_revision(state: ProjectState, provider, challenge: dict, role: str = "director") -> Version:
    """Apply accepted feedback (bounded by revision.max_cycles)."""
    max_c, done = state.revision.get("max_cycles", 1), state.revision.get("cycles_done", 0)
    if done >= max_c:
        raise StudioError(f"All {max_c} revision cycle(s) used. Edit strings directly, or approve.")
    cur = state.current_version()
    if cur is None:
        raise StudioError("Run the translator first.")
    rnd, human, accepts, locked = _revision_plan(state)
    if not human and not accepts:
        raise StudioError(f"Nothing to revise: no finding from round {rnd} was accepted or given "
                          "your wording (rejected ones are never applied).")
    translations = dict(cur.translations)
    notes = {}
    for sid, text in human.items():
        translations[sid] = text
        notes[sid] = "Human director's text applied directly (no AI request)."
    accept_ids = [sid for sid in state.string_ids() if sid in accepts] or list(accepts)
    _check_cap(state, provider, len(_batches(accept_ids)))
    source = "human"
    if accept_ids:
        source = _source(provider)
        cfg = state.agents["translator"]
        temp = temperature_for("reviser", cfg.get("settings"))
        model = _model_for(state, "translator")
        rev_notes = ((getattr(provider, "fixtures", {}) or {}).get("challenges", {})
                     .get(state.challenge_id, {}).get("revision_notes", {}))
        results = {}
        for batch in _batches(accept_ids):
            fb = [f for sid in batch for f in accepts[sid]]
            system, user = build_revision_prompt(challenge, cfg, state.locale, _rules(state),
                                                 translations, fb, batch, locked)
            key = {"challenge": state.challenge_id, "stage": "reviser", "round": rnd,
                   "string_ids": batch, "variant": version_variant(state, cur)}
            if not getattr(provider, "is_live", True):
                out = []
                for sid in batch:
                    sugg = next((f["suggestion"] for f in reversed(accepts[sid]) if f["suggestion"]), "")
                    if sugg:
                        out.append({"id": sid, "text": sugg, "note": rev_notes.get(
                            sid, "Applied accepted reviewer suggestion (simulated).")})
                key["deterministic_output"] = {"translations": out}
                if not out:   # accepted findings without suggestion text: nothing to apply
                    continue
            items = _ask(state, provider, agent="reviser", rnd=rnd, system=system, user=user,
                         model=model, temperature=temp, replay_key=key,
                         parse=lambda t, b=batch: parse_translations(t, b),
                         json_schema=translations_json_schema(batch))
            results.update({it["id"]: it for it in items})
        merged, merged_notes = _merge(state, results, accept_ids, translations, "reviser")
        translations = merged
        notes.update(merged_notes)
    state.invalidate_approval("revision")
    state.revision["cycles_done"] = done + 1
    v = state.add_version(f"Revision {done + 1}", "revision", source, translations, round=rnd,
                          parent_id=cur.version_id, notes=notes)
    v.variant = version_variant(state, cur)
    state.add_decision("send_revision", role,
                       comment=f"Revision {done + 1}: {len(accept_ids)} via agent, "
                               f"{len(human)} human text(s)")
    if state.stage not in ("APPROVED", "EXPORTED"):
        state.stage = "REVISED"
    return v


def preview(state: ProjectState, challenge: dict, step: str,
            provider_config: dict | None = None) -> dict:
    """What the next step will send (first batch), for display before running it."""
    cfg_t, cfg_r = state.agents["translator"], state.agents["reviewer"]
    cur = state.current_version()
    if step == "baseline":
        system, user = build_baseline_prompt(challenge, state.locale)
        role, settings = "baseline", None
    elif step == "translator":
        ids = _batches([s["id"] for s in challenge.get("strings", [])])[0]
        system, user = build_translator_prompt(challenge, cfg_t, state.locale, _rules(state), ids)
        role, settings = "translator", cfg_t.get("settings")
    elif step == "reviewer":
        ids = (_batches(_review_targets(state)) or [[]])[0]
        system, user = build_reviewer_prompt(challenge, cfg_r, state.locale, _rules(state),
                                             cur.translations if cur else {}, ids)
        role, settings = "reviewer", cfg_r.get("settings")
    elif step == "revision":
        rnd, human, accepts, locked = _revision_plan(state)
        ids = (_batches(list(accepts)) or [[]])[0]
        fb = [f for sid in ids for f in accepts[sid]]
        system, user = build_revision_prompt(challenge, cfg_t, state.locale, _rules(state),
                                             cur.translations, fb, ids, locked)
        role, settings = "reviser", cfg_t.get("settings")
    else:
        raise StudioError(f"Unknown step '{step}'.")
    pname = state.provider.get("name", "replay")
    return {"system": system, "user": user, "temperature": temperature_for(role, settings),
            "temperature_note": temperature_note(role, settings, pname, provider_config),
            "requests": estimate_requests(state, challenge, step)}
