"""Shared validation, dates, cancellation and deterministic artifact digests."""
import asyncio
import copy
import hashlib
import inspect
import json
import math
import unicodedata
from datetime import date, datetime, timedelta, timezone

SHANGHAI = timezone(timedelta(hours=8))


class DomainError(ValueError):
    def __init__(self, code, **details):
        super().__init__(code)
        self.code, self.details = code, details


def require(condition, code):
    if not condition:
        raise DomainError(code)


def clone(value):
    return copy.deepcopy(value)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.replace(tzinfo=SHANGHAI) if result.tzinfo is None else result
    except (TypeError, ValueError, AttributeError):
        raise DomainError('INVALID_TIME') from None


def date_at(value):
    return instant(value).astimezone(SHANGHAI).date().isoformat()


def today():
    return datetime.now(SHANGHAI).date().isoformat()


def valid_date(value):
    try:
        return isinstance(value, str) and len(value) == 10 and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def add_days(value, days):
    require(valid_date(value), 'INVALID_DATE')
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def days_until(end, start):
    require(valid_date(end) and valid_date(start), 'INVALID_DATE')
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).strip().lower().split())


def parse_model_json(content):
    import re
    require(isinstance(content, str), 'AI_INVALID_RESPONSE')
    content = re.sub(r'^\s*```(?:json)?\s*', '', content, flags=re.I)
    content = re.sub(r'\s*```\s*$', '', content)
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        raise DomainError('AI_INVALID_RESPONSE') from None


async def resolve(value):
    return await value if inspect.isawaitable(value) else value


class Cancellation:
    def __init__(self):
        self.event = asyncio.Event()

    def cancel(self):
        self.event.set()

    @property
    def aborted(self):
        return self.event.is_set()

    def check(self):
        if self.aborted:
            raise asyncio.CancelledError()


def check_cancel(signal):
    if signal:
        signal.check()
