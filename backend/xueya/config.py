"""Environment is read only by the host; never sent to the frontend."""
from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
# Bumped together with the inline constant in frontend/index.html. A stale page
# compares this against /api/health and reloads once after a deployment.
UI_BUILD = '2026-11-15-course-shelf-cache-1'


@dataclass(frozen=True)
class Config:
    root: Path = ROOT
    data_dir: Path = ROOT / ".xueya-data"
    port: int = 4173
    api_key: str = ""
    tavily_api_key: str = ""
    base_url: str = "https://api.xiaomimimo.com/v1"
    model: str = "mimo-v2.6-flash"
    api_slots: int = 2
    platform_enabled: bool = True
    auto_import_demo: bool = False
    auto_import_stack: bool = False
    auto_import_corpus: bool = False
    preserve_legacy_data: bool = False
    rag_general_fallback: bool = False
    tool_timeout: float = 5.0
    max_output_tokens: int = 4096
    # Host-owned answer-latency controls. Dataclass defaults keep the legacy
    # behavior for callers that build Config directly (tests/tools);
    # load_config() below opts the running host into the faster values unless
    # the operator overrides them in .env.
    answer_output_tokens: int = 4096
    retrieval_limit: int = 6
    review_shards: int = 2
    review_shard_min_claims: int = 4
    answer_repair_enabled: bool = False
    answer_repair_tokens: int = 1024
    draft_streaming: bool = False
    early_review: bool = False
    early_review_failfast: bool = False
    api_queue_timeout: float = 0.0
    answer_cache_ttl: int = 0
    planner_thinking_disabled: bool = False
    answer_thinking_disabled: bool = False
    prose_review: bool = True
    general_route_min_score: float = 0.0
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
    agent_durable_enabled: bool = True
    agent_interactive_enabled: bool = True
    agent_rollout_percent: int = 100

    def __post_init__(self):
        from .common import require
        from .execution_budget import decimal_setting
        require(type(self.auto_import_demo) is bool, 'INVALID_DEMO_IMPORT_CONFIG')
        require(type(self.preserve_legacy_data) is bool, 'INVALID_PRESERVATION_CONFIG')
        require(type(self.rag_general_fallback) is bool, 'INVALID_GENERAL_FALLBACK_CONFIG')
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
        require(type(self.agent_durable_enabled) is bool and type(self.agent_interactive_enabled) is bool, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.agent_rollout_percent) is int and 0 <= self.agent_rollout_percent <= 100, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.answer_output_tokens) is int and 256 <= self.answer_output_tokens <= 16384, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.retrieval_limit) is int and 1 <= self.retrieval_limit <= 6, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.review_shards) is int and 1 <= self.review_shards <= 3, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.review_shard_min_claims) is int and 1 <= self.review_shard_min_claims <= 12, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.answer_repair_tokens) is int and 256 <= self.answer_repair_tokens <= 4096, 'AI_INVALID_BUDGET_CONFIG')
        require(type(self.answer_cache_ttl) is int and 0 <= self.answer_cache_ttl <= 604800, 'AI_INVALID_BUDGET_CONFIG')
        require(math.isfinite(self.api_queue_timeout) and 0 <= self.api_queue_timeout <= 60, 'AI_INVALID_BUDGET_CONFIG')
        require(math.isfinite(self.general_route_min_score) and self.general_route_min_score >= 0, 'AI_INVALID_BUDGET_CONFIG')
        for value in (self.answer_repair_enabled, self.draft_streaming, self.early_review, self.early_review_failfast,
                      self.planner_thinking_disabled, self.answer_thinking_disabled, self.prose_review):
            require(type(value) is bool, 'AI_INVALID_BUDGET_CONFIG')


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
                  tavily_api_key=env.get("TAVILY_API_KEY", "").strip("\"'"),
                  base_url=env.get("MIMO_BASE_URL", Config.base_url), model=env.get("MIMO_MODEL", Config.model),
                  api_slots=max(1, min(8, int(env.get("API_MAX_CONCURRENT", 4)))),
                  platform_enabled=env.get("XUEYA_PLATFORM_ENABLED", "1") != "0",
                  auto_import_demo=env.get('XUEYA_AUTO_IMPORT_DEMO', '0') == '1',
                  auto_import_stack=env.get('XUEYA_AUTO_IMPORT_STACK', '1') == '1',
                  auto_import_corpus=env.get('XUEYA_AUTO_IMPORT_CORPUS', '1') == '1',
                  preserve_legacy_data=env.get('XUEYA_PRESERVE_LEGACY_DATA', '0') == '1',
                  rag_general_fallback=env.get('AI_RAG_GENERAL_FALLBACK', '0') == '1',
                  tool_timeout=max(.05, min(60, float(env.get("MCP_TOOL_TIMEOUT_MS", 5000))/1000)),
                  max_output_tokens=int(env.get('AI_MAX_OUTPUT_TOKENS', 4096)),
                  answer_output_tokens=max(256, min(16384, int(env.get('AI_ANSWER_OUTPUT_TOKENS', '3072')))),
                  retrieval_limit=max(1, min(6, int(env.get('AI_ANSWER_SOURCE_LIMIT', '4')))),
                  review_shards=max(1, min(3, int(env.get('AI_REVIEW_SHARDS', '2')))),
                  review_shard_min_claims=max(1, min(12, int(env.get('AI_REVIEW_SHARD_MIN_CLAIMS', '4')))),
                  answer_repair_enabled=env.get('AI_ANSWER_REPAIR', '1') == '1',
                  answer_repair_tokens=max(256, min(4096, int(env.get('AI_ANSWER_REPAIR_TOKENS', '1024')))),
                  draft_streaming=env.get('AI_DRAFT_STREAMING', '1') == '1',
                  early_review=env.get('AI_EARLY_REVIEW', '1') == '1',
                  early_review_failfast=env.get('AI_EARLY_REVIEW_FAILFAST', '1') == '1',
                  api_queue_timeout=max(0.0, min(60.0, float(env.get('AI_API_QUEUE_TIMEOUT_SECONDS', '12')))),
                  answer_cache_ttl=max(0, min(604800, int(env.get('AI_ANSWER_CACHE_TTL_SECONDS', '86400')))),
                  planner_thinking_disabled=env.get('AI_PLANNER_NO_THINKING', '1') == '1',
                  answer_thinking_disabled=env.get('AI_ANSWER_NO_THINKING', '0') == '1',
                  prose_review=env.get('AI_PROSE_REVIEW', '0') == '1',
                  general_route_min_score=max(0.0, float(env.get('AI_GENERAL_ROUTE_MIN_SCORE', '0'))),
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
                  agent_decision_tokens=int(env.get('AI_AGENT_DECISION_TOKENS', 1536)),
                  agent_durable_enabled=env.get('AI_AGENT_DURABLE_ENABLED', '1') == '1',
                  agent_interactive_enabled=env.get('AI_AGENT_INTERACTIVE_ENABLED', '1') == '1',
                  agent_rollout_percent=int(env.get('AI_AGENT_ROLLOUT_PERCENT', 100)))
