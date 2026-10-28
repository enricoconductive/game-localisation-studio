"""Model providers: Claude, Hugging Face, HKBU (configurable) and Replay (CONTRACTS §10).

All live HTTP goes through :func:`post_json`. API keys live only inside provider
instances; they are masked in every message, ``repr`` and log line.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import random
import time
import weakref
from dataclasses import dataclass, asdict
from typing import Any, Callable

import requests

from .validation import parse_json_strict, repo_path

REPLAY_HINT = "If this keeps happening, switch to Replay Mode to carry on with prepared outputs."
DEFAULT_TIMEOUT = 45
DEFAULT_MAX_TOKENS = 4000   # output limit per request (providers.json "limits.max_tokens")
_LOG = logging.getLogger(__name__)
DEFAULT_BACKOFF = (1, 3)
DEFAULT_REQUEST_CAP = 40

# Patterns for things that look like credentials (shared with exports.scan_for_secrets).
# Generic patterns need a token with digits next to "Bearer"/"key"/"token" so that game
# text such as "the Lantern Bearer Extraordinaire" or "the key to the attic" is not flagged.
_KEY_WORDS = (r"(?i)(?<![A-Za-z])(?:api[_-]?key|x-api-key|apikey|access[_-]?token|auth[_-]?token|"
              r"secret|password|token|key)")
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{16,}")),
    ("API key (sk-…)", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("Bearer token", re.compile(r"Bearer\s+(?=[A-Za-z0-9._\-]*\d)[A-Za-z0-9._\-]{20,}")),
    ("key/token value", re.compile(
        _KEY_WORDS + r"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9._+/=\-]{16,})")),
    # "our key is 3f9a…", "token 0d3c9b6e-…": a long hex/base64-like value after the word
    ("key/token value", re.compile(
        _KEY_WORDS + r"\s+(?:is\s+|was\s+)?[\"']?([A-Za-z0-9._+/=\-]{20,})")),
]
KNOWN_KEY_LABEL = "your loaded API key"

# Providers that hold a key register here (weakly), so every find_secrets/mask_secrets
# call also checks the keys actually loaded in this session, whatever their format
# (e.g. a 32-hex gateway key). The key itself still lives only inside its provider.
_KEY_HOLDERS: "weakref.WeakSet[Provider]" = weakref.WeakSet()
_MIN_LOADED_KEY = 8


def loaded_secrets() -> tuple:
    """The keys held by providers that are currently alive (never stored anywhere else)."""
    keys = []
    for prov in list(_KEY_HOLDERS):
        key = getattr(prov, "_api_key", "")
        if len(key) >= _MIN_LOADED_KEY and key not in keys:
            keys.append(key)
    return tuple(keys)


def find_secrets(text: str, extra_secrets=()) -> list[str]:
    """Masked descriptions of secret-looking substrings in ``text``.

    Checks ``extra_secrets`` and every loaded key first, then the generic patterns.
    """
    found: list[str] = []
    text = text or ""
    for secret in dict.fromkeys([*(extra_secrets or ()), *loaded_secrets()]):
        if secret and len(secret) >= 4 and secret in text:
            found.append(f"{KNOWN_KEY_LABEL} ({_mask_one(secret)})")
    for label, pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            value = m.group(m.lastindex or 0)
            if label == "key/token value":
                # avoid flagging names such as ANTHROPIC_API_KEY or plain words
                if not (re.search(r"\d", value) and re.search(r"[A-Za-z]", value)):
                    continue
            found.append(f"{label} ({_mask_one(value)})")
    return found


def key_refusal(text: str, what: str, generic: str | None = None) -> str | None:
    """Why student-typed ``text`` cannot be accepted (it holds a key), or None if it is fine."""
    hits = find_secrets(text)
    if not hits:
        return None
    if any(h.startswith(KNOWN_KEY_LABEL) for h in hits):
        return (f"This text contains your API key — remove it from the {what}. Your key "
                "belongs only in Colab Secrets.")
    return generic or f"The {what} looks like it contains an API key. Please remove it."


def _mask_one(secret: str) -> str:
    return "…" + secret[-4:] if len(secret) > 8 else "****"


def mask_secrets(text: str, secrets=()) -> str:
    """Replace known secrets and secret-looking tokens with ``[hidden]``."""
    text = "" if text is None else str(text)
    every = [*(secrets or ()), *loaded_secrets()]
    for s in sorted((s for s in every if s and len(s) >= 4), key=len, reverse=True):
        text = text.replace(s, "[hidden]")
    for _label, pat in SECRET_PATTERNS[:4]:
        text = pat.sub("[hidden]", text)
    return text


# --------------------------------------------------------------------------- errors / data


_KIND_MESSAGES = {
    "auth": "The {p} key was not accepted. Check that you pasted the whole key into Colab Secrets "
            "and that it is still active.",
    "rate_limit": "The {p} service is busy — many classmates are using the service at once. "
                  "Wait 30 seconds and try again, or switch to Replay.",
    "no_credit": "The {p} account has no credit left, so the request was refused. "
                 "Tell your instructor.",
    "invalid_model": "The model '{m}' is not available on {p}. Pick another model from the list "
                     "or ask your instructor.",
    "timeout": "{p} did not answer within {t} seconds.",
    "network": "Could not reach {p}. Check the internet connection of this Colab session.",
    "server": "{p} reported a temporary problem on its side.",
    "cap_reached": "You have used all {cap} live requests allowed for this exercise.",
    "bad_response": "{p} sent back a reply the studio could not use.",
    "not_configured": "{p} is not set up for this course yet. Ask your instructor, or switch to "
                      "Claude or Replay Mode.",
    "no_key": "No {p} key was provided.",
}


class ProviderError(Exception):
    """A provider failure with a plain-English, secret-free ``user_message``."""

    def __init__(self, kind: str, user_message: str, retryable: bool = False,
                 status: int | None = None, secrets=(), detail: str = ""):
        msg = mask_secrets(user_message, secrets)
        if REPLAY_HINT not in msg:
            msg = f"{msg.rstrip()} {REPLAY_HINT}"
        super().__init__(msg)
        self.kind = kind
        self.user_message = msg
        self.retryable = retryable
        self.status = status
        self.detail = mask_secrets(detail, secrets)[:300]   # the provider's own error text

    def __repr__(self) -> str:
        return f"ProviderError(kind={self.kind!r}, status={self.status!r})"


def _error(kind: str, provider: str = "the AI service", model: str = "", status=None,
           retryable=False, extra: str = "", secrets=(), **fmt) -> ProviderError:
    base = _KIND_MESSAGES[kind].format(p=provider, m=model, t=fmt.get("timeout", DEFAULT_TIMEOUT),
                                       cap=fmt.get("cap", DEFAULT_REQUEST_CAP))
    if extra:
        base = f"{base} ({extra})"
    return ProviderError(kind, base, retryable=retryable, status=status, secrets=secrets)


@dataclass
class ModelResponse:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    source: str = "live"
    simulated: bool = False
    stop_reason: str | None = None

    TRUNCATED_REASONS = ("max_tokens", "length")   # Anthropic stop_reason / OpenAI finish_reason

    @property
    def truncated(self) -> bool:
        """True when the reply was cut off at the output limit."""
        return self.stop_reason in self.TRUNCATED_REASONS

    def to_dict(self) -> dict:
        return asdict(self)


class UsageMeter:
    """Counts live requests and tokens; refuses to go past ``request_cap``.

    ``requests`` counts every live HTTP attempt (retries, repair requests and connection
    tests included) through :meth:`count_request`; :meth:`record` adds tokens and cost.
    The studio keeps one meter for the whole session, shared by every provider it loads.
    """

    def __init__(self, request_cap: int = DEFAULT_REQUEST_CAP, pricing: dict | None = None):
        self.request_cap = int(request_cap)
        self.pricing = pricing or {}
        self.requests = 0
        self.simulated_requests = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.est_cost_usd: float | None = 0.0 if self.pricing else None

    def remaining(self) -> int:
        return max(0, self.request_cap - self.requests)

    def check(self, n: int = 1) -> None:
        if self.requests + n > self.request_cap:
            raise _error("cap_reached", cap=self.request_cap)

    def count_request(self) -> None:
        """Called just before each live HTTP attempt; refuses once the cap is used up."""
        self.check()
        self.requests += 1

    def record(self, resp: ModelResponse) -> None:
        if resp.simulated:
            self.simulated_requests += 1
            return
        self.input_tokens += resp.input_tokens or 0
        self.output_tokens += resp.output_tokens or 0
        price = self.pricing.get(resp.model)
        if price and self.est_cost_usd is not None:
            self.est_cost_usd += ((resp.input_tokens or 0) * price.get("input_per_mtok", 0)
                                  + (resp.output_tokens or 0) * price.get("output_per_mtok", 0)) / 1e6

    def snapshot(self) -> dict:
        return {"requests": self.requests, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "request_cap": self.request_cap,
                "est_cost_usd": None if self.est_cost_usd is None else round(self.est_cost_usd, 6),
                "simulated_requests": self.simulated_requests}


# --------------------------------------------------------------------------- HTTP helper


def _error_details(resp) -> tuple[str, str]:
    """``(error type, message)`` from an error reply (either may be empty)."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 - any non-JSON body
        return "", (getattr(resp, "text", "") or "")[:300]
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            names = [str(x) for x in (err.get("type"), err.get("code")) if x]
            etype = next((x for x in names if x.lower() in _TYPE_KINDS), names[0] if names else "")
            return etype[:80], str(err.get("message") or etype or "")[:300]
        return "", str(err)[:300]
    return "", str(body)[:300]


