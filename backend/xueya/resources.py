"""Bounded CPU/API permits; no local model or GPU resource exists."""
from .common import require


class Resources:
    def __init__(self, api_slots=2, cpu_slots=2):
        self.active = {"cpu": 0, "api": 0}
        self.limits = {"cpu": cpu_slots, "api": api_slots}

    def acquire(self, resource):
        require(resource in self.limits, "RESOURCE_UNSUPPORTED")
        if self.active[resource] >= self.limits[resource]:
            return None
        self.active[resource] += 1
        released = False

        def release():
            nonlocal released
            if not released:
                released = True
                self.active[resource] -= 1
        return release

    def stats(self):
        return {"active": dict(self.active), "limits": dict(self.limits), "inference": "external-api-only"}
