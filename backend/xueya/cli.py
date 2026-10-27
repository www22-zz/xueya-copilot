"""Python maintenance CLI. Backups/doctor never run startup recovery on live data."""
import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
import httpx
from .backup import create_backup, inventory, restore_backup
from .common import AppError, dumps, require
from .config import load_config
from .platform import Platform


async def main(args=None):
    parser = argparse.ArgumentParser(description="学涯 Copilot 本地工程工具")
    parser.add_argument("command", nargs="?", default="doctor", choices=["doctor", "init", "backup", "restore", "export", "gc", "stop"])
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--apply", action="store_true", help="实际清理无历史版本引用的原件；默认只预览")
    options = parser.parse_args(args)
    config, command = load_config(), options.command
    if command == "doctor":
        print(json.dumps({"python": sys.version.split()[0], "pythonSupported": sys.version_info >= (3, 11), "sqlite": sqlite3.sqlite_version, "dataDir": str(config.data_dir), "model": config.model, "apiConfigured": bool(config.api_key), "inference": "external-api-only", "pythonRequired": True, "gpuRequired": False}, ensure_ascii=False, indent=2))
        require(sys.version_info >= (3, 11), "PYTHON_VERSION_UNSUPPORTED")
        return
    if command == "restore":
        require(len(options.paths) == 2, "RESTORE_REQUIRES_SOURCE_AND_NEW_DESTINATION")
        print(dumps(restore_backup(*options.paths)))
        return
    if command == "backup":
        require(len(options.paths) == 1, "BACKUP_REQUIRES_NEW_DESTINATION")
        print(dumps(create_backup(config.data_dir, options.paths[0])))
        return
    if command == "stop":
        lock = config.data_dir / "server.json"
        require(lock.exists(), "SERVER_PID_NOT_FOUND")
        info = json.loads(lock.read_text(encoding="utf-8"))
        async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as client:
            base = "http://127.0.0.1:"+str(int(info["port"]))
            response = await client.get(base+"/api/health")
            require(response.json().get("instanceId") == info["instanceId"], "SERVER_IDENTITY_MISMATCH")
            response = await client.post(base+"/api/platform/shutdown", headers={"X-Xueya-Stop": info["stopToken"]})
            require(response.is_success, "STOP_REJECTED")
        print("已请求安全停止")
        return
    platform = Platform(config.data_dir, config.api_slots, recover=False, preserve_legacy_data=config.preserve_legacy_data)
    try:
        if command == "init":
            print(dumps({"ok": True, "dataDir": str(config.data_dir), "courses": platform.repo.courses(platform.user_id)}))
        elif command == "export":
            require(len(options.paths) == 1 and not Path(options.paths[0]).exists(), "EXPORT_REQUIRES_NEW_FILE")
            with Path(options.paths[0]).open("x", encoding="utf-8") as stream:
                json.dump({"schemaVersion": 1, "workspace": platform.repo.get_workspace(platform.user_id), "courses": platform.repo.courses(platform.user_id)}, stream, ensure_ascii=False, indent=2)
            print("导出完成")
        elif command == "gc":
            refs = {value["fileHash"] for row in platform.db.all("SELECT data FROM revisions WHERE kind='document'") if (value := json.loads(row["data"])).get("fileHash")}
            refs.update(value['bundleHash'] for row in platform.db.all("SELECT input FROM jobs WHERE type='rag-prepared-pdf'")
                        if (value := json.loads(row['input'])).get('bundleHash'))
            candidates = [f for f in inventory(platform.files) if f["hash"] not in refs]
            if options.apply:
                for file in candidates:
                    platform.files.path(file["hash"]).unlink()
            print(dumps({"dryRun": not options.apply, "candidates": candidates}))
    finally:
        await platform.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AppError as error:
        print(error.code, file=sys.stderr)
        raise SystemExit(1)
