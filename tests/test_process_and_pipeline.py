import json
import sys

import pytest

from creator_skill.errors import ExternalCommandError
from creator_skill.process import CommandRunner


def test_command_runner_audits_and_raises(tmp_path):
    audit = tmp_path / "commands.jsonl"
    runner = CommandRunner(audit)
    result = runner.run([sys.executable, "-c", "print('ok')"])
    assert result.stdout.strip() == "ok"
    record = json.loads(audit.read_text().splitlines()[0])
    assert record["returncode"] == 0
    with pytest.raises(ExternalCommandError):
        runner.run([sys.executable, "-c", "raise SystemExit(3)"])


def test_command_audit_redacts_secrets(tmp_path):
    audit = tmp_path / "commands.jsonl"
    runner = CommandRunner(audit)
    runner.run(
        [sys.executable, "-c", "pass", "--api-key", "secret-value"]
    )
    record = json.loads(audit.read_text())
    assert "secret-value" not in json.dumps(record)
    assert "***REDACTED***" in record["args"]
