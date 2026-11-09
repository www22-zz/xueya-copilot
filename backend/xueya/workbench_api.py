"""Learning-workbench extensions mounted on the main learning router.

Each feature lives in its own module (``code_runner``, ``learning_map``) and is
imported lazily, so an unfinished or disabled feature never breaks the host.
Feature modules implement::

    async def dispatch(rest, request, course, host) -> Response | dict | None

``rest`` is the path after the feature prefix, e.g. ``run`` for
``/api/learning/space/workbench/code/run``.
"""
from __future__ import annotations


class WorkbenchWorkspace:
    def __init__(self, host):
        self.host = host

    async def dispatch(self, path, request, course):
        # The learning router mounts the catch-all at /api/learning/{path:path},
        # so the captured path keeps the "space/" segment for space-side routes.
        if path.startswith("space/workbench/"):
            rest = path[len("space/workbench/"):]
        elif path.startswith("workbench/"):
            rest = path[len("workbench/"):]
        else:
            return None
        feature, _, tail = rest.partition("/")
        if feature == "code":
            from . import code_runner
            return await code_runner.dispatch(tail, request, course, self.host)
        if feature == "map":
            from . import learning_map
            return await learning_map.dispatch(tail, request, course, self.host)
        return None
