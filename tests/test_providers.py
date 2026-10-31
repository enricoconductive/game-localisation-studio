import pytest
import requests

from src import providers as p
from conftest import (FAKE_ANTHROPIC_KEY, FAKE_HF_TOKEN, FakeResponse, FakeSession, anthropic_body,
                      error_body, openai_body)


def anthropic(session, provider_config, sleeps=None, meter=None):
    sleeps = sleeps if sleeps is not None else []
    return p.make_provider("anthropic", FAKE_ANTHROPIC_KEY, provider_config, meter,
                           session=session, sleep=sleeps.append)


def call(prov, model="claude-haiku-5-5"):
    return prov.complete("SYS", "USER", model=model, max_tokens=1200, temperature=0.4)


def assert_friendly(err: p.ProviderError):
    assert err.user_message.endswith(p.REPLAY_HINT)
    assert FAKE_ANTHROPIC_KEY not in err.user_message and FAKE_ANTHROPIC_KEY not in repr(err)


def test_anthropic_success_request_shape(provider_config):
    s = FakeSession(FakeResponse(200, anthropic_body('{"translations": []}')))
    r = call(anthropic(s, provider_config))
    assert r.text == '{"translations": []}'          # thinking block ignored
    assert (r.input_tokens, r.output_tokens, r.source, r.simulated) == (100, 50, "live", False)
    c = s.calls[0]
    assert c["url"] == "https://api.anthropic.com/v1/messages"
    assert c["headers"]["x-api-key"] == FAKE_ANTHROPIC_KEY
    assert c["headers"]["anthropic-version"] == "2026-10-21"
    assert c["timeout"] == 90                       # Claude's own timeout_seconds
    body = c["json"]
    assert body["system"] == "SYS" and body["messages"] == [{"role": "user", "content": "USER"}]
    assert body["max_tokens"] == 1200 and body["model"] == "claude-haiku-5-5"
    assert "temperature" not in body and "top_p" not in body   # rejected on 2026-10-21
    assert body["output_config"] == {"effort": "low"}        # no json_schema passed here
    assert body["thinking"] == {"type": "disabled"}          # request_options in models.json


def test_401_not_retried(provider_config):
    sleeps = []
    s = FakeSession(FakeResponse(401, error_body("authentication_error", "invalid x-api-key")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, sleeps))
    assert e.value.kind == "auth" and not e.value.retryable
    assert len(s.calls) == 1 and sleeps == []
    assert_friendly(e.value)


def test_403_is_auth(provider_config):
    s = FakeSession(FakeResponse(403, error_body("permission_error", "nope")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config))
    assert e.value.kind == "auth"


def test_429_then_success(provider_config):
    sleeps = []
    s = FakeSession(FakeResponse(429, error_body("rate_limit_error", "slow down")),
                    FakeResponse(200, anthropic_body("OK")))
    assert call(anthropic(s, provider_config, sleeps)).text == "OK"
    assert len(s.calls) == 2 and len(sleeps) == 1 and 1 <= sleeps[0] <= 1.5   # backoff + jitter


def test_429_exhausted(provider_config):
    sleeps = []
    s = FakeSession(FakeResponse(429, error_body("rate_limit_error", "slow down")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, sleeps))
    assert e.value.kind == "rate_limit"
    assert len(s.calls) == 3 and 1 <= sleeps[0] <= 1.5 and 3 <= sleeps[1] <= 4.5
    assert "30 seconds" in e.value.user_message and "classmates" in e.value.user_message
    assert_friendly(e.value)


def test_529_overloaded_retried(provider_config):
    sleeps = []
    s = FakeSession(FakeResponse(529, error_body("overloaded_error", "Overloaded")),
                    FakeResponse(200, anthropic_body("OK")))
    assert call(anthropic(s, provider_config, sleeps)).text == "OK"
    assert len(sleeps) == 1 and 1 <= sleeps[0] <= 1.5


def test_timeout(provider_config):
    sleeps = []
    s = FakeSession(requests.exceptions.Timeout("read timed out"))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, sleeps))
    assert e.value.kind == "timeout" and len(s.calls) == 3
    assert 1 <= sleeps[0] <= 1.5 and 3 <= sleeps[1] <= 4.5
    assert "90 seconds" in e.value.user_message
    assert_friendly(e.value)


