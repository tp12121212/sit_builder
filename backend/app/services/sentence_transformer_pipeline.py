from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings


@dataclass
class PhraseResult:
    stream_name: str
    phrase: str
    score: float


def _extract_json_payload(raw_output: str) -> list[dict]:
    text = (raw_output or "").strip()
    if not text:
        raise RuntimeError("PowerShell output was empty")

    # Remove ANSI color/control sequences that can contain "[" and break naive parsing.
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)

    # Prefer strict parse when script output is clean JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fallback: find first decodable JSON object/array inside mixed logs/output.
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed

    raise RuntimeError("Unexpected response format from keyword_extraction.py")


def _resolve_path(path_value: Path) -> Path:
    return path_value if path_value.is_absolute() else (Path.cwd() / path_value).resolve()


def _build_command(
    file_path: str,
    user_principal_name: str | None,
    organization: str | None,
    preserve_case: bool,
) -> list[str]:
    settings = get_settings()
    script_path = _resolve_path(settings.sentence_transformer_powershell_script)
    python_script_path = _resolve_path(settings.sentence_transformer_python_script)
    python_executable = settings.sentence_transformer_python_executable.strip()

    if not script_path.exists():
        raise RuntimeError(f"PowerShell script not found: {script_path}")
    if not python_script_path.exists():
        raise RuntimeError(f"Python keyword extraction script not found: {python_script_path}")

    pwsh = shutil.which("pwsh")
    if not pwsh:
        raise RuntimeError("pwsh is not installed or not found in PATH")

    # For local development, prefer the same interpreter as the running backend
    # when the configured value is a generic python command.
    if python_executable in {"python", "python3"}:
        python_executable = sys.executable or python_executable

    args = [
        pwsh,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-PythonScriptPath",
        str(python_script_path),
        "-PythonExecutable",
        python_executable,
    ]
    if user_principal_name:
        args.extend(["-UserPrincipalName", user_principal_name])
    if organization:
        args.extend(["-Organization", organization])
    if preserve_case:
        args.append("-PreserveCase")

    if platform.system().lower().startswith("win"):
        args.extend(["-WinFile", file_path])
    else:
        args.extend(["-MacFile", file_path])

    return args


def run_sentence_transformer_scan(
    file_path: str,
    user_principal_name: str | None,
    exchange_access_token: str,
    organization: str | None = None,
    preserve_case: bool = False,
) -> list[PhraseResult]:
    command = _build_command(
        file_path=file_path,
        user_principal_name=user_principal_name,
        organization=organization,
        preserve_case=preserve_case,
    )

    env = {**os.environ, "EXO_ACCESS_TOKEN": exchange_access_token}

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(Path.cwd()),
        env=env,
        check=False,
    )

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr if stderr else stdout
        raise RuntimeError(f"SentenceTransformer scan failed: {detail}")

    try:
        streams = _extract_json_payload(completed.stdout)
    except Exception as exc:
        stdout_preview = (completed.stdout or "").strip()[:1200]
        stderr_preview = (completed.stderr or "").strip()[:1200]
        raise RuntimeError(
            "SentenceTransformer scan failed: unable to parse JSON output. "
            f"stdout={stdout_preview!r} stderr={stderr_preview!r}"
        ) from exc

    results: list[PhraseResult] = []
    for stream in streams:
        if stream.get("status") != "success":
            continue

        stream_name = str(stream.get("stream_name", "Unknown"))
        for item in stream.get("top_bigrams", []):
            phrase = str(item.get("phrase", "")).strip()
            if not phrase:
                continue
            score = float(item.get("score", 0.0))
            results.append(PhraseResult(stream_name=stream_name, phrase=phrase, score=score))

    return results
