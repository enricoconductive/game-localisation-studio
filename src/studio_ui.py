"""Game Localisation Studio v0.3 — the notebook user interface (ipywidgets).

Students never edit Python: every step is a button, slider or text box. The engine
(``agents``, ``project_state``, ``providers``, ``exports``, ``validation``, ``importers``)
does the work; this module only collects input, calls the engine and shows results.

Rules followed throughout:
* Every piece of model, student or challenge text shown through ``widgets.HTML`` is
  ``html.escape``d. Raw text is shown in ``Textarea`` widgets where possible.
* API keys live only inside the provider object. They are never stored on the studio,
  in state, in messages or in files, and they are masked in error details.
* After every state-changing action the project is autosaved, so a Colab disconnection
  loses nothing. Buttons are disabled while working and always re-enabled afterwards.

"The student is the localisation director. The agents are collaborators, not authorities."
"""
from __future__ import annotations

import html
import json
import math
import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

import ipywidgets as widgets

from . import agents, exports, importers, project_state as ps, providers, validation
from . import ui_compat as compat
from .project_state import StudioError

GAME_URL = "https://enricoconductive.github.io/game-localisation-studio/game/"
REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES = ("AI Director", "Quality Evaluator")
PROVIDER_CHOICES = [("Claude (Anthropic)", "anthropic"), ("HKBU GenAI", "hkbu"),
                    ("Hugging Face", "huggingface"), ("Replay Mode — prepared outputs, no key", "replay")]
LOCALE_CHOICES = [("British English (en-GB)", "en-GB"), ("American English (en-US)", "en-US"),
                  ("International English (en)", "en")]
MISSION_ORDER = ("intro", "voice", "pun", "ui")
REFLECTION_QUESTION = ("What did your agents get wrong, what did you change, and why was the "
                       "final result better?")
REPLAY_BADGE = "REPLAY MODE — prepared, simulated outputs. Not a live AI response."
REPLAY_LOCALE_NOTE = ("Replay examples are written in British English; live agents will follow "
                      "your choice.")
DOWNLOAD_REMINDER = ("💾 Your autosave lives in this Colab runtime and is lost when Colab recycles "
                     "it (for example after a long break). Click “Download progress” in the status "
                     "bar to keep a copy you can resume from.")
ACTION_TEXT = {"accept": "Accepted", "reject": "Rejected", "accept_edited": "Accepted with my edit",
               "override": "Overridden with my own wording", "direct_edit": "Edited directly",
               "add_rule": "Added a project rule", "send_revision": "Sent feedback to translator",
               "restore_version": "Restored a version", "approve_final": "Approved final translation",
               "revoke_approval": "Revoked approval"}
STEP_TITLES = ("Connect", "Choose mission", "Configure agents", "Run agents", "Human Director",
               "Test & export")
FILES_PANEL = "open the Files panel (📁 folder icon on the left)"
# One stylesheet, shown (hidden) inside the status bar and the welcome box, so every Colab
# output frame has it. Each section is a light "card" with dark text, so the studio reads
# the same in Colab's light and dark themes (dark mode otherwise puts our dark-grey text
# on a dark background). The --jp-* variables are the ones ipywidgets 7 and 8 use.
STUDIO_CSS = """<style>
.studio-card{--jp-widgets-color:#1f2933;--jp-widgets-label-color:#1f2933;
 --jp-widgets-readout-color:#1f2933;--jp-widgets-input-color:#1f2933;
 --jp-widgets-input-background-color:#ffffff;--jp-widgets-input-border-color:#9aa5b1;
 --jp-widgets-input-focus-border-color:#2471a3;--jp-ui-font-color0:#1f2933;
 --jp-ui-font-color1:#1f2933;--jp-ui-font-color2:#3e4c59;--jp-ui-font-color3:#616e7c;
 --jp-content-font-color0:#1f2933;--jp-content-font-color1:#1f2933;--jp-layout-color0:#ffffff;
 --jp-layout-color1:#ffffff;--jp-layout-color2:#e4e9f0;--jp-layout-color3:#c3ccd6;
 --jp-border-color0:#9aa5b1;--jp-border-color1:#c3ccd6;--jp-border-color2:#d9e2ec;
 --jp-widgets-slider-handle-background-color:#ffffff;--jp-widgets-slider-handle-border-color:#616e7c;
 --jp-widgets-slider-active-handle-color:#2471a3;
 background:#fffdf8 !important;color:#1f2933 !important;border:1px solid #d9e2ec;
 border-radius:8px;padding:8px 12px !important;margin:0 0 6px 0;box-sizing:border-box;
 color-scheme:light}
.studio-card .widget-html,.studio-card .widget-html-content,.studio-card .widget-label,
.studio-card .widget-label-basic,.studio-card label,.studio-card .widget-readout,
.studio-card .widget-checkbox span{color:#1f2933 !important}
.studio-card .widget-html-content{line-height:1.4}
.studio-card h3,.studio-card h4,.studio-card p,.studio-card li,.studio-card td,.studio-card th,
.studio-card summary,.studio-card b,.studio-card i,.studio-card ul,.studio-card ol{color:inherit}
.studio-card code{color:#1f2933;background:#eef2f6;border-radius:3px;padding:0 3px}
.studio-card a{color:#1a5fb4}
.studio-card input:not([type=checkbox]):not([type=range]),.studio-card textarea,
.studio-card select{background:#ffffff !important;color:#1f2933 !important;
 border:1px solid #9aa5b1 !important}
.studio-card .jupyter-button:not(.mod-primary):not(.mod-success):not(.mod-info):not(.mod-warning):not(.mod-danger){
 background:#e4e9f0;color:#1f2933}
.studio-card .jupyter-button:disabled{opacity:.75}
.studio-card .widget-toggle-button.mod-active{background:#2471a3 !important;color:#ffffff !important;
 font-weight:bold;box-shadow:0 0 0 2px #1a4f72 inset}
.studio-card .widget-toggle-button:not(.mod-active){background:#e4e9f0 !important;color:#1f2933 !important}
.studio-card .p-TabBar-tab,.studio-card .lm-TabBar-tab{background:#e4e9f0;color:#1f2933}
.studio-card .p-TabBar-tab.p-mod-current,.studio-card .lm-TabBar-tab.lm-mod-current{
 background:#ffffff;color:#1f2933;font-weight:bold}
.studio-card .p-Collapse-header,.studio-card .lm-Collapse-header,
.studio-card .jupyter-widget-Collapse-header{background:#eef2f6 !important;color:#1f2933 !important}
.studio-card .p-Collapse-contents,.studio-card .lm-Collapse-contents,
.studio-card .jupyter-widget-Collapse-contents,.studio-card .widget-tab-contents,
.studio-card .p-TabPanel-tabContents,.studio-card .lm-TabPanel-tabContents{background:#ffffff;color:#1f2933}
.studio-scroll{border:1px solid #e4e7eb;border-radius:4px}
.studio-scroll>*{flex-shrink:0 !important}
</style>"""


# --------------------------------------------------------------------------- HTML helpers


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def esc_br(x) -> str:
    return esc(x).replace("\n", "<br>")


class Safe(str):
    """An HTML string built by this module from escaped parts (not escaped again)."""


class Warn(str):
    """A plain-text result that needs the student's attention (shown in amber)."""


_BOX_COLOURS = {"info": ("#eaf2fb", "#2471a3"), "ok": ("#e9f7ef", "#1e8449"),
                "warn": ("#fef5e7", "#b9770e"), "error": ("#fdedec", "#c0392b"),
                "replay": ("#fff4e5", "#d35400"), "plain": ("#f5f7fa", "#9aa5b1")}


def box(kind: str, inner_html: str) -> str:
    bg, fg = _BOX_COLOURS.get(kind, _BOX_COLOURS["info"])
    return (f'<div style="background:{bg};border-left:5px solid {fg};padding:8px 12px;'
            f'margin:6px 0;border-radius:4px;color:#1f2933;line-height:1.45">{inner_html}</div>')


def badge(text: str, colour: str = "#2471a3") -> str:
    return (f'<span style="display:inline-block;background:{colour};color:#fff;border-radius:10px;'
            f'padding:1px 8px;font-size:12px;margin-right:4px">{esc(text)}</span>')


_SEV_COLOURS = {"critical": "#c0392b", "major": "#d35400", "minor": "#7f8c8d",
                "CRITICAL": "#c0392b", "WARNING": "#b9770e"}

_TABLE_CSS = ("border-collapse:collapse;width:100%;font-size:13px;color:#1f2933;"
              "background:#fff;margin:4px 0")
_CELL = "border:1px solid #d9e2ec;padding:4px 6px;vertical-align:top;text-align:left"
_DIFF_CSS = ("<style>.gls-diff table.diff{border-collapse:collapse;width:100%;font-size:12px;"
             "font-family:monospace;background:#fff;color:#1f2933}"
             ".gls-diff td,.gls-diff th{border:1px solid #d9e2ec;padding:2px 6px;vertical-align:top;"
             "white-space:pre-wrap;text-align:left}.gls-diff td.del{background:#fdecea}"
             ".gls-diff td.ins{background:#e6f4ea}.gls-diff td.skip{color:#616e7c;text-align:center;"
             "font-style:italic}</style>")


def table(headers, rows, row_styles=None) -> str:
    """``rows`` hold already-escaped HTML cell strings."""
    head = "".join(f'<th style="{_CELL};background:#f0f4f8">{esc(h)}</th>' for h in headers)
    body = []
    for n, r in enumerate(rows):
        style = (row_styles or {}).get(n, "")
        body.append(f'<tr style="{style}">' + "".join(f'<td style="{_CELL}">{c}</td>' for c in r)
                    + "</tr>")
    return (f'<div style="overflow-x:auto"><table style="{_TABLE_CSS}"><thead><tr>{head}</tr>'
            f'</thead><tbody>{"".join(body)}</tbody></table></div>')


def _layout(**kw) -> widgets.Layout:
    return widgets.Layout(**kw)


def _button(text, style="", width="auto", icon="") -> widgets.Button:
    return widgets.Button(description=text, button_style=style, icon=icon,
                          layout=_layout(width=width, height="auto", min_height="32px"))


def _html(value="") -> widgets.HTML:
    return widgets.HTML(value=value, layout=_layout(width="100%"))


def _textarea(value="", rows=4, placeholder="") -> widgets.Textarea:
    return widgets.Textarea(value=value, rows=rows, placeholder=placeholder,
                            continuous_update=False, layout=_layout(width="100%"))


def _scroll(child, max_height="400px") -> widgets.Box:
    """``child`` in a box of bounded height that scrolls, so long results do not make the
    Colab output frame jump (the buttons above stay in view)."""
    b = widgets.Box([child], layout=_layout(max_height=max_height, overflow="auto", width="100%",
                                            flex_flow="column"))
    b.add_class("studio-scroll")
    return b


def _accordion(pairs, open_index=None) -> widgets.Accordion:
    """``[(title, widget)]`` as an Accordion, collapsed unless ``open_index`` is given."""
    acc = widgets.Accordion(children=[w for _, w in pairs])
    for i, (title, _) in enumerate(pairs):
        acc.set_title(i, title)
    acc.selected_index = open_index
    return acc


def _tabs(pairs) -> widgets.Tab:
    tab = widgets.Tab(children=[w for _, w in pairs])
    for i, (title, _) in enumerate(pairs):
        tab.set_title(i, title)
    tab.selected_index = 0
    return tab


def _card(*children) -> widgets.VBox:
    """A light card with dark text: readable in Colab's light and dark themes."""
    v = widgets.VBox(list(children), layout=_layout(width="100%"))
    v.add_class("studio-card")
    return v


def _hidden(w, hidden=True):
    # "" (not None): Colab's widget manager leaves an already-rendered display:none in place
    # when the trait becomes None, so a panel shown after rendering stayed invisible.
    w.layout.display = "none" if hidden else ""
    return w


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iter_widgets(root):
    """Every widget below ``root`` (used by tests to check escaping)."""
    seen, stack = set(), [root]
    while stack:
        w = stack.pop()
        if id(w) in seen:
            continue
        seen.add(id(w))
        yield w
        stack.extend(getattr(w, "children", ()) or ())


class _ProgressProvider:
    """Wraps a provider to show "Working… (n of m requests)" while a step runs."""

    def __init__(self, inner, total: int, report):
        self._inner, self._total, self._report, self._n = inner, max(total, 1), report, 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def complete(self, *a, **k):
        self._n += 1
        self._report(f"Working… ({self._n} of {max(self._total, self._n)} requests)")
        return self._inner.complete(*a, **k)


# --------------------------------------------------------------------------- the studio