def test_connection_error(provider_config):
    s = FakeSession(requests.exceptions.ConnectionError("dns"))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, []))
    assert e.value.kind == "network"


@pytest.mark.parametrize("resp", [
    FakeResponse(400, error_body("invalid_request_error",
                                 "Your credit balance is too low to access the Anthropic API.")),
    FakeResponse(402, error_body("billing_error", "Payment required")),
])
def test_no_credit(provider_config, resp):
    s = FakeSession(resp)
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, []))
    assert e.value.kind == "no_credit" and len(s.calls) == 1
    assert_friendly(e.value)


def test_invalid_model(provider_config):
    s = FakeSession(FakeResponse(404, error_body("not_found_error", "model: claude-nope")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, []), model="claude-nope")
    assert e.value.kind == "invalid_model" and "claude-nope" in e.value.user_message
    assert len(s.calls) == 1


def test_refusal_is_bad_response(provider_config):
    s = FakeSession(FakeResponse(200, anthropic_body("", stop="refusal")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config))
    assert e.value.kind == "bad_response"


def test_key_echoed_by_server_is_masked(provider_config):
    s = FakeSession(FakeResponse(400, error_body("invalid_request_error",
                                                 f"bad header {FAKE_ANTHROPIC_KEY}")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config))
    assert_friendly(e.value)
    assert FAKE_ANTHROPIC_KEY not in str(e.value)


def test_repr_hides_key(provider_config):
    prov = anthropic(FakeSession(FakeResponse(200, anthropic_body("x"))), provider_config)
    assert FAKE_ANTHROPIC_KEY not in repr(prov) and FAKE_ANTHROPIC_KEY not in str(prov)
    assert "sk-ant" not in repr(vars(prov).get("config"))


def test_missing_key(provider_config):
    prov = p.make_provider("anthropic", "", provider_config, session=FakeSession())
    with pytest.raises(p.ProviderError) as e:
        call(prov)
    assert e.value.kind == "no_key"


def test_huggingface_request_shape(provider_config):
    s = FakeSession(FakeResponse(200, openai_body("hello")))
    prov = p.make_provider("huggingface", FAKE_HF_TOKEN, provider_config, session=s)
    r = prov.complete("SYS", "USER", model="openai/gpt-oss-120b", temperature=0.6)
    assert (r.text, r.input_tokens, r.output_tokens) == ("hello", 11, 7)
    c = s.calls[0]
    assert c["url"] == "https://router.huggingface.co/v1/chat/completions"
    assert c["headers"]["Authorization"] == f"Bearer {FAKE_HF_TOKEN}"
    assert c["json"]["model"] == "openai/gpt-oss-120b" and c["json"]["temperature"] == 0.6
    assert c["json"]["messages"][0] == {"role": "system", "content": "SYS"}


def test_hkbu_not_configured(provider_config):
    s = FakeSession(FakeResponse(200, openai_body("x")))
    cfg = {**provider_config, "hkbu": {**provider_config["hkbu"], "base_url": ""}}
    prov = p.make_provider("hkbu", "hkbu-key-123456", cfg, session=s)
    with pytest.raises(p.ProviderError) as e:
        prov.complete("S", "U", model="any")
    assert e.value.kind == "not_configured" and s.calls == []
    assert "instructor" in e.value.user_message and e.value.user_message.endswith(p.REPLAY_HINT)


def test_hkbu_configured_openai_style(provider_config):
    cfg = {**provider_config, "hkbu": {**provider_config["hkbu"],
           "base_url": "https://genai.example.test/api/v0/rest/",
           "path_template": "{base_url}/deployments/{model}/chat/completions",
           "api_version": "2024-05-01", "query_params": {"api-version": "{api_version}"},
           "auth_header_name": "api-key", "auth_prefix": "", "extra_headers": {"X-Course": "TRA"},
           "model_in_body": False, "response_text_path": "choices.0.message.content",
           "send_temperature": True}}
    s = FakeSession(FakeResponse(200, openai_body("hi from hkbu")))
    prov = p.make_provider("hkbu", "hkbu-key-123456", cfg, session=s)
    r = prov.complete("S", "U", model="gpt-x", temperature=0.2)
    c = s.calls[0]
    assert r.text == "hi from hkbu"
    assert c["url"] == "https://genai.example.test/api/v0/rest/deployments/gpt-x/chat/completions"
    assert c["params"] == {"api-version": "2024-05-01"}
    assert c["headers"]["api-key"] == "hkbu-key-123456" and c["headers"]["X-Course"] == "TRA"
    assert "model" not in c["json"] and c["json"]["temperature"] == 0.2


