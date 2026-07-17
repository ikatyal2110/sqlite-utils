"""LLM adapter: headless `claude -p`.

Uses the Claude Code CLI so the tool inherits the machine's existing Claude
auth — no API keys to manage. Falls back to the ANTHROPIC_API_KEY-based
`anthropic` SDK if the CLI is unavailable.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

DEFAULT_MODEL = "sonnet"


class LLMError(RuntimeError):
    pass


def complete(prompt: str, *, system: str | None = None, model: str = DEFAULT_MODEL,
             timeout: int = 600) -> str:
    """Run a single completion and return the text response."""
    if shutil.which("claude"):
        return _complete_cli(prompt, system=system, model=model, timeout=timeout)
    return _complete_sdk(prompt, system=system, model=model)


def _complete_cli(prompt: str, *, system: str | None, model: str, timeout: int) -> str:
    cmd = ["claude", "-p", "--model", model]
    if system:
        cmd += ["--append-system-prompt", system]
    proc = subprocess.run(
        cmd, input=prompt, text=True, capture_output=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise LLMError(f"claude CLI failed ({proc.returncode}): {proc.stderr[:2000]}")
    return proc.stdout.strip()


def _complete_sdk(prompt: str, *, system: str | None, model: str) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("Neither `claude` CLI nor `anthropic` SDK available") from e
    client = anthropic.Anthropic()
    model_ids = {"sonnet": "claude-sonnet-5", "opus": "claude-opus-4-8",
                 "haiku": "claude-haiku-4-5-20251001"}
    msg = client.messages.create(
        model=model_ids.get(model, model),
        max_tokens=8192,
        system=system or anthropic.NOT_GIVEN,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def complete_json(prompt: str, *, system: str | None = None,
                  model: str = DEFAULT_MODEL, retries: int = 2) -> Any:
    """Completion that must return JSON; extracts and parses it, with retries."""
    last_err: Exception | None = None
    p = prompt
    for _ in range(retries + 1):
        text = complete(p, system=system, model=model)
        try:
            return extract_json(text)
        except ValueError as e:
            last_err = e
            p = (prompt + "\n\nYour previous reply was not valid JSON "
                 f"({e}). Reply with ONLY the JSON, no prose, no code fences.")
    raise LLMError(f"LLM did not return valid JSON: {last_err}")


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of an LLM reply."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text
    candidate = candidate.strip()
    start = min((i for i in (candidate.find("{"), candidate.find("[")) if i >= 0),
                default=-1)
    if start == -1:
        raise ValueError("no JSON object found in reply")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(candidate[start:])
    return obj


def extract_code(text: str, language: str = "python") -> str:
    """Pull a fenced code block out of an LLM reply (or return the raw text)."""
    fence = re.search(rf"```(?:{language})?\s*\n(.*?)```", text, re.DOTALL)
    return (fence.group(1) if fence else text).strip()
