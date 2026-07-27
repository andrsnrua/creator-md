from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Sequence

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
        check: bool = True,
    ) -> CommandResult:
        command = [str(arg) for arg in args]
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=merged_env,
            text=True,
            capture_output=True,
            check=False,
        )
        result = CommandResult(
            command, completed.returncode, completed.stdout, completed.stderr
        )
        self._audit(result, cwd)
        if check and result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or "no output"
            raise ExternalCommandError(
                f"Command failed ({result.returncode}): {' '.join(command)}\n{detail}"
            )
        return result

    def _audit(self, result: CommandResult, cwd: Path | None) -> None:
        if not self.audit_path:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "cwd": str(cwd) if cwd else None,
            "args": result.args,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

