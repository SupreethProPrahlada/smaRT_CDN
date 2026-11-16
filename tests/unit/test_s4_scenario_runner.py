import os
from pathlib import Path
from types import SimpleNamespace

import tests.run_scenarios as runner


def test_start_controller_exposes_project_root_for_ryu_app_import(monkeypatch):
    captured = {}

    class Process:
        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        captured.update(kwargs)
        return Process()

    checks = iter((False, True))
    monkeypatch.setattr(runner.shutil, "which", lambda _name: None)
    monkeypatch.setattr(runner.Path, "is_file", lambda _self: True)
    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runner, "port_open", lambda *_args: next(checks))
    monkeypatch.setattr(runner.os, "environ", {"PATH": os.environ.get("PATH", "")})

    runner.start_controller("dynamic")

    env = captured["env"]
    assert str(runner.PROJECT_ROOT) in env["PYTHONPATH"].split(os.pathsep)
    assert env["CDN_MODE"] == "dynamic"
    assert captured["cwd"] == str(runner.PROJECT_ROOT)
