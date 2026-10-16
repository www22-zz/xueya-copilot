import asyncio
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.core import clone, require


@pytest.fixture
def course():
    file = Path(__file__).resolve().parent.parent/'backend/fixtures/local-study-course.json'
    return json.loads(file.read_text(encoding='utf-8'))


class Repository:
    """Test-only atomic store. Production must inject E's durable repository."""
    def __init__(self):
        self.rows, self.operations, self.history = {}, {}, []
        self.lock = asyncio.Lock()

    async def get(self, course, key):
        return clone(self.rows.get((course, key)))

    async def get_operation(self, course, key):
        return clone(self.operations.get((course, key)))

    async def commit(self, value):
        async with self.lock:
            scope = value['courseId'], value['id']
            operation = value['courseId'], value['operationId']
            old = self.operations.get(operation)
            if old:
                require(old['requestHash'] == value['requestHash'], 'IDEMPOTENCY_CONFLICT')
                return clone(old['value'])
            current = self.rows.get(scope)
            require((current['revision'] if current else 0) == value['expectedRevision'], 'ARTIFACT_CONFLICT')
            self.rows[scope] = clone(value['value'])
            self.operations[operation] = clone(value)
            self.history.append(clone(value['value']))
            return clone(value['value'])

    async def compare_and_set(self, course, key, revision, value):
        async with self.lock:
            old = self.rows.get((course, key))
            if (old['revision'] if old else 0) != revision:
                return False
            self.rows[course, key] = clone(value)
            return True


@pytest.fixture
def repository():
    return Repository()
