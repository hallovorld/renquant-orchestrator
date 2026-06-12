#!/usr/bin/env python3
"""Alert escalation lifecycle prototype (#108 §12.3 / L6).

The fundamentals-stale warning fired daily for ~4 months and was ignored:
detection without lifecycle = noise. State machine:
NEW -> WARN(ntfy) -> unacked N days -> CRITICAL(blocks scope) -> RESOLVED.
Dedup by (audit, scope, cause_hash): a 121-day-old condition is ONE
escalating incident, not 121 identical warnings.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Alert:
    audit: str
    scope: str
    cause_hash: str
    first_seen: dt.date
    last_seen: dt.date
    state: str = "WARN"          # WARN -> CRITICAL -> RESOLVED
    acked: bool = False
    notifications: int = 0


@dataclass
class AlertBook:
    escalate_after_days: int = 5
    alerts: dict = field(default_factory=dict)

    def observe(self, audit: str, scope: str, cause_hash: str, today: dt.date) -> Alert:
        k = (audit, scope, cause_hash)
        a = self.alerts.get(k)
        if a is None or a.state == "RESOLVED":
            a = Alert(audit, scope, cause_hash, today, today)
            a.notifications = 1                      # one ntfy on NEW
            self.alerts[k] = a
            return a
        a.last_seen = today                          # dedup: NO new notification
        if (not a.acked and a.state == "WARN"
                and (today - a.first_seen).days >= self.escalate_after_days):
            a.state = "CRITICAL"                     # blocks scope at the L6 barrier
            a.notifications += 1                     # one escalation ntfy
        return a

    def ack(self, audit, scope, cause_hash):
        self.alerts[(audit, scope, cause_hash)].acked = True

    def resolve_if_absent(self, seen_today: set, today: dt.date):
        for k, a in self.alerts.items():
            if a.state != "RESOLVED" and k not in seen_today and a.last_seen < today:
                a.state = "RESOLVED"

    def blocking_scopes(self) -> set:
        return {a.scope for a in self.alerts.values() if a.state == "CRITICAL"}


if __name__ == "__main__":
    book = AlertBook(escalate_after_days=5)
    d0 = dt.date(2026, 2, 10)
    # P1: 121 identical daily observations => exactly 2 notifications (new + escalation)
    for i in range(121):
        a = book.observe("staleness", "fund_daily", "max_date=2026-02-10", d0 + dt.timedelta(days=i))
    assert a.notifications == 2 and a.state == "CRITICAL", (a.notifications, a.state)
    assert "fund_daily" in book.blocking_scopes()
    # P2: acked alerts never escalate
    b2 = AlertBook(escalate_after_days=5)
    for i in range(3):
        b2.observe("staleness", "x", "h", d0 + dt.timedelta(days=i))
    b2.ack("staleness", "x", "h")
    for i in range(3, 30):
        al = b2.observe("staleness", "x", "h", d0 + dt.timedelta(days=i))
    assert al.state == "WARN" and al.notifications == 1
    # P3: resolution on absence, and a recurrence is a NEW incident
    book.resolve_if_absent(set(), d0 + dt.timedelta(days=200))
    a3 = book.observe("staleness", "fund_daily", "max_date=2026-02-10", d0 + dt.timedelta(days=300))
    assert a3.state == "WARN" and a3.first_seen == d0 + dt.timedelta(days=300)
    print("P1 121 days -> 2 notifications + CRITICAL block ✓  "
          "P2 ack suppresses escalation ✓  P3 absence resolves, recurrence = new incident ✓")