class Studio:
    """The whole notebook UI. Build with :meth:`boot`; show sections with :meth:`section`."""

    def __init__(self, repo_root=None, state_path=None, export_dir=None, checkpoints_dir=None,
                 fixtures: dict | None = None, provider_factory=None, getpass_fn=None,
                 userdata=None, colab: bool | None = None):
        self.root = Path(repo_root or REPO_ROOT).resolve()
        self.colab = compat.in_colab() if colab is None else bool(colab)
        self.state_path = Path(state_path) if state_path else compat.default_state_path(self.colab)
        self.export_dir = Path(export_dir) if export_dir else compat.default_export_dir(self.colab)
        self.checkpoints_dir = (Path(checkpoints_dir) if checkpoints_dir
                                else self.root / "fixtures" / "checkpoints")
        self._fixtures = fixtures
        self._provider_factory = provider_factory or providers.make_provider
        self._getpass_fn, self._userdata = getpass_fn, userdata
        self.provider_config = providers.load_provider_config(str(self.root / "config" / "providers.json"))
        self.catalog = providers.load_model_catalog(str(self.root / "config" / "models.json"))
        self.manifest = validation.load_manifest(str(self.root / "game" / "strings_manifest.json"))
        self.request_cap = int((self.provider_config.get("limits") or {}).get("request_cap", 40))
        # One meter for the whole session: it survives "Load my key", provider switches and
        # mission changes, and counts every live HTTP attempt (Replay never counts).
        self.meter = providers.UsageMeter(self.request_cap, providers.pricing_from_catalog(self.catalog))
        self.state: ps.ProjectState | None = None
        self.challenge: dict | None = None
        self.custom_challenge: dict | None = None
        self.provider = None
        self.provider_name: str | None = None
        self.translator_model = ""
        self.reviewer_model = ""
        self.role = ROLES[0]
        self.extras: dict = self._fresh_extras()
        self.autosaved_at: str | None = None
        self.autosave_problem: str | None = None
        self._suspend = False
        self._pending_provider = None
        self._live_hint = False
        self._saved_session_handled = False
        self._finding_cards: dict[str, dict] = {}
        self._grid: dict[str, widgets.Textarea] = {}
        self._grid_version: str | None = None
        self._grid_ids: tuple = ()
        self._busy_msg: widgets.HTML | None = None
        self.w: dict = {}
        self._build_all()
        self.refresh()

    # ------------------------------------------------------------------ boot
    @classmethod
    def boot(cls, show_welcome: bool = True, **kw) -> "Studio":
        """Create the studio (Replay Mode by default) and show the welcome / resume box."""
        compat.enable_colab_widgets()
        kw.setdefault("repo_root", os.environ.get("STUDIO_REPO_ROOT") or None)
        if os.environ.get("STUDIO_STATE_PATH"):
            kw.setdefault("state_path", os.environ["STUDIO_STATE_PATH"])
        if os.environ.get("STUDIO_EXPORT_DIR"):
            kw.setdefault("export_dir", os.environ["STUDIO_EXPORT_DIR"])
        studio = cls(**kw)
        if compat.env_flag("STUDIO_MODE", "replay") != "live":
            try:
                studio.connect_replay()
            except Exception as e:  # noqa: BLE001 - shown in the welcome box
                studio.w["msg_connect"].value = box("error", esc(getattr(e, "user_message", str(e))))
        studio.refresh()
        if show_welcome:
            try:
                from IPython.display import display
                display(studio.welcome())
            except Exception:  # noqa: BLE001 - no IPython (plain Python)
                pass
        return studio

    def welcome(self) -> widgets.VBox:
        # The status bar is shown in every section, so its download Output lives here instead:
        # an Output displayed N times runs files.download N times (duplicate files in Colab).
        return _card(self.w["style"], self.w["welcome_html"], self.w["resume_row"], self.w["msg_welcome"],
                     self.w["download_out"])

    # ------------------------------------------------------------------ public API
    def section(self, n: int) -> widgets.VBox:
        """Section ``n`` (1–6) with the status bar and progress tracker on top."""
        self.refresh()
        body = self.w["sections"].get(int(n))
        if body is None:
            raise StudioError("There are six sections, numbered 1 to 6.")
        return _card(self.w["status_bar"], self.w["progress"], body)

    def stuck(self) -> widgets.VBox:
        """The 'If you get stuck' box."""
        self.refresh()
        return _card(self.w["status_bar"], self.w["stuck_box"])

    def all_widgets(self):
        roots = [self.w["status_bar"], self.w["progress"], self.welcome(), self.w["stuck_box"],
                 *self.w["sections"].values()]
        for r in roots:
            yield from iter_widgets(r)

    # ------------------------------------------------------------------ extras / persistence
    @staticmethod
    def _fresh_extras() -> dict:
        return {"ui_version": 1, "role": ROLES[0], "version_meta": {}, "custom_challenge": None,
                "configured": False, "exported": False}

    def _secrets(self) -> tuple:
        fn = getattr(self.provider, "_secrets", None)
        inner = getattr(self.provider, "_inner", None)
        if fn is None and inner is not None:
            fn = getattr(inner, "_secrets", None)
        try:
            return tuple(fn()) if callable(fn) else ()
        except Exception:  # noqa: BLE001
            return ()

    def _mask(self, text) -> str:
        return providers.mask_secrets(text, self._secrets())

    def _state_text(self) -> str:
        data = self.state.to_dict()
        self.extras["role"] = self.role
        data["ui_extras"] = self.extras
        text = json.dumps(data, ensure_ascii=False, indent=2)
        hits = providers.find_secrets(text, self._secrets())
        if hits:
            raise StudioError("Not saved: the project contains something that looks like an API key ("
                              + ", ".join(hits[:3]) + "). Remove it and try again.")
        return text

    def _write_atomic(self, path: Path, text: str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def autosave(self) -> None:
        if self.state is None:
            return
        self._backup_unhandled_session()
        self._write_atomic(self.state_path, self._state_text())
        self.autosaved_at = datetime.now().strftime("%H:%M:%S")
        self._saved_session_handled = True

    def _backup_unhandled_session(self) -> None:
        """Before the first save of this session, keep a copy of an older saved session."""
        if self._saved_session_handled or not self.state_path.exists():
            self._saved_session_handled = True
            return
        backup = self.state_path.with_name(f"studio_state_backup_{_ts()}.json")
        try:
            backup.write_bytes(self.state_path.read_bytes())
        except OSError:
            pass
        self._saved_session_handled = True

    def _load_text(self, text, origin: str) -> str:
        if isinstance(text, (bytes, bytearray)):
            text = bytes(text).decode("utf-8-sig", errors="replace")
        state = ps.load_state(text)
        try:
            extras = json.loads(text).get("ui_extras") or {}
        except (ValueError, AttributeError):
            extras = {}
        challenge = self._challenge_for_state(state, extras)
        self._set_project(state, challenge, extras)
        cur = state.current_version()
        return (f"Loaded {origin}: {self._challenge_title()} — {len(state.versions)} version(s), "
                f"{len(state.findings)} finding(s), {len(state.decisions)} decision(s)"
                + (f", current version {cur.version_id}" if cur else "") + ".")

    def _challenge_for_state(self, state: ps.ProjectState, extras: dict) -> dict:
        mission = state.mission or state.challenge_id
        if state.challenge_id != "custom" and mission in self._mission_files():
            return self._load_challenge(mission)
        ch = extras.get("custom_challenge")
        if isinstance(ch, dict) and ch.get("strings"):
            return ch
        return {"schema_version": "1.0", "id": state.challenge_id, "mission": mission,
                "title": f"Custom upload ({state.challenge_id})", "brief": "", "scene_context": "",
                "characters": [], "glossary": [], "strings": [dict(s) for s in state.strings]}

    def _set_project(self, state, challenge, extras=None) -> None:
        self.state, self.challenge = state, challenge
        ex = self._fresh_extras()
        ex.update({k: v for k, v in (extras or {}).items() if k in ex})
        if not isinstance(ex.get("version_meta"), dict):
            ex["version_meta"] = {}
        self.extras = ex
        if ex.get("role") in ROLES:
            self.role = ex["role"]
            self._suspend = True
            try:
                self.w["role"].value = self.role
            finally:
                self._suspend = False
        if challenge.get("id") == "custom":
            self.custom_challenge = challenge
            self.extras["custom_challenge"] = challenge
        cfg = state.agents.get("translator") or agents.default_agent_config("translator")
        if "preset" not in cfg:
            cfg = dict(cfg)
            cfg["preset"] = "balanced"
            cfg = compat.mark_edited(cfg)
        state.agents["translator"] = cfg
        if self.provider is not None and not (state.mode == "live" and not self._is_live()):
            self._apply_provider_to_state()
        self._live_hint = state.mode == "live" and not self._is_live()
        self._finding_cards.clear()
        self._grid.clear()
        self._grid_version, self._grid_ids = None, ()
        self.w["findings_box"].children = ()
        self.w["edit_grid"].children = ()
        self._sync_mission_widgets()
        self._load_config_widgets()
        self.w["reflection"].value = state.reflection or ""

    # ------------------------------------------------------------------ challenges
    def _mission_files(self) -> dict:
        return {m["id"]: m["challenge_file"] for m in self.manifest.get("missions", [])}

    def _load_challenge(self, mission: str) -> dict:
        if mission == "custom":
            if not self.custom_challenge:
                raise StudioError("Upload your own material first (in the box below the mission list).")
            return self.custom_challenge
        path = self._mission_files().get(mission)
        if not path:
            raise StudioError(f"There is no mission called '{mission}'.")
        return validation.parse_json_strict((self.root / path).read_text(encoding="utf-8"))

    def _challenge_title(self) -> str:
        return (self.challenge or {}).get("title") or (self.state.challenge_id if self.state else "—")

    def _mission_options(self):
        opts = []
        for mid in self._mission_files():
            try:
                title = self._load_challenge(mid).get("title", mid)
            except Exception:  # noqa: BLE001
                title = mid
            suffix = " — start here" if mid == "intro" else " — after the intro"
            opts.append((f"{title}{suffix}", mid))
        if self.custom_challenge:
            opts.append((f"Your own material: {self.custom_challenge.get('title', 'custom')}", "custom"))
        return opts

    # ------------------------------------------------------------------ action wrapper
    def _action(self, button, fn, msg_key: str, working: str = "Working…") -> None:
        """Run ``fn`` with the button disabled; show friendly results/errors; always recover."""
        msg = self.w[msg_key]
        buttons = [b for b in (button if isinstance(button, (list, tuple)) else [button]) if b is not None]
        for b in buttons:
            b.disabled = True
        self._busy_msg = msg
        msg.value = box("info", esc(working))
        before = self.state
        was_approved = bool(before and before.approval.get("approved"))
        try:
            result = fn()
            text = result if isinstance(result, Safe) else esc_br(result or "Done.")
            kind = "warn" if isinstance(result, Warn) else "ok"
            if was_approved and self.state is before and not before.approval.get("approved"):
                text += ("<br><b>⚠️ Approval revoked:</b> the translation or its decisions changed "
                         "after approval. Approve the final translation again in Section 5.")
                kind = "warn"
            msg.value = box(kind, text)
        except Exception as e:  # noqa: BLE001 - every error becomes a friendly message
            user_message = getattr(e, "user_message", None)
            if isinstance(e, (StudioError, providers.ProviderError, importers.ImportRejected)) and user_message:
                msg.value = box("error", "❌ " + esc_br(self._mask(user_message)))
            else:
                saved = self._try_autosave()
                details = esc(self._mask(traceback.format_exc()[-3000:]))
                msg.value = box("error", "❌ Something unexpected went wrong, and this step did not "
                                "finish. " + ("Your work is saved." if saved else
                                              "Your earlier work is still in the notebook.")
                                + " Try again, or use “If you get stuck” at the bottom."
                                + f"<details><summary>Technical details (for your instructor)</summary>"
                                  f"<pre style='white-space:pre-wrap'>{details}</pre></details>")
        finally:
            for b in buttons:
                b.disabled = False
            self._busy_msg = None
            if not self._try_autosave():
                msg.value += box("warn", "Autosave did not work this time: "
                                 + esc(self.autosave_problem or "unknown reason.")
                                 + " Fix this, or use “Download progress” to keep a copy of your work.")
            try:
                self.refresh()
            except Exception:  # noqa: BLE001 - never leave the UI stuck
                msg.value += box("warn", "The display could not be fully refreshed. Run this "
                                 "section's cell again.")

    def _try_autosave(self) -> bool:
        """Autosave; on failure remember the reason in plain English (shown to the student)."""
        try:
            self.autosave()
        except StudioError as e:
            self.autosave_problem = self._mask(e.user_message)
            return False
        except OSError as e:
            self.autosave_problem = (f"the project file could not be written "
                                     f"({e.strerror or type(e).__name__}).")
            return False
        except Exception as e:  # noqa: BLE001
            self.autosave_problem = f"an unexpected problem ({type(e).__name__})."
            return False
        self.autosave_problem = None
        return True

    def _set_working(self, text: str) -> None:
        if self._busy_msg is not None:
            self._busy_msg.value = box("info", esc(text))

    def _require_project(self) -> ps.ProjectState:
        if self.state is None:
            raise StudioError("Start a mission first (Section 2 → “Start this mission”).")
        return self.state

    def _require_provider(self):
        if self.provider is None:
            raise StudioError("Connect to an AI provider first (Section 1), or click “Use Replay "
                              "Mode instead”.")
        return self.provider

    # ------------------------------------------------------------------ providers
    def _models_for(self, name: str):
        entry = self.catalog.get(name) or {}
        models = list(entry.get("models") or [])
        if name == "hkbu" and not models:
            models = [{"id": m, "label": m, "verified": False}
                      for m in (self.provider_config.get("hkbu", {}).get("models") or [])
                      if isinstance(m, str)]
        opts = []
        for m in models:
            if not isinstance(m, dict) or not m.get("id"):
                continue
            label = m.get("label") or m["id"]
            if name == "hkbu":
                label += " (configured by your instructor — not yet verified)" if not m.get("verified") else ""
            elif not m.get("verified"):
                label += " (not yet verified)"
            opts.append((label, m["id"]))
        if not opts and name == "hkbu":
            opts = [("configured by your instructor — not yet verified", "")]
        return opts or [("(no models listed)", "")]

    def _default_model(self, name: str) -> str:
        opts = self._models_for(name)
        want = (self.catalog.get(name) or {}).get("default")
        ids = [v for _, v in opts]
        return want if want in ids else ids[0]

    def _replay_variant(self, stage: str) -> str:
        if self.state is None:
            return "balanced"
        if stage in ("translator", "baseline"):
            return self.state.agents.get("translator", {}).get("preset") or "balanced"
        return self._version_variant(self.state.current_version())

    def _load_fixtures(self) -> dict:
        if self._fixtures is not None:
            return self._fixtures
        path = (self.provider_config.get("replay") or {}).get("fixtures_path", "fixtures/replay_outputs.json")
        return providers.load_replay_fixtures(str(self.root / path))

    def connect_replay(self) -> str:
        fixtures = self._load_fixtures()
        prov = compat.ReplayVariantProvider(fixtures, self.provider_config.get("replay"),
                                            variant_fn=self._replay_variant)
        self.use_provider(prov, "replay", "replay")
        self._suspend = True
        try:
            self.w["provider"].value = "replay"
            self._refresh_model_options()
        finally:
            self._suspend = False
        return ("✅ Replay Mode is on. Every AI output is prepared in advance by the course team "
                "(simulated, free, no key needed). You can switch to a live AI later.")

    def use_provider(self, provider, name: str, translator_model: str,
                     reviewer_model: str | None = None) -> None:
        """Connect a provider object (the key, if any, stays inside it)."""
        if getattr(provider, "is_live", True) and getattr(provider, "usage_meter", None) is None:
            try:
                provider.usage_meter = self.meter   # the session cap applies to every live provider
            except AttributeError:
                pass
        self.provider, self.provider_name = provider, name
        self.translator_model = translator_model or ""
        self.reviewer_model = reviewer_model or translator_model or ""
        self._pending_provider = None
        if getattr(provider, "is_live", True):
            self._live_hint = False
        if self.state is not None and not self._live_hint:
            self._apply_provider_to_state()

    def _apply_provider_to_state(self) -> None:
        st = self.state
        new = {"name": self.provider_name, "translator_model": self.translator_model,
               "reviewer_model": self.reviewer_model or self.translator_model}
        mode = "live" if getattr(self.provider, "is_live", True) else "replay"
        if st.provider != new or st.mode != mode:
            st.provider, st.mode = new, mode
            st.log("provider", f"Now using {self._provider_display()} ({mode} mode)")

    def _provider_display(self) -> str:
        cfg = self.provider_config.get(self.provider_name or "", {})
        return cfg.get("display_name") or (self.provider_name or "no provider")

    def _is_live(self) -> bool:
        return bool(self.provider is not None and getattr(self.provider, "is_live", True))

    # ------------------------------------------------------------------ UI building
    def _build_all(self) -> None:
        w = self.w
        for key in ("msg_status", "msg_connect", "msg_mission", "msg_config", "msg_run",
                    "msg_director", "msg_export", "msg_stuck", "msg_welcome", "msg_preview"):
            w[key] = _html()
        w["style"] = _hidden(widgets.HTML(STUDIO_CSS))   # a <style> applies even when hidden
        # files.download needs an output context in Colab (see compat.colab_download): one
        # Output per download button, each displayed exactly once.
        for key in ("download_out", "download_out_stuck", "download_out_game_translation",
                    "download_out_agent_settings", "download_out_workflow_report"):
            w[key] = widgets.Output(layout=_layout(width="100%"))
        self._build_status()
        w["sections"] = {1: self._build_connect(), 2: self._build_mission(), 3: self._build_configure(),
                         4: self._build_run(), 5: self._build_director(), 6: self._build_export()}
        self._build_stuck()
        w["welcome_html"] = _html()

    # .................................................................. status bar
    def _build_status(self) -> None:
        w = self.w
        w["status_html"] = _html()
        w["role"] = widgets.ToggleButtons(options=self._role_options(), value=self.role,
                                          description="Who is deciding:",
                                          tooltips=[f"Record decisions as {r}" for r in ROLES],
                                          style={"description_width": "initial"})
        w["role"].observe(self._on_role, names="value")
        w["btn_status_replay"] = _button("Switch to Replay", "warning", icon="play")
        w["btn_status_replay"].on_click(lambda b: self._action(b, self.connect_replay, "msg_status"))
        w["btn_status_download"] = _button("Download progress", "", icon="download")
        w["btn_status_download"].on_click(
            lambda b: self._action(b, lambda: self._download_progress("download_out"), "msg_status"))
        w["status_bar"] = widgets.VBox(
            [w["style"], w["status_html"],
             widgets.HBox([w["role"], w["btn_status_replay"], w["btn_status_download"]],
                          layout=_layout(flex_flow="row wrap", align_items="center")),
             w["msg_status"]],
            layout=_layout(border="1px solid #d9e2ec", padding="4px 8px", margin="0 0 6px 0"))
        w["progress"] = _html()

    @staticmethod
    def _role_options(selected: str | None = None):
        """The selected role gets a ✓, so it is obvious in every Colab theme."""
        return [(("✓ " if r == selected else "") + r, r) for r in ROLES]

    def _refresh_role_labels(self) -> None:
        opts = self._role_options(self.role)
        tb = self.w["role"]
        if [tuple(o) for o in tb.options] == opts:
            return
        self._suspend = True
        try:   # changing options moves the selection to the first option: put it back
            tb.options = opts
            tb.value = self.role
        finally:
            self._suspend = False

    def _on_role(self, change) -> None:
        if self._suspend:
            return
        self.role = change["new"]
        self.extras["role"] = self.role
        self._try_autosave()
        self._refresh_status()

    # .................................................................. 1 connect
    def _build_connect(self) -> widgets.VBox:
        w = self.w
        w["provider"] = widgets.Dropdown(options=PROVIDER_CHOICES, value="replay", description="Provider:",
                                         style={"description_width": "initial"}, layout=_layout(width="420px"))
        w["model"] = widgets.Dropdown(options=self._models_for("replay"), description="Model:",
                                      style={"description_width": "initial"}, layout=_layout(width="560px"))
        w["provider"].observe(self._on_provider_change, names="value")
        w["key_help"] = _html()
        w["btn_load_key"] = _button("Load my key", "primary", icon="key")
        w["btn_load_key"].on_click(lambda b: self._action(b, self._load_key, "msg_connect",
                                                          "Looking for your key in Colab Secrets…"))
        w["key_box"] = _hidden(widgets.Password(
            value="", placeholder="…or paste your key here (hidden), then click Load my key again",
            layout=_layout(width="560px")))
        w["btn_test"] = _button("Test connection", "info", icon="plug")
        w["btn_test"].on_click(lambda b: self._action(b, self._test_connection, "msg_connect",
                                                      "Testing the connection (1 small request)…"))
        w["btn_use_replay"] = _button("Use Replay Mode instead", "warning", width="320px", icon="play")
        w["btn_use_replay"].layout.height = "44px"
        w["btn_use_replay"].on_click(lambda b: self._action(b, self.connect_replay, "msg_connect"))
        w["adv_reviewer"] = widgets.Checkbox(value=False, indent=False,
                                             description="Advanced: use a different model for the reviewer")
        w["reviewer_model"] = _hidden(widgets.Dropdown(options=self._models_for("replay"),
                                                       description="Reviewer model:",
                                                       style={"description_width": "initial"},
                                                       layout=_layout(width="560px")))
        w["adv_reviewer"].observe(lambda c: (_hidden(w["reviewer_model"], not c["new"]),
                                             self._on_model_change(None)), names="value")
        w["model"].observe(self._on_model_change, names="value")
        w["reviewer_model"].observe(self._on_model_change, names="value")
        w["connect_state"] = _html()
        intro = _html(box("info", "You start in <b>Replay Mode</b>: prepared, simulated outputs that "
                                  "need no key. To use a live AI, pick a provider and model, click "
                                  "<b>Load my key</b>, then <b>Test connection</b>."))
        self._refresh_key_help()
        return widgets.VBox([
            _html("<h3 style='margin:4px 0'>1 · Connect (≈5 min)</h3>"), intro,
            w["provider"], w["model"], w["key_help"],
            widgets.HBox([w["btn_load_key"], w["btn_test"]]), w["key_box"], w["msg_connect"],
            w["connect_state"],
            w["btn_use_replay"], w["adv_reviewer"], w["reviewer_model"]])

    def _on_provider_change(self, change) -> None:
        if self._suspend:
            return
        self._refresh_model_options()
        self._refresh_key_help()
        name = change["new"]
        if name == "hkbu" and not (self.provider_config.get("hkbu", {}).get("base_url") or "").strip():
            self.w["msg_connect"].value = box("warn", esc(
                providers._error("not_configured", "HKBU GenAI").user_message))
        elif name == "replay":
            self._action(None, self.connect_replay, "msg_connect")
        else:
            self.w["msg_connect"].value = box("info", "Now click <b>Load my key</b>.")

    def _refresh_model_options(self) -> None:
        name = self.w["provider"].value
        opts = self._models_for(name)
        for key in ("model", "reviewer_model"):
            self.w[key].options = opts
            self.w[key].value = self._default_model(name)

    def _on_model_change(self, change) -> None:
        if self._suspend or self.provider is None or self.provider_name != self.w["provider"].value:
            return
        self.translator_model = self.w["model"].value or ""
        self.reviewer_model = (self.w["reviewer_model"].value if self.w["adv_reviewer"].value
                               else self.translator_model) or self.translator_model
        if self.state is not None:
            self._apply_provider_to_state()
            self._try_autosave()
        self._refresh_status()

    def _refresh_key_help(self) -> None:
        name = self.w["provider"].value
        cfg = self.provider_config.get(name, {})
        if name == "replay":
            self.w["key_help"].value = box("plain", "Replay Mode needs no key and no internet.")
            return
        secret = esc(cfg.get("secret_name") or "API_KEY")
        extra = ""
        if name == "hkbu" and not cfg.get("verified"):
            extra = ("<br>HKBU GenAI is <b>configured by your instructor — not yet verified</b>.")
        elif name == "hkbu":
            extra = "<br>HKBU GenAI is configured by your instructor."
        elif not cfg.get("verified"):
            extra = "<br>This provider is <b>not yet verified</b> for this course."
        self.w["key_help"].value = box("info", (
            f"<b>How to add your key (Colab Secrets)</b> — the key never appears in the notebook:"
            f"<ol style='margin:4px 0 0 18px'><li>Click the <b>key icon 🔑</b> in Colab's left sidebar.</li>"
            f"<li>Click <b>Add new secret</b>.</li><li>Name: <code>{secret}</code></li>"
            f"<li>Value: paste your key.</li><li>Switch on <b>Notebook access</b>.</li>"
            f"<li>Come back and click <b>Load my key</b>.</li></ol>"
            f"If Colab Secrets is not available, a hidden box will ask you to paste the key.{extra}"))

    def _load_key(self) -> str:
        name = self.w["provider"].value
        if name == "replay":
            return self.connect_replay()
        model = self.w["model"].value
        if name == "hkbu" and not (self.provider_config.get("hkbu", {}).get("base_url") or "").strip():
            raise providers._error("not_configured", "HKBU GenAI")
        if not model:
            raise StudioError("No model is configured for this provider yet. Ask your instructor, "
                              "or use Replay Mode.")
        box_w = self.w["key_box"]

        def from_box(_prompt=""):
            # Fallback when Colab Secrets is unavailable: a masked box, emptied straight away.
            value, box_w.value = box_w.value, ""
            return value

        try:
            key = providers.load_api_key(name, self.provider_config,
                                         getpass_fn=self._getpass_fn or from_box,
                                         userdata=self._userdata)
        except providers.ProviderError as e:
            if e.kind == "no_key":
                _hidden(box_w, False)
                raise StudioError(e.user_message + " You can also paste the key into the hidden "
                                  "box under the buttons and click “Load my key” again.") from None
            raise
        finally:
            box_w.value = ""
        _hidden(box_w)
        try:
            prov = self._provider_factory(name, key, self.provider_config, self.meter)
        finally:
            key = None  # noqa: F841 - the key now lives only inside the provider object
        reviewer = self.w["reviewer_model"].value if self.w["adv_reviewer"].value else model
        self.use_provider(prov, name, model, reviewer)
        return (f"🔑 Key loaded for {self._provider_display()} (it stays hidden). "
                "Now click “Test connection”.")

    def _test_connection(self) -> Safe:
        prov = self._require_provider()
        if self.provider_name != self.w["provider"].value:
            raise StudioError("Click “Load my key” for this provider first.")
        ok, message = prov.test_connection(self.translator_model or "replay")
        message = self._mask(message)
        if ok:
            self.w["connect_state"].value = box("ok", "✅ " + esc(message))
            return Safe("✅ " + esc(message))
        raise StudioError(message)

    # .................................................................. 2 mission
    def _build_mission(self) -> widgets.VBox:
        w = self.w
        opts = self._mission_options()
        ids = [v for _, v in opts]
        w["mission"] = widgets.Dropdown(options=opts, value="intro" if "intro" in ids else ids[0],
                                        description="Mission:", style={"description_width": "initial"},
                                        layout=_layout(width="680px"))
        w["mission"].observe(lambda c: self._refresh_mission_preview(), names="value")
        w["locale"] = widgets.ToggleButtons(options=LOCALE_CHOICES, value="en-GB",
                                            description="English variant:",
                                            style={"description_width": "initial"})
        w["team"] = widgets.Text(value="", placeholder="e.g. Team Lantern (no personal data)",
                                 description="Team name (optional):",
                                 style={"description_width": "initial"}, layout=_layout(width="480px"))
        w["mission_brief"] = _html()
        w["source_table"] = _html()
        w["ctx_scene"], w["ctx_chars"], w["ctx_meaning"], w["ctx_gloss"] = _html(), _html(), _html(), _html()
        w["context_acc"] = _accordion([
            ("Scene", w["ctx_scene"]), ("Character profiles", _scroll(w["ctx_chars"], "360px")),
            ("Intended meaning of each string", _scroll(w["ctx_meaning"], "360px")),
            ("Glossary (required terms flagged)", _scroll(w["ctx_gloss"], "360px"))])
        w["upload"] = widgets.FileUpload(accept=".txt,.csv,.json", multiple=False,
                                         description="Choose file")
        w["btn_use_upload"] = _button("Use this file", "info", icon="upload")
        w["btn_use_upload"].on_click(lambda b: self._action(b, self._use_upload, "msg_mission",
                                                            "Reading your file…"))
        w["btn_start"] = _button("Start this mission", "success", width="260px", icon="flag")
        w["btn_start"].on_click(lambda b: self._action(b, self._start_mission, "msg_mission"))
        w["btn_start_confirm"] = _button("Yes, start again (a backup copy is kept)", "danger")
        w["btn_start_confirm"].on_click(
            lambda b: self._action(b, lambda: self._start_mission(confirmed=True), "msg_mission"))
        w["btn_start_cancel"] = _button("Cancel")
        w["btn_start_cancel"].on_click(lambda b: (_hidden(w["start_confirm"]),
                                                  setattr(w["msg_mission"], "value",
                                                          box("info", "Nothing was changed."))))
        w["start_confirm"] = _hidden(widgets.HBox([w["btn_start_confirm"], w["btn_start_cancel"]]))
        upload_help = _html(box("plain", (
            "<b>Upload your own material</b> (optional): a <code>.txt</code> file (one string per line), "
            "a <code>.csv</code> with a <code>source</code> column (optional: id, context, max_len, "
            "speaker), or a <code>.json</code> list/challenge. Limits: UTF-8 text, at most "
            f"{importers.MAX_BYTES // 1024} KB, {importers.MAX_STRINGS} strings, "
            f"{importers.MAX_CHARS} characters each. Custom material <b>cannot be played in the game</b>; "
            "you will still get the translation file and the report.")))
        self._refresh_mission_preview()
        w["upload_acc"] = _accordion([("Optional: upload your own material (.txt / .csv / .json)",
                                       widgets.VBox([upload_help,
                                                     widgets.HBox([w["upload"], w["btn_use_upload"]])]))])
        return widgets.VBox([
            _html("<h3 style='margin:4px 0'>2 · Choose your mission (≈5 min)</h3>"),
            w["mission"], w["locale"], w["team"], w["mission_brief"],
            _html("<b>Source strings</b>"), _scroll(w["source_table"], "360px"),
            w["context_acc"], w["upload_acc"],
            w["btn_start"], w["start_confirm"], w["msg_mission"]])

    def _selected_challenge(self) -> dict:
        return self._load_challenge(self.w["mission"].value)

    def _refresh_mission_preview(self) -> None:
        w = self.w
        try:
            ch = self._selected_challenge()
        except Exception as e:  # noqa: BLE001
            w["mission_brief"].value = box("warn", esc(getattr(e, "user_message", str(e))))
            return
        names = {c.get("id"): f"{c.get('name_zh', '')} / {c.get('name_en_suggestion') or '—'}"
                 for c in ch.get("characters", []) if isinstance(c, dict)}
        warn = ""
        if ch.get("import_warnings"):
            warn = box("warn", "<br>".join(esc(x) for x in ch["import_warnings"]))
        est = ch.get("estimated_minutes")
        when = ""
        if est and ch.get("id") == "intro":
            when = f"About {est} minutes, including setup"
        elif est:
            when = f"About {est} minutes — already connected? Skip Section 1"
        w["mission_brief"].value = (
            f"<h4 style='margin:6px 0'>{esc(ch.get('title'))} {esc(ch.get('title_zh', ''))}</h4>"
            + (f"<p style='margin:2px 0'><i>{esc(when)}</i></p>" if when else "")
            + f"<p style='margin:2px 0'>{esc_br(ch.get('brief', ''))}</p>" + warn)
        rows = []
        for s in ch.get("strings", []):
            cons = list(s.get("constraints") or [])
            if s.get("max_len") and not any("aximum" in c for c in cons):
                cons.append(f"Maximum {s['max_len']} characters")
            if s.get("placeholders"):
                cons.append("Placeholders: " + ", ".join(s["placeholders"]))
            rows.append([f"<code>{esc(s['id'])}</code>",
                         esc(names.get(s.get("speaker"), s.get("speaker") or "—")),
                         f"<span style='font-size:15px'>{esc_br(s.get('source', ''))}</span>",
                         esc(s.get("type", "")), "<br>".join(esc(c) for c in cons) or "—"])
        w["source_table"].value = table(["Id", "Speaker", "Chinese (source)", "Type", "Constraints"], rows)
        w["ctx_scene"].value = f"<p>{esc_br(ch.get('scene_context') or 'Not given.')}</p>"
        chars = []
        for c in ch.get("characters", []):
            if isinstance(c, dict):
                chars.append(f"<p><b>{esc(c.get('name_zh', ''))} — {esc(c.get('name_en_suggestion') or c.get('id'))}"
                             f"</b><br>{esc(c.get('profile', ''))}<br><i>Voice:</i> {esc(c.get('voice', ''))}"
                             f"<br><i>Relationships:</i> {esc(c.get('relationships', ''))}</p>")
        w["ctx_chars"].value = "".join(chars) or "<p>No character profiles.</p>"
        w["ctx_meaning"].value = table(["Id", "Context", "Intended meaning"], [
            [f"<code>{esc(s['id'])}</code>", esc(s.get("context", "")), esc(s.get("intended_meaning", ""))]
            for s in ch.get("strings", [])])
        gl = [[esc(g.get("source", "")), esc(g.get("target", "")),
               (badge("REQUIRED", "#c0392b") if g.get("strictness") == "required"
                else esc(g.get("strictness", ""))), esc(g.get("note", ""))]
              for g in ch.get("glossary", []) if isinstance(g, dict)]
        w["ctx_gloss"].value = table(["Source", "English", "Strictness", "Note"], gl) if gl else "<p>No glossary.</p>"

    def _sync_mission_widgets(self) -> None:
        self._suspend = True
        try:
            self.w["mission"].options = self._mission_options()
            mid = "custom" if self.state and self.state.challenge_id == "custom" else (
                self.state.mission if self.state else "intro")
            if mid in [v for _, v in self.w["mission"].options]:
                self.w["mission"].value = mid
            if self.state:
                self.w["locale"].value = self.state.locale
                self.w["team"].value = self.state.team_name or ""
        finally:
            self._suspend = False
        self._refresh_mission_preview()

    def _use_upload(self) -> str:
        files = compat.uploaded_files(self.w["upload"].value)
        if not files:
            raise StudioError("Choose a file first with the “Choose file” button.")
        name, data = files[0]
        return self.import_material(name, data)

    def import_material(self, name: str, data: bytes) -> str:
        problem = providers.key_refusal(bytes(data).decode("utf-8", errors="replace"), "file")
        if problem:
            raise StudioError(problem)
        ch = importers.import_upload(name, data)
        self.custom_challenge = ch
        self._suspend = True
        try:
            self.w["mission"].options = self._mission_options()
            self.w["mission"].value = "custom"
        finally:
            self._suspend = False
        self._refresh_mission_preview()
        compat.clear_upload(self.w["upload"])
        msg = (f"Loaded {len(ch['strings'])} string(s) from your file. Check the table above, then "
               "click “Start this mission”. Remember: custom material cannot be played in the game.")
        if ch.get("import_warnings"):
            msg += f" Warnings: {len(ch['import_warnings'])} (see above)."
        return msg

    def _start_mission(self, confirmed: bool = False) -> str:
        self._require_provider()
        challenge = self._selected_challenge()
        if not confirmed:
            has_progress = self.state is not None and (self.state.versions or self.state.decisions)
            unhandled = (self.state is None and not self._saved_session_handled
                         and self.state_path.exists())
            if has_progress or unhandled:
                _hidden(self.w["start_confirm"], False)
                what = ("You already have work in this mission." if has_progress else
                        "A saved session was found (see “Resume my saved session”).")
                return Warn(f"⚠️ {what} Starting will replace it. A backup copy is kept. Are you sure?")
        _hidden(self.w["start_confirm"])
        if self.state is not None:
            self._save_copy(f"backup_{self.state.challenge_id}")
        team = self.w["team"].value.strip()
        state = ps.new_project(challenge, self.w["locale"].value,
                               "live" if self._is_live() else "replay", self.provider_name,
                               self.translator_model, self.reviewer_model or None, max_cycles=1,
                               team_name=team, request_cap=self.request_cap)
        state.agents["translator"] = compat.apply_preset(state.agents["translator"], "balanced")
        extras = self._fresh_extras()
        extras["role"] = self.role
        if challenge.get("id") == "custom":
            extras["custom_challenge"] = challenge
        self._set_project(state, challenge, extras)
        msg = (f"Mission started: {challenge.get('title')} ({len(state.strings)} strings, "
               f"{state.locale}). Next: Section 3 — configure your agents.")
        return msg + (" " + REPLAY_LOCALE_NOTE if self._replay_locale_note() else "")

    # .................................................................. 3 configure
    def _build_configure(self) -> widgets.VBox:
        w = self.w
        w["preset_buttons"] = {}
        pbtns = []
        for name in compat.PRESET_ORDER:
            b = _button(compat.preset_label(name), "", width="160px")
            b.on_click(lambda btn, n=name: self._action(btn, lambda: self._apply_preset(n), "msg_config"))
            w["preset_buttons"][name] = b
            pbtns.append(b)
        w["preset_info"] = _html()
        w["t_settings"] = {}
        t_rows = []
        for spec in agents.TRANSLATOR_SETTINGS_SPEC:
            ctrl, row = self._setting_control(spec)
            w["t_settings"][spec["key"]] = ctrl
            ctrl.observe(self._on_translator_change, names="value")
            t_rows.append(row)
        w["t_instructions"] = _textarea(rows=8)
        w["t_instructions"].observe(self._on_translator_change, names="value")
        w["btn_t_reset"] = _button("Reset to preset", "", icon="undo")
        w["btn_t_reset"].on_click(lambda b: self._action(b, self._reset_translator, "msg_config"))
        w["replay_notice"] = _html()
        w["r_settings"] = {}
        r_rows = []
        for spec in agents.REVIEWER_SETTINGS_SPEC:
            ctrl, row = self._setting_control(spec)
            w["r_settings"][spec["key"]] = ctrl
            ctrl.observe(self._on_reviewer_change, names="value")
            r_rows.append(row)
        w["r_instructions"] = _textarea(rows=6)
        w["r_instructions"].observe(self._on_reviewer_change, names="value")
        w["btn_r_reset"] = _button("Reset reviewer to default", "", icon="undo")
        w["btn_r_reset"].on_click(lambda b: self._action(b, self._reset_reviewer, "msg_config"))
        w["preview_step"] = widgets.Dropdown(
            options=[("Translator agent", "translator"), ("Baseline (one-shot)", "baseline"),
                     ("Reviewer agent", "reviewer"), ("Revision (feedback to translator)", "revision")],
            value="translator", description="Prompt for:", style={"description_width": "initial"})
        w["btn_preview"] = _button("Show the full prompt that will be sent", "info", width="340px", icon="eye")
        w["btn_preview"].on_click(lambda b: self._action(b, self._show_preview, "msg_preview"))
        w["preview_info"] = _html()
        w["preview_system"] = _textarea(rows=3)
        w["preview_user"] = _textarea(rows=10)
        w["preview_box"] = widgets.VBox([
            w["preview_info"], _html("<b>System message</b>"), w["preview_system"],
            _html("<b>User message</b> (exactly what the model receives; editing here changes nothing "
                  "— edit the instructions and settings above)"), w["preview_user"]])
        w["preview_acc"] = _hidden(_accordion([("Full prompt that will be sent", w["preview_box"])]))
        examples = _html(box("plain", (
            "<b>Writing good instructions</b><table style='width:100%;font-size:13px'>"
            "<tr><td style='vertical-align:top;width:50%'>✅ <b>Good</b><ul style='margin:2px 0 0 16px'>"
            "<li>“Granny Wong speaks like a proud, sharp-tongued elder: short sentences, an old proverb "
            "where the source has one, never slang.”</li>"
            "<li>“Buttons: one or two words, imperative verb, no full stop, within the character limit.”"
            "</li></ul></td><td style='vertical-align:top'>❌ <b>Poor</b><ul style='margin:2px 0 0 16px'>"
            "<li>“Make it good.” (no criteria the agent can follow)</li>"
            "<li>“Be creative and add some jokes.” (invites invented content; ignores constraints)</li>"
            "</ul></td></tr></table>")))
        grid = _layout(flex_flow="row wrap", width="100%")
        return widgets.VBox([
            _html("<h3 style='margin:4px 0'>3 · Configure your agents (≈15 min)</h3>"),
            _html("<h4 style='margin:4px 0'>Translator agent</h4>"
                  "<p style='margin:2px 0'>Pick a starting preset, then change anything you like. "
                  "Each preset only sets the sliders and the instructions below — nothing is hidden.</p>"),
            widgets.HBox(pbtns, layout=_layout(flex_flow="row wrap")), w["msg_config"], w["preset_info"],
            widgets.HBox(t_rows, layout=grid),
            _html("<b>Translator instructions</b> (fully editable)"), w["t_instructions"],
            w["btn_t_reset"], w["replay_notice"],
            _html("<h4 style='margin:10px 0 4px 0'>Reviewer agent</h4>"
                  "<p style='margin:2px 0'>The reviewer only makes suggestions. You decide in Section 5.</p>"),
            widgets.HBox(r_rows, layout=grid), _html("<b>Reviewer instructions</b> (fully editable)"),
            w["r_instructions"], w["btn_r_reset"],
            _accordion([("Good vs poor instructions (examples)", examples)]),
            _html("<h4 style='margin:10px 0 4px 0'>See exactly what will be sent</h4>"),
            widgets.HBox([w["preview_step"], w["btn_preview"]], layout=_layout(flex_flow="row wrap")),
            w["msg_preview"], w["preview_acc"]])

    def _setting_control(self, spec):
        kind = spec["kind"]
        levels = spec.get("levels") or {}
        desc = _html()
        if kind == "slider":
            lo, hi = spec["range"]
            ctrl = widgets.IntSlider(value=spec["default"], min=lo, max=hi, step=1,
                                     continuous_update=False, layout=_layout(width="95%", max_width="360px"))
        elif kind == "dropdown":
            ctrl = widgets.Dropdown(options=[(str(o).replace("_", " "), o) for o in spec["options"]],
                                    value=spec["default"], layout=_layout(width="95%", max_width="260px"))
        else:
            ctrl = widgets.Checkbox(value=bool(spec["default"]), indent=False, description=spec["label"])

        def update(_=None):
            text = levels.get(str(ctrl.value)) if levels else ""
            desc.value = (f"<span style='color:#3e4c59;font-size:12px'>{esc(spec.get('help', ''))}"
                          + (f"<br>→ <i>{esc(text)}</i>" if text else "") + "</span>")
        ctrl.observe(update, names="value")
        update()
        parts = [ctrl, desc] if kind == "checkbox" else [_html(f"<b>{esc(spec['label'])}</b>"), ctrl, desc]
        return ctrl, widgets.VBox(parts, layout=_layout(margin="2px 0", width="32%", min_width="240px",
                                                        padding="0 8px 0 0"))

    def _translator_cfg(self) -> dict:
        return self._require_project().agents["translator"]

    def _load_config_widgets(self) -> None:
        if self.state is None:
            return
        self._suspend = True
        try:
            for role, wkey, ikey in (("translator", "t_settings", "t_instructions"),
                                     ("reviewer", "r_settings", "r_instructions")):
                cfg = self.state.agents.get(role) or agents.default_agent_config(role)
                settings = agents.normalise_settings(role, cfg.get("settings"))
                for k, ctrl in self.w[wkey].items():
                    if k in settings:
                        ctrl.value = settings[k]
                self.w[ikey].value = cfg.get("instructions", "")
        finally:
            self._suspend = False
        self._refresh_configure()

    def _read_settings(self, role: str) -> dict:
        wkey = "t_settings" if role == "translator" else "r_settings"
        return {k: c.value for k, c in self.w[wkey].items()}

    def _sync_config_from_widgets(self) -> None:
        """Copy the current widget values into the project (also done on every change)."""
        if self.state is None:
            return
        for role, ikey in (("translator", "t_instructions"), ("reviewer", "r_instructions")):
            text = self.w[ikey].value
            problem = providers.key_refusal(
                text, f"{role} instructions",
                f"The {role} instructions look like they contain an API key. Please remove it.")
            if problem:
                raise StudioError(problem)
            if len(text) > 8000:
                raise StudioError(f"The {role} instructions are too long (limit 8000 characters).")
            cfg = dict(self.state.agents.get(role) or agents.default_agent_config(role))
            new_settings = agents.normalise_settings(role, self._read_settings(role))
            if cfg.get("settings") == new_settings and cfg.get("instructions") == text:
                continue
            cfg["settings"], cfg["instructions"] = new_settings, text
            if role == "translator":
                cfg = compat.mark_edited(cfg)
            self.state.agents[role] = cfg
            self.extras["configured"] = True
            self.state.log("agent_config", f"{role} settings/instructions changed")

    def _config_changed(self, role: str) -> None:
        if self._suspend or self.state is None:
            return
        try:
            self._sync_config_from_widgets()
            self.w["msg_config"].value = box("ok", f"Saved your {esc(role)} changes.")
        except Exception as e:  # noqa: BLE001
            self.w["msg_config"].value = box("error", "❌ " + esc(getattr(e, "user_message", str(e))))
        self._try_autosave()
        self._refresh_configure()
        self._refresh_status()

    def _on_translator_change(self, change) -> None:
        self._config_changed("translator")

    def _on_reviewer_change(self, change) -> None:
        self._config_changed("reviewer")

    def _apply_preset(self, name: str) -> str:
        st = self._require_project()
        old = st.agents["translator"]
        lost = bool(old.get("edited"))
        st.agents["translator"] = compat.apply_preset(old, name)
        self.extras["configured"] = True
        st.log("preset", f"Translator preset: {compat.preset_label(name)}")
        self._load_config_widgets()
        p = compat.presets().get(name, {})
        msg = (f"{compat.preset_label(name)} preset applied: {p.get('description', '')} "
               "The sliders and the instructions below now show exactly what it sets.")
        if lost:
            msg += " (Your earlier edits were replaced.)"
        return msg

    def _reset_translator(self) -> str:
        name = self._translator_cfg().get("preset") or "balanced"
        return self._apply_preset(name)

    def _reset_reviewer(self) -> str:
        st = self._require_project()
        st.agents["reviewer"] = agents.default_agent_config("reviewer")
        st.log("agent_config", "reviewer reset to default")
        self._load_config_widgets()
        return "Reviewer settings and instructions reset to the default."

    def _show_preview(self) -> str:
        st = self._require_project()
        self._sync_config_from_widgets()
        step = self.w["preview_step"].value
        p = agents.preview(st, self.challenge, step, self.provider_config)
        self.extras["configured"] = True
        self.w["preview_system"].value = p["system"]
        self.w["preview_user"].value = p["user"]
        live = self._is_live()
        reqs = p["requests"]
        req_text = (f"This will make {reqs} request(s)." if live else
                    f"{reqs} simulated request(s) in Replay Mode — free and not counted.")
        self.w["preview_info"].value = box("info", (
            f"<b>{esc(dict((v, k) for k, v in self.w['preview_step'].options)[step])}</b> · "
            f"{esc(req_text)}<br>{esc(p['temperature_note'])}"
            + ("<br>Only the first batch is shown; other batches differ only in their strings."
               if reqs > 1 else "")))
        _hidden(self.w["preview_acc"], False)
        self.w["preview_acc"].selected_index = 0
        return f"Showing the full prompt for this step ({len(p['user'])} characters). Nothing is hidden."

    def _refresh_configure(self) -> None:
        if self.state is None:
            self.w["preset_info"].value = box("plain", "Start a mission first (Section 2).")
            self.w["replay_notice"].value = ""
            return
        cfg = self.state.agents["translator"]
        current = cfg.get("preset") or "balanced"
        for name, b in self.w["preset_buttons"].items():
            b.button_style = "primary" if name == current else ""
        pres = compat.presets()
        keys = [s["key"] for s in agents.TRANSLATOR_SETTINGS_SPEC]
        labels = {s["key"]: s["label"].split(" (")[0] for s in agents.TRANSLATOR_SETTINGS_SPEC}
        rows = [[esc(labels[k])] + [esc(str((pres.get(n, {}).get("settings") or {}).get(k, "—"))
                                        .replace("_", " ")) for n in compat.PRESET_ORDER] for k in keys]
        rows.append(["<i>Idea</i>"] + [esc(pres.get(n, {}).get("description", "")) for n in compat.PRESET_ORDER])
        state_line = (f"Current: <b>{esc(compat.preset_label(current))}</b> preset"
                      + (" — <b>edited by you</b>" if cfg.get("edited") else " (unchanged)"))
        self.w["preset_info"].value = (
            f"<p style='margin:4px 0'>{state_line}</p><details><summary>What the presets change</summary>"
            + table(["Setting"] + [compat.preset_label(n) for n in compat.PRESET_ORDER], rows)
            + "</details>")
        if not self._is_live() and self.state.mode == "replay":
            note = esc(compat.replay_variant_note(cfg))
            if self._replay_locale_note():
                note += "<br>" + esc(REPLAY_LOCALE_NOTE)
            self.w["replay_notice"].value = box("replay" if cfg.get("edited") else "plain",
                                                ("<b>Replay Mode:</b> " + note))
        else:
            self.w["replay_notice"].value = ""

    def _replay_locale_note(self) -> bool:
        """True when Replay's British English differs from the project's English variant."""
        return bool(self.state is not None and not self._is_live()
                    and self.state.locale in ("en-US", "en"))

    # .................................................................. 4 run
    def _build_run(self) -> widgets.VBox:
        w = self.w
        steps = (("baseline", "1 · Baseline (one-shot)"), ("translator", "2 · Run translator agent"),
                 ("reviewer", "3 · Run reviewer agent"))
        rows = []
        for step, text in steps:
            b = _button(text, "primary", width="260px")
            b.on_click(lambda btn, s=step: self._action(btn, lambda: self.run_step(s), "msg_run",
                                                        "Working… (0 requests so far)"))
            w[f"btn_{step}"] = b
            w[f"est_{step}"] = _html()
            rows.append(widgets.HBox([b, w[f"est_{step}"]], layout=_layout(align_items="center")))
        w["results_table"] = _html()
        w["cmp_a"] = widgets.Dropdown(options=[("—", "")], description="Run A:",
                                      style={"description_width": "initial"}, layout=_layout(width="460px"))
        w["cmp_b"] = widgets.Dropdown(options=[("—", "")], description="Run B:",
                                      style={"description_width": "initial"}, layout=_layout(width="460px"))
        w["btn_compare"] = _button("Compare these two runs", "info", icon="columns")
        w["btn_compare"].on_click(lambda b: self._action(b, self._compare_runs, "msg_run"))
        w["compare_out"] = _html()
        w["review_cards"] = _html()
        w["validation_summary"] = _html()
        # Results live in tabs of bounded height, so a long table does not push the run
        # buttons and the status bar out of the Colab output frame.
        w["run_tabs"] = _tabs([
            ("Results", _scroll(w["results_table"], "400px")),
            ("Compare runs", widgets.VBox([
                widgets.HBox([w["cmp_a"], w["cmp_b"], w["btn_compare"]],
                             layout=_layout(flex_flow="row wrap", align_items="center")),
                _scroll(w["compare_out"], "360px")])),
            ("Reviewer findings", _scroll(w["review_cards"], "400px")),
            ("Technical checks", _scroll(w["validation_summary"], "400px"))])
        return widgets.VBox([
            _html("<h3 style='margin:4px 0'>4 · Run the agents (≈20 min)</h3>"
                  "<p style='margin:2px 0'>Run the steps in order. Then <b>change the translator's prompt "
                  "in Section 3 and run it again</b>: every run becomes a new version you can compare.</p>"),
            *rows, w["msg_run"], w["run_tabs"]])

    def run_step(self, step: str) -> str:
        st = self._require_project()
        prov = self._require_provider()
        self._sync_config_from_widgets()
        n = agents.estimate_requests(st, self.challenge, step)
        wrapped = _ProgressProvider(prov, n, self._set_working)
        before = len(st.prompt_snapshots)
        history_before = len(st.history)
        cfg = st.agents["translator"]
        if step == "baseline":
            v = agents.run_baseline(st, wrapped, self.challenge)
            self._record_version(v, before, "baseline", cfg)
            self.w["run_tabs"].selected_index = 0
            return self._with_partial(f"Baseline ready ({v.version_id}). Now run the translator "
                                      "agent.", history_before)
        if step == "translator":
            v = agents.run_translator(st, wrapped, self.challenge)
            self._record_version(v, before, "translator", cfg)
            self.w["run_tabs"].selected_index = 1 if self._auto_compare(v) else 0
            extra = ""
            if not self._is_live() and cfg.get("edited"):
                extra = " " + compat.replay_variant_note(cfg)
            return self._with_partial(
                f"New version {v.version_id}: {v.label}. Try another preset or edit the prompt "
                "and run again, then compare the runs below (tab “Compare runs”)." + extra, history_before)
        if step == "reviewer":
            found = agents.run_reviewer(st, wrapped, self.challenge)
            self.w["run_tabs"].selected_index = 2
            return self._review_message(found)
        if step == "revision":
            v = agents.run_revision(st, wrapped, self.challenge, role=self.role)
            self._record_version(v, before, "reviser", cfg)
            return (f"Revision ready ({v.version_id}). Only strings with accepted findings were re-sent; "
                    "your own wording was applied directly without any AI request.")
        raise StudioError(f"Unknown step '{step}'.")

    def _with_partial(self, message: str, history_before: int) -> str:
        """Turn a run message amber when some batches failed (history event ``partial_run``)."""
        partial = [h["detail"] for h in self.state.history[history_before:]
                   if h.get("event") == "partial_run"]
        if not partial:
            return message
        return Warn("⚠️ Only part of this step worked. " + " ".join(partial) + "\n" + message)

    @staticmethod
    def _review_message(found) -> str:
        """Plain-English result of a reviewer run (skipped / nothing found / all dropped)."""
        counts = found.counts_text() if hasattr(found, "counts_text") else ""
        if getattr(found, "skipped", False):
            return ("Review skipped: no string has changed since the last review, so no request "
                    "was sent. Edit strings or run a revision first, then review again.")
        if getattr(found, "all_dropped", False):
            return Warn(f"⚠️ The reviewer replied with {found.received} finding(s), but none could "
                        f"be used ({counts}). This does NOT mean the translation is fine. Run the "
                        "reviewer again, or switch to Replay Mode.")
        if not found:
            n = len(getattr(found, "reviewed_ids", ()) or ())
            msg = (f"The reviewer checked {n} string(s) and found no problems." if n else
                   "The reviewer had no findings for the strings it checked.")
            return Warn(msg + f" Note: {counts}.") if counts else msg
        msg = (f"The reviewer made {len(found)} suggestion(s). They are suggestions — you decide "
               "in Section 5.")
        return Warn(msg + f" Note: {counts}.") if counts else msg

    def _record_version(self, v, snap_before: int, agent: str, cfg: dict) -> None:
        st = self.state
        snaps = [s for s in st.prompt_snapshots[snap_before:]
                 if s.agent == agent and agents.REPAIR_MARK not in s.user]
        meta = {"preset": cfg.get("preset") or "balanced", "edited": bool(cfg.get("edited")),
                "snapshot": snaps[0].snapshot_id if snaps else None, "source": v.source}
        if v.kind == "baseline":
            meta.pop("preset")
            meta.pop("edited")
        self.extras["version_meta"][v.version_id] = meta
        if v.kind == "translator" and "preset" not in v.label.lower():
            mode = "Live" if v.source == "live" else "Replay"
            v.label = f"Translator · {mode} · {compat.preset_label(meta['preset'])} preset"
            if meta["edited"]:
                v.label += " (edited prompt)" if mode == "Live" else " (your edits not simulated)"

    def _auto_compare(self, v) -> bool:
        tr = [x for x in self.state.versions if x.kind == "translator"]
        if len(tr) >= 2:
            self._refresh_compare_options()
            self.w["cmp_a"].value, self.w["cmp_b"].value = tr[-2].version_id, v.version_id
            self.w["compare_out"].value = self.compare_html(tr[-2].version_id, v.version_id)
            return True
        return False

    def _version_meta(self, v) -> dict:
        return self.extras.get("version_meta", {}).get(v.version_id, {}) if v else {}

    def _version_variant(self, v) -> str:
        seen = set()
        while v is not None and v.version_id not in seen:
            seen.add(v.version_id)
            var = getattr(v, "variant", None) or self._version_meta(v).get("preset")
            if var:
                return var
            low = (v.label or "").lower()
            for name in compat.PRESET_ORDER:
                if f"{compat.preset_label(name).lower()} preset" in low:
                    return name
            v = self.state.version(v.parent_id)
        return (self.state.agents.get("translator", {}).get("preset") if self.state else None) or "balanced"

    def version_label(self, v) -> str:
        label = f"{v.version_id} · {v.label}"
        if v.source not in label.lower():
            label += f" · {v.source}"
        if v.version_id == self.state.current_version_id:
            label += " (current)"
        return label

    def _prompt_for_version(self, v):
        st = self.state
        if v is None or v.kind in ("human_edit", "restored"):
            return None
        meta = self._version_meta(v)
        if "snapshot" in meta:  # recorded by this UI when the version was made
            sid = meta["snapshot"]
            return next((s for s in st.prompt_snapshots if s.snapshot_id == sid), None) if sid else None
        agent = {"baseline": "baseline", "translator": "translator", "revision": "reviser"}.get(v.kind)
        snaps = [s for s in st.prompt_snapshots if s.agent == agent and agents.REPAIR_MARK not in s.user]
        if not snaps:
            return None
        if v.kind == "revision":
            return next((s for s in snaps if s.round == v.round), snaps[-1])
        same = [x for x in st.versions if x.kind == v.kind]
        per_run = max(1, math.ceil(len(st.strings) / agents.BATCH_SIZE))
        idx = same.index(v) * per_run if v in same else 0
        return snaps[min(idx, len(snaps) - 1)]

    def compare_html(self, vid_a: str, vid_b: str) -> str:
        st = self._require_project()
        a, b = st.version(vid_a), st.version(vid_b)
        if a is None or b is None:
            raise StudioError("Choose two versions to compare.")
        rows, styles, changed = [], {}, 0
        for n, sid in enumerate(st.string_ids()):
            ta, tb = a.translations.get(sid, "—"), b.translations.get(sid, "—")
            diff = ta != tb
            if diff:
                changed += 1
                styles[n] = "background:#fff8e1"
            rows.append([f"<code>{esc(sid)}</code>" + (" " + badge("changed", "#d35400") if diff else ""),
                         esc_br(st.source_text(sid)), esc_br(ta), esc_br(tb)])
        head = (f"<p style='margin:4px 0'><b>{changed} of {len(rows)} strings differ</b> between "
                f"<b>{esc(self.version_label(a))}</b> (A) and <b>{esc(self.version_label(b))}</b> (B). "
                "Changed rows are highlighted.</p>")
        out = head + table(["String", "Source", f"A · {a.version_id}", f"B · {b.version_id}"], rows, styles)
        pa, pb = self._prompt_for_version(a), self._prompt_for_version(b)
        if pa is not None and pb is not None:
            sys_diff = ""
            if pa.system != pb.system:
                sys_diff = "<p><b>System message</b></p>" + exports.prompt_diff_html(pa.system, pb.system)
            out += ("<h4 style='margin:8px 0 2px 0'>What changed in the prompt (A → B)</h4>"
                    f"<div class='gls-diff'>{_DIFF_CSS}{sys_diff}"
                    + exports.prompt_diff_html(pa.user, pb.user) + "</div>")
        else:
            who = a if pa is None else b
            out += box("plain", f"{esc(who.version_id)} was written or restored by a human, so no "
                                "prompt produced it.")
        if not st.mode == "live" and any(self._version_meta(x).get("edited") for x in (a, b)):
            out += box("replay", esc(compat.replay_variant_note(st.agents["translator"])))
        out += box("info", "💬 <b>Discuss:</b> What in the prompt caused these differences?")
        return Safe(out)

    def _compare_runs(self) -> Safe:
        a, b = self.w["cmp_a"].value, self.w["cmp_b"].value
        if not a or not b:
            raise StudioError("Run the translator at least once, then choose two versions.")
        self.w["compare_out"].value = self.compare_html(a, b)
        self.w["run_tabs"].selected_index = 1
        return Safe("Comparison updated below (tab “Compare runs”).")

    def _refresh_compare_options(self) -> None:
        st = self.state
        opts = [(self.version_label(v), v.version_id) for v in st.versions] if st else []
        opts = opts or [("—", "")]
        for key in ("cmp_a", "cmp_b", "hist_pick"):
            dd = self.w.get(key)
            if dd is None:
                continue
            old = dd.value
            self._suspend = True
            try:
                dd.options = opts
                ids = [v for _, v in opts]
                dd.value = old if old in ids else ids[-1]
            finally:
                self._suspend = False

    def _finding_card_html(self, f, with_decision=True) -> str:
        st = self.state
        cur = st.current_version()
        reviewed = st.version(f.reviewed_version_id)
        text = (reviewed or cur).translations.get(f.string_id, "") if (reviewed or cur) else ""
        d = st.latest_decisions().get(f.finding_id)
        decision = ""
        if with_decision:
            if d is None:
                decision = badge("No decision yet", "#7f8c8d")
            else:
                colour = "#1e8449" if d.agrees_with_reviewer else "#c0392b"
                decision = badge(ACTION_TEXT.get(d.action, d.action) + f" · {d.role}", colour)
        return (
            f"<div style='border:1px solid #d9e2ec;border-radius:6px;padding:6px 10px;margin:4px 0;"
            f"background:#fff;color:#1f2933'>"
            f"<div><b>{esc(f.finding_id)}</b> · <code>{esc(f.string_id)}</code> "
            f"{badge(f.category.replace('_', ' '), '#2471a3')}"
            f"{badge(f.severity, _SEV_COLOURS.get(f.severity, '#7f8c8d'))} {decision}"
            f"<span style='float:right;color:#b9770e;font-weight:bold'>Suggestion — you decide</span></div>"
            f"<div style='margin-top:4px'><i>Source:</i> {esc_br(st.source_text(f.string_id))}</div>"
            f"<div><i>Translation reviewed:</i> {esc_br(text)}</div>"
            f"<div><i>Issue:</i> {esc_br(f.issue)}</div>"
            f"<div><i>Reasoning:</i> {esc_br(f.reasoning)}</div>"
            f"<div><i>Reviewer's suggestion:</i> <b>{esc_br(f.suggestion) or '—'}</b></div>"
            + (f"<div><i>Your text:</i> {esc_br(d.human_text)}</div>" if d is not None and d.human_text else "")
            + (f"<div><i>Comment:</i> {esc_br(d.comment)}</div>" if d is not None and d.comment else "")
            + "</div>")

    def _refresh_run(self) -> None:
        w, st = self.w, self.state
        for step in ("baseline", "translator", "reviewer"):
            w[f"est_{step}"].value = self._estimate_text(step)
        if st is None:
            w["results_table"].value = box("plain", "Start a mission first (Section 2).")
            w["review_cards"].value = ""
            w["validation_summary"].value = ""
            self._refresh_compare_options()
            return
        base = st.baseline_version()
        latest_tr = next((v for v in reversed(st.versions) if v.kind == "translator"), None)
        if base is None and latest_tr is None:
            w["results_table"].value = box("plain", "No results yet — click “1 · Baseline”.")
        else:
            rows = []
            for sid in st.string_ids():
                note = latest_tr.notes.get(sid) if latest_tr else ""
                rows.append([f"<code>{esc(sid)}</code>", esc_br(st.source_text(sid)),
                             esc_br(base.translations.get(sid, "—") if base else "—"),
                             esc_br(latest_tr.translations.get(sid, "—") if latest_tr else "—")
                             + (f"<br><span style='color:#616e7c;font-size:12px'>Note: {esc(note)}</span>"
                                if note else "")])
            label = f"Translator (latest: {latest_tr.version_id})" if latest_tr else "Translator (latest)"
            w["results_table"].value = (
                (f"<p style='margin:2px 0'>Latest translator run: <b>{esc(latest_tr.label)}</b></p>"
                 if latest_tr else "")
                + (box("plain", esc(REPLAY_LOCALE_NOTE)) if self._replay_locale_note() else "")
                + table(["Id", "Source", "Baseline", label], rows))
        self._refresh_compare_options()
        if st.findings:
            last = max(f.round for f in st.findings)
            cards = "".join(self._finding_card_html(f) for f in st.findings if f.round == last)
            w["review_cards"].value = (f"<p style='margin:2px 0'>Review round {last}: these are "
                                       "<b>suggestions — you decide</b> in Section 5.</p>" + cards)
        else:
            w["review_cards"].value = box("plain", "No reviewer findings yet.")
        w["validation_summary"].value = self._validation_html()

    def _estimate_text(self, step: str) -> str:
        if self.state is None or self.challenge is None:
            return ""
        try:
            n = agents.estimate_requests(self.state, self.challenge, step)
        except Exception:  # noqa: BLE001
            return ""
        if self._is_live():
            left = self.meter.remaining()
            return (f"<span style='margin-left:8px'>This will make <b>{n}</b> request(s) "
                    f"({left} left).</span>")
        return (f"<span style='margin-left:8px;color:#616e7c'>Replay: {n} simulated request(s), free "
                "and not counted.</span>")

    def _validation_html(self) -> str:
        st = self.state
        if st is None or st.current_version() is None:
            return box("plain", "Nothing to check yet.")
        rep = ps.validate_current(st)
        if not rep.issues:
            return box("ok", "✅ " + esc(rep.summary()))
        items = []
        for i in rep.critical + rep.warnings:
            colour = _SEV_COLOURS.get(i.severity, "#7f8c8d")
            label = "MUST FIX" if i.severity == "CRITICAL" else "CHECK"
            items.append(f"<li>{badge(label, colour)} <code>{esc(i.string_id or '')}</code> "
                         f"{esc(i.message)} <i>{esc(i.fix_hint)}</i></li>")
        return box("error" if rep.critical else "warn",
                   f"<b>{esc(rep.summary())}</b> These are automatic technical checks, separate from "
                   f"the reviewer's opinions.<ul style='margin:4px 0 0 18px'>{''.join(items)}</ul>")

    # .................................................................. 5 director
    def _build_director(self) -> widgets.VBox:
        w = self.w
        w["director_intro"] = _html()
        w["findings_box"] = widgets.VBox()
        w["bulk_comment"] = widgets.Text(placeholder="Comment for the selected findings (optional)",
                                         layout=_layout(width="480px"))
        w["btn_bulk_accept"] = _button("Accept selected", "success")
        w["btn_bulk_reject"] = _button("Reject selected", "danger")
        w["btn_bulk_accept"].on_click(lambda b: self._action(b, lambda: self._bulk("accept"), "msg_director"))
        w["btn_bulk_reject"].on_click(lambda b: self._action(b, lambda: self._bulk("reject"), "msg_director"))
        w["rule_kind"] = widgets.Dropdown(options=[("Style rule", "style"), ("Glossary rule", "glossary")],
                                          value="style", description="Rule type:")
        w["rule_text"] = widgets.Text(placeholder="e.g. Kit always calls Granny Wong 'Granny'.",
                                      description="Rule:", layout=_layout(width="620px"))
        w["rule_src"] = widgets.Text(placeholder="source term (glossary)", description="Source:",
                                     layout=_layout(width="300px"))
        w["rule_tgt"] = widgets.Text(placeholder="English term (glossary)", description="English:",
                                     layout=_layout(width="300px"))
        w["rule_from"] = widgets.Dropdown(options=[("(not linked to a finding)", "")], description="From:")
        w["btn_rule"] = _button("Add a project rule", "info", icon="plus")
        w["btn_rule"].on_click(lambda b: self._action(b, self._add_rule, "msg_director"))
        w["rules_list"] = _html()
        w["edit_grid"] = widgets.VBox()
        w["edit_comment"] = widgets.Text(placeholder="Why did you edit? (optional)",
                                         layout=_layout(width="480px"))
        w["btn_save_edits"] = _button("Save my edits as a new version", "warning", width="300px", icon="save")
        w["btn_save_edits"].on_click(lambda b: self._action(b, self._save_edits, "msg_director"))
        w["max_cycles"] = widgets.Dropdown(options=[("0 (no revision)", 0), ("1 (default)", 1), ("2", 2)],
                                           value=1, description="Revision cycles allowed:",
                                           style={"description_width": "initial"})
        w["max_cycles"].observe(self._on_max_cycles, names="value")
        w["revision_info"] = _html()
        w["btn_revision"] = _button("Send accepted feedback to the translator", "primary", width="360px",
                                    icon="paper-plane")
        w["btn_revision"].on_click(lambda b: self._action(b, lambda: self.run_step("revision"),
                                                          "msg_director", "Working… (0 requests so far)"))
        w["btn_review2"] = _button("Review the revised strings (round 2, optional)", "", width="360px")
        w["btn_review2"].on_click(lambda b: self._action(b, lambda: self.run_step("reviewer"),
                                                         "msg_director", "Working… (0 requests so far)"))
        w["history_table"] = _html()
        w["hist_pick"] = widgets.Dropdown(options=[("—", "")], description="Version:",
                                          layout=_layout(width="520px"))
        w["btn_hist_compare"] = _button("Compare with current", "info")
        w["btn_hist_compare"].on_click(lambda b: self._action(b, self._history_compare, "msg_director"))
        w["btn_restore"] = _button("Restore this version", "warning", icon="history")
        w["btn_restore"].on_click(lambda b: self._action(b, self._restore, "msg_director"))
        w["hist_compare_out"] = _html()
        w["decision_log"] = _html()
        w["approval_info"] = _html()
        w["btn_approve"] = _button("Approve final translation", "success", width="300px", icon="check")
        w["btn_approve"].on_click(lambda b: self._action(b, self._approve, "msg_director"))
        rule_label = _html(box("plain", "<b>Project memory</b> — sent to your agents in future prompts. "
                                        "The AI model itself is not retrained."))
        row = _layout(flex_flow="row wrap", align_items="center")
        # Steps a–g are tabs of bounded height; every result message appears just below them.
        w["director_tabs"] = _tabs([
            ("a · Decide", widgets.VBox([
                widgets.HBox([w["bulk_comment"], w["btn_bulk_accept"], w["btn_bulk_reject"]], layout=row),
                _scroll(w["findings_box"], "420px")])),
            ("b · Rules", widgets.VBox([
                rule_label, widgets.HBox([w["rule_kind"], w["rule_from"]], layout=row), w["rule_text"],
                widgets.HBox([w["rule_src"], w["rule_tgt"]], layout=row), w["btn_rule"],
                _scroll(w["rules_list"], "240px")])),
            ("c · Revise", widgets.VBox([
                w["max_cycles"], w["revision_info"], widgets.HBox([w["btn_revision"], w["btn_review2"]],
                                                                  layout=row)])),
            ("d · Edit", widgets.VBox([
                _html("<p style='margin:2px 0'>Edit any string yourself, then save your edits before "
                      "running other steps.</p>"),
                widgets.HBox([w["edit_comment"], w["btn_save_edits"]], layout=row),
                _scroll(w["edit_grid"], "400px")])),
            ("e · Versions", widgets.VBox([
                widgets.HBox([w["hist_pick"], w["btn_hist_compare"], w["btn_restore"]], layout=row),
                _scroll(w["history_table"], "200px"), _scroll(w["hist_compare_out"], "360px")])),
            ("f · Decision log", _scroll(w["decision_log"], "400px")),
            ("g · Approve", widgets.VBox([w["btn_approve"], w["approval_info"]]))])
        return widgets.VBox([
            _html("<h3 style='margin:4px 0'>5 · Human Director (≈25 min — the most important part)</h3>"),
            w["director_intro"],
            _html("<p style='margin:2px 0'>Work through the tabs: <b>a</b> decide on each reviewer "
                  "suggestion · <b>b</b> add a project rule · <b>c</b> send accepted feedback to the "
                  "translator · <b>d</b> edit the final translation yourself · <b>e</b> version history · "
                  "<b>f</b> decision log · <b>g</b> approve.</p>"),
            w["director_tabs"], w["msg_director"]])

    def _card_widgets(self, f) -> dict:
        st = self.state
        cur = st.current_version()
        cw = {"html": _html(), "select": widgets.Checkbox(value=False, indent=False, description="Select"),
              "comment": widgets.Text(placeholder="Your comment: why? (recorded in the log)",
                                      layout=_layout(width="100%")),
              "edit": _textarea(f.suggestion or "", rows=2),
              "override": _textarea((cur.translations.get(f.string_id, "") if cur else ""), rows=2)}
        for action, text, style in (("accept", "Accept", "success"), ("reject", "Reject", "danger"),
                                    ("accept_edited", "Accept with my edit", "info"),
                                    ("override", "Override with my own wording", "warning")):
            b = _button(text, style)
            b.on_click(lambda btn, a=action, fid=f.finding_id:
                       self._action(btn, lambda: self.decide(fid, a), "msg_director"))
            cw[f"btn_{action}"] = b
        cw["box"] = widgets.VBox([
            cw["html"], widgets.HBox([cw["select"], cw["btn_accept"], cw["btn_reject"]]),
            _html("<span style='font-size:12px'>Accept with my edit (starts from the reviewer's suggestion):</span>"),
            widgets.HBox([cw["edit"], cw["btn_accept_edited"]]),
            _html("<span style='font-size:12px'>Override — my own wording (records that you disagreed):</span>"),
            widgets.HBox([cw["override"], cw["btn_override"]]), cw["comment"]],
            layout=_layout(border="1px solid #e4e7eb", padding="4px", margin="4px 0"))
        return cw

    def decide(self, finding_id: str, action: str) -> str:
        st = self._require_project()
        cw = self._finding_cards.get(finding_id) or {}
        human = None
        if action == "accept_edited":
            human = cw["edit"].value if cw else None
        elif action == "override":
            human = cw["override"].value if cw else None
        comment = cw["comment"].value if cw else ""
        d = ps.decide_finding(st, finding_id, action, self.role, human_text=human, comment=comment)
        if cw:
            cw["comment"].value = ""
        return (f"{d.decision_id}: {ACTION_TEXT[action]} for {finding_id} ({d.string_id}), recorded "
                f"as {self.role}." + ("" if d.agrees_with_reviewer else " Your disagreement is recorded."))

    def _bulk(self, action: str) -> str:
        st = self._require_project()
        ids = [fid for fid, cw in self._finding_cards.items() if cw["select"].value]
        if not ids:
            raise StudioError("Tick “Select” on at least one finding first.")
        ds = ps.bulk_decide(st, ids, action, self.role, comment=self.w["bulk_comment"].value)
        for fid in ids:
            self._finding_cards[fid]["select"].value = False
        self.w["bulk_comment"].value = ""
        return f"{ACTION_TEXT[action]}: {len(ds)} finding(s) ({', '.join(ids)})."

    def _add_rule(self) -> str:
        st = self._require_project()
        r = ps.add_rule(st, self.w["rule_kind"].value, self.w["rule_text"].value, self.role,
                        source_term=self.w["rule_src"].value.strip() or None,
                        target_term=self.w["rule_tgt"].value.strip() or None,
                        from_finding=self.w["rule_from"].value or None)
        for k in ("rule_text", "rule_src", "rule_tgt"):
            self.w[k].value = ""
        return (f"Rule {r.rule_id} added to project memory. It will be included in your agents' "
                "future prompts (the AI model itself is not retrained).")

    def _save_edits(self) -> str:
        st = self._require_project()
        cur = st.current_version()
        if cur is None:
            raise StudioError("Run the translator first; there is nothing to edit yet.")
        edits = {sid: ta.value for sid, ta in self._grid.items() if ta.value != cur.translations.get(sid, "")}
        if not edits:
            raise StudioError("You have not changed any string in the grid.")
        v = ps.direct_edit(st, edits, self.role, comment=self.w["edit_comment"].value)
        self.w["edit_comment"].value = ""
        return f"Saved your edits to {len(edits)} string(s) as a new human version {v.version_id}."

    def _on_max_cycles(self, change) -> None:
        if self._suspend or self.state is None:
            return
        if self.state.revision.get("cycles_done", 0):
            self._refresh_director()
            return
        self.state.revision["max_cycles"] = int(change["new"])
        self.state.log("revision_limit", f"Revision cycles allowed: {change['new']}")
        self._try_autosave()
        self._refresh_director()

    def _history_compare(self) -> Safe:
        st = self._require_project()
        vid = self.w["hist_pick"].value
        if not vid or st.current_version_id is None:
            raise StudioError("Choose a version first.")
        self.w["hist_compare_out"].value = self.compare_html(vid, st.current_version_id)
        return Safe("Comparison shown below the version history.")

    def _restore(self) -> str:
        st = self._require_project()
        vid = self.w["hist_pick"].value
        if not vid:
            raise StudioError("Choose a version first.")
        v = ps.restore_version(st, vid, self.role)
        meta = dict(self._version_meta(st.version(vid)))
        meta["restored_from"] = vid
        meta.pop("snapshot", None)
        self.extras["version_meta"][v.version_id] = meta
        return f"Restored {vid} as the new current version {v.version_id}."

    def _approve(self) -> str:
        st = self._require_project()
        open_n = len(st.open_findings())
        ps.approve_final(st, self.role)
        msg = (f"Approved {st.approval['version_id']} as the final translation ({self.role}). "
               "Any later change (an edit, a decision, a restore or a revision) revokes this approval "
               "automatically. Next: Section 6.")
        if open_n:
            msg += f" Note: {open_n} finding(s) had no decision."
        return msg + "\n" + DOWNLOAD_REMINDER

    def _refresh_director(self) -> None:
        w, st = self.w, self.state
        if st is None:
            w["director_intro"].value = box("plain", "Start a mission first (Section 2).")
            for k in ("rules_list", "revision_info", "history_table", "decision_log", "approval_info"):
                w[k].value = ""
            return
        # finding cards (cached so typed text survives refreshes)
        for f in st.findings:
            if f.finding_id not in self._finding_cards:
                self._finding_cards[f.finding_id] = self._card_widgets(f)
        ordered = sorted(st.findings, key=lambda f: (-f.round, f.finding_id))
        for f in ordered:
            self._finding_cards[f.finding_id]["html"].value = self._finding_card_html(f)
        boxes = tuple(self._finding_cards[f.finding_id]["box"] for f in ordered)
        if tuple(w["findings_box"].children) != boxes:
            w["findings_box"].children = boxes
        open_n = len(st.open_findings())
        w["director_intro"].value = box("info", (
            f"You are deciding as <b>{esc(self.role)}</b> (change it in the status bar). "
            f"{len(st.findings)} finding(s), <b>{open_n} without a decision</b>. The reviewer is a "
            "collaborator, not an authority: accept, edit, reject or override each suggestion, and "
            "say why in the comment.") if st.findings else
            "No reviewer findings yet — run the reviewer in Section 4.")
        rule_opts = [("(not linked to a finding)", "")] + [(f"{f.finding_id} · {f.string_id}", f.finding_id)
                                                            for f in st.findings]
        if list(w["rule_from"].options) != rule_opts:
            w["rule_from"].options = rule_opts
            w["rule_from"].value = ""
        rrows = [[esc(r.rule_id), esc(r.kind), esc(r.text), esc(r.source_term or ""),
                  esc(r.target_term or ""), esc(r.role)] for r in st.memory_rules]
        w["rules_list"].value = (table(["Rule", "Type", "Text", "Source", "English", "Added by"], rrows)
                                 if rrows else "<i>No project rules yet.</i>")
        done, max_c = st.revision.get("cycles_done", 0), st.revision.get("max_cycles", 1)
        self._suspend = True
        try:
            w["max_cycles"].value = max_c
            w["max_cycles"].disabled = done > 0
        finally:
            self._suspend = False
        try:
            n = agents.estimate_requests(st, self.challenge, "revision")
        except Exception:  # noqa: BLE001
            n = 0
        req = (f"This will make {n} request(s)." if self._is_live()
               else f"Replay: {n} simulated request(s), free.")
        w["revision_info"].value = box("plain", (
            f"Revision cycles: <b>{done} used of {max_c}</b> ({max(0, max_c - done)} left). "
            "Only the strings with <b>accepted</b> findings are re-sent to the translator. Your own "
            "wording (accept with edit / override / direct edits) is locked and applied without any "
            f"AI request. Rejected suggestions are never applied. {esc(req)}"))
        self._refresh_grid()
        hrows = []
        for v in st.versions:
            cur_mark = " ← current" if v.version_id == st.current_version_id else ""
            appr = " ✔ approved" if st.approval.get("version_id") == v.version_id and st.approval.get("approved") else ""
            hrows.append([f"<b>{esc(v.version_id)}</b>{esc(cur_mark)}{esc(appr)}", esc(v.label), esc(v.kind),
                          esc(v.source), esc(v.parent_id or ""), esc(v.created_at)])
        w["history_table"].value = (table(["Version", "Label", "Kind", "Source", "Based on", "Created"], hrows)
                                    if hrows else "<i>No versions yet.</i>")
        w["decision_log"].value = self._decision_log_html()
        w["approval_info"].value = self._approval_html()

    def _refresh_grid(self) -> None:
        st = self.state
        cur = st.current_version() if st else None
        ids = tuple(st.string_ids()) if st else ()
        if cur is None:
            self.w["edit_grid"].children = (_html("<i>Run the translator first.</i>"),)
            self._grid, self._grid_ids, self._grid_version = {}, (), None
            return
        if ids != self._grid_ids:
            self._grid = {}
            rows = []
            spec = {s["id"]: s for s in st.strings}
            for sid in ids:
                s = spec.get(sid, {})
                cons = []
                if s.get("max_len"):
                    cons.append(f"max {s['max_len']} characters")
                if s.get("placeholders"):
                    cons.append("keep " + " ".join(s["placeholders"]))
                ta = _textarea(cur.translations.get(sid, ""), rows=2)
                self._grid[sid] = ta
                rows.append(widgets.VBox([_html(f"<code>{esc(sid)}</code> — {esc(st.source_text(sid))}"
                                                + (f" <i>({esc('; '.join(cons))})</i>" if cons else "")), ta]))
            self.w["edit_grid"].children = tuple(rows)
            self._grid_ids, self._grid_version = ids, cur.version_id
        elif cur.version_id != self._grid_version:
            for sid, ta in self._grid.items():
                ta.value = cur.translations.get(sid, "")
            self._grid_version = cur.version_id

    def _decision_log_html(self) -> str:
        st = self.state
        rows = []
        for d in st.decisions:
            if d.agrees_with_reviewer is None:
                agree = "—"
            else:
                agree = "Agreed" if d.agrees_with_reviewer else "Overrode"
            rows.append([esc(d.decision_id), esc(d.role), esc(ACTION_TEXT.get(d.action, d.action)),
                         f"<code>{esc(d.string_id or '')}</code> {esc(d.finding_id or '')}",
                         esc_br(d.reviewer_suggestion or ""), esc_br(d.human_text or ""), esc(agree),
                         esc_br(d.comment or "")])
        return (table(["#", "Who", "What", "String / finding", "Reviewer suggestion", "Human choice",
                       "Agreed / overrode", "Comment"], rows) if rows else "<i>No decisions yet.</i>")

    def _approval_html(self) -> str:
        st = self.state
        ok, reasons = ps.can_export(st)
        ap = st.approval
        if ap.get("approved") and ok:
            return box("ok", f"✅ <b>{esc(ap['version_id'])}</b> approved by {esc(ap.get('role'))} at "
                             f"{esc(ap.get('approved_at'))}. Any later change revokes this approval.")
        rep = ps.validate_current(st) if st.current_version() else None
        blocking = [i.message for i in rep.critical] if rep else ["There is no translation yet."]
        text = "<b>Not approved yet.</b> "
        if blocking:
            text += ("Approval is blocked until these are fixed (edit the strings in d.):<ul style='margin:2px 0 0 18px'>"
                     + "".join(f"<li>{esc(m)}</li>" for m in blocking) + "</ul>")
        else:
            text += "No blocking problems — you can approve when you are satisfied."
        other = [r for r in reasons if not r.startswith("Blocking problem") and "not been approved" not in r]
        if other:
            text += "<br>" + "<br>".join(esc(r) for r in other)
        return box("warn" if blocking else "info", text + "<br><i>Any change after approval revokes it.</i>")

    # .................................................................. 6 export
    def _build_export(self) -> widgets.VBox:
        w = self.w
        w["summary_table"] = _html()
        w["summary_findings"] = _html()
        w["summary_validation"] = _html()
        w["summary_history"] = _html()
        w["prompt_evolution"] = _html()
        w["reflection"] = _textarea(rows=6, placeholder="Write your answer together (a few sentences).")
        w["btn_reflection"] = _button("Save reflection", "info", icon="save")
        w["btn_reflection"].on_click(lambda b: self._action(b, self._save_reflection, "msg_export"))
        w["btn_export_game"] = _button("Export game_translation_en.json", "success", width="320px", icon="download")
        w["btn_export_settings"] = _button("Export agent_settings.json", "", width="260px", icon="download")
        w["btn_export_report"] = _button("Export workflow_report.html", "", width="260px", icon="download")
        w["btn_export_all"] = _button("Export all three files", "primary", width="260px", icon="download")
        for key, which in (("btn_export_game", "game_translation"), ("btn_export_settings", "agent_settings"),
                           ("btn_export_report", "workflow_report"), ("btn_export_all", "all")):
            w[key].on_click(lambda b, wh=which: self._action(b, lambda: self.export(wh), "msg_export",
                                                             "Checking and saving…"))
        w["game_help"] = _html(box("info", (
            f"<b>Play your translation</b><ol style='margin:4px 0 0 18px'>"
            f"<li>Export and download <code>game_translation_en.json</code> (button above).</li>"
            f"<li>Open the game: <a href='{esc(GAME_URL)}' target='_blank' rel='noopener noreferrer'>"
            f"{esc(GAME_URL)}</a></li>"
            f"<li>Click <b>Import student JSON</b> and choose the file. The game switches <b>Dialogue "
            f"language</b> to <b>Student's imported English</b> by itself.</li></ol>")))
        w["btn_next_mission"] = _button("Start the next mission", "warning", width="260px", icon="forward")
        w["btn_next_mission"].on_click(lambda b: self._action(b, self._next_mission, "msg_export"))
        w["summary_tabs"] = _tabs([
            ("Summary", _scroll(w["summary_table"], "380px")),
            ("Findings & decisions", _scroll(w["summary_findings"], "380px")),
            ("Technical checks", _scroll(w["summary_validation"], "380px")),
            ("Revision history", _scroll(w["summary_history"], "380px")),
            ("Prompt evolution", _scroll(w["prompt_evolution"], "380px"))])
        return widgets.VBox([
            _html("<h3 style='margin:4px 0'>6 · Test and export (≈10 min)</h3>"),
            w["summary_tabs"],
            _html(f"<h4 style='margin:6px 0 2px 0'>Reflection</h4><p style='margin:2px 0'><b>{esc(REFLECTION_QUESTION)}</b></p>"),
            w["reflection"], w["btn_reflection"],
            _html("<h4 style='margin:6px 0 2px 0'>Export</h4>"),
            widgets.HBox([w["btn_export_game"], w["btn_export_settings"], w["btn_export_report"],
                          w["btn_export_all"]], layout=_layout(flex_flow="row wrap")),
            w["msg_export"], w["download_out_game_translation"], w["download_out_agent_settings"],
            w["download_out_workflow_report"], w["game_help"], w["btn_next_mission"]])

    def _save_reflection(self, silent: bool = False) -> str:
        st = self._require_project()
        text = self.w["reflection"].value
        if text != st.reflection:
            ps.set_reflection(st, text)
        return "Reflection saved. It will appear in your workflow report."

    def export(self, which: str = "all") -> Safe:
        st = self._require_project()
        self._sync_config_from_widgets()
        self._save_reflection()
        ok, reasons = ps.can_export(st)
        if not ok:
            raise StudioError(
                "Export blocked — nothing was written, and all your work is kept.\n"
                + "\n".join(f"• {r}" for r in reasons[:6])
                + "\nHow to fix: in Section 5, fix any blocking problem in the edit grid (d.), then click "
                  "“Approve final translation” (g.), and export again.")
        out_dir = self.mission_export_dir()
        results = exports.export_all(st, self.challenge, self.manifest, out_dir)
        bad = [r for r in results.values() if not r.ok]
        if bad:
            raise StudioError(bad[0].message + "\nYour work is kept.")
        self.extras["exported"] = True
        keys = list(results) if which == "all" else [which]
        parts, all_started = [], True
        for k in keys:
            r = results[k]
            # One Output per file, cleared each time: Colab re-runs every download script still
            # in an Output whenever another is added, which duplicated the earlier files.
            started = self._start_download(r.path, self.w[f"download_out_{k}"], clear=True)
            all_started = all_started and started
            parts.append(f"<li>✅ <b>{esc(Path(r.path).name)}</b> saved to <code>{esc(r.path)}</code>"
                         + (" — download started." if started else
                            " — use the Files panel to download it." if self.colab else "") + "</li>")
        warn = results["game_translation"].issues
        wtxt = (f"<br>{len(warn)} warning(s) to review (not blocking)." if warn else "")
        if self.colab:
            steps = self._files_panel_steps(results[keys[0]].path, "the file")
            where = ("If nothing downloads: " if all_started else "To download: ") + steps
        else:
            where = f"Folder: {esc(out_dir)}"
        where += (" Every mission uses the same file names; if your browser already has a file with "
                  "that name, it may add “(1)” to the downloaded copy.")
        return Safe("<ul style='margin:2px 0 0 18px'>" + "".join(parts) + "</ul>" + where + wtxt
                    + "<br>" + esc(DOWNLOAD_REMINDER))

    def mission_export_dir(self) -> Path:
        """Exports go into one folder per mission, e.g. /content/exports/intro/."""
        st = self._require_project()
        name = "custom" if st.challenge_id == "custom" else (st.mission or st.challenge_id)
        return self.export_dir / name

    def _start_download(self, path, out, clear: bool = True) -> bool:
        """Colab: start a browser download inside the Output ``out``; True only if it started."""
        if not self.colab:
            return False
        return compat.colab_download(path, out, clear=clear)

    def _files_panel_steps(self, path, what: str | None = None) -> str:
        """Escaped HTML: where to find ``path`` in Colab's Files panel, step by step."""
        p = Path(path)
        try:
            folders = list(p.parent.resolve().relative_to(self.export_dir.resolve().parent).parts)
        except ValueError:
            folders = [str(p.parent)]
        steps = " → ".join(f"<b>{esc(x)}</b>" for x in folders)
        return (f"{esc(FILES_PANEL)} → {steps} → <b>⋮</b> next to {esc(what or p.name)} → "
                "<b>Download</b>.")

    def _save_copy(self, prefix: str) -> Path:
        path = self.export_dir / f"{prefix}_{_ts()}.json"
        self._write_atomic(path, self._state_text())
        return path

    def _download_progress(self, out_key: str = "download_out") -> Safe:
        self._require_project()
        path = self._save_copy(f"studio_progress_{self.state.challenge_id}")
        started = self._start_download(path, self.w[out_key])
        if started:
            text = (f"Progress file saved to <code>{esc(path)}</code> — download started.<br>"
                    "If nothing downloads: " + self._files_panel_steps(path))
        elif self.colab:
            text = (f"Saved to <code>{esc(path)}</code> — use the Files panel to download it: "
                    + self._files_panel_steps(path))
        else:
            text = f"Progress file saved to <code>{esc(path)}</code>."
        return Safe(text + "<br>To continue later, use “Resume from file” in “If you get stuck”.")

    def _next_mission(self) -> str:
        st = self._require_project()
        copy_path = self._save_copy(f"finished_{st.challenge_id}")
        order = list(MISSION_ORDER)
        cur = st.mission if st.mission in order else None
        nxt = order[(order.index(cur) + 1) % len(order)] if cur else "intro"
        self._suspend = True
        try:
            self.w["mission"].value = nxt
        finally:
            self._suspend = False
        self._refresh_mission_preview()
        msg = self._start_mission(confirmed=True)
        return (f"Your finished project was saved as {copy_path}. {msg} "
                "🔁 Swap roles now: the AI Director becomes the Quality Evaluator and vice versa.")

    def _refresh_export(self) -> None:
        w, st = self.w, self.state
        if st is None:
            for k in ("summary_table", "summary_findings", "summary_validation", "summary_history",
                      "prompt_evolution"):
                w[k].value = ""
            w["summary_table"].value = box("plain", "Start a mission first (Section 2).")
            return
        base = st.baseline_version()
        reviewed = st.version(st.findings[0].reviewed_version_id) if st.findings else None
        agent_v = next((v for v in reversed(st.versions) if v.kind == "revision"), None) or reviewed or \
            next((v for v in reversed(st.versions) if v.kind == "translator"), None)
        ap = st.approval
        final = st.version(ap.get("version_id")) if ap.get("approved") else st.current_version()
        final_head = "Final approved" if ap.get("approved") else "Final approved (current — not approved yet)"
        rows = []
        for sid in st.string_ids():
            rows.append([f"<code>{esc(sid)}</code>", esc_br(st.source_text(sid)),
                         esc_br(base.translations.get(sid, "—") if base else "—"),
                         esc_br(agent_v.translations.get(sid, "—") if agent_v else "—"),
                         esc_br(final.translations.get(sid, "—") if final else "—")])
        w["summary_table"].value = table(["Id", "Source", "Baseline", "Agent-reviewed", final_head], rows)
        dec = st.latest_decisions()
        frows = []
        for f in st.findings:
            d = dec.get(f.finding_id)
            frows.append([esc(f.finding_id), f"<code>{esc(f.string_id)}</code>", esc(f.issue),
                          esc(f.suggestion), esc(ACTION_TEXT.get(d.action, d.action) if d else "No decision"),
                          esc(d.human_text or "") if d else "", esc(d.comment or "") if d else "",
                          esc(("Agreed" if d.agrees_with_reviewer else "Overrode") if d else "—")])
        w["summary_findings"].value = (table(["Finding", "String", "Issue", "Suggestion", "Decision",
                                              "Human text", "Comment", "Agreed / overrode"], frows)
                                       if frows else "<i>No findings.</i>")
        w["summary_validation"].value = self._validation_html()
        w["summary_history"].value = self.w["history_table"].value
        parts = []
        try:
            prompts = exports.build_agent_settings(st, self.challenge)["prompts"]
        except Exception:  # noqa: BLE001
            prompts = {}
        for role in ("translator", "reviewer"):
            cfg = st.agents.get(role, {})
            parts.append(f"<p><b>{esc(role.title())} instructions: default → current</b></p>"
                         + exports.prompt_diff_html(cfg.get("default_instructions", ""), cfg.get("instructions", "")))
            pair = prompts.get(role) or {}
            if pair.get("initial") and pair.get("final"):
                parts.append(f"<p><b>{esc(role.title())}: first prompt sent → latest prompt sent</b></p>"
                             + exports.prompt_diff_html(pair["initial"]["user"], pair["final"]["user"]))
        w["prompt_evolution"].value = f"<div class='gls-diff'>{_DIFF_CSS}{''.join(parts)}</div>"

    # .................................................................. stuck box
    def _build_stuck(self) -> None:
        w = self.w
        w["btn_resume"] = _button("Resume my saved session", "success", width="280px", icon="refresh")
        w["btn_resume"].on_click(lambda b: self._action(b, self._resume_saved, "msg_welcome"))
        w["resume_row"] = _hidden(widgets.HBox([w["btn_resume"]]))
        w["btn_stuck_resume"] = _button("Resume my saved session", "success", width="280px")
        w["btn_stuck_resume"].on_click(lambda b: self._action(b, self._resume_saved, "msg_stuck"))
        w["btn_stuck_download"] = _button("Download progress file", "", width="240px", icon="download")
        w["btn_stuck_download"].on_click(
            lambda b: self._action(b, lambda: self._download_progress("download_out_stuck"), "msg_stuck"))
        w["resume_upload"] = widgets.FileUpload(accept=".json", multiple=False, description="Choose file")
        w["btn_resume_file"] = _button("Resume from file", "info", icon="upload")
        w["btn_resume_file"].on_click(lambda b: self._action(b, self._resume_from_upload, "msg_stuck"))
        w["checkpoint"] = widgets.Dropdown(options=self._checkpoint_options(), description="Checkpoint:",
                                           style={"description_width": "initial"}, layout=_layout(width="520px"))
        w["btn_checkpoint"] = _button("Load this checkpoint", "warning")
        w["btn_checkpoint"].on_click(lambda b: self._action(b, self._load_checkpoint, "msg_stuck"))
        w["btn_reset"] = _button("Reset this mission", "danger", icon="trash")
        w["btn_reset"].on_click(lambda b: self._action(b, self._reset_mission, "msg_stuck"))
        w["btn_reset_confirm"] = _button("Yes, reset (a backup copy is kept)", "danger")
        w["btn_reset_confirm"].on_click(lambda b: self._action(b, lambda: self._reset_mission(True), "msg_stuck"))
        w["reset_confirm"] = _hidden(widgets.HBox([w["btn_reset_confirm"]]))
        w["stuck_box"] = widgets.VBox([
            _html("<h3 style='margin:4px 0'>🆘 If you get stuck</h3>" + box("plain", (
                "<b>Disconnected, same runtime?</b> Run the setup cell again, then click <b>Resume my saved "
                "session</b> (the autosave is still in this Colab runtime). "
                "<b>Runtime reset or deleted?</b> The autosave went with it: choose your downloaded "
                "progress file and click <b>Resume from file</b>. "
                "<b>Behind the class?</b> Load a catch-up checkpoint. <b>Changing computer?</b> Download the "
                "progress file and resume from it. Nobody ever needs to edit Python."))),
            widgets.HBox([w["btn_stuck_resume"], w["btn_stuck_download"]], layout=_layout(flex_flow="row wrap")),
            widgets.HBox([w["resume_upload"], w["btn_resume_file"]]),
            widgets.HBox([w["checkpoint"], w["btn_checkpoint"]], layout=_layout(flex_flow="row wrap")),
            widgets.HBox([w["btn_reset"], w["reset_confirm"]]), w["msg_stuck"], w["download_out_stuck"]],
            layout=_layout(border="2px dashed #b9770e", padding="6px 10px"))

    def _checkpoint_options(self):
        opts = []
        try:
            files = sorted(self.checkpoints_dir.glob("*.json"))
        except OSError:
            files = []
        for p in files:
            label = p.stem.replace("_", " ")
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                label = (data.get("ui_extras") or {}).get("checkpoint_label") or data.get("checkpoint_label") or label
            except (OSError, ValueError, AttributeError):
                pass
            opts.append((str(label), str(p)))
        return opts or [("(no checkpoints available)", "")]

    def _resume_saved(self) -> str:
        if not self.state_path.exists():
            raise StudioError("No saved session was found in this Colab session. Use “Resume from file” "
                              "if you downloaded a progress file.")
        msg = self._load_text(self.state_path.read_text(encoding="utf-8"), "your saved session")
        self._saved_session_handled = True
        _hidden(self.w["resume_row"])
        return msg

    def _resume_from_upload(self) -> str:
        files = compat.uploaded_files(self.w["resume_upload"].value)
        if not files:
            raise StudioError("Choose your progress file (.json) first with “Choose file”.")
        name, data = files[0]
        if len(data) > 5_000_000:
            raise StudioError("That file is too large to be a progress file.")
        self._backup_unhandled_session()
        msg = self._load_text(data, f"“{name}”")
        compat.clear_upload(self.w["resume_upload"])
        return msg

    def resume_from_bytes(self, data: bytes, name: str = "progress file") -> str:
        """Same as the “Resume from file” button (used by tests and the bundle fallback)."""
        self._backup_unhandled_session()
        return self._load_text(data, name)

    def _load_checkpoint(self) -> str:
        path = self.w["checkpoint"].value
        if not path:
            raise StudioError("No checkpoint is available. Ask your instructor.")
        if self.state is not None:
            self._save_copy(f"backup_{self.state.challenge_id}")
        self._backup_unhandled_session()
        msg = self._load_text(Path(path).read_text(encoding="utf-8"), "the catch-up checkpoint")
        return msg + " Your previous work (if any) was saved as a backup in the exports folder."

    def _reset_mission(self, confirmed: bool = False) -> str:
        st = self._require_project()
        if not confirmed:
            _hidden(self.w["reset_confirm"], False)
            return Warn("⚠️ This clears all versions and decisions for this mission. A backup copy is "
                        "kept. Click “Yes, reset” to continue.")
        _hidden(self.w["reset_confirm"])
        mission = "custom" if st.challenge_id == "custom" else st.mission
        self._suspend = True
        try:
            if mission in [v for _, v in self.w["mission"].options]:
                self.w["mission"].value = mission
            self.w["locale"].value = st.locale
        finally:
            self._suspend = False
        return self._start_mission(confirmed=True)

    # ------------------------------------------------------------------ refresh
    def refresh(self) -> None:
        self._refresh_status()
        self._refresh_progress()
        self._refresh_welcome()
        self._refresh_configure()
        self._refresh_run()
        self._refresh_director()
        self._refresh_export()

    def _refresh_status(self) -> None:
        st = self.state
        if self.provider is None:
            mode = badge("NOT CONNECTED — go to Section 1", "#7f8c8d")
        elif self._is_live():
            mode = badge(f"LIVE · {self._provider_display()} / {self.translator_model}", "#1e8449")
            if self.reviewer_model and self.reviewer_model != self.translator_model:
                mode += badge(f"reviewer: {self.reviewer_model}", "#1e8449")
        else:
            mode = badge(REPLAY_BADGE, "#d35400")
        parts = [mode, f"Live requests this session: <b>{esc(self.meter.requests)} / "
                       f"{esc(self.meter.request_cap)}</b>"]
        if st is not None:
            u = st.usage
            if u.get("simulated_requests"):
                parts.append(f"simulated: {esc(u.get('simulated_requests'))}")
            if u.get("input_tokens") or u.get("output_tokens"):
                parts.append(f"Tokens: {esc(u.get('input_tokens', 0))} in / {esc(u.get('output_tokens', 0))} out")
            if self.catalog.get("pricing_verified") and u.get("est_cost_usd") is not None:
                parts.append(f"Est. cost: ${u['est_cost_usd']:.4f}")
            parts.append(f"Mission: <b>{esc(self._challenge_title())}</b>")
            if self._live_hint:
                parts.append("⚠️ this project was made in Live Mode — load your key again in Section 1 "
                             "to continue live, or click “Switch to Replay”")
        else:
            parts.append("Mission: <i>not started</i>")
        parts.append(f"Role: <b>{esc(self.role)}</b>")
        parts.append(f"Autosaved: {esc(self.autosaved_at)}" if self.autosaved_at else "Not saved yet")
        if self.autosave_problem:
            parts.append(f"⚠️ <b>Autosave failed:</b> {esc(self.autosave_problem)}")
        self.w["status_html"].value = ("<div style='font-size:13px;color:#1f2933'>"
                                       + " · ".join(parts) + "</div>")
        replay_on = self.provider is not None and not self._is_live()
        b = self.w["btn_status_replay"]
        b.description = "✓ Replay Mode on" if replay_on else "Switch to Replay"
        b.button_style = "" if replay_on else "warning"
        b.icon = "" if replay_on else "play"
        b.tooltip = ("You are in Replay Mode (prepared outputs)" if replay_on
                     else "Use prepared outputs instead of a live AI")
        b.disabled = replay_on
        self._refresh_role_labels()

    def progress_steps(self) -> list[bool]:
        st = self.state
        has_tr = bool(st and any(v.kind == "translator" for v in st.versions))
        reviewed = bool(st and (st.findings or any(s.agent == "reviewer" for s in st.prompt_snapshots)))
        approved = bool(st and (st.approval.get("approved") or st.stage == "EXPORTED"))
        return [self.provider is not None, st is not None,
                bool(st and (self.extras.get("configured") or has_tr)),
                has_tr and reviewed, approved,
                bool(st and (self.extras.get("exported") or st.stage == "EXPORTED"))]

    def _refresh_progress(self) -> None:
        cells = []
        for n, (title, done) in enumerate(zip(STEP_TITLES, self.progress_steps()), 1):
            colour = "#1e8449" if done else "#616e7c"
            cells.append(f"<span style='color:{colour};margin-right:10px;white-space:nowrap'>"
                         f"{'✅' if done else '⬜'} {n}. {esc(title)}</span>")
        self.w["progress"].value = f"<div style='font-size:13px;margin:2px 0 6px 0'>{''.join(cells)}</div>"

    def _refresh_welcome(self) -> None:
        saved = self.state_path.exists() and not self._saved_session_handled and self.state is None
        _hidden(self.w["resume_row"], not saved)
        info = ""
        if saved:
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                info = (f" A saved session was found (mission “{esc(data.get('challenge_id'))}”, last "
                        f"updated {esc(data.get('updated_at'))}). Click <b>Resume my saved session</b> "
                        "to continue where you left off.")
            except (OSError, ValueError, AttributeError):
                info = " A saved session file was found but could not be read."
        mode = ("Replay Mode (prepared outputs)" if self.provider is not None and not self._is_live()
                else ("live AI" if self.provider is not None else "not connected"))
        self.w["welcome_html"].value = box("ok", f"✅ <b>The studio is ready</b> — currently: {esc(mode)}."
                                           + info + " Scroll down to Section 1.")
