"""Compatibility helpers for the notebook UI (``studio_ui.py``).

* ipywidgets 7 (Colab) and 8 (local) differences, e.g. ``FileUpload.value``.
* Colab helpers: custom widget manager, downloads, default paths.
* CONTRACTS §15 presets / Replay prompt variants, with fallbacks so the UI works
  both before and after the engine gains ``TRANSLATOR_PRESETS``/``apply_preset``.

Nothing in here talks to the network.
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

from . import agents, providers

# --------------------------------------------------------------------------- Colab


def in_colab() -> bool:
    if "google.colab" in sys.modules:
        return True
    try:
        import google.colab  # type: ignore  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - not running in Colab
        return False


def enable_colab_widgets() -> None:
    """Colab needs the custom widget manager for ipywidgets (FileUpload etc.)."""
    try:
        from google.colab import output  # type: ignore
        output.enable_custom_widget_manager()
    except Exception:  # noqa: BLE001 - not Colab, or already enabled
        pass


def colab_download(path, out=None, clear: bool = True) -> bool:
    """Start a browser download in Colab. Returns False outside Colab or on failure.

    ``files.download`` sends JavaScript to the cell that is "running". A widget button
    callback has no running cell, so in Colab the download silently goes nowhere. Calling
    it inside ``with out:`` (an ``ipywidgets.Output`` shown next to the button) gives it
    that output context. ``out`` is cleared first (unless ``clear`` is False, e.g. for the
    second of several files) so old download scripts do not pile up.
    True only when ``files.download`` returned without raising.
    """
    try:
        from google.colab import files  # type: ignore
    except Exception:  # noqa: BLE001 - not Colab
        return False
    started = False
    try:
        if out is None:
            files.download(str(path))
            return True
        if clear:
            out.clear_output()
        with out:
            try:  # caught here: Output.__exit__ would swallow it and show a traceback
                files.download(str(path))
                started = True
            except Exception:  # noqa: BLE001
                started = False
    except Exception:  # noqa: BLE001
        return False
    return started


def default_state_path(colab: bool) -> Path:
    if colab and Path("/content").is_dir():
        return Path("/content/studio_state.json")
    return Path.cwd() / "studio_state.json"


def default_export_dir(colab: bool) -> Path:
    if colab and Path("/content").is_dir():
        return Path("/content/exports")
    return Path.cwd() / "exports"


# --------------------------------------------------------------------------- ipywidgets 7/8


def uploaded_files(value) -> list[tuple[str, bytes]]:
    """``FileUpload.value`` → ``[(name, bytes)]`` for ipywidgets 7 (dict) and 8 (tuple)."""
    out: list[tuple[str, bytes]] = []
    if not value:
        return out
    if isinstance(value, dict):  # ipywidgets 7: {name: {"content": bytes, "metadata": {...}}}
        for name, info in value.items():
            if not isinstance(info, dict):
                continue
            meta = info.get("metadata") or {}
            content = info.get("content") or b""
            out.append((str(meta.get("name") or name), bytes(content)))
        return out
    for item in value:  # ipywidgets 8: ({"name", "content": memoryview, ...}, ...)
        if isinstance(item, dict):
            out.append((str(item.get("name") or "upload"), bytes(item.get("content") or b"")))
    return out


def clear_upload(fu) -> None:
    """Empty a FileUpload widget (both major versions)."""
    try:
        fu.value = ()          # ipywidgets 8
        return
    except Exception:  # noqa: BLE001
        pass
    try:                       # ipywidgets 7
        fu.value.clear()
        fu._counter = 0
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- presets (§15)

PRESET_ORDER = tuple(getattr(agents, "PRESET_ORDER", ("faithful", "balanced", "creative")))

_FAITHFUL_INSTRUCTIONS = (
    "Translate each string as closely to the source as English allows.\n"
    "- Keep the source wording, images and sentence order wherever the English stays correct.\n"
    "- Do not add, drop or explain ideas; keep idioms and cultural references as they are.\n"
    "- Interface text must stay within its limits; choices must read as actions.\n"
    "- Always use the glossary terms.\n"
    "- Respect every constraint: character limits, placeholders and line-break rules.\n"
    "- Use the note to flag any phrase you had to change, in one short sentence."
)
_CREATIVE_INSTRUCTIONS = (
    "Recreate the experience of each string for English-speaking players.\n"
    "- Put the effect on the player first: rewrite idioms, jokes and wordplay so they land in "
    "English, but keep every plot fact.\n"
    "- Give each character a vivid, distinctive voice based on their profile.\n"
    "- Interface text must stay short and punchy; choices must read as actions.\n"
    "- Respect every constraint: character limits, placeholders and line-break rules.\n"
    "- Use the note to explain any creative change in one short sentence."
)

_FALLBACK_PRESETS = {
    "faithful": {"label": "Faithful", "description": "Stay close to the source wording and structure.",
                 "settings": {"strategy": 1, "cultural_adaptation": 1, "register": "match_source",
                              "voice_strength": 2, "glossary_strictness": "must_use"},
                 "instructions": _FAITHFUL_INSTRUCTIONS},
    "balanced": {"label": "Balanced", "description": "Natural English that keeps meaning and function exact.",
                 "settings": agents.default_settings("translator"),
                 "instructions": agents.DEFAULT_TRANSLATOR_INSTRUCTIONS},
    "creative": {"label": "Creative", "description": "Lively, player-first adaptation with strong voices.",
                 "settings": {"strategy": 5, "cultural_adaptation": 4, "register": "playful",
                              "voice_strength": 5, "glossary_strictness": "prefer"},
                 "instructions": _CREATIVE_INSTRUCTIONS},
}


def engine_has_presets() -> bool:
    return isinstance(getattr(agents, "TRANSLATOR_PRESETS", None), dict) and hasattr(agents, "apply_preset")


def presets() -> dict:
    p = getattr(agents, "TRANSLATOR_PRESETS", None)
    return p if isinstance(p, dict) and p else _FALLBACK_PRESETS


def preset_label(name: str | None) -> str:
    p = presets().get(name or "")
    return (p or {}).get("label") or (name or "Balanced").title()


def apply_preset(cfg: dict, name: str) -> dict:
    """Return the translator config with preset ``name`` applied (engine version if present)."""
    if name not in presets():
        name = "balanced"
    if engine_has_presets():
        out = agents.apply_preset(cfg, name)
        return out if isinstance(out, dict) else cfg
    p = presets()[name]
    cfg = dict(cfg)
    cfg["settings"] = agents.normalise_settings("translator", p["settings"])
    cfg["instructions"] = p["instructions"]
    cfg.setdefault("default_instructions", agents.DEFAULT_TRANSLATOR_INSTRUCTIONS)
    cfg["preset"] = name
    cfg["edited"] = False
    return cfg


def mark_edited(cfg: dict) -> dict:
    if hasattr(agents, "mark_edited"):
        out = agents.mark_edited(cfg)
        return out if isinstance(out, dict) else cfg
    cfg = dict(cfg)
    p = presets().get(cfg.get("preset") or "balanced", presets()["balanced"])
    try:
        same_settings = (agents.normalise_settings("translator", cfg.get("settings"))
                         == agents.normalise_settings("translator", p["settings"]))
    except Exception:  # noqa: BLE001 - invalid settings count as edited
        same_settings = False
    cfg["edited"] = not (same_settings and (cfg.get("instructions") or "").strip()
                         == (p.get("instructions") or "").strip())
    return cfg


def replay_variant_note(cfg: dict) -> str:
    if hasattr(agents, "replay_variant_note"):
        try:
            return str(agents.replay_variant_note(cfg))
        except Exception:  # noqa: BLE001
            pass
    label = preset_label(cfg.get("preset"))
    if cfg.get("edited"):
        return (f"Prepared output for the ‘{label}’ preset. Your own edits are saved in your "
                "prompt and report, but Replay Mode cannot generate a new response — switch to "
                "Live Mode to test them.")
    return f"Prepared output for the ‘{label}’ preset."


# --------------------------------------------------------------------------- Replay variants


def _pick(entry, variant: str):
    """A plain stage entry, or the ``variant`` entry of a {variant: entry} dict (§15)."""
    if not isinstance(entry, dict):
        return None
    if "translations" in entry or "findings" in entry:
        return entry
    return entry.get(variant) or entry.get("balanced") or next(
        (v for v in entry.values() if isinstance(v, dict)), None)


def flatten_fixtures(fixtures: dict, variant: str) -> dict:
    """Fixture file in the pre-§15 shape (single translator/reviewer entries) for ``variant``."""
    out = {k: v for k, v in (fixtures or {}).items() if k != "challenges"}
    chs = {}
    for cid, ch in ((fixtures or {}).get("challenges") or {}).items():
        if not isinstance(ch, dict):
            continue
        flat = {k: v for k, v in ch.items()
                if k not in ("translator_variants", "translator", "reviewer", "reviewer_round2")}
        tr = _pick(ch.get("translator_variants"), variant) or _pick(ch.get("translator"), variant)
        for key, val in (("translator", tr), ("reviewer", _pick(ch.get("reviewer"), variant)),
                         ("reviewer_round2", _pick(ch.get("reviewer_round2"), variant))):
            if val is not None:
                flat[key] = copy.deepcopy(val)
        chs[cid] = flat
    out["challenges"] = chs
    return out


class ReplayVariantProvider:
    """Thin adapter over :class:`providers.ReplayProvider` that serves §15 prompt variants.

    It works with the engine before and after §15: the variant is read from the replay key
    if the engine sends one, otherwise from ``variant_fn(stage)`` (the UI's current preset /
    the variant of the version under review). The fixture is flattened to the plain shape
    for that variant, so the engine's ReplayProvider and parser do the rest unchanged.
    """
    name = "replay"
    display_name = "Replay Mode"
    is_live = False
    verified = True

    def __init__(self, fixtures: dict, config: dict | None = None, variant_fn=None, usage_meter=None):
        self.fixtures = fixtures or {}
        self.config = config or {}
        self.usage_meter = usage_meter
        self.label = self.fixtures.get("label", "SIMULATED OUTPUT")
        self._variant_fn = variant_fn or (lambda stage: "balanced")
        self._inner: dict[str, providers.ReplayProvider] = {}
        self.last_variant = None

    def __repr__(self) -> str:
        return "<ReplayVariantProvider name='replay' key=none>"

    def _provider(self, variant: str) -> providers.ReplayProvider:
        if variant not in self._inner:
            self._inner[variant] = providers.ReplayProvider(flatten_fixtures(self.fixtures, variant),
                                                            self.config, usage_meter=self.usage_meter)
        return self._inner[variant]

    def complete(self, system, user, *, model="replay", max_tokens=providers.DEFAULT_MAX_TOKENS,
                 temperature=0.3, replay_key=None):
        key = dict(replay_key or {})
        variant = key.pop("variant", None) or self._variant_fn(key.get("stage", "")) or "balanced"
        self.last_variant = variant
        return self._provider(variant).complete(system, user, model=model, max_tokens=max_tokens,
                                                temperature=temperature, replay_key=key)

    def test_connection(self, model: str = "replay"):
        return providers.ReplayProvider(self.fixtures, self.config).test_connection(model)


def env_flag(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip().lower()