def test_hkbu_configured_anthropic_style(provider_config):
    cfg = {**provider_config, "hkbu": {**provider_config["hkbu"], "base_url": "https://gw.example.test",
           "path_template": "{base_url}/v1/messages", "request_style": "anthropic_messages",
           "auth_header_name": "x-api-key", "auth_prefix": "", "send_temperature": False}}
    s = FakeSession(FakeResponse(200, {"content": [{"type": "text", "text": "yo"}],
                                       "usage": {"input_tokens": 3, "output_tokens": 4}}))
    r = p.make_provider("hkbu", "k-123456789", cfg, session=s).complete("S", "U", model="claude-x")
    assert r.text == "yo" and (r.input_tokens, r.output_tokens) == (3, 4)
    assert s.calls[0]["json"]["system"] == "S" and "temperature" not in s.calls[0]["json"]


def test_hkbu_bad_response_path(provider_config):
    cfg = {**provider_config, "hkbu": {**provider_config["hkbu"], "base_url": "https://gw.example.test",
           "response_text_path": "output.text"}}
    s = FakeSession(FakeResponse(200, openai_body("x")))
    with pytest.raises(p.ProviderError) as e:
        p.make_provider("hkbu", "k-123456789", cfg, session=s).complete("S", "U", model="m")
    assert e.value.kind == "bad_response"


def test_provider_switching_shares_meter(provider_config, replay_fixtures):
    meter = p.UsageMeter(request_cap=5)
    a = p.make_provider("anthropic", FAKE_ANTHROPIC_KEY, provider_config, meter,
                        session=FakeSession(FakeResponse(200, anthropic_body("A"))))
    h = p.make_provider("huggingface", FAKE_HF_TOKEN, provider_config, meter,
                        session=FakeSession(FakeResponse(200, openai_body("H"))))
    r = p.make_provider("replay", "", provider_config, meter, fixtures=replay_fixtures)
    assert isinstance(a, p.AnthropicProvider) and isinstance(h, p.HuggingFaceProvider)
    assert isinstance(r, p.ReplayProvider) and not r.is_live
    call(a), h.complete("S", "U", model="m")
    r.complete("S", "U", model="replay", replay_key={"challenge": "demo", "stage": "translator"})
    snap = meter.snapshot()
    assert snap["requests"] == 2 and snap["simulated_requests"] == 1


def test_request_cap(provider_config):
    meter = p.UsageMeter(request_cap=2)
    s = FakeSession(FakeResponse(200, anthropic_body("ok")))
    prov = anthropic(s, provider_config, meter=meter)
    call(prov), call(prov)
    with pytest.raises(p.ProviderError) as e:
        call(prov)
    assert e.value.kind == "cap_reached" and len(s.calls) == 2
    assert e.value.user_message.endswith(p.REPLAY_HINT)


def test_usage_meter_cost():
    m = p.UsageMeter(pricing={"claude-haiku-5-5": {"input_per_mtok": 0.1, "output_per_mtok": 0.5}})
    m.record(p.ModelResponse("x", "claude-haiku-5-5", 1_000_000, 1_000_000))
    assert m.snapshot()["est_cost_usd"] == pytest.approx(0.6)
    assert p.UsageMeter().snapshot()["est_cost_usd"] is None


def test_replay_provider(replay_fixtures):
    r = p.ReplayProvider(replay_fixtures)
    resp = r.complete("S", "U", replay_key={"challenge": "demo", "stage": "baseline",
                                           "string_ids": ["demo.ui.start"]})
    assert resp.simulated and resp.source == "replay" and '"demo.ui.start"' in resp.text
    assert "demo.choice.ask" not in resp.text
    with pytest.raises(p.ProviderError) as e:
        r.complete("S", "U", replay_key={"challenge": "nope", "stage": "baseline"})
    assert e.value.kind == "not_configured"
    assert r.test_connection()[0]


