"""Scope provider delivery independently of inbox history and device registration."""
from dataclasses import dataclass
from datetime import datetime
import os
import re


PUBLIC_APNS_TOPIC = 'cz.toozservis.spravavozidel.ios'


@dataclass(frozen=True)
class DeliveryPolicy:
    enabled: bool
    valid: bool
    recipients: frozenset[int]
    public_apns_from: datetime | None

    def public_apns_active(self, now):
        return self.valid and self.public_apns_from is not None and now >= self.public_apns_from

    def can_queue(self, recipient_id, device, source_at, now):
        if not self.valid:
            return False
        if recipient_id in self.recipients:
            return True
        return (self.public_apns_active(now) and device.platform == 'apns'
                and device.environment == 'production' and device.bundle_id == PUBLIC_APNS_TOPIC
                and source_at >= self.public_apns_from)

    def allows(self, recipient_id, public_apns=False):
        return (self.enabled and self.valid and
                (recipient_id in self.recipients or (public_apns and self.public_apns_active(datetime.utcnow()))))


def delivery_policy():
    enabled = os.getenv('PUSH_DELIVERY_ENABLED', '').lower() in {'1', 'true'}
    denied = DeliveryPolicy(enabled, False, frozenset(), None)
    raw = os.getenv('PUSH_DELIVERY_RECIPIENT_IDS', '').strip()
    parts = [part.strip() for part in raw.split(',')] if raw else []
    if len(raw) > 10000 or len(parts) > 1000 or any(
        not re.fullmatch(r'[1-9][0-9]{0,9}', part) or int(part) > 2147483647 for part in parts
    ):
        return denied

    # The database stores naive UTC timestamps. Never interpret local times.
    cutoff = None
    value = os.getenv('PUSH_PUBLIC_APNS_FROM_UTC')
    if value is not None:
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z', value):
            return denied
        try:
            cutoff = datetime.fromisoformat(value[:-1])
        except ValueError:
            return denied
    return DeliveryPolicy(enabled, True, frozenset(map(int, parts)), cutoff)