def _error_text(resp) -> str:
    return _error_details(resp)[1]


# The error is about the model id itself (not, say, "max_tokens > the maximum for this model").
_MODEL_ID_ERROR = re.compile(
    r"\b(?:unknown|invalid|unsupported|unrecogni[sz]ed|no such)\s+model\b"
    r"|\bmodel[_ ]not[_ ]found\b|\bmodel\s*:\s*\S"
    r"|\bmodel\b[^.]{0,80}?\b(?:does not exist|not found|is not (?:available|supported|valid))", re.I)
_TYPE_KINDS = {"authentication_error": "auth", "permission_error": "auth", "invalid_api_key": "auth",
               "billing_error": "no_credit", "insufficient_quota": "no_credit",
               "not_found_error": "invalid_model", "model_not_found": "invalid_model",
               "rate_limit_error": "rate_limit", "overloaded_error": "server", "api_error": "server"}


def classify_http_error(status: int, detail: str, provider: str, model: str,
                        secrets=(), error_type: str = "") -> ProviderError:
    """Map an HTTP status, the provider's error ``type`` and its text to a :class:`ProviderError`.

    429 is always ``rate_limit``. Otherwise a known error type wins, then the status code.
    """
    err = _classify_http_error(status, detail, provider, model, secrets, error_type)
    err.detail = mask_secrets(detail or "", secrets)[:300]
    return err


