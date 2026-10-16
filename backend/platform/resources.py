from ..core import require


class Resources:
    def __init__(self, api_slots=2, cpu_slots=2):
        self.active, self.limits = {'api': 0, 'cpu': 0}, {'api': api_slots, 'cpu': cpu_slots}

    def choose(self, resource):
        require(resource in self.limits, 'RESOURCE_UNSUPPORTED')
        return resource

    def acquire(self, resource):
        self.choose(resource)
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
        return {'active': dict(self.active), 'limits': dict(self.limits), 'inference': 'external-api-only'}