def test_test_connection(provider_config):
    ok_prov = anthropic(FakeSession(FakeResponse(200, anthropic_body("OK"))), provider_config)
    assert ok_prov.test_connection("claude-haiku-5-5")[0]
    bad = anthropic(FakeSession(FakeResponse(401, error_body("authentication_error", "x"))),
                    provider_config)
    ok, msg = bad.test_connection("claude-haiku-5-5")
    assert not ok and msg.endswith(p.REPLAY_HINT)


class SecretNotFoundError(Exception):
    pass


class FakeUserdata:
    def __init__(self, value=None, exc=None):
        self.value, self.exc = value, exc

    def get(self, name):
        if self.exc:
            raise self.exc
        return self.value


def test_load_api_key_from_colab(provider_config, capsys):
    key = p.load_api_key("anthropic", provider_config, userdata=FakeUserdata(FAKE_ANTHROPIC_KEY),
                         getpass_fn=lambda prompt: pytest.fail("should not prompt"))
    assert key == FAKE_ANTHROPIC_KEY
    assert FAKE_ANTHROPIC_KEY not in capsys.readouterr().out


@pytest.mark.parametrize("exc", [SecretNotFoundError("ANTHROPIC_API_KEY"), PermissionError("no access")])
def test_load_api_key_falls_back_to_getpass(provider_config, exc, capsys):
    prompts = []
    key = p.load_api_key("anthropic", provider_config, userdata=FakeUserdata(exc=exc),
                         getpass_fn=lambda prompt: prompts.append(prompt) or f"  {FAKE_ANTHROPIC_KEY}\n")
    assert key == FAKE_ANTHROPIC_KEY and prompts
    assert FAKE_ANTHROPIC_KEY not in capsys.readouterr().out


def test_load_api_key_empty(provider_config):
    with pytest.raises(p.ProviderError) as e:
        p.load_api_key("huggingface", provider_config, userdata=FakeUserdata(""),
                       getpass_fn=lambda prompt: "")
    assert e.value.kind == "no_key" and "HF_TOKEN" in e.value.user_message


def test_catalog_default_is_cheapest():
    cat = p.load_model_catalog()
    models = cat["anthropic"]["models"]
    cheapest = min(models, key=lambda m: m["pricing"]["input_per_mtok"])
    assert cat["anthropic"]["default"] == cheapest["id"] == "claude-haiku-5-5"
    assert {m["id"] for m in models} == {"claude-haiku-5-5", "claude-sonnet-5-5"}
    assert all(m["verified"] is False for m in cat["huggingface"]["models"])
    assert cat["hkbu"]["default"] in {m["id"] for m in cat["hkbu"]["models"]}
    assert all(m["verified"] is False for m in cat["hkbu"]["models"])


def test_provider_config_hkbu_gateway(provider_config):
    h = provider_config["hkbu"]
    assert h["base_url"] == "https://genai.hkbu.edu.hk/api/v1" and h["verified"] is False
    assert h["auth_prefix"] == "Bearer " and h["request_style"] == "openai_chat"
    for k in ("path_template", "auth_header_name", "auth_prefix", "extra_headers", "query_params",
              "request_style", "response_text_path", "notes"):
        assert k in h
    assert provider_config["limits"]["request_cap"] == 40


def test_mask_secrets():
    text = f"key={FAKE_ANTHROPIC_KEY} token {FAKE_HF_TOKEN} Bearer abcdefghijklmnop12345"
    masked = p.mask_secrets(text, [FAKE_ANTHROPIC_KEY])
    assert FAKE_ANTHROPIC_KEY not in masked and FAKE_HF_TOKEN not in masked
    assert "abcdefghijklmnop12345" not in masked


# ----------------------------------------------------------------- review fixes (v0.3.1)


def _with_headers(resp, headers):
    resp.headers = headers
    return resp


