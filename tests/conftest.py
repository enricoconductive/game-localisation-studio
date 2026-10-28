"""Shared fixtures for the engine tests. No test touches the network."""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import agents, project_state as ps, providers  # noqa: E402

FX = ROOT / "tests" / "fixtures_synthetic"
PACK_SKIP = ("instructor pack not found (set INSTRUCTOR_PACK, or put the private instructor-pack "
             "folder next to the repository); this test needs the answer key")
FAKE_ANTHROPIC_KEY = "sk-ant-api03-FAKEtestKEY1234567890abcdefXYZ"
FAKE_HF_TOKEN = "hf_FAKEtokenABCDEFGHIJ1234567890"


def load_fx(name: str):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def instructor_pack_dir() -> Path | None:
    """The private instructor pack (answer key), or None when it is not available.

    ``INSTRUCTOR_PACK`` names the folder; by default it is ``../instructor-pack`` next to
    the repository. The public repository never contains it.
    """
    env = os.environ.get("INSTRUCTOR_PACK", "").strip()
    path = Path(env) if env else ROOT.parent / "instructor-pack"
    return path if path.is_dir() else None


def load_teaching_notes() -> dict | None:
    """``teaching_notes`` (verdicts per prepared finding) from the pack, or None."""
    pack = instructor_pack_dir()
    path = pack / "teaching_notes.json" if pack else None
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["teaching_notes"]


@pytest.fixture(scope="session")
def teaching_notes():
    notes = load_teaching_notes()
    if notes is None:
        pytest.skip(PACK_SKIP)
    return notes


@pytest.fixture(scope="session")
def instructor_notes():
    """{mission: instructor_notes} from the pack's instructor_notes/<challenge>.json files."""
    pack = instructor_pack_dir()
    files = sorted((pack / "instructor_notes").glob("*.json")) if pack else []
    if not files:
        pytest.skip(PACK_SKIP)
    out = {}
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        out[data["mission"]] = data["instructor_notes"]
    return out


class FakeResponse:
    def __init__(self, status: int, body=None, text: str | None = None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    """Plays back a list of FakeResponse objects or exceptions; records every call."""

    def __init__(self, *items):
        self.items = list(items)
        self.calls = []

    def post(self, url, headers=None, json=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "params": params,
                           "timeout": timeout})
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, BaseException):
            raise item
        return item


def anthropic_body(text: str, model="claude-haiku-5-5", inp=100, out=50, stop="end_turn"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "thinking", "thinking": "", "signature": "x"},
                        {"type": "text", "text": text}],
            "stop_reason": stop, "usage": {"input_tokens": inp, "output_tokens": out}}


def openai_body(text: str, model="m"):
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "model": model, "usage": {"prompt_tokens": 11, "completion_tokens": 7}}


def error_body(kind: str, message: str):
    return {"type": "error", "error": {"type": kind, "message": message}}


class ScriptedProvider(providers.Provider):
    """A 'live' provider whose replies come from a list (strings or callables)."""
    name = "scripted"
    is_live = True

    def __init__(self, replies):
        super().__init__("sk-ant-api03-SCRIPTEDkey000111222333444", {})
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, user, *, model, max_tokens=1200, temperature=0.3, replay_key=None):
        self.calls.append({"system": system, "user": user, "model": model,
                           "temperature": temperature, "replay_key": replay_key})
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        text = r(system, user, replay_key) if callable(r) else r
        return providers.ModelResponse(text, model, 10, 5, "live", False, "end_turn")


def echo_translations(prefix="EN "):
    """Reply callable: translate every id in the replay_key batch as prefix+id."""
    def reply(system, user, key):
        return json.dumps({"translations": [{"id": sid, "text": f"{prefix}{sid}"}
                                            for sid in key["string_ids"]]})
    return reply


@pytest.fixture
def challenge():
    return load_fx("challenge.json")


@pytest.fixture
def manifest():
    return load_fx("manifest.json")


@pytest.fixture
def replay_fixtures():
    return load_fx("replay_outputs.json")


@pytest.fixture
def provider_config():
    return providers.load_provider_config()


@pytest.fixture
def replay(replay_fixtures):
    return providers.ReplayProvider(replay_fixtures)


@pytest.fixture
def state(challenge):
    return ps.new_project(challenge, "en-GB", "replay", "replay", "replay", team_name="Team A")


@pytest.fixture
def reviewed_state(state, replay, challenge):
    agents.run_baseline(state, replay, challenge)
    agents.run_translator(state, replay, challenge)
    agents.run_reviewer(state, replay, challenge)
    return state


@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to open a socket or send an HTTP request fails the test."""
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(requests.Session, "request", boom)
    monkeypatch.setattr(requests, "post", boom)
    yield
