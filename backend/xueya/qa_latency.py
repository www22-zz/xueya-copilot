"""Request-local monotonic timings; logs contain no prompts, keys or source text."""
from contextvars import ContextVar
from time import perf_counter

current_timing = ContextVar('qa_timing', default=None)


class ResponseTiming:
    def __init__(self):
        self.started = perf_counter()
        self.route = 'workflow'
        self.phases = {}
        self.active = None
        self.first_content = None
        self.first_token = None
        self.model_ms = 0.0
        self.model_calls = 0

    def elapsed(self):
        return (perf_counter()-self.started)*1000

    def phase(self, event):
        if event.get('type') != 'workflow':
            if event.get('type') == 'content' and self.first_content is None:
                self.first_content = self.elapsed()
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
                'firstModelTokenMs': round(self.first_token, 2) if self.first_token is not None else None,
                'modelMs': round(self.model_ms, 2), 'modelCalls': self.model_calls,
                'phasesMs': {k: round(v, 2) for k, v in phases.items()}}