def test_meter_counts_every_http_attempt_including_retries(provider_config):
    meter = p.UsageMeter(request_cap=10)
    s = FakeSession(FakeResponse(429, error_body("rate_limit_error", "slow down")),
                    FakeResponse(529, error_body("overloaded_error", "Overloaded")),
                    FakeResponse(200, anthropic_body("OK")))
    assert call(anthropic(s, provider_config, meter=meter)).text == "OK"
    assert len(s.calls) == 3 and meter.requests == 3          # retries are real HTTP requests
    assert meter.snapshot()["input_tokens"] == 100            # tokens only from the reply


def test_cap_stops_retries_midway(provider_config):
    meter = p.UsageMeter(request_cap=2)
    s = FakeSession(FakeResponse(429, error_body("rate_limit_error", "slow down")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, meter=meter))
    assert e.value.kind == "cap_reached" and len(s.calls) == 2 and meter.requests == 2


def test_test_connection_is_counted(provider_config):
    meter = p.UsageMeter(request_cap=10)
    prov = anthropic(FakeSession(FakeResponse(200, anthropic_body("OK"))), provider_config, meter=meter)
    assert prov.test_connection("claude-haiku-5-5")[0] and meter.requests == 1


@pytest.mark.parametrize("header, expected", [("7", 7), ("120", p.MAX_RETRY_AFTER)])
def test_retry_after_is_honoured_and_bounded(provider_config, header, expected):
    sleeps = []
    s = FakeSession(_with_headers(FakeResponse(429, error_body("rate_limit_error", "slow")),
                                  {"retry-after": header}),
                    FakeResponse(200, anthropic_body("OK")))
    assert call(anthropic(s, provider_config, sleeps)).text == "OK"
    assert sleeps == [expected]


def test_backoff_has_jitter():
    sleeps = []
    s = FakeSession(FakeResponse(503, {"error": {"message": "down"}}))
    with pytest.raises(p.ProviderError):
        p.post_json(s, "https://x.test", {}, {}, provider="P", model="m", sleep=sleeps.append,
                    jitter=lambda base: base / 4)
    assert sleeps == [1.25, 3.75]


@pytest.mark.parametrize("status, etype, message, kind", [
    (400, "invalid_request_error", "max_tokens: 1300 > 1024, the maximum for this model", "bad_response"),
    (400, "invalid_request_error", "model: claude-nope", "invalid_model"),
    (422, "", "The model `x/y` does not exist", "invalid_model"),
    (400, "", "Unknown model 'abc'", "invalid_model"),
    (429, "", "Rate limit reached; see the billing page for higher tiers", "rate_limit"),
    (429, "insufficient_quota", "You exceeded your current quota", "rate_limit"),
    (400, "invalid_request_error", "Your credit balance is too low", "no_credit"),
    (400, "billing_error", "Payment problem", "no_credit"),
    (403, "permission_error", "Not allowed", "auth"),
    (400, "authentication_error", "invalid x-api-key", "auth"),
    (404, "not_found_error", "not found", "invalid_model"),
    (500, "overloaded_error", "Overloaded", "server"),
    (500, "", "quota service broken", "server"),
])
def test_error_classification_precedence(status, etype, message, kind):
    err = p.classify_http_error(status, message, "Claude", "m", error_type=etype)
    assert err.kind == kind, (status, etype, message, err.kind)
    assert err.retryable == (kind in ("rate_limit", "server"))


def test_error_type_field_is_read_from_the_reply(provider_config):
    s = FakeSession(FakeResponse(400, error_body("authentication_error", "bad key")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config))
    assert e.value.kind == "auth"
    body = {"error": {"message": "nope", "type": "invalid_request_error", "code": "model_not_found"}}
    assert p.classify_http_error(400, "nope", "HF", "m",
                                 error_type=p._error_details(FakeResponse(400, body))[0]).kind \
        == "invalid_model"


@pytest.mark.parametrize("exc", [requests.exceptions.InvalidURL("bad"),
                                 requests.exceptions.MissingSchema("no scheme"),
                                 requests.exceptions.InvalidHeader("bad header"),
                                 requests.exceptions.InvalidSchema("ftp")])
