"""UTC time helpers. Every timestamp is ISO 8601 with a Z suffix, second precision."""
from datetime import datetime, timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def ms_to_iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(ISO_FORMAT)


def iso_to_ms(iso):
    return int(datetime.strptime(iso, ISO_FORMAT).replace(tzinfo=timezone.utc).timestamp() * 1000)


def now_iso():
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


def utc_day(iso):
    return iso[:10]
