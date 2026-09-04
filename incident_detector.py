"""Detect cohort-level technical failure spikes before contacting customers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from config import DB_CONFIG


WINDOW_MINUTES = 15
MIN_SYSTEMIC_FAILURES = 3
MIN_FAILURE_SHARE = 0.60
SYSTEMIC_FAILURE_REASONS = {
    "bank_timeout",
    "bank_unavailable",
    "gateway_timeout",
    "technical_error",
    "upi_switch_unavailable",
}
OUTPUT_FILE = Path("incident_state.json")


def detect_incident(events: list[dict[str, Any]]) -> dict[str, Any]:
    total_events = len(events)
    reasons = Counter(
        str(event.get("failure_reason") or "").strip().lower()
        for event in events
        if str(event.get("status", "")).strip().lower() == "failed"
    )
    candidates = [
        (reason, count)
        for reason, count in reasons.items()
        if reason in SYSTEMIC_FAILURE_REASONS
        and count >= MIN_SYSTEMIC_FAILURES
        and total_events > 0
        and count / total_events >= MIN_FAILURE_SHARE
    ]
    if not candidates:
        return {
            "incident_active": False,
            "window_minutes": WINDOW_MINUTES,
            "events_analyzed": total_events,
            "reason": None,
            "matching_failures": 0,
            "failure_share_percent": 0,
        }

    reason, count = max(candidates, key=lambda item: item[1])
    return {
        "incident_active": True,
        "window_minutes": WINDOW_MINUTES,
        "events_analyzed": total_events,
        "reason": reason,
        "matching_failures": count,
        "failure_share_percent": round(count / total_events * 100, 2),
        "recommended_guardrail": "PAUSE_CUSTOMER_CONTACT_AND_MONITOR",
    }


def detect_recent_incident() -> dict[str, Any]:
    import mysql.connector

    connection = mysql.connector.connect(**DB_CONFIG)
    query = """
        SELECT status, failure_reason
        FROM payment_attempts
        WHERE attempt_time >= (
            SELECT DATE_SUB(MAX(attempt_time), INTERVAL %s MINUTE)
            FROM payment_attempts
        )
    """
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, (WINDOW_MINUTES,))
        events = cursor.fetchall()
        cursor.close()
    finally:
        connection.close()

    result = detect_incident(events)
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=4)
    return result


def display_incident(result: dict[str, Any]) -> None:
    print("=" * 100)
    print("                 COHORT DEGRADATION CHECK")
    print("=" * 100)
    print(f"Events analyzed   : {result['events_analyzed']}")
    print(f"Incident active   : {result['incident_active']}")
    if result["incident_active"]:
        print(f"Failure reason    : {result['reason']}")
        print(f"Matching failures : {result['matching_failures']}")
        print(f"Failure share     : {result['failure_share_percent']}%")
        print("Guardrail         : Pause customer contact and monitor")
    print("=" * 100)


if __name__ == "__main__":
    display_incident(detect_recent_incident())
