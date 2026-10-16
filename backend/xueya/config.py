"""Environment is read only by the host; never sent to the frontend."""
from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    root: Path = ROOT
    data_dir: Path = ROOT / ".xueya-data"
    port: int = 4173
    api_key: str = ""
    base_url: str = "https://api.xiaomimimo.com/v1"
    model: str = "mimo-v2.6-flash"
    api_slots: int = 2
    platform_enabled: bool = True
    tool_timeout: float = 5.0


def load_config() -> Config:
    env = dict(os.environ)
    file = ROOT / ".env"
    if file.exists():
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip("\"'"))
    key = env.get("MIMO_API_KEY", "")
    if key == "replace_with_your_key":
        key = ""
    return Config(data_dir=Path(env.get("XUEYA_DATA_DIR", ROOT / ".xueya-data")).resolve(),
                  port=int(env.get("PORT", 4173)), api_key=key,
                  base_url=env.get("MIMO_BASE_URL", Config.base_url), model=env.get("MIMO_MODEL", Config.model),
                  api_slots=max(1, min(8, int(env.get("API_MAX_CONCURRENT", 2)))),
                  platform_enabled=env.get("XUEYA_PLATFORM_ENABLED", "1") != "0",
                  tool_timeout=max(.05, min(60, float(env.get("MCP_TOOL_TIMEOUT_MS", 5000))/1000)))