def _classify_http_error(status, detail, provider, model, secrets, error_type) -> ProviderError:
    low = (detail or "").lower()
    kw = dict(provider=provider, model=model, status=status, secrets=secrets)
    kind = _TYPE_KINDS.get((error_type or "").lower())
    if status == 429:
        return _error("rate_limit", retryable=True, **kw)
    if kind is None:
        if status == 402 or (400 <= status < 500
                             and ("credit balance" in low or "billing" in low or "quota" in low)):
            kind = "no_credit"
        elif status in (401, 403):
            kind = "auth"
        elif status == 404 or (status in (400, 422) and _MODEL_ID_ERROR.search(detail or "")):
            kind = "invalid_model"
        elif status >= 500:
            kind = "server"
    if kind == "rate_limit":
        return _error("rate_limit", retryable=True, **kw)
    if kind == "server":
        overloaded = status == 529 or (error_type or "").lower() == "overloaded_error"
        return _error("server", retryable=True,
                      extra="the service is overloaded" if overloaded else f"HTTP {status}", **kw)
    if kind is not None:
        return _error(kind, **kw)
    return _error("bad_response", extra=f"HTTP {status}: {mask_secrets(detail, secrets)[:160]}", **kw)


MAX_RETRY_AFTER = 20   # seconds; a longer Retry-After is capped


def _retry_after(resp) -> float | None:
    """Seconds from a ``Retry-After`` header (429/529 only), or None."""
    headers = getattr(resp, "headers", None) or {}
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None   # an HTTP date or junk: use the normal backoff


_BAD_ADDRESS = (requests.exceptions.InvalidURL, requests.exceptions.MissingSchema,
                requests.exceptions.InvalidSchema, requests.exceptions.InvalidHeader,
                requests.exceptions.URLRequired)


