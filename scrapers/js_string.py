from __future__ import annotations

import json
import re

# Content of a JS double-quoted string passed to JSON.parse("…"), with escapes preserved.
_JS_JSON_PARSE_INNER = re.compile(
    r'JSON\.parse\("((?:\\.|[^"\\])*)"\)',
)


def decode_js_string_literal(raw: str) -> str:
    """Decode a JS string literal body (without surrounding quotes)."""
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(raw):
            break
        esc = raw[i]
        i += 1
        if esc == "n":
            out.append("\n")
        elif esc == "r":
            out.append("\r")
        elif esc == "t":
            out.append("\t")
        elif esc == '"':
            out.append('"')
        elif esc == "\\":
            out.append("\\")
        elif esc == "u" and i + 4 <= len(raw):
            out.append(chr(int(raw[i : i + 4], 16)))
            i += 4
        elif esc == "u" and i + 8 <= len(raw) and raw[i] == "{":
            # \u{1F600} — skip brace form for now; consume hex until }
            j = raw.find("}", i)
            if j != -1:
                hex_part = raw[i + 1 : j]
                out.append(chr(int(hex_part, 16)))
                i = j + 1
            else:
                out.append(esc)
        else:
            out.append(esc)
    return "".join(out)


def extract_json_parse_payload(html: str, *, marker: str | None = None) -> dict | list | None:
    haystack = html
    if marker is not None:
        start = html.find(marker)
        if start == -1:
            return None
        haystack = html[start : start + 500_000]
    match = _JS_JSON_PARSE_INNER.search(haystack)
    if not match:
        return None
    inner = decode_js_string_literal(match.group(1))
    try:
        return json.loads(inner)
    except json.JSONDecodeError:
        return None
