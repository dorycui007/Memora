"""Shared JSON extraction utility for parsing LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from LLM response text.

    Tries in order:
    1. Direct JSON parse (text starts with '{')
    2. Fenced code block extraction (```json ... ```)
    3. Brace-matching extraction (find first '{' and match to closing '}')

    Raises ValueError if no valid JSON found.
    """
    text = text.strip()

    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    matches = re.findall(pattern, text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    brace_start = text.find("{")
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start:i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"No valid JSON found in response: {text[:200]}...")