def post_json(session, url: str, headers: dict, payload: dict, *, provider: str, model: str,
              params: dict | None = None, timeout: float = DEFAULT_TIMEOUT, max_retries: int = 2,
              backoff=DEFAULT_BACKOFF, sleep: Callable[[float], None] = time.sleep,
              secrets=(), on_attempt: Callable[[], None] | None = None,
              jitter: Callable[[float], float] | None = None) -> dict:
    """POST JSON with bounded retries on 429/5xx/timeout/connection errors.

    ``on_attempt`` runs before every HTTP attempt (the usage meter counts it there).
    Waits use ``backoff`` plus a little random jitter; a 429/529 ``Retry-After`` header is
    honoured up to :data:`MAX_RETRY_AFTER` seconds.
    """
    jitter = jitter or (lambda base: random.uniform(0, 0.5 * base))
    attempt = 0
    while True:
        if on_attempt is not None:
            on_attempt()
        wait = None
        try:
            resp = session.post(url, headers=headers, json=payload, params=params or None,
                                timeout=timeout)
        except requests.exceptions.Timeout:
            err = _error("timeout", provider, model, retryable=True, secrets=secrets,
                         timeout=int(timeout) if float(timeout).is_integer() else timeout)
        except _BAD_ADDRESS:
            err = _error("not_configured", provider, model, secrets=secrets,
                         extra="the provider address is not set up correctly — ask your instructor")
        except requests.exceptions.RequestException:
            err = _error("network", provider, model, retryable=True, secrets=secrets)
        else:
            if 200 <= resp.status_code < 300:
                try:
                    return resp.json()
                except ValueError:
                    raise _error("bad_response", provider, model, status=resp.status_code,
                                 extra="the reply was not JSON", secrets=secrets) from None
            etype, detail = _error_details(resp)
            err = classify_http_error(resp.status_code, detail, provider, model, secrets, etype)
            if resp.status_code in (429, 529):
                wait = _retry_after(resp)
        if not err.retryable or attempt >= max_retries:
            raise err
        base = backoff[min(attempt, len(backoff) - 1)]
        delay = base + jitter(base)
        if wait is not None:
            delay = max(delay, wait)
        sleep(min(delay, MAX_RETRY_AFTER))
        attempt += 1


def get_path(obj: Any, dotted: str) -> Any:
    """Follow a dot path such as ``choices.0.message.content``; None if absent."""
    cur = obj
    for part in (dotted or "").split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


# --------------------------------------------------------------------------- providers


