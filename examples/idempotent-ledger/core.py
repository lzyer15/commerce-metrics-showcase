"""Shared data contract. Money stays Decimal/text until the Sheets boundary."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List
import hashlib
import json

KST = timezone(timedelta(hours=9))
PLATFORMS = ("cafe24", "smartstore", "meta", "naver_search")
METRICS = ("gross", "refunds", "orders", "spend", "attributed_revenue", "conversions")


class MetricsError(Exception):
    """Only fixed, non-secret error codes cross the CLI boundary."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def gross_fingerprint(basis, inputs):
    ordered = sorted(inputs, key=lambda x: (x["order"], x["event"]["id"]))
    return hashlib.sha256(json.dumps({"basis": basis, "inputs": ordered}, sort_keys=True).encode()).hexdigest()


def money(value):
    if value is None or isinstance(value, bool):
        raise MetricsError("missing_or_invalid_amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise MetricsError("missing_or_invalid_amount") from None
    if not result.is_finite():
        raise MetricsError("non_finite_amount")
    return result


def nonnegative(value):
    result = money(value)
    if result < 0:
        raise MetricsError("negative_amount")
    return result


def day_of(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp.astimezone(KST).date().isoformat()
    except (ValueError, TypeError):
        raise MetricsError("timestamp_requires_timezone") from None


def days(since, until):
    try:
        first, last = date.fromisoformat(since), date.fromisoformat(until)
    except (ValueError, TypeError):
        raise MetricsError("invalid_date_range") from None
    if last < first or (last - first).days > 365:
        raise MetricsError("invalid_date_range")
    while first <= last:
        yield first.isoformat()
        first += timedelta(days=1)


def required(obj, key):
    value = obj.get(key)
    if value is None or value == "":
        raise MetricsError("missing_" + key)
    return value


def array(obj, key):
    value = required(obj, key)
    if not isinstance(value, list):
        raise MetricsError("invalid_response_shape")
    return value


def event(event_id, order_id, when, kind, amount):
    if kind not in ("payment", "refund", "additional_payment"):
        raise MetricsError("unknown_payment_type")
    return {"id": str(event_id), "order_id": str(order_id), "date": day_of(when),
            "kind": kind, "amount": str(nonnegative(amount))}


@dataclass
class Batch:
    platform: str
    account: str
    since: str
    until: str
    records: List[Dict[str, Any]] = field(default_factory=list)
    complete_metrics: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    mode: str = "live"
    evidence: Dict[str, Any] = field(default_factory=dict)

    def validate(self):
        list(days(self.since, self.until))
        if self.platform not in PLATFORMS or not self.account:
            raise MetricsError("invalid_source")
        if not set(self.complete_metrics) <= set(METRICS):
            raise MetricsError("invalid_metric")
        if self.mode not in ("live", "demo"):
            raise MetricsError("invalid_mode")
        keys = set()
        for record in self.records:
            key = (record["kind"], record["id"])
            if key in keys:
                raise MetricsError("duplicate_source_record")
            keys.add(key)
            if record["kind"] == "ad":
                if not self.since <= record["date"] <= self.until:
                    raise MetricsError("response_outside_date_range")
            elif record["kind"] != "order":
                raise MetricsError("unknown_record_kind")