def test_bad_address_is_not_configured_and_not_retried(provider_config, exc):
    sleeps = []
    s = FakeSession(exc)
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config, sleeps))
    assert e.value.kind == "not_configured" and not e.value.retryable
    assert len(s.calls) == 1 and sleeps == []
    assert "the provider address is not set up correctly — ask your instructor" in e.value.user_message


def test_truncated_replies_are_flagged(provider_config):
    r = call(anthropic(FakeSession(FakeResponse(200, anthropic_body('{"tr', stop="max_tokens"))),
                       provider_config))
    assert r.stop_reason == "max_tokens" and r.truncated
    body = openai_body('{"tr')
    body["choices"][0]["finish_reason"] = "length"
    h = p.make_provider("huggingface", FAKE_HF_TOKEN, provider_config,
                        session=FakeSession(FakeResponse(200, body)))
    assert h.complete("S", "U", model="m").truncated
    cfg = {**provider_config, "hkbu": {**provider_config["hkbu"], "base_url": "https://gw.example.test",
                                       "request_style": "anthropic_messages",
                                       "response_text_path": "content.1.text"}}
    k = p.make_provider("hkbu", "k-123456789", cfg,
                        session=FakeSession(FakeResponse(200, anthropic_body("x", stop="max_tokens"))))
    assert k.complete("S", "U", model="m").truncated
    assert not call(anthropic(FakeSession(FakeResponse(200, anthropic_body("x"))), provider_config)).truncated


def test_prompt_with_the_key_is_never_sent(provider_config):
    s = FakeSession(FakeResponse(200, anthropic_body("x")))
    prov = anthropic(s, provider_config)
    with pytest.raises(p.ProviderError) as e:
        prov.complete("SYS", f"note {FAKE_ANTHROPIC_KEY}", model="claude-haiku-5-5")
    assert s.calls == [] and FAKE_ANTHROPIC_KEY not in e.value.user_message


# ----------------------------------------------------------------- live-API request options
# (thinking / effort per model from config/models.json, structured outputs, max_tokens)