class Provider:
    name = "base"
    display_name = "AI service"
    is_live = True
    verified = False
    # ``complete`` takes an optional ``json_schema`` (agents check this before passing one);
    # only providers that can enforce it (Claude, HKBU with ``supports_json_schema``) send it.
    accepts_json_schema = True

    def __init__(self, api_key: str = "", config: dict | None = None, *, session=None,
                 sleep: Callable[[float], None] | None = None, usage_meter: UsageMeter | None = None,
                 limits: dict | None = None, request_options: dict | None = None):
        self._api_key = (api_key or "").strip()
        self.config = config or {}
        self.limits = limits or {}
        # per-model request options from config/models.json (e.g. thinking / effort for Claude)
        self.request_options = copy.deepcopy(request_options or {})
        self.notes: list[str] = []   # plain notes about adjustments made (shown in the run log)
        self.display_name = self.config.get("display_name", self.display_name)
        self.verified = bool(self.config.get("verified", self.verified))
        self.usage_meter = usage_meter
        self._session = session
        self._sleep = sleep or time.sleep
        if self._api_key:
            _KEY_HOLDERS.add(self)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} key={'set' if self._api_key else 'missing'}>"

    __str__ = __repr__

    @property
    def session(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _secrets(self) -> tuple:
        return (self._api_key,) if self._api_key else ()

    def _note(self, text: str) -> None:
        self.notes.append(text)
        _LOG.info("%s: %s", self.display_name, text)

    @property
    def timeout_seconds(self) -> float:
        """The provider's own ``timeout_seconds`` (providers.json), else the shared limit."""
        return self.config.get("timeout_seconds") or self.limits.get("timeout_seconds", DEFAULT_TIMEOUT)

    def _post(self, url, headers, payload, model, params=None) -> dict:
        if not self._api_key:
            raise _error("no_key", self.display_name)
        return post_json(self.session, url, headers, payload, provider=self.display_name,
                         model=model, params=params,
                         timeout=self.timeout_seconds,
                         max_retries=self.limits.get("max_retries", 2),
                         backoff=tuple(self.limits.get("backoff_seconds", DEFAULT_BACKOFF)),
                         sleep=self._sleep, secrets=self._secrets(),
                         on_attempt=self.usage_meter.count_request if self.usage_meter else None)

    def complete(self, system: str, user: str, *, model: str, max_tokens: int = DEFAULT_MAX_TOKENS,
                 temperature: float = 0.3, replay_key: dict | None = None,
                 json_schema: dict | None = None) -> ModelResponse:
        """One request. ``json_schema`` (a strict JSON Schema for the reply) is enforced by
        providers that support structured outputs and ignored by the others."""
        if self.usage_meter is not None:
            self.usage_meter.check()
        if self._api_key and self._api_key in f"{system}\n{user}":
            raise _error("bad_response", self.display_name, model,
                         extra="the request was not sent because it contains your API key; "
                               "remove the key from your text")
        try:
            resp = self._complete(system, user, model=model, max_tokens=max_tokens,
                                  temperature=temperature, json_schema=json_schema)
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001 - never leak a raw traceback with a key in it
            raise _error("bad_response", self.display_name, model,
                         extra=mask_secrets(type(e).__name__, self._secrets())) from None
        if self.usage_meter is not None:
            self.usage_meter.record(resp)
        return resp

    def _complete(self, system, user, *, model, max_tokens, temperature,
                  json_schema=None) -> ModelResponse:
        raise NotImplementedError

    def test_connection(self, model: str) -> tuple[bool, str]:
        try:
            self.complete("You are a connection test.", "Reply with the single word OK.",
                          model=model, max_tokens=64, temperature=0)
        except ProviderError as e:
            return False, e.user_message
        return True, f"Connected to {self.display_name} with model '{model}'."


def _anthropic_body(system, user, model, max_tokens, temperature, cfg, model_params,
                    request_options=None, json_schema=None) -> dict:
    """Messages API body. ``request_options`` (config/models.json) may set ``thinking``
    (top level) and ``effort`` (into ``output_config``); ``json_schema`` becomes
    ``output_config.format`` (structured outputs)."""
    body = {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}]}
    body.update(copy.deepcopy(model_params or {}))
    opts = request_options or {}
    if isinstance(opts.get("thinking"), dict):
        body["thinking"] = copy.deepcopy(opts["thinking"])
    out = dict(body.get("output_config") or {})
    if opts.get("effort"):
        out["effort"] = opts["effort"]
    if json_schema:
        out["format"] = {"type": "json_schema", "schema": copy.deepcopy(json_schema)}
    if out:
        body["output_config"] = out
    if cfg.get("send_temperature", False):
        body["temperature"] = temperature
    return body


def _thinking_rejected(err: "ProviderError") -> bool:
    """A 400 whose error text is about the ``thinking`` field."""
    return err.status == 400 and "thinking" in (getattr(err, "detail", "") or "").lower()


def _anthropic_text(data: dict, provider: str, model: str) -> tuple[str, str | None]:
    blocks = data.get("content") if isinstance(data, dict) else None
    if not isinstance(blocks, list):
        raise _error("bad_response", provider, model, extra="no content in the reply")
    stop = data.get("stop_reason")
    if stop == "refusal":
        raise _error("bad_response", provider, model,
                     extra="the model declined this request; try rephrasing your instructions")
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    return text, stop


