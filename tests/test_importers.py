import json

import pytest

from src.importers import ImportRejected, import_upload, MAX_BYTES
from src import validation as v


def test_txt_import():
    ch = import_upload("scene.txt", "開始調查\n\n  {player_name}，你好！  \n第三句\n".encode())
    assert ch["id"] == "custom" and ch["mission"] == "custom"
    assert [s["id"] for s in ch["strings"]] == ["custom.text.001", "custom.text.002", "custom.text.003"]
    assert ch["strings"][1]["source"] == "{player_name}，你好！"
    assert ch["strings"][1]["placeholders"] == ["{player_name}"]
    assert all(v.ID_RE.match(s["id"]) for s in ch["strings"])
    assert v.spec_from_challenge(ch)["custom.text.001"].max_len is None


def test_csv_import_with_optional_columns():
    data = ("﻿source,id,context,max_len,speaker\n"
            '開始,btn_start,Start button,12,\n'
            '"你好,朋友",line1,Greeting,,黃婆婆\n').encode("utf-8")
    ch = import_upload("strings.CSV", data)
    s1, s2 = ch["strings"]
    assert s1["max_len"] == 12 and "Maximum 12 characters" in s1["constraints"]
    assert "original id: btn_start" in s1["context"]
    assert s2["source"] == "你好,朋友" and s2["type"] == "dialogue"
    assert ch["characters"][0]["name_zh"] == "黃婆婆" and s2["speaker"] == ch["characters"][0]["id"]


def test_csv_requires_source_header():
    with pytest.raises(ImportRejected) as e:
        import_upload("x.csv", b"text,id\nhello,1\n")
    assert "source" in e.value.user_message


def test_csv_bad_max_len():
    with pytest.raises(ImportRejected) as e:
        import_upload("x.csv", "source,max_len\n你好,abc\n".encode())
    assert "Row 1" in e.value.user_message


def test_json_list_and_challenge():
    ch = import_upload("a.json", json.dumps([{"source": "你好", "context": "hi", "max_len": 10},
                                             {"source": "再見"}], ensure_ascii=False).encode())
    assert len(ch["strings"]) == 2 and ch["strings"][0]["max_len"] == 10
    full = {"id": "intro", "title": "T", "scene_context": "S", "glossary": [{"source": "a", "target": "b"}],
            "strings": [{"id": "intro.ui.start", "source": "開始"}],
            "instructor_notes": {"deliberate_traps": ["TRAP"]}}
    ch2 = import_upload("c.json", json.dumps(full, ensure_ascii=False).encode())
    assert ch2["scene_context"] == "S" and ch2["glossary"] == [{"source": "a", "target": "b"}]
    assert "TRAP" not in json.dumps(ch2, ensure_ascii=False)


@pytest.mark.parametrize("name,data,needle", [
    ("a.json", b'{"strings": [], "strings": []}', "repeats a key"),
    ("a.json", b"{oops", "not valid JSON"),
    ("a.json", b'"just a string"', "challenge file or a list"),
    ("a.json", b'[{"context": "no source"}]', "no source"),
    ("a.txt", b"\n\n   \n", "No strings"),
    ("a.docx", b"hello", ".txt, .csv or .json"),
    ("a.txt", "caf\xe9".encode("latin-1"), "UTF-8"),
    ("a.txt", b"x" * (MAX_BYTES + 1), "limit is 200 KB"),
    ("a.txt", ("\n".join(f"line {i}" for i in range(201))).encode(), "more than 200"),
    ("a.csv", ("source\n" + "\n".join(f"line {i}" for i in range(201))).encode(), "more than 200"),
    ("a.txt", ("長" * 501).encode(), "limit is 500"),
    ("a.txt", "bell\x07here".encode(), "control"),
    ("a.json", b'[{"source": "bad \\ud800 text"}]', "control"),
])
def test_rejections(name, data, needle):
    with pytest.raises(ImportRejected) as e:
        import_upload(name, data)
    assert needle in e.value.user_message


def test_html_looking_text_kept_as_plain_text():
    payload = '<script>alert(1)</script>\n<img src=x onerror=alert(1)>\nplain'
    ch = import_upload("x.txt", payload.encode())
    assert ch["strings"][0]["source"] == "<script>alert(1)</script>"
    assert ch["strings"][1]["source"] == "<img src=x onerror=alert(1)>"
    assert len(ch["import_warnings"]) == 2 and "plain text" in ch["import_warnings"][0]


def test_exactly_at_limits_accepted():
    ch = import_upload("a.txt", "\n".join("a" * 500 for _ in range(200)).encode())
    assert len(ch["strings"]) == 200
