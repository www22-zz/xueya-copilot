"""Request-local monotonic timings; logs contain no prompts, keys or source text."""
from contextvars import ContextVar
from time import perf_counter

current_timing = ContextVar('qa_timing', default=None)

# Upstream usage keys differ between providers; keep one canonical counter per
# field so the summary is stable for the frontend and the QA log.
_USAGE_FIELDS = {
    'prompt_tokens': 'prompt_tokens',
    'promptTokens': 'prompt_tokens',
    'input_tokens': 'prompt_tokens',
    'inputTokens': 'prompt_tokens',
    'completion_tokens': 'output_tokens',
    'completionTokens': 'output_tokens',
    'output_tokens': 'output_tokens',
    'outputTokens': 'output_tokens',
    'repairs': 'repairs',
    'review_calls': 'review_calls',
    'reviewCalls': 'review_calls',
    'cache_hits': 'cache_hits',
    'cacheHits': 'cache_hits',
}


class ResponseTiming:
    def __init__(self):
        self.started = perf_counter()
        self.route = 'workflow'
        self.phases = {}
        self.active = None
        self.first_content = None
        self.first_token = None
        self.first_draft = None
        self.model_ms = 0.0
        self.model_calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.repairs = 0
        self.review_calls = 0
        self.cache_hits = 0

    def elapsed(self):
        return (perf_counter()-self.started)*1000

    def note_usage(self, usage):
        """Accumulate integer counters from a provider usage dict; ignore the rest."""
        if not isinstance(usage, dict):
            return
        for key, value in usage.items():
            field = _USAGE_FIELDS.get(key)
            if field is not None and type(value) is int:
                setattr(self, field, getattr(self, field)+value)

    def phase(self, event):
        if event.get('type') != 'workflow':
            if event.get('type') == 'content' and self.first_content is None:
                self.first_content = self.elapsed()
            if event.get('type') == 'draft' and self.first_draft is None:
                self.first_draft = self.elapsed()
            return
        stage, now = event.get('stage'), perf_counter()
        if stage == 'tool':
            return
        if self.active and self.active[0] != stage:
            name, start = self.active
            self.phases[name] = self.phases.get(name, 0)+(now-start)*1000
            self.active = None
        if event.get('status') == 'running' and self.active is None:
            self.active = (stage, now)
        elif event.get('status') != 'running' and self.active and self.active[0] == stage:
            self.phases[stage] = self.phases.get(stage, 0)+(now-self.active[1])*1000
            self.active = None

    def snapshot(self):
        phases = dict(self.phases)
        if self.active:
            name, start = self.active
            phases[name] = phases.get(name, 0)+(perf_counter()-start)*1000
        return {'route': self.route, 'totalMs': round(self.elapsed(), 2),
                'firstContentMs': round(self.first_content, 2) if self.first_content is not None else None,
                'firstDraftMs': round(self.first_draft, 2) if self.first_draft is not None else None,
                'firstModelTokenMs': round(self.first_token, 2) if self.first_token is not None else None,
                'modelMs': round(self.model_ms, 2), 'modelCalls': self.model_calls,
                'promptTokens': self.prompt_tokens, 'outputTokens': self.output_tokens,
                'repairs': self.repairs, 'reviewCalls': self.review_calls, 'cacheHits': self.cache_hits,
                'phasesMs': {k: round(v, 2) for k, v in phases.items()}}