def _openai_body(system, user, model, max_tokens, temperature, cfg, model_params,
                 include_model=True) -> dict:
    body: dict = {"messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                  "max_tokens": max_tokens}
    if include_model:
        body["model"] = model
    if cfg.get("send_temperature", True):
        body["temperature"] = temperature
    body.update(copy.deepcopy(model_params or {}))
    return body


class AnthropicProvider(Provider):
    """Claude Messages API: POST {base_url}/v1/messages."""
    name = "anthropic"
    display_name = "Claude (Anthropic)"
    verified = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._no_thinking: set[str] = set()   # models whose ``thinking`` setting was refused

    def _complete(self, system, user, *, model, max_tokens, temperature, json_schema=None):
        cfg = self.config
        url = cfg.get("base_url", "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        headers = {"x-api-key": self._api_key,
                   "anthropic-version": cfg.get("anthropic_version", "2026-10-21"),
                   "content-type": "application/json"}
        opts = dict(self.request_options.get(model) or {})
        if model in self._no_thinking:
            opts.pop("thinking", None)
        body = _anthropic_body(system, user, model, max_tokens, temperature, cfg,
                               (cfg.get("model_params") or {}).get(model), opts, json_schema)
        try:
            data = self._post(url, headers, body, model)
        except ProviderError as e:
            if "thinking" not in body or not _thinking_rejected(e):
                raise
            # bounded: one retry without the thinking field, then remembered for this model
            self._no_thinking.add(model)
            self._note(f"Claude did not accept the thinking setting {body['thinking']} for "
                       f"'{model}', so the request was sent again without it (ask your "
                       "instructor to check request_options in config/models.json).")
            body = {k: v for k, v in body.items() if k != "thinking"}
            data = self._post(url, headers, body, model)
        text, stop = _anthropic_text(data, self.display_name, model)
        usage = data.get("usage") or {}
        return ModelResponse(text, data.get("model", model), usage.get("input_tokens"),
                             usage.get("output_tokens"), "live", False, stop)


def _openai_response(data, provider, model, text_path="choices.0.message.content",
                     in_path="usage.prompt_tokens", out_path="usage.completion_tokens",
                     stop_path="choices.0.finish_reason"):
    text = get_path(data, text_path)
    if not isinstance(text, str):
        raise _error("bad_response", provider, model, extra="no text in the reply")
    stop = get_path(data, stop_path)
    return ModelResponse(text, model, get_path(data, in_path), get_path(data, out_path),
                         "live", False, stop)


class HuggingFaceProvider(Provider):
    """Hugging Face Inference Providers router (OpenAI-compatible chat completions)."""
    name = "huggingface"
    display_name = "Hugging Face"

    def _complete(self, system, user, *, model, max_tokens, temperature, json_schema=None):
        # json_schema is not sent: structured outputs are not verified on the router
        cfg = self.config
        url = cfg.get("base_url", "https://router.huggingface.co/v1").rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body = _openai_body(system, user, model, max_tokens, temperature, cfg,
                            (cfg.get("model_params") or {}).get(model))
        return _openai_response(self._post(url, headers, body, model), self.display_name, model)


class HKBUProvider(Provider):
    """University gateway: every HTTP detail comes from config/providers.json["hkbu"]."""
    name = "hkbu"
    display_name = "HKBU GenAI"

    def _complete(self, system, user, *, model, max_tokens, temperature, json_schema=None):
        cfg = self.config
        if not cfg.get("supports_json_schema", False):
            json_schema = None
        base = (cfg.get("base_url") or "").strip().rstrip("/")
        if not base:
            raise _error("not_configured", self.display_name)
        style = cfg.get("request_style", "openai_chat")
        if style not in ("openai_chat", "anthropic_messages"):
            raise _error("not_configured", self.display_name,
                         extra=f"unknown request_style '{style}'")
        template = cfg.get("path_template") or "{base_url}/chat/completions"
        fill = {"base_url": base, "model": model, "api_version": cfg.get("api_version", "")}
        url = template.format(**fill)
        params = {k: str(v).format(**fill) for k, v in (cfg.get("query_params") or {}).items()}
        header_name = cfg.get("auth_header_name") or "Authorization"
        headers = {header_name: f"{cfg.get('auth_prefix', '')}{self._api_key}",
                   "Content-Type": "application/json"}
        headers.update({k: str(v) for k, v in (cfg.get("extra_headers") or {}).items()})
        model_params = (cfg.get("model_params") or {}).get(model)
        if style == "anthropic_messages":
            body = _anthropic_body(system, user, model, max_tokens, temperature, cfg, model_params,
                                   json_schema=json_schema)
            default_path = "content.0.text"
            in_p, out_p, stop_p = "usage.input_tokens", "usage.output_tokens", "stop_reason"
        else:
            body = _openai_body(system, user, model, max_tokens, temperature, cfg, model_params,
                                include_model=cfg.get("model_in_body", True))
            if json_schema:
                body["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": "reply", "strict": True, "schema": copy.deepcopy(json_schema)}}
            default_path = "choices.0.message.content"
            in_p, out_p = "usage.prompt_tokens", "usage.completion_tokens"
            stop_p = "choices.0.finish_reason"
        data = self._post(url, headers, body, model, params=params)
        return _openai_response(data, self.display_name, model,
                                cfg.get("response_text_path") or default_path,
                                cfg.get("usage_input_path") or in_p,
                                cfg.get("usage_output_path") or out_p,
                                cfg.get("stop_reason_path") or stop_p)


