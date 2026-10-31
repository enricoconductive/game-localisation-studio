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
import traitlets

from . import agents, exports, importers, project_state as ps, providers, validation
from . import ui_compat as compat
from .project_state import StudioError

GAME_URL = "https://enricoconductive.github.io/game-localisation-studio/game/"
REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES = ("AI Director", "Quality Evaluator")
PROVIDER_CHOICES = [("Claude (Anthropic)", "anthropic"), ("HKBU GenAI", "hkbu"),
                    ("Hugging Face", "huggingface"), ("Replay Mode (simulated, no key)", "replay")]
LOCALE_CHOICES = [("British (en-GB)", "en-GB"), ("American (en-US)", "en-US"),
                  ("International (en)", "en")]
MISSION_ORDER = ("intro", "voice", "pun", "ui")
REFLECTION_QUESTION = ("What did your agents get wrong, what did you change, and why was the "
                       "final result better?")
REPLAY_BADGE = "REPLAY MODE — simulated outputs, not live AI"
REPLAY_LOCALE_NOTE = "Replay text is British English; live agents follow your choice."
DOWNLOAD_REMINDER = "💾 Click “Download progress” (status bar): autosave is lost if Colab resets."
PLAY_TEXT = "▶ Play my translation in the game"
# One layout grid for every panel: each labelled input has the same label width, so all
# inputs start at the same x; buttons in a row share one width and height.
LABEL_W = "170px"
INPUT_W = "600px"      # dropdowns and short inputs (max width)
BTN_W = "240px"
BTN_H = "34px"
_LABEL_STYLE = {"description_width": LABEL_W}
# Short help under each Section 3 control (the engine's help text is longer).
SHORT_HELP = {"strategy": "How close to the source.",
              "cultural_adaptation": "Keep or adapt Hong Kong references.",
              "register": "Tone of the English.",
              "voice_strength": "How distinct each voice is.",
              "glossary_strictness": "How strictly to follow the glossary.",
              "strictness": "Smallest problem it reports.",
              "max_findings": "Most suggestions per round."}
# "override" is no longer a button ("Use my wording" records accept_edited); kept for saved projects.
ACTION_TEXT = {"accept": "Accepted", "reject": "Rejected", "accept_edited": "Used my wording",
               "override": "Overrode with own wording", "direct_edit": "Edited directly",
               "add_rule": "Added a rule", "send_revision": "Sent feedback to translator",
               "restore_version": "Restored a version", "approve_final": "Approved final translation",
               "revoke_approval": "Revoked approval"}
