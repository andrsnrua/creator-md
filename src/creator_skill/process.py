from __future__ import annotations

import json
import os
import sys
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .errors import ExternalCommandError


@dataclass(slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def __init__(self, audit_path: Path | None = None):
        self.audit_path = audit_path

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        input_text: str | None = None,
        capture_output: bool = True,
        check: bool = True,
        on_output: Callable[[str, str], None] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        command = [str(arg) for arg in args]
        if command[0] == "yt-dlp":
            node = shutil.which("node")
            bundled_node = Path(sys.executable).parent.parent / "node" / "bin" / "node.exe"
            if not node and bundled_node.exists():
                node = str(bundled_node)
            if node:
                command += ["--js-runtimes", "node:" + node]
        if command[0] == "yt-dlp" and ((Path(__file__).resolve().parents[2] / ".venv/runtime-packages/yt_dlp").exists() or not shutil.which("yt-dlp")):
            entrypoint = Path(__file__).resolve().parents[2] / "run.py"
            command = [sys.executable, str(entrypoint), "ytdlp", *command[1:]]
        merged_env = os.environ.copy()
        merged_env.setdefault("PYTHONIOENCODING", "utf-8")
        if env:
            merged_env.update(env)
        if on_output is None:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=merged_env,
                text=True,
                encoding="utf-8", errors="replace",
                capture_output=capture_output,
                input=input_text,
                check=False,
                timeout=timeout,
            )
            result = CommandResult(
                command,
                completed.returncode,
                completed.stdout or "",
                completed.stderr or "",
            )
        else:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=merged_env,
                text=True,
                encoding="utf-8", errors="replace",
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
            )
            stdout: list[str] = []
            stderr: list[str] = []

            def consume(stream, name: str, destination: list[str]) -> None:
                if stream is None:
                    return
                for line in iter(stream.readline, ""):
                    destination.append(line)
                    on_output(name, line)
                stream.close()

            readers = [
                threading.Thread(
                    target=consume,
                    args=(process.stdout, "stdout", stdout),
                ),
                threading.Thread(
                    target=consume,
                    args=(process.stderr, "stderr", stderr),
                ),
            ]
            for reader in readers:
                reader.start()
            if input_text is not None and process.stdin is not None:
                process.stdin.write(input_text)
                process.stdin.close()
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                for reader in readers:
                    reader.join(timeout=2)
                raise
            for reader in readers:
                reader.join()
            result = CommandResult(
                command,
                returncode,
                "".join(stdout),
                "".join(stderr),
            )
        self._audit(result, cwd)
        if check and result.returncode:
            detail = "\n".join(
                part for part in (result.stdout.strip(), result.stderr.strip()) if part
            ) or "no output"
            raise ExternalCommandError(
                f"Command failed ({result.returncode}): {' '.join(command)}\n{detail}"
            )
        return result

    def _audit(self, result: CommandResult, cwd: Path | None) -> None:
        if not self.audit_path:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        safe_args = list(result.args)
        secret_flags = {"--api-key", "--token", "--password"}
        for index, value in enumerate(safe_args):
            if index and safe_args[index - 1] in secret_flags:
                safe_args[index] = "***REDACTED***"
            elif any(value.startswith(flag + "=") for flag in secret_flags):
                safe_args[index] = value.split("=", 1)[0] + "=***REDACTED***"
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "cwd": str(cwd) if cwd else None,
            "args": safe_args,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