class ReplayProvider(Provider):
    """Serves prepared fixture outputs as JSON text. Never touches the network."""
    name = "replay"
    display_name = "Replay Mode"
    is_live = False
    verified = True

    STAGES = {"baseline": "baseline", "translator": "translator", "reviewer": "reviewer",
              "reviewer_round2": "reviewer_round2"}

    def __init__(self, fixtures: dict, config: dict | None = None, usage_meter=None, **_ignored):
        super().__init__("", config or {}, usage_meter=usage_meter)
        self.fixtures = fixtures or {}
        self.label = self.fixtures.get("label", "SIMULATED OUTPUT")

    @property
    def session(self):  # pragma: no cover - guard
        raise RuntimeError("Replay Mode never uses the network.")

    VARIANTS = ("faithful", "balanced", "creative")
    DEFAULT_VARIANT = "balanced"

    @classmethod
    def _entry(cls, ch: dict, stage: str, variant: str | None):
        """The prepared output for ``stage`` and prompt ``variant`` (CONTRACTS §15).

        New fixtures keep ``translator_variants`` and per-variant ``reviewer`` /
        ``reviewer_round2`` maps; old fixtures keep one ``translator`` / ``reviewer``
        entry, which is treated as the ``balanced`` variant. Other keys (for example
        ``revision_notes`` or ``locale_note``) are never served.
        """
        variant = variant if variant in cls.VARIANTS else cls.DEFAULT_VARIANT
        if stage == "translator":
            variants = ch.get("translator_variants")
            if isinstance(variants, dict) and variants:
                return variants.get(variant) or variants.get(cls.DEFAULT_VARIANT)
            return ch.get("translator")
        entry = ch.get(stage)
        if stage in ("reviewer", "reviewer_round2") and isinstance(entry, dict) \
                and "findings" not in entry and any(v in entry for v in cls.VARIANTS):
            return entry.get(variant) or entry.get(cls.DEFAULT_VARIANT)
        return entry

    def complete(self, system, user, *, model="replay", max_tokens=DEFAULT_MAX_TOKENS,
                 temperature=0.3, replay_key=None, json_schema=None) -> ModelResponse:
        key = replay_key or {}
        stage = key.get("stage", "")
        if "deterministic_output" in key:  # replay revision (CONTRACTS §8)
            payload = key["deterministic_output"]
        else:
            if stage == "reviewer" and int(key.get("round", 1)) >= 2:
                stage = "reviewer_round2"
            ch = (self.fixtures.get("challenges") or {}).get(key.get("challenge"), {})
            entry = self._entry(ch, stage, key.get("variant"))
            if stage not in self.STAGES or entry is None:
                raise _error("not_configured", self.display_name,
                             extra=f"no prepared output for '{key.get('challenge')}' / '{stage}'")
            payload = copy.deepcopy(entry)
            ids = key.get("string_ids")
            if ids is not None:
                ids = set(ids)
                if "translations" in payload:
                    payload["translations"] = [t for t in payload["translations"]
                                               if isinstance(t, dict) and t.get("id") in ids]
                if "findings" in payload:
                    # findings for unknown ids reach the parser (and are dropped there) once,
                    # in the batch whose key lists ``known_ids``
                    known = set(key.get("known_ids") or ())
                    payload["findings"] = [f for f in payload["findings"] if isinstance(f, dict)
                                           and (f.get("string_id") in ids
                                                or (known and f.get("string_id") not in known))]
        resp = ModelResponse(json.dumps(payload, ensure_ascii=False), "replay", None, None,
                             "replay", True, "end_turn")
        if self.usage_meter is not None:
            self.usage_meter.record(resp)
        return resp

    def test_connection(self, model: str = "replay") -> tuple[bool, str]:
        n = len(self.fixtures.get("challenges") or {})
        return (n > 0, f"Replay Mode ready ({n} prepared challenge(s)). Outputs are simulated."
                if n else "No prepared Replay outputs were found. Ask your instructor.")