def _all_objects(schema):
    """Every object-typed node in a JSON Schema."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for v in schema.values():
            yield from _all_objects(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _all_objects(v)


def test_haiku_body_thinking_disabled_effort_low_and_json_schema(provider_config):
    from src import agents as a
    schema = a.translations_json_schema(["intro.ui.start", "intro.ui.coins"])
    s = FakeSession(FakeResponse(200, anthropic_body('{"translations": []}')))
    anthropic(s, provider_config).complete("SYS", "USER", model="claude-haiku-5-5",
                                           json_schema=schema)
    body = s.calls[0]["json"]
    assert body["thinking"] == {"type": "disabled"}
    assert body["output_config"]["effort"] == "low"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"] == schema
    objs = list(_all_objects(fmt["schema"]))
    assert len(objs) == 2 and all(o["additionalProperties"] is False for o in objs)
    assert all(set(o["required"]) == set(o["properties"]) for o in objs)
    item = fmt["schema"]["properties"]["translations"]["items"]
    assert item["properties"]["id"]["enum"] == ["intro.ui.start", "intro.ui.coins"]
    assert body["max_tokens"] == p.DEFAULT_MAX_TOKENS == 4000      # the default
    assert "temperature" not in body and "top_p" not in body and "budget_tokens" not in str(body)


def test_sonnet_body_between_tools(provider_config):
    s = FakeSession(FakeResponse(200, anthropic_body("ok", model="claude-sonnet-5-5")))
    call(anthropic(s, provider_config), model="claude-sonnet-5-5")
    body = s.calls[0]["json"]
    assert body["thinking"] == {"type": "between_tools"}
    assert body["output_config"] == {"effort": "low"}


def test_request_options_are_data_driven(provider_config):
    cat = p.load_model_catalog()
    opts = p.request_options_from_catalog(cat, "anthropic")
    assert opts["claude-haiku-5-5"] == {"thinking": {"type": "disabled"}, "effort": "low"}
    assert opts["claude-sonnet-5-5"] == {"thinking": {"type": "between_tools"}, "effort": "low"}
    custom = {"anthropic": {"models": [{"id": "claude-haiku-5-5",
                                        "request_options": {"effort": "medium"}}]}}
    s = FakeSession(FakeResponse(200, anthropic_body("ok")))
    prov = p.make_provider("anthropic", FAKE_ANTHROPIC_KEY, provider_config, session=s,
                           model_catalog=custom)
    call(prov)
    assert "thinking" not in s.calls[0]["json"]
    assert s.calls[0]["json"]["output_config"] == {"effort": "medium"}


def test_thinking_400_retried_once_without_thinking(provider_config):
    sleeps = []
    meter = p.UsageMeter(request_cap=10)
    bad = FakeResponse(400, error_body("invalid_request_error",
                                       "thinking.type: 'disabled' is not supported for this model"))
    s = FakeSession(bad, FakeResponse(200, anthropic_body("ok")))
    prov = anthropic(s, provider_config, sleeps, meter)
    r = call(prov)
    assert r.text == "ok" and len(s.calls) == 2 and sleeps == []
    assert s.calls[0]["json"]["thinking"] == {"type": "disabled"}
    assert "thinking" not in s.calls[1]["json"]
    assert s.calls[1]["json"]["output_config"] == {"effort": "low"}
    assert meter.requests == 2
    assert len(prov.notes) == 1 and "without it" in prov.notes[0]
    call(prov)                                   # remembered: no second 400 for this model
    assert len(s.calls) == 3 and "thinking" not in s.calls[2]["json"]


def test_thinking_400_twice_raises_after_one_retry(provider_config):
    bad = FakeResponse(400, error_body("invalid_request_error", "thinking: unsupported value"))
    s = FakeSession(bad)
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config))
    assert e.value.status == 400 and len(s.calls) == 2
    assert_friendly(e.value)


def test_other_400_not_retried(provider_config):
    s = FakeSession(FakeResponse(400, error_body("invalid_request_error", "messages: field required")),
                    FakeResponse(200, anthropic_body("ok")))
    with pytest.raises(p.ProviderError) as e:
        call(anthropic(s, provider_config))
    assert e.value.kind == "bad_response" and len(s.calls) == 1


def test_other_providers_ignore_json_schema(provider_config, replay_fixtures):
    schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    s1, s2 = FakeSession(FakeResponse(200, openai_body("x"))), FakeSession(FakeResponse(200, openai_body("x")))
    h = p.make_provider("huggingface", FAKE_HF_TOKEN, provider_config, session=s1)
    h.complete("S", "U", model="m", temperature=0.2)
    h.complete("S", "U", model="m", temperature=0.2, json_schema=schema)
    assert s1.calls[0]["json"] == s1.calls[1]["json"]
    assert "response_format" not in s1.calls[1]["json"] and "thinking" not in s1.calls[1]["json"]
    cfg = {**provider_config, "hkbu": {**provider_config["hkbu"], "base_url": "https://gw.example.test"}}
    k = p.make_provider("hkbu", "k-123456789", cfg, session=s2)
    k.complete("S", "U", model="m", temperature=0.2)
    k.complete("S", "U", model="m", temperature=0.2, json_schema=schema)
    assert s2.calls[0]["json"] == s2.calls[1]["json"] and "response_format" not in s2.calls[1]["json"]
    assert s2.calls[0]["timeout"] == 45                 # the shared limit
    on = {**cfg, "hkbu": {**cfg["hkbu"], "supports_json_schema": True}}
    s3 = FakeSession(FakeResponse(200, openai_body("x")))
    p.make_provider("hkbu", "k-123456789", on, session=s3).complete("S", "U", model="m",
                                                                    json_schema=schema)
    assert s3.calls[0]["json"]["response_format"]["json_schema"]["schema"] == schema
    r = p.make_provider("replay", "", provider_config, fixtures=replay_fixtures)
    key = {"challenge": "demo", "stage": "translator"}
    assert (r.complete("S", "U", replay_key=key, json_schema=schema).text
            == r.complete("S", "U", replay_key=key).text)


def test_limits_max_tokens_configured(provider_config):
    assert provider_config["limits"]["max_tokens"] == 4000
    assert provider_config["anthropic"]["timeout_seconds"] == 90
    assert provider_config["hkbu"]["supports_json_schema"] is False