STEP_TITLES = ("Connect", "Mission", "Configure", "Run", "Director", "Export")
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
.studio-card,.studio-card .widget-box,.studio-card .widget-container{overflow:visible !important}
.studio-card .studio-scroll{overflow:auto !important}
.studio-scroll{border:1px solid #e4e7eb;border-radius:4px}
.studio-scroll>*{flex-shrink:0 !important}
.studio-card .studio-acc-head{justify-content:flex-start;text-align:left;font-weight:600}
.studio-card .studio-h3{margin:2px 0 8px 0;font-size:18px}
.studio-card .studio-h4{margin:12px 0 4px 0;font-size:15px}
.studio-card .studio-row{margin:4px 0}
.studio-card .studio-row .jupyter-button{margin:0 8px 0 0}
.studio-card .studio-grid{margin:4px 0}
.studio-card .widget-dropdown,.studio-card .widget-text,.studio-card .widget-textarea,
.studio-card .widget-password,.studio-card .widget-toggle-buttons,.studio-card .widget-checkbox,
.studio-card .widget-slider{margin:3px 0}
.studio-play{display:inline-block;background:#1e8449;color:#ffffff !important;font-size:17px;
 font-weight:bold;padding:10px 22px;border-radius:6px;text-decoration:none !important;margin:4px 0}
.studio-play:hover{background:#196f3d}
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


def _button(text, style="", width=BTN_W, icon="") -> widgets.Button:
    return widgets.Button(description=text, button_style=style, icon=icon, tooltip=text,
                          layout=_layout(width=width, height=BTN_H))


def _row(*children, width=None) -> widgets.HBox:
    """One row of buttons (or a control plus buttons), vertically centred. ``width`` gives
    every button in the row the same width."""
    if width:
        for c in children:
            if isinstance(c, widgets.Button):
                c.layout.width = width
    r = widgets.HBox(list(children), layout=_layout(flex_flow="row wrap", align_items="center",
                                                    width="100%"))
    r.add_class("studio-row")
    return r


def _html(value="") -> widgets.HTML:
    return widgets.HTML(value=value, layout=_layout(width="100%"))


def _h3(text) -> widgets.HTML:
    return _html(f"<h3 class='studio-h3'>{esc(text)}</h3>")


def _h4(text) -> widgets.HTML:
    return _html(f"<h4 class='studio-h4'>{esc(text)}</h4>")


def _note_html(inner_html) -> str:
    """One grey line of guidance (``inner_html`` is already escaped)."""
    return f"<div style='color:#3e4c59;font-size:13px;margin:2px 0'>{inner_html}</div>"


def _note(inner_html) -> widgets.HTML:
    return _html(_note_html(inner_html))


def _textarea(value="", rows=4, placeholder="", label=None) -> widgets.Textarea:
    kw = {"description": label, "style": dict(_LABEL_STYLE)} if label else {}
    return widgets.Textarea(value=value, rows=rows, placeholder=placeholder,
                            continuous_update=False, layout=_layout(width="100%"), **kw)


def _labelled(label, widget, width="100%") -> widgets.HBox:
    """``widget`` (e.g. ToggleButtons) behind a label as wide as every other input label.
    ToggleButtons' own description sits above the buttons in ipywidgets 8, so it is not used."""
    lab = widgets.HTML(f"<div style='text-align:right;white-space:nowrap'>{esc(label)}</div>",
                       layout=_layout(width=LABEL_W, min_width=LABEL_W, margin="0 4px 0 2px"))
    return widgets.HBox([lab, widget], layout=_layout(width=width, align_items="center"))


def _dropdown(options, label, value=None, width=INPUT_W) -> widgets.Dropdown:
    kw = {} if value is None else {"value": value}
    return widgets.Dropdown(options=options, description=label, style=dict(_LABEL_STYLE),
                            layout=_layout(width="100%", max_width=width), **kw)


def _text(label, placeholder="", full=True) -> widgets.Text:
    return widgets.Text(value="", placeholder=placeholder, description=label,
                        style=dict(_LABEL_STYLE),
                        layout=_layout(width="100%", max_width=None if full else INPUT_W))


def _grid(children, min_col="240px") -> widgets.GridBox:
    """Equal-width columns (three on a normal screen, fewer on a narrow one)."""
    g = widgets.GridBox(list(children), layout=_layout(
        width="100%", grid_template_columns=f"repeat(auto-fill, minmax({min_col}, 1fr))",
        grid_gap="4px 16px"))
    g.add_class("studio-grid")
    return g


def _scroll(child, max_height="400px") -> widgets.Box:
    """``child`` in a box of bounded height that scrolls, so long results do not make the
    Colab output frame jump (the buttons above stay in view)."""
    b = widgets.Box([child], layout=_layout(max_height=max_height, overflow="auto", width="100%",
                                            flex_flow="column"))
    b.add_class("studio-scroll")
    return b


# Colab's widget manager (ipywidgets 7.7.1, tested 2026-10-28) renders neither widgets.Tab nor
# widgets.Accordion: the panels never appear. These two stand-ins use only buttons and boxes,
# and keep the `selected_index` API the rest of this module uses.

class _Accordion(widgets.VBox):
    """``[(title, widget)]`` as click-to-open panels; at most one open (``selected_index``)."""
    selected_index = traitlets.Int(None, allow_none=True)

    def __init__(self, pairs, open_index=None):
        self._titles = [t for t, _ in pairs]
        self._bodies = [w for _, w in pairs]
        self._heads = []
        rows = []
        for i, title in enumerate(self._titles):
            head = widgets.Button(layout=_layout(width="100%"))
            head.add_class("studio-acc-head")
            head.on_click(lambda _b, i=i: setattr(self, "selected_index",
                                                  None if self.selected_index == i else i))
            self._heads.append(head)
            rows += [head, self._bodies[i]]
        super().__init__(rows, layout=_layout(width="100%"))
        self.observe(lambda _c: self._sync(), names="selected_index")
        self.selected_index = open_index
        self._sync()

    def _sync(self):
        for i, (head, body) in enumerate(zip(self._heads, self._bodies)):
            is_open = i == self.selected_index
            head.description = ("▾ " if is_open else "▸ ") + self._titles[i]
            _hidden(body, not is_open)


class _Tabs(widgets.VBox):
    """``[(title, widget)]`` as a row of tab buttons above one visible panel."""
    selected_index = traitlets.Int(0)

    def __init__(self, pairs):
        self._bodies = [w for _, w in pairs]
        self._bar = widgets.ToggleButtons(options=[(t, i) for i, (t, _) in enumerate(pairs)], value=0,
                                          style={"button_width": "auto"})
        self._bar.add_class("studio-tabbar")
        self._bar.observe(lambda c: setattr(self, "selected_index", c["new"]), names="value")
        super().__init__([self._bar, *self._bodies], layout=_layout(width="100%"))
        self.observe(lambda _c: self._sync(), names="selected_index")
        self._sync()

    def _sync(self):
        self._bar.value = self.selected_index
        for i, body in enumerate(self._bodies):
            _hidden(body, i != self.selected_index)


def _accordion(pairs, open_index=None) -> _Accordion:
    return _Accordion(pairs, open_index)


def _tabs(pairs) -> _Tabs:
    return _Tabs(pairs)


def _card(*children) -> widgets.VBox:
    """A light card with dark text: readable in Colab's light and dark themes."""
    v = widgets.VBox(list(children), layout=_layout(width="100%", padding="8px 12px"))
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
                raise StudioError("Upload your own file first (below the mission list).")
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
            suffix = " — start here" if mid == "intro" else ""
            opts.append((f"{title}{suffix}", mid))
        if self.custom_challenge:
            opts.append((f"Your file: {self.custom_challenge.get('title', 'custom')}", "custom"))
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
                text += "<br><b>⚠️ Approval revoked</b> — approve again (Section 5 → e · Approve)."
                kind = "warn"
            msg.value = box(kind, text)
        except Exception as e:  # noqa: BLE001 - every error becomes a friendly message
            user_message = getattr(e, "user_message", None)
            if isinstance(e, (StudioError, providers.ProviderError, importers.ImportRejected)) and user_message:
                msg.value = box("error", "❌ " + esc_br(self._mask(user_message)))
            else:
                saved = self._try_autosave()
                details = esc(self._mask(traceback.format_exc()[-3000:]))
                msg.value = box("error", "❌ This step did not finish. "
                                + ("Your work is saved." if saved else "Your earlier work is kept.")
                                + " Try again, or see “If you get stuck”."
                                + f"<details><summary>Details (for your instructor)</summary>"
                                  f"<pre style='white-space:pre-wrap'>{details}</pre></details>")
        finally:
            for b in buttons:
                b.disabled = False
            self._busy_msg = None
            if not self._try_autosave():
                msg.value += box("warn", "Autosave failed: "
                                 + esc(self.autosave_problem or "unknown reason.")
                                 + " Fix it, or click “Download progress”.")
            try:
                self.refresh()
            except Exception:  # noqa: BLE001 - never leave the UI stuck
                msg.value += box("warn", "Display not refreshed: run this section's cell again.")

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
            raise StudioError("Start a mission first (Section 2).")
        return self.state

    def _require_provider(self):
        if self.provider is None:
            raise StudioError("Connect first (Section 1), or click “Use Replay instead”.")
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
                label += " (set up by your instructor, unverified)" if not m.get("verified") else ""
            elif not m.get("verified"):
                label += " (unverified)"
            opts.append((label, m["id"]))
        if not opts and name == "hkbu":
            opts = [("set up by your instructor, unverified", "")]
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
        return "✅ Replay Mode is on: simulated outputs, free, no key."

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
                                          tooltips=[f"Record decisions as {r}" for r in ROLES],
                                          style={"button_width": "150px"},
                                          layout=_layout(width="auto", margin="0 16px 0 0"))
        w["role"].observe(self._on_role, names="value")
        w["btn_status_replay"] = _button("Switch to Replay", "warning", width="180px", icon="play")
        w["btn_status_replay"].on_click(lambda b: self._action(b, self.connect_replay, "msg_status"))
        w["btn_status_download"] = _button("Download progress", "", width="180px", icon="download")
        w["btn_status_download"].on_click(
            lambda b: self._action(b, lambda: self._download_progress("download_out"), "msg_status"))
        w["status_bar"] = widgets.VBox(
            [w["style"], w["status_html"],
             _row(_labelled("Who is deciding:", w["role"], "auto"), w["btn_status_download"],
                  w["btn_status_replay"]),
             w["msg_status"]],
            layout=_layout(border="1px solid #d9e2ec", padding="6px 0", margin="0 0 8px 0"))
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
        w["provider"] = _dropdown(PROVIDER_CHOICES, "Provider:", "replay")
        w["model"] = _dropdown(self._models_for("replay"), "Model:")
        w["provider"].observe(self._on_provider_change, names="value")
        w["key_help"] = _html()
        w["btn_load_key"] = _button("Load my key", "primary", icon="key")
        w["btn_load_key"].on_click(lambda b: self._action(b, self._load_key, "msg_connect",
                                                          "Looking for your key in Colab Secrets…"))
        w["key_box"] = _hidden(widgets.Password(
            value="", description="Key:", placeholder="…or paste your key here (hidden)",
            style=dict(_LABEL_STYLE), layout=_layout(width="100%", max_width=INPUT_W)))
        w["btn_test"] = _button("Test connection", "info", icon="plug")
        w["btn_test"].on_click(lambda b: self._action(b, self._test_connection, "msg_connect",
                                                      "Testing the connection (1 small request)…"))
        w["btn_use_replay"] = _button("Use Replay instead", "warning", icon="play")
        w["btn_use_replay"].on_click(lambda b: self._action(b, self.connect_replay, "msg_connect"))
        w["adv_reviewer"] = widgets.Checkbox(value=False, indent=True, style=dict(_LABEL_STYLE),
                                             description="Advanced: separate reviewer model",
                                             layout=_layout(width="100%"))
        w["reviewer_model"] = _hidden(_dropdown(self._models_for("replay"), "Reviewer model:"))
        w["adv_reviewer"].observe(lambda c: (_hidden(w["reviewer_model"], not c["new"]),
                                             self._on_model_change(None)), names="value")
        w["model"].observe(self._on_model_change, names="value")
        w["reviewer_model"].observe(self._on_model_change, names="value")
        w["connect_state"] = _html()
        self._refresh_key_help()
        return widgets.VBox([
            _h3("1 · Connect (≈5 min)"),
            w["provider"], w["model"], w["adv_reviewer"], w["reviewer_model"], w["key_help"], w["key_box"],
            _row(w["btn_load_key"], w["btn_test"], w["btn_use_replay"]), w["msg_connect"],
            w["connect_state"]])

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
            self.w["key_help"].value = _note_html("Replay needs no key or internet.")
            return
        secret = esc(cfg.get("secret_name") or "API_KEY")
        extra = ""
        if name == "hkbu" and not cfg.get("verified"):
            extra = "<br>HKBU GenAI: set up by your instructor, <b>unverified</b>."
        elif name == "hkbu":
            extra = "<br>HKBU GenAI: set up by your instructor."
        elif not cfg.get("verified"):
            extra = "<br>This provider is <b>unverified</b> for this course."
        self.w["key_help"].value = box("info", (
            f"<b>Colab Secrets:</b> 🔑 (left sidebar) → <b>Add new secret</b> → Name "
            f"<code>{secret}</code> → paste key → <b>Notebook access</b> on → <b>Load my key</b>.{extra}"))

    def _load_key(self) -> str:
        name = self.w["provider"].value
        if name == "replay":
            return self.connect_replay()
        model = self.w["model"].value
        if name == "hkbu" and not (self.provider_config.get("hkbu", {}).get("base_url") or "").strip():
            raise providers._error("not_configured", "HKBU GenAI")
        if not model:
            raise StudioError("No model set up for this provider. Ask your instructor, or use Replay.")
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
                raise StudioError(e.user_message + " Or paste it in the “Key:” box and click "
                                  "“Load my key” again.") from None
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
        return f"🔑 Key loaded for {self._provider_display()} (hidden). Next: “Test connection”."

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
        w["mission"] = _dropdown(opts, "Mission:", "intro" if "intro" in ids else ids[0])
        w["mission"].observe(lambda c: self._refresh_mission_preview(), names="value")
        w["locale"] = widgets.ToggleButtons(options=LOCALE_CHOICES, value="en-GB",
                                            style={"button_width": "200px"})
        w["team"] = _text("Team (optional):", "e.g. Team Lantern (no real names)", full=False)
        w["mission_brief"] = _html()
        w["source_table"] = _html()
        w["ctx_scene"], w["ctx_chars"], w["ctx_meaning"], w["ctx_gloss"] = _html(), _html(), _html(), _html()
        w["context_acc"] = _accordion([
            ("Scene", w["ctx_scene"]), ("Characters", _scroll(w["ctx_chars"], "360px")),
            ("Intended meanings", _scroll(w["ctx_meaning"], "360px")),
            ("Glossary", _scroll(w["ctx_gloss"], "360px"))])
        w["upload"] = widgets.FileUpload(accept=".txt,.csv,.json", multiple=False,
                                         description="Choose file")
        w["btn_use_upload"] = _button("Use this file", "info", icon="upload")
        w["btn_use_upload"].on_click(lambda b: self._action(b, self._use_upload, "msg_mission",
                                                            "Reading your file…"))
        w["btn_start"] = _button("Start this mission", "success", icon="flag")
        w["btn_start"].on_click(lambda b: self._action(b, self._start_mission, "msg_mission"))
        w["btn_start_confirm"] = _button("Yes, start again (backup kept)", "danger")
        w["btn_start_confirm"].on_click(
            lambda b: self._action(b, lambda: self._start_mission(confirmed=True), "msg_mission"))
        w["btn_start_cancel"] = _button("Cancel")
        w["btn_start_cancel"].on_click(lambda b: (_hidden(w["start_confirm"]),
                                                  setattr(w["msg_mission"], "value",
                                                          box("info", "Nothing changed."))))
        w["start_confirm"] = _hidden(_row(w["btn_start_confirm"], w["btn_start_cancel"], width="260px"))
        upload_help = _note(
            "<code>.txt</code> (one string per line), <code>.csv</code> (a <code>source</code> column) "
            f"or <code>.json</code>. Max {importers.MAX_BYTES // 1024} KB, {importers.MAX_STRINGS} "
            "strings. <b>Not playable in the game.</b>")
        w["upload"].layout = _layout(width=BTN_W, height=BTN_H)
        self._refresh_mission_preview()
        w["upload_acc"] = _accordion([("Optional: upload your own text",
                                       widgets.VBox([upload_help, _row(w["upload"], w["btn_use_upload"])]))])
        return widgets.VBox([
            _h3("2 · Choose your mission (≈5 min)"),
            w["mission"], _labelled("English variant:", w["locale"]), w["team"], w["mission_brief"],
            _h4("Source strings"), _scroll(w["source_table"], "360px"),
            w["context_acc"], w["upload_acc"],
            _row(w["btn_start"]), w["start_confirm"], w["msg_mission"]])

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
            when = f"≈{est} min, including setup"
        elif est:
            when = f"≈{est} min — already connected? Skip Section 1"
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
            raise StudioError("Click “Choose file” first.")
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
        msg = (f"Loaded {len(ch['strings'])} string(s). Check the table, then “Start this mission”. "
               "Custom material cannot be played in the game.")
        if ch.get("import_warnings"):
            msg += f" {len(ch['import_warnings'])} warning(s) above."
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
                what = ("This mission has work." if has_progress else
                        "A saved session exists (“Resume my saved session”).")
                return Warn(f"⚠️ {what} Starting replaces it (backup kept). Are you sure?")
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
               f"{state.locale}). Next: Section 3.")
        return msg + (" " + REPLAY_LOCALE_NOTE if self._replay_locale_note() else "")

    # .................................................................. 3 configure
    def _build_configure(self) -> widgets.VBox:
        w = self.w
        w["preset_buttons"] = {}
        pbtns = []
        for name in compat.PRESET_ORDER:
            b = _button(compat.preset_label(name), "")
            b.on_click(lambda btn, n=name: self._action(btn, lambda: self._apply_preset(n), "msg_config"))
            w["preset_buttons"][name] = b
            pbtns.append(b)
        w["preset_info"] = _html()
        w["t_settings"] = {}
        t_cells = []
        for spec in agents.TRANSLATOR_SETTINGS_SPEC:
            ctrl, cell = self._setting_control(spec)
            w["t_settings"][spec["key"]] = ctrl
            ctrl.observe(self._on_translator_change, names="value")
            t_cells.append(cell)
        w["t_instructions"] = _textarea(rows=8)
        w["t_instructions"].observe(self._on_translator_change, names="value")
        w["btn_t_reset"] = _button("Reset to preset", "", icon="undo")
        w["btn_t_reset"].on_click(lambda b: self._action(b, self._reset_translator, "msg_config"))
        w["replay_notice"] = _html()
        w["r_settings"] = {}
        r_checks, r_sliders = [], []
        for spec in agents.REVIEWER_SETTINGS_SPEC:
            ctrl, cell = self._setting_control(spec)
            w["r_settings"][spec["key"]] = ctrl
            ctrl.observe(self._on_reviewer_change, names="value")
            (r_checks if spec["kind"] == "checkbox" else r_sliders).append(cell)
        w["r_instructions"] = _textarea(rows=6)
        w["r_instructions"].observe(self._on_reviewer_change, names="value")
        w["btn_r_reset"] = _button("Reset reviewer", "", icon="undo")
        w["btn_r_reset"].on_click(lambda b: self._action(b, self._reset_reviewer, "msg_config"))
        w["preview_step"] = _dropdown(
            [("Translator", "translator"), ("Baseline", "baseline"),
             ("Reviewer", "reviewer"), ("Revision", "revision")],
            "Prompt for:", "translator", width="460px")
        w["btn_preview"] = _button("Show full prompt", "info", icon="eye")
        w["btn_preview"].on_click(lambda b: self._action(b, self._show_preview, "msg_preview"))
        w["preview_info"] = _html()
        w["preview_system"] = _textarea(rows=3)
        w["preview_user"] = _textarea(rows=10)
        w["preview_box"] = widgets.VBox([
            w["preview_info"], _html("<b>System message</b>"), w["preview_system"],
            _html("<b>User message</b> (a copy: edit the instructions above)"), w["preview_user"]])
        w["preview_acc"] = _hidden(_accordion([("Full prompt", w["preview_box"])]))
        examples = _html(table(["✅ Good", "❌ Poor"], [[
            "“Granny Wong: short, sharp sentences; an old proverb where the source has one; never slang.”",
            "“Make it good.” — nothing the agent can check."]]))
        return widgets.VBox([
            _h3("3 · Configure your agents (≈15 min)"),
            _h4("Translator"),
            _row(*pbtns, width="180px"), w["msg_config"], w["preset_info"],
            _grid(t_cells),
            _html("<b>Translator instructions</b>"), w["t_instructions"],
            _row(w["btn_t_reset"]), w["replay_notice"],
            _h4("Reviewer"),
            _grid(r_checks), _grid(r_sliders),
            _html("<b>Reviewer instructions</b>"), w["r_instructions"], _row(w["btn_r_reset"]),
            _accordion([("Good vs poor instructions", examples)]),
            _h4("Preview the prompt"),
            _row(w["preview_step"], w["btn_preview"]),
            w["msg_preview"], w["preview_acc"]])

    def _setting_control(self, spec):
        kind = spec["kind"]
        levels = spec.get("levels") or {}
        desc = _html()
        if kind == "slider":
            lo, hi = spec["range"]
            ctrl = widgets.IntSlider(value=spec["default"], min=lo, max=hi, step=1,
                                     continuous_update=False, layout=_layout(width="100%"))
        elif kind == "dropdown":
            ctrl = widgets.Dropdown(options=[(str(o).replace("_", " "), o) for o in spec["options"]],
                                    value=spec["default"], layout=_layout(width="100%"))
        else:
            ctrl = widgets.Checkbox(value=bool(spec["default"]), indent=False, description=spec["label"],
                                    layout=_layout(width="100%"))

        def update(_=None):
            # sliders show the short name of the chosen level ("balanced"), not the full text
            text = (levels.get(str(ctrl.value)) or "").split(" — ")[0] if kind == "slider" else ""
            desc.value = (f"<span style='color:#3e4c59;font-size:12px'>"
                          f"{esc(SHORT_HELP.get(spec['key'], spec.get('help', '')))}"
                          + (f" → <i>{esc(text)}</i>" if text else "") + "</span>")
        ctrl.observe(update, names="value")
        update()
        if kind == "checkbox":
            return ctrl, widgets.VBox([ctrl], layout=_layout(width="100%"))
        return ctrl, widgets.VBox([_html(f"<b>{esc(spec['label'])}</b>"), ctrl, desc],
                                  layout=_layout(width="100%"))

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
                f"The {role} instructions seem to contain an API key. Remove it.")
            if problem:
                raise StudioError(problem)
            if len(text) > 8000:
                raise StudioError(f"The {role} instructions are too long (max 8000 characters).")
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
            self.w["msg_config"].value = box("ok", f"Saved {esc(role)} changes.")
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
        msg = f"{compat.preset_label(name)} preset applied: {p.get('description', '')}"
        if lost:
            msg += " Your edits were replaced."
        return msg

    def _reset_translator(self) -> str:
        name = self._translator_cfg().get("preset") or "balanced"
        return self._apply_preset(name)

    def _reset_reviewer(self) -> str:
        st = self._require_project()
        st.agents["reviewer"] = agents.default_agent_config("reviewer")
        st.log("agent_config", "reviewer reset to default")
        self._load_config_widgets()
        return "Reviewer reset."

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
                    f"Replay: {reqs} simulated request(s), free.")
        self.w["preview_info"].value = box("info", (
            f"<b>{esc(dict((v, k) for k, v in self.w['preview_step'].options)[step])}</b> · "
            f"{esc(req_text)}<br>{esc(p['temperature_note'])}"
            + ("<br>First batch shown; the others differ only in their strings."
               if reqs > 1 else "")))
        _hidden(self.w["preview_acc"], False)
        self.w["preview_acc"].selected_index = 0
        return f"Full prompt below ({len(p['user'])} characters)."

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
        steps = (("baseline", "1 · Baseline (one-shot)"), ("translator", "2 · Run translator"),
                 ("reviewer", "3 · Run reviewer"))
        rows = []
        for step, text in steps:
            b = _button(text, "primary")
            b.on_click(lambda btn, s=step: self._action(btn, lambda: self.run_step(s), "msg_run",
                                                        "Working… (0 requests so far)"))
            w[f"btn_{step}"] = b
            w[f"est_{step}"] = widgets.HTML(layout=_layout(width="auto"))
            rows.append(_row(b, w[f"est_{step}"]))
        w["results_table"] = _html()
        w["cmp_a"] = _dropdown([("—", "")], "Run A:")
        w["cmp_b"] = _dropdown([("—", "")], "Run B:")
        w["btn_compare"] = _button("Compare A and B", "info", icon="columns")
        w["btn_compare"].on_click(lambda b: self._action(b, self._compare_runs, "msg_run"))
        w["compare_out"] = _html()
        w["review_cards"] = _html()
        w["validation_summary"] = _html()
        # Results live in tabs of bounded height, so a long table does not push the run
        # buttons and the status bar out of the Colab output frame.
        w["run_tabs"] = _tabs([
            ("Results", _scroll(w["results_table"], "400px")),
            ("Compare runs", widgets.VBox([
                w["cmp_a"], w["cmp_b"], _row(w["btn_compare"]), _scroll(w["compare_out"], "360px")])),
            ("Findings", _scroll(w["review_cards"], "400px")),
            ("Technical checks", _scroll(w["validation_summary"], "400px"))])
        return widgets.VBox([_h3("4 · Run the agents (≈20 min)"), *rows, w["msg_run"], w["run_tabs"]])

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
            return self._with_partial(f"Baseline ready ({v.version_id}). Next: run the translator.",
                                      history_before)
        if step == "translator":
            v = agents.run_translator(st, wrapped, self.challenge)
            self._record_version(v, before, "translator", cfg)
            self.w["run_tabs"].selected_index = 1 if self._auto_compare(v) else 0
            extra = ""
            if not self._is_live() and cfg.get("edited"):
                extra = " " + compat.replay_variant_note(cfg)
            return self._with_partial(
                f"New version {v.version_id}: {v.label}. Change the prompt and run again to compare."
                + extra, history_before)
        if step == "reviewer":
            found = agents.run_reviewer(st, wrapped, self.challenge)
            self.w["run_tabs"].selected_index = 2
            return self._review_message(found)
        if step == "revision":
            v = agents.run_revision(st, wrapped, self.challenge, role=self.role)
            self._record_version(v, before, "reviser", cfg)
            return (f"Revision ready ({v.version_id}): accepted findings re-sent; your wording applied "
                    "directly.")
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
            return ("Review skipped: no string has changed since the last review. Edit or revise first.")
        if getattr(found, "all_dropped", False):
            return Warn(f"⚠️ The reviewer sent {found.received} finding(s), but none could be used "
                        f"({counts}). This does NOT mean the translation is fine: run it again, "
                        "or switch to Replay.")
        if not found:
            n = len(getattr(found, "reviewed_ids", ()) or ())
            msg = (f"The reviewer checked {n} string(s) and found no problems." if n else
                   "The reviewer found no problems.")
            return Warn(msg + f" Note: {counts}.") if counts else msg
        msg = f"The reviewer made {len(found)} suggestion(s): decide in Section 5."
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
        head = (f"<p style='margin:4px 0'><b>{changed} of {len(rows)} strings differ</b> · "
                f"A = {esc(self.version_label(a))} · B = {esc(self.version_label(b))}</p>")
        out = head + table(["String", "Source", f"A · {a.version_id}", f"B · {b.version_id}"], rows, styles)
        pa, pb = self._prompt_for_version(a), self._prompt_for_version(b)
        if pa is not None and pb is not None:
            sys_diff = ""
            if pa.system != pb.system:
                sys_diff = "<p><b>System message</b></p>" + exports.prompt_diff_html(pa.system, pb.system)
            out += ("<h4 style='margin:8px 0 2px 0'>Prompt changes (A → B)</h4>"
                    f"<div class='gls-diff'>{_DIFF_CSS}{sys_diff}"
                    + exports.prompt_diff_html(pa.user, pb.user) + "</div>")
        else:
            who = a if pa is None else b
            out += box("plain", f"{esc(who.version_id)} is human-written: no prompt to compare.")
        if not st.mode == "live" and any(self._version_meta(x).get("edited") for x in (a, b)):
            out += box("replay", esc(compat.replay_variant_note(st.agents["translator"])))
        out += box("info", "💬 <b>Discuss:</b> What in the prompt caused these differences?")
        return Safe(out)

    def _compare_runs(self) -> Safe:
        a, b = self.w["cmp_a"].value, self.w["cmp_b"].value
        if not a or not b:
            raise StudioError("Run the translator first, then pick two versions.")
        self.w["compare_out"].value = self.compare_html(a, b)
        self.w["run_tabs"].selected_index = 1
        return Safe("Comparison updated.")

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
                decision = badge("Undecided", "#7f8c8d")
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
            f"<div><i>Translation:</i> {esc_br(text)}</div>"
            f"<div><i>Issue:</i> {esc_br(f.issue)}</div>"
            f"<div><i>Reasoning:</i> {esc_br(f.reasoning)}</div>"
            f"<div><i>Suggestion:</i> <b>{esc_br(f.suggestion) or '—'}</b></div>"
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
            w["results_table"].value = box("plain", "No results yet: click “1 · Baseline”.")
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
                (f"<p style='margin:2px 0'>Latest: <b>{esc(latest_tr.label)}</b></p>"
                 if latest_tr else "")
                + (box("plain", esc(REPLAY_LOCALE_NOTE)) if self._replay_locale_note() else "")
                + table(["Id", "Source", "Baseline", label], rows))
        self._refresh_compare_options()
        if st.findings:
            last = max(f.round for f in st.findings)
            cards = "".join(self._finding_card_html(f) for f in st.findings if f.round == last)
            w["review_cards"].value = (f"<p style='margin:2px 0'>Review round {last} · decide in "
                                       "Section 5.</p>" + cards)
        else:
            w["review_cards"].value = box("plain", "No findings yet.")
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
        return f"<span style='margin-left:8px;color:#616e7c'>Replay: {n} simulated request(s), free.</span>"

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
                   f"<b>{esc(rep.summary())}</b> (automatic, not the reviewer)"
                   f"<ul style='margin:4px 0 0 18px'>{''.join(items)}</ul>")

    # .................................................................. 5 director
    def _build_director(self) -> widgets.VBox:
        w = self.w
        w["decide_status"] = _html()
        w["findings_box"] = widgets.VBox(layout=_layout(width="100%"))
        w["rule_kind"] = _dropdown([("Style", "style"), ("Glossary", "glossary")], "Rule type:", "style")
        w["rule_from"] = _dropdown([("(no finding)", "")], "From finding:")
        w["rule_text"] = _text("Rule:", "e.g. Kit always calls Granny Wong 'Granny'.")
        w["rule_src"] = _text("Source:", "glossary only", full=False)
        w["rule_tgt"] = _text("English:", "glossary only", full=False)
        w["btn_rule"] = _button("Add rule", "info", icon="plus")
        w["btn_rule"].on_click(lambda b: self._action(b, self._add_rule, "msg_director"))
        w["rules_list"] = _html()
        w["edit_grid"] = widgets.VBox(layout=_layout(width="100%"))
        w["edit_comment"] = _text("Comment:", "Why? (optional)")
        w["btn_save_edits"] = _button("Save edits as new version", "warning", width="260px", icon="save")
        w["btn_save_edits"].on_click(lambda b: self._action(b, self._save_edits, "msg_director"))
        w["max_cycles"] = _dropdown([("0 (no revision)", 0), ("1 (default)", 1), ("2", 2)],
                                    "Revision cycles:", 1, width="360px")
        w["max_cycles"].observe(self._on_max_cycles, names="value")
        w["revision_info"] = _html()
        w["btn_revision"] = _button("Send accepted feedback", "primary", icon="paper-plane")
        w["btn_revision"].on_click(lambda b: self._action(b, lambda: self.run_step("revision"),
                                                          "msg_director", "Working… (0 requests so far)"))
        w["btn_review2"] = _button("Review again (optional)", "")
        w["btn_review2"].on_click(lambda b: self._action(b, lambda: self.run_step("reviewer"),
                                                         "msg_director", "Working… (0 requests so far)"))
        w["history_table"] = _html()
        w["hist_pick"] = _dropdown([("—", "")], "Version:")
        w["btn_hist_compare"] = _button("Compare with current", "info")
        w["btn_hist_compare"].on_click(lambda b: self._action(b, self._history_compare, "msg_director"))
        w["btn_restore"] = _button("Restore version", "warning", icon="history")
        w["btn_restore"].on_click(lambda b: self._action(b, self._restore, "msg_director"))
        w["hist_compare_out"] = _html()
        w["decision_log"] = _html()
        w["approval_info"] = _html()
        w["btn_approve"] = _button("Approve final translation", "success", width="300px", icon="check")
        w["btn_approve"].on_click(lambda b: self._action(b, self._approve, "msg_director"))
        # Five tabs, worked left to right; every result message appears just below them.
        w["director_tabs"] = _tabs([
            ("a · Decide", widgets.VBox([w["decide_status"], _scroll(w["findings_box"], "420px")])),
            ("b · Rules", widgets.VBox([
                _note("Rules are added to future prompts (the model is not retrained)."),
                w["rule_kind"], w["rule_from"], w["rule_text"], w["rule_src"], w["rule_tgt"],
                _row(w["btn_rule"]), _scroll(w["rules_list"], "240px")])),
            ("c · Revise", widgets.VBox([
                w["max_cycles"], w["revision_info"],
                _row(w["btn_revision"], w["btn_review2"], width="360px")])),
            ("d · Final edits", widgets.VBox([
                w["edit_comment"], _row(w["btn_save_edits"]), _scroll(w["edit_grid"], "400px")])),
            ("e · Approve", widgets.VBox([_row(w["btn_approve"]), w["approval_info"]]))])
        w["history_acc"] = _accordion([("History and decision log", widgets.VBox([
            w["hist_pick"], _row(w["btn_hist_compare"], w["btn_restore"]),
            _scroll(w["history_table"], "200px"), _scroll(w["hist_compare_out"], "360px"),
            _h4("Decision log"), _scroll(w["decision_log"], "400px")]))])
        return widgets.VBox([
            _h3("5 · Human Director (≈25 min)"),
            w["director_tabs"], w["msg_director"], w["history_acc"]])

    def _card_widgets(self, f) -> dict:
        """One finding: Accept / Reject, or edit the suggestion and “Use my wording”."""
        st = self.state
        cur = st.current_version()
        start = f.suggestion or (cur.translations.get(f.string_id, "") if cur else "")
        cw = {"html": _html(),
              "edit": _textarea(start, rows=2),
              "comment": widgets.Text(placeholder="Comment: why? (optional, logged)",
                                      layout=_layout(width="100%"))}
        for action, text, style in (("accept", "Accept", "success"), ("reject", "Reject", "danger"),
                                    ("accept_edited", "Use my wording", "info")):
            b = _button(text, style, width="160px")
            b.on_click(lambda btn, a=action, fid=f.finding_id:
                       self._action(btn, lambda: self.decide(fid, a), "msg_director"))
            cw[f"btn_{action}"] = b
        cw["edit"].layout = _layout(flex="1 1 auto", width="auto", margin="0 8px 0 0")
        cw["box"] = widgets.VBox([
            cw["html"], _row(cw["btn_accept"], cw["btn_reject"]),
            widgets.HBox([cw["edit"], cw["btn_accept_edited"]],
                         layout=_layout(width="100%", align_items="center", margin="3px 0")),
            cw["comment"]],
            layout=_layout(border="1px solid #e4e7eb", padding="6px 8px", margin="4px 0"))
        return cw

    def decide(self, finding_id: str, action: str) -> str:
        """Record a decision. "accept_edited" and the older "override" both take the card's
        text box (projects saved before the two buttons were merged may hold "override")."""
        st = self._require_project()
        cw = self._finding_cards.get(finding_id) or {}
        human = cw["edit"].value if cw and action in ("accept_edited", "override") else None
        comment = cw["comment"].value if cw else ""
        d = ps.decide_finding(st, finding_id, action, self.role, human_text=human, comment=comment)
        if cw:
            cw["comment"].value = ""
        return (f"{d.decision_id}: {ACTION_TEXT[action]} — {finding_id} ({d.string_id}), as "
                f"{self.role}." + ("" if d.agrees_with_reviewer else " Disagreement recorded."))

    def _add_rule(self) -> str:
        st = self._require_project()
        r = ps.add_rule(st, self.w["rule_kind"].value, self.w["rule_text"].value, self.role,
                        source_term=self.w["rule_src"].value.strip() or None,
                        target_term=self.w["rule_tgt"].value.strip() or None,
                        from_finding=self.w["rule_from"].value or None)
        for k in ("rule_text", "rule_src", "rule_tgt"):
            self.w[k].value = ""
        return f"Rule {r.rule_id} added to future prompts."

    def _save_edits(self) -> str:
        st = self._require_project()
        cur = st.current_version()
        if cur is None:
            raise StudioError("Run the translator first.")
        edits = {sid: ta.value for sid, ta in self._grid.items() if ta.value != cur.translations.get(sid, "")}
        if not edits:
            raise StudioError("No string has changed.")
        v = ps.direct_edit(st, edits, self.role, comment=self.w["edit_comment"].value)
        self.w["edit_comment"].value = ""
        return f"Saved {len(edits)} edit(s) as version {v.version_id}."

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
        return Safe("Comparison shown under the version table.")

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
        return f"Restored {vid} as {v.version_id} (current)."

    def _approve(self) -> str:
        st = self._require_project()
        open_n = len(st.open_findings())
        ps.approve_final(st, self.role)
        msg = f"Approved {st.approval['version_id']} ({self.role}). Later changes revoke it. Next: Section 6."
        if open_n:
            msg += f" Note: {open_n} finding(s) had no decision."
        return msg + "\n" + DOWNLOAD_REMINDER

    def _refresh_director(self) -> None:
        w, st = self.w, self.state
        if st is None:
            w["decide_status"].value = box("plain", "Start a mission first (Section 2).")
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
        w["decide_status"].value = (_note_html(
            f"Deciding as <b>{esc(self.role)}</b> · {len(st.findings)} finding(s), "
            f"<b>{open_n} undecided</b>") if st.findings else
            box("plain", "No findings yet: run the reviewer (Section 4)."))
        rule_opts = [("(no finding)", "")] + [(f"{f.finding_id} · {f.string_id}", f.finding_id)
                                                            for f in st.findings]
        if list(w["rule_from"].options) != rule_opts:
            w["rule_from"].options = rule_opts
            w["rule_from"].value = ""
        rrows = [[esc(r.rule_id), esc(r.kind), esc(r.text), esc(r.source_term or ""),
                  esc(r.target_term or ""), esc(r.role)] for r in st.memory_rules]
        w["rules_list"].value = (table(["Rule", "Type", "Text", "Source", "English", "Added by"], rrows)
                                 if rrows else "<i>No rules yet.</i>")
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
        w["revision_info"].value = _note_html(
            f"Cycles used: <b>{done} of {max_c}</b> · re-sends <b>accepted</b> findings; your wording "
            f"is applied directly · {esc(req)}")
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
                                                + (f" <i>({esc('; '.join(cons))})</i>" if cons else "")), ta],
                                         layout=_layout(width="100%", margin="0 0 8px 0")))
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
        return (table(["#", "Who", "What", "String / finding", "Suggestion", "Human text",
                       "Agreed / overrode", "Comment"], rows) if rows else "<i>No decisions yet.</i>")

    def _approval_html(self) -> str:
        st = self.state
        ok, reasons = ps.can_export(st)
        ap = st.approval
        if ap.get("approved") and ok:
            return box("ok", f"✅ <b>{esc(ap['version_id'])}</b> approved by {esc(ap.get('role'))} at "
                             f"{esc(ap.get('approved_at'))}. Later changes revoke it.")
        rep = ps.validate_current(st) if st.current_version() else None
        blocking = [i.message for i in rep.critical] if rep else ["There is no translation yet."]
        text = "<b>Not approved yet.</b> "
        if blocking:
            text += ("Fix these first (in d · Final edits):<ul style='margin:2px 0 0 18px'>"
                     + "".join(f"<li>{esc(m)}</li>" for m in blocking) + "</ul>")
        else:
            text += "No blocking problems."
        other = [r for r in reasons if not r.startswith("Blocking problem") and "not been approved" not in r]
        if other:
            text += "<br>" + "<br>".join(esc(r) for r in other)
        return box("warn" if blocking else "info", text)

    # .................................................................. 6 export
    def _build_export(self) -> widgets.VBox:
        w = self.w
        w["summary_table"] = _html()
        w["summary_findings"] = _html()
        w["summary_validation"] = _html()
        w["summary_history"] = _html()
        w["prompt_evolution"] = _html()
        w["reflection"] = _textarea(rows=6, placeholder="A few sentences, written together.")
        w["btn_reflection"] = _button("Save reflection (goes in your report)", "info", width="320px",
                                      icon="save")
        w["btn_reflection"].on_click(lambda b: self._action(b, self._save_reflection, "msg_export"))
        w["btn_export_all"] = _button("Export all three files", "primary", width="270px", icon="download")
        w["btn_export_game"] = _button("Export game_translation_en.json", "", width="270px", icon="download")
        w["btn_export_settings"] = _button("Export agent_settings.json", "", width="270px", icon="download")
        w["btn_export_report"] = _button("Export workflow_report.html", "", width="270px", icon="download")
        for key, which in (("btn_export_game", "game_translation"), ("btn_export_settings", "agent_settings"),
                           ("btn_export_report", "workflow_report"), ("btn_export_all", "all")):
            w[key].on_click(lambda b, wh=which: self._action(b, lambda: self.export(wh), "msg_export",
                                                             "Checking and saving…"))
        # The game link is rebuilt by _refresh_export after every action (approval, edits…).
        w["play_link"] = _html()
        w["btn_next_mission"] = _button("Next mission", "warning", icon="forward")
        w["btn_next_mission"].on_click(lambda b: self._action(b, self._next_mission, "msg_export"))
        w["summary_tabs"] = _tabs([
            ("Summary", _scroll(w["summary_table"], "380px")),
            ("Decisions", _scroll(w["summary_findings"], "380px")),
            ("Technical checks", _scroll(w["summary_validation"], "380px")),
            ("History", _scroll(w["summary_history"], "380px")),
            ("Prompt changes", _scroll(w["prompt_evolution"], "380px"))])
        return widgets.VBox([
            _h3("6 · Test and export (≈10 min)"),
            w["summary_tabs"],
            _h4("Reflection"), _html(f"<b>{esc(REFLECTION_QUESTION)}</b>"),
            w["reflection"], _row(w["btn_reflection"]),
            _h4("Play"), w["play_link"],
            _h4("Export"), _note("Hand in these three files."),
            _row(w["btn_export_all"]),
            _row(w["btn_export_game"], w["btn_export_settings"], w["btn_export_report"]),
            w["msg_export"], w["download_out_game_translation"], w["download_out_agent_settings"],
            w["download_out_workflow_report"], _row(w["btn_next_mission"])])

    def _save_reflection(self, silent: bool = False) -> str:
        st = self._require_project()
        text = self.w["reflection"].value
        if text != st.reflection:
            ps.set_reflection(st, text)
        return "Reflection saved (it goes in your report)."

    def export(self, which: str = "all") -> Safe:
        st = self._require_project()
        self._sync_config_from_widgets()
        self._save_reflection()
        ok, reasons = ps.can_export(st)
        if not ok:
            raise StudioError(
                "Export blocked (nothing written; your work is kept).\n"
                + "\n".join(f"• {r}" for r in reasons[:6])
                + "\nHow to fix: Section 5 → fix in “d · Final edits”, approve in “e · Approve”, "
                  "export again.")
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
        wtxt = (f"<br>{len(warn)} warning(s) (not blocking)." if warn else "")
        if self.colab:
            steps = self._files_panel_steps(results[keys[0]].path, "the file")
            where = ("If nothing downloads: " if all_started else "To download: ") + steps
        else:
            where = f"Folder: {esc(out_dir)}"
        where += " Same names every mission: your browser may add “(1)”."
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
            text = (f"Progress saved to <code>{esc(path)}</code> — download started.<br>"
                    "If nothing downloads: " + self._files_panel_steps(path))
        elif self.colab:
            text = (f"Saved to <code>{esc(path)}</code> — use the Files panel to download it: "
                    + self._files_panel_steps(path))
        else:
            text = f"Progress saved to <code>{esc(path)}</code>."
        return Safe(text + "<br>To continue later: “Resume from file” (If you get stuck).")

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
        return f"Finished project saved ({copy_path}). {msg} 🔁 Swap roles now."

    def _refresh_export(self) -> None:
        w, st = self.w, self.state
        if st is None:
            for k in ("summary_table", "summary_findings", "summary_validation", "summary_history",
                      "prompt_evolution"):
                w[k].value = ""
            w["summary_table"].value = box("plain", "Start a mission first (Section 2).")
            self._refresh_play_link()
            return
        base = st.baseline_version()
        reviewed = st.version(st.findings[0].reviewed_version_id) if st.findings else None
        agent_v = next((v for v in reversed(st.versions) if v.kind == "revision"), None) or reviewed or \
            next((v for v in reversed(st.versions) if v.kind == "translator"), None)
        ap = st.approval
        final = st.version(ap.get("version_id")) if ap.get("approved") else st.current_version()
        final_head = "Final (approved)" if ap.get("approved") else "Current (not approved yet)"
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
                parts.append(f"<p><b>{esc(role.title())}: first → latest prompt sent</b></p>"
                             + exports.prompt_diff_html(pair["initial"]["user"], pair["final"]["user"]))
        w["prompt_evolution"].value = f"<div class='gls-diff'>{_DIFF_CSS}{''.join(parts)}</div>"
        self._refresh_play_link()

    def play_url(self) -> str | None:
        """The game link carrying the approved translation, or None (with the reason in
        ``self._play_reason``). Only for an approved game mission with no CRITICAL issue."""
        st = self.state
        self._play_reason = "Approve in Section 5 first."
        if st is None or self.challenge is None or not st.approval.get("approved"):
            return None
        obj, report = exports.build_game_translation(st, self.challenge, self.manifest)
        if report.critical:
            return None
        if obj.get("mission") == "custom":
            self._play_reason = "Custom material cannot be played in the game."
            return None
        try:
            return exports.game_play_url(obj, GAME_URL)
        except ValueError as e:
            self._play_reason = str(e)
            return None

    def _refresh_play_link(self) -> None:
        try:
            url = self.play_url()
        except Exception:  # noqa: BLE001 - the link is a convenience; exports still work
            url, self._play_reason = None, "No game link: export the game file instead."
        if url is None:
            self.w["play_link"].value = _note_html(esc(self._play_reason))
            return
        self.w["play_link"].value = (
            f'<a class="studio-play" href="{esc(url)}" target="_blank" rel="noopener" '
            f'style="display:inline-block;background:#1e8449;color:#ffffff;font-size:17px;'
            f'font-weight:bold;padding:10px 22px;border-radius:6px;text-decoration:none">'
            f'{esc(PLAY_TEXT)}</a>')

    # .................................................................. stuck box
    def _build_stuck(self) -> None:
        w = self.w
        w["btn_resume"] = _button("Resume my saved session", "success", icon="refresh")
        w["btn_resume"].on_click(lambda b: self._action(b, self._resume_saved, "msg_welcome"))
        w["resume_row"] = _hidden(_row(w["btn_resume"]))
        w["btn_stuck_resume"] = _button("Resume my saved session", "success", icon="refresh")
        w["btn_stuck_resume"].on_click(lambda b: self._action(b, self._resume_saved, "msg_stuck"))
        w["btn_stuck_download"] = _button("Download progress file", "", icon="download")
        w["btn_stuck_download"].on_click(
            lambda b: self._action(b, lambda: self._download_progress("download_out_stuck"), "msg_stuck"))
        w["resume_upload"] = widgets.FileUpload(accept=".json", multiple=False, description="Choose file")
        w["btn_resume_file"] = _button("Resume from file", "info", icon="upload")
        w["btn_resume_file"].on_click(lambda b: self._action(b, self._resume_from_upload, "msg_stuck"))
        w["resume_upload"].layout = _layout(width=BTN_W, height=BTN_H)
        w["checkpoint"] = _dropdown(self._checkpoint_options(), "Checkpoint:")
        w["btn_checkpoint"] = _button("Load checkpoint", "warning")
        w["btn_checkpoint"].on_click(lambda b: self._action(b, self._load_checkpoint, "msg_stuck"))
        w["btn_reset"] = _button("Reset this mission", "danger", icon="trash")
        w["btn_reset"].on_click(lambda b: self._action(b, self._reset_mission, "msg_stuck"))
        w["btn_reset_confirm"] = _button("Yes, reset (backup kept)", "danger")
        w["btn_reset_confirm"].on_click(lambda b: self._action(b, lambda: self._reset_mission(True), "msg_stuck"))
        w["btn_reset_confirm"].layout.width = "260px"
        w["reset_confirm"] = _hidden(_row(w["btn_reset_confirm"]))
        w["stuck_box"] = widgets.VBox([
            _h3("🆘 If you get stuck"),
            _row(w["btn_stuck_resume"], w["btn_stuck_download"]),
            _row(w["resume_upload"], w["btn_resume_file"]),
            w["checkpoint"], _row(w["btn_checkpoint"]),
            _row(w["btn_reset"], w["reset_confirm"]), w["msg_stuck"], w["download_out_stuck"]],
            layout=_layout(border="2px dashed #b9770e", padding="8px 12px"))

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
        return opts or [("(none available)", "")]

    def _resume_saved(self) -> str:
        if not self.state_path.exists():
            raise StudioError("No saved session here. Use “Resume from file” with your progress file.")
        msg = self._load_text(self.state_path.read_text(encoding="utf-8"), "your saved session")
        self._saved_session_handled = True
        _hidden(self.w["resume_row"])
        return msg

    def _resume_from_upload(self) -> str:
        files = compat.uploaded_files(self.w["resume_upload"].value)
        if not files:
            raise StudioError("Click “Choose file” and pick your progress file (.json) first.")
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
            raise StudioError("No checkpoint available. Ask your instructor.")
        if self.state is not None:
            self._save_copy(f"backup_{self.state.challenge_id}")
        self._backup_unhandled_session()
        msg = self._load_text(Path(path).read_text(encoding="utf-8"), "the catch-up checkpoint")
        return msg + " Earlier work (if any) is backed up in exports."

    def _reset_mission(self, confirmed: bool = False) -> str:
        st = self._require_project()
        if not confirmed:
            _hidden(self.w["reset_confirm"], False)
            return Warn("⚠️ This clears all versions and decisions (backup kept). Click “Yes, reset” "
                        "to confirm.")
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
            mode = badge("NOT CONNECTED — see Section 1", "#7f8c8d")
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
                parts.append("⚠️ Live project: load your key (Section 1) or “Switch to Replay”")
        else:
            parts.append("Mission: <i>not started</i>")
        parts.append(f"Role: <b>{esc(self.role)}</b>")
        parts.append(f"Autosaved: {esc(self.autosaved_at)}" if self.autosaved_at else "Not saved yet")
        if self.autosave_problem:
            parts.append(f"⚠️ <b>Autosave failed:</b> {esc(self.autosave_problem)}")
        self.w["status_html"].value = ("<div style='font-size:13px;color:#1f2933;padding:0 10px'>"
                                       + " · ".join(parts) + "</div>")
        replay_on = self.provider is not None and not self._is_live()
        b = self.w["btn_status_replay"]
        b.description = "✓ Replay Mode on" if replay_on else "Switch to Replay"
        b.button_style = "" if replay_on else "warning"
        b.icon = "" if replay_on else "play"
        b.tooltip = ("Replay Mode is on (simulated outputs)" if replay_on
                     else "Use simulated outputs instead of live AI")
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
                info = (f" Saved session found (mission “{esc(data.get('challenge_id'))}”, "
                        f"{esc(data.get('updated_at'))}): click <b>Resume my saved session</b>.")
            except (OSError, ValueError, AttributeError):
                info = " A saved session exists but could not be read."
        mode = ("Replay Mode (simulated outputs)" if self.provider is not None and not self._is_live()
                else ("live AI" if self.provider is not None else "not connected"))
        self.w["welcome_html"].value = box("ok", f"✅ <b>The studio is ready</b> — {esc(mode)}."
                                           + info + " Go to Section 1.")