# --------------------------------------------------------------------------- factory / config


PROVIDER_CLASSES = {"anthropic": AnthropicProvider, "huggingface": HuggingFaceProvider,
                    "hkbu": HKBUProvider, "replay": ReplayProvider}


def load_model_catalog(path: str = "config/models.json") -> dict:
    with open(repo_path(path), encoding="utf-8") as f:
        return parse_json_strict(f.read())


def load_provider_config(path: str = "config/providers.json") -> dict:
    with open(repo_path(path), encoding="utf-8") as f:
        return parse_json_strict(f.read())


def load_replay_fixtures(path: str = "fixtures/replay_outputs.json") -> dict:
    try:
        with open(repo_path(path), encoding="utf-8") as f:
            return parse_json_strict(f.read())
    except (OSError, ValueError):
        raise _error("not_configured", "Replay Mode",
                     extra="the prepared outputs file is missing or damaged") from None


def pricing_from_catalog(catalog: dict) -> dict:
    out = {}
    for prov in catalog.values():
        if isinstance(prov, dict):
            for m in prov.get("models", []):
                if isinstance(m, dict) and m.get("pricing"):
                    out[m["id"]] = m["pricing"]
    return out


def request_options_from_catalog(catalog: dict | None, provider_name: str) -> dict:
    """``{model id: request_options}`` for one provider from config/models.json."""
    out = {}
    prov = (catalog or {}).get(provider_name)
    for m in (prov.get("models", []) if isinstance(prov, dict) else []):
        if isinstance(m, dict) and isinstance(m.get("request_options"), dict) and m.get("id"):
            out[m["id"]] = m["request_options"]
    return out


def make_provider(name: str, api_key: str, provider_config: dict,
                  usage_meter: UsageMeter | None = None, *, session=None, sleep=None,
                  fixtures: dict | None = None, model_catalog: dict | None = None) -> Provider:
    """Build a provider by name (``anthropic | huggingface | hkbu | replay``).

    Per-model ``request_options`` come from ``model_catalog`` (default: config/models.json).
    """
    if name not in PROVIDER_CLASSES:
        raise _error("not_configured", f"'{name}'")
    cfg = (provider_config or {}).get(name, {})
    limits = (provider_config or {}).get("limits", {})
    if name == "replay":
        if fixtures is None:
            fixtures = load_replay_fixtures(cfg.get("fixtures_path", "fixtures/replay_outputs.json"))
        return ReplayProvider(fixtures, cfg, usage_meter=usage_meter)
    if model_catalog is None:
        try:
            model_catalog = load_model_catalog()
        except (OSError, ValueError):
            model_catalog = {}
    return PROVIDER_CLASSES[name](api_key, cfg, session=session, sleep=sleep,
                                  usage_meter=usage_meter, limits=limits,
                                  request_options=request_options_from_catalog(model_catalog, name))


def load_api_key(provider_name: str, provider_config: dict, *, getpass_fn=None,
                 userdata=None) -> str:
    """Read the key from Colab Secrets, else ask with getpass. Never printed."""
    cfg = (provider_config or {}).get(provider_name, {})
    label = cfg.get("display_name", provider_name)
    secret_name = cfg.get("secret_name")
    if provider_name == "replay":
        return ""
    key = ""
    if secret_name:
        if userdata is None:
            try:
                from google.colab import userdata as _ud  # type: ignore
                userdata = _ud
            except Exception:  # noqa: BLE001 - not running in Colab
                userdata = None
        if userdata is not None:
            try:
                key = userdata.get(secret_name) or ""
            except Exception:  # noqa: BLE001 - SecretNotFoundError / NotebookAccessError / timeout
                key = ""
    if not key:
        if getpass_fn is None:
            import getpass
            getpass_fn = getpass.getpass
        try:
            key = getpass_fn(f"Paste your {label} key (it stays hidden; Enter to cancel): ") or ""
        except (EOFError, KeyboardInterrupt, OSError):
            key = ""
    key = key.strip()
    if not key:
        hint = (f" Add it in Colab under the key icon (Secrets) as {secret_name} and allow notebook access."
                if secret_name else "")
        raise _error("no_key", label, extra=hint.strip() or None)
    return key
