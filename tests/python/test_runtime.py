import json
import os
import subprocess
import sys
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]


def test_python_cli_clean_start_stop_backup_restore_and_gc(tmp_path):
    directory = tmp_path / "runtime"
    env = {**os.environ, "PYTHONUTF8": "1", "XUEYA_DATA_DIR": str(directory), "PORT": "0", "MIMO_API_KEY": "", "XUEYA_PLATFORM_ENABLED": "1"}

    def cli(*args):
        result = subprocess.run([sys.executable, "-X", "utf8", "-m", "backend.xueya.cli", *map(str, args)], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
        assert result.returncode == 0, result.stderr
        return result.stdout

    assert json.loads(cli("doctor"))["pythonRequired"] is True
    assert not json.loads(cli("doctor"))["gpuRequired"]
    assert json.loads(cli("init"))["ok"]
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    cli("backup", backup)
    cli("restore", backup, restored)
    assert (restored / "workspace.sqlite").is_file()
    cli("export", tmp_path / "export.json")
    assert json.loads(cli("gc"))["dryRun"]
    assert not json.loads(cli("gc", "--apply"))["dryRun"]
    with subprocess.Popen([sys.executable, "-X", "utf8", "-m", "backend.xueya.server"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        try:
            ready = False
            for _ in range(150):
                assert process.poll() is None, "Python host exited before startup"
                try:
                    info = json.loads((directory / "server.json").read_text(encoding="utf-8"))
                    response = httpx.get("http://127.0.0.1:"+str(info["port"])+"/api/health", timeout=.2)
                    if response.is_success:
                        ready = True
                        assert response.json()["instanceId"] == info["instanceId"]
                        break
                except (OSError, ValueError, httpx.HTTPError):
                    pass
                time.sleep(.03)
            assert ready
            second = subprocess.run([sys.executable, "-m", "backend.xueya.server"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
            assert second.returncode != 0 and "ANOTHER_PLATFORM_INSTANCE_RUNNING" in second.stderr
            cli("stop")
            process.wait(timeout=10)
            assert process.returncode == 0, process.stderr.read()
            assert not (directory / "server.json").exists()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
