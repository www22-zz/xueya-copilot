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
    max_output_tokens: int = 4096
    run_model_calls: int = 10
    run_tool_calls: int = 12
    run_output_tokens: int = 32768
    run_timeout: float = 300.0
    run_budget_cny: str = '0'
    input_cny_per_million: str = '0'
    output_cny_per_million: str = '0'
    agent_planning_enabled: bool = True
    agent_max_rounds: int = 8
    agent_max_replans: int = 2
    agent_no_progress_limit: int = 2
    agent_decision_tokens: int = 1536

    def __post_init__(self):
        from .common import require
        from .execution_budget import decimal_setting
        for value in (self.max_output_tokens, self.run_model_calls, self.run_tool_calls, self.run_output_tokens):
            require(type(value) is int and value > 0, 'AI_INVALID_BUDGET_CONFIG')
        import math
        require(math.isfinite(self.run_timeout) and self.run_timeout > 0, 'AI_INVALID_BUDGET_CONFIG')
        for value in (self.run_budget_cny, self.input_cny_per_million, self.output_cny_per_million):
            decimal_setting(value)
        require(type(self.agent_planning_enabled) is bool, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.agent_max_rounds) is int and 1 <= self.agent_max_rounds <= 24, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.agent_max_replans) is int and 0 <= self.agent_max_replans <= 4, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.agent_no_progress_limit) is int and 1 <= self.agent_no_progress_limit <= 4, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.agent_decision_tokens) is int and 1 <= self.agent_decision_tokens <= 16384, 'AI_INVALID_BUDGET_CONFIG')


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
                  tool_timeout=max(.05, min(60, float(env.get("MCP_TOOL_TIMEOUT_MS", 5000))/1000)),
                  max_output_tokens=int(env.get('AI_MAX_OUTPUT_TOKENS', 4096)),
                  run_model_calls=int(env.get('AI_RUN_MAX_MODEL_CALLS', 10)),
                  run_tool_calls=int(env.get('AI_RUN_MAX_TOOL_CALLS', 12)),
                  run_output_tokens=int(env.get('AI_RUN_MAX_OUTPUT_TOKENS', 32768)),
                  run_timeout=float(env.get('AI_RUN_TIMEOUT_SECONDS', 300)),
                  run_budget_cny=env.get('AI_RUN_BUDGET_CNY', '0'),
                  input_cny_per_million=env.get('AI_INPUT_CNY_PER_MILLION', '0'),
                  output_cny_per_million=env.get('AI_OUTPUT_CNY_PER_MILLION', '0'),
                  agent_planning_enabled=env.get('AI_AGENT_PLANNING_ENABLED', '1') == '1',
                  agent_max_rounds=int(env.get('AI_AGENT_MAX_ROUNDS', 8)),
                  agent_max_replans=int(env.get('AI_AGENT_MAX_REPLANS', 2)),
                  agent_no_progress_limit=int(env.get('AI_AGENT_NO_PROGRESS_LIMIT', 2)),
                  agent_decision_tokens=int(env.get('AI_AGENT_DECISION_TOKENS', 1536)))
