"""Persistent state and audit history for the recovery agent."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMORY_FILE = os.getenv("AGENT_MEMORY_FILE", "agent_memory.json")
TRACKED_INTERVENTIONS = {
    "PAYMENT_REMINDER",
    "HIGH_PRIORITY_RECOVERY",
}
MAX_ACTION_HISTORY = 50


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_memory() -> dict[str, dict[str, Any]]:
    path = Path(MEMORY_FILE)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_memory(memory: dict[str, dict[str, Any]]) -> None:
    path = Path(MEMORY_FILE)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(memory, file, indent=4)
    temporary_path.replace(path)


def get_customer_memory(customer_id: str) -> dict[str, Any]:
    return load_memory().get(customer_id, {})


def calculate_health_change(
    customer_id: str,
    new_health_score: int,
) -> dict[str, Any]:
    previous_score = get_customer_memory(customer_id).get(
        "last_health_score"
    )
    if previous_score is None:
        return {
            "previous_score": None,
            "change": 0,
            "deteriorated": False,
        }
    change = int(new_health_score) - int(previous_score)
    return {
        "previous_score": int(previous_score),
        "change": change,
        "deteriorated": change < 0,
    }


def update_customer_memory(
    customer_id: str,
    health_score: int,
    health_status: str,
    action: str,
    event_id: str | None = None,
    *,
    attempt_id: str | None = None,
    payment_id: str | None = None,
    action_status: str | None = None,
) -> None:
    """Update state without deleting historical actions or outcomes."""

    memory = load_memory()
    customer = memory.setdefault(customer_id, {})
    customer.update(
        {
            "last_health_score": int(health_score),
            "last_health_status": health_status,
            "last_action": action,
            "last_action_status": action_status,
            "last_event_id": event_id or attempt_id or payment_id,
            "last_attempt_id": attempt_id,
            "last_payment_id": payment_id,
            "last_decision_time": now_iso(),
        }
    )
    customer.setdefault("intervention_count", 0)
    customer.setdefault("recovery_count", 0)
    customer.setdefault("recovered_amount", 0.0)
    customer.setdefault("action_history", [])
    memory[customer_id] = customer
    save_memory(memory)


def _action_id(
    customer_id: str,
    action: str,
    attempt_id: str | None,
    payment_id: str | None,
) -> str:
    source_id = attempt_id or payment_id or "NO_EVENT"
    return f"ACT-{customer_id}-{source_id}-{action}"


def register_action_execution(
    customer_id: str,
    action: str,
    action_status: str,
    *,
    attempt_id: str | None,
    payment_id: str | None,
    amount_at_risk: float | int | None,
    timestamp: str | None = None,
    policy_name: str | None = None,
    policy_version: int | None = None,
) -> dict[str, Any]:
    """Create one idempotent audit record for the final executed action."""

    memory = load_memory()
    customer = memory.setdefault(customer_id, {})
    history = customer.setdefault("action_history", [])
    action_id = _action_id(customer_id, action, attempt_id, payment_id)

    for existing in history:
        if existing.get("action_id") == action_id:
            return existing

    is_tracked = action in TRACKED_INTERVENTIONS
    record = {
        "action_id": action_id,
        "action_type": action,
        "action_status": action_status,
        "source_attempt_id": attempt_id,
        "source_payment_id": payment_id,
        "amount_at_risk": float(amount_at_risk or 0),
        "executed_at": timestamp or now_iso(),
        "policy_name": policy_name,
        "policy_version": policy_version,
        "outcome": "PENDING" if is_tracked else "NOT_APPLICABLE",
        "outcome_attempt_id": None,
        "outcome_payment_id": None,
        "outcome_time": None,
        "amount_recovered": 0.0,
    }
    history.append(record)
    customer["action_history"] = history[-MAX_ACTION_HISTORY:]
    customer["last_action_id"] = action_id
    customer["last_action"] = action
    customer["last_action_status"] = action_status
    customer["last_action_time"] = record["executed_at"]

    if is_tracked:
        customer["intervention_count"] = int(
            customer.get("intervention_count", 0)
        ) + 1
        customer["last_outcome"] = "PENDING"

    memory[customer_id] = customer
    save_memory(memory)
    return record


def get_pending_action(customer_id: str) -> dict[str, Any] | None:
    history = get_customer_memory(customer_id).get("action_history", [])
    for action in reversed(history):
        if action.get("outcome") == "PENDING":
            return action
    return None


def get_latest_intervention(customer_id: str) -> dict[str, Any] | None:
    history = get_customer_memory(customer_id).get("action_history", [])
    for action in reversed(history):
        if action.get("action_type") in TRACKED_INTERVENTIONS:
            return action
    return None


def update_action_outcome(
    customer_id: str,
    action_id: str,
    outcome: str,
    *,
    outcome_attempt_id: str | None,
    outcome_payment_id: str | None,
    amount_recovered: float | int = 0,
    outcome_time: str | None = None,
) -> dict[str, Any] | None:
    memory = load_memory()
    customer = memory.get(customer_id)
    if not customer:
        return None

    history = customer.get("action_history", [])
    updated_record = None
    for record in history:
        if record.get("action_id") != action_id:
            continue
        if record.get("outcome") != "PENDING":
            return record
        record.update(
            {
                "outcome": outcome,
                "outcome_attempt_id": outcome_attempt_id,
                "outcome_payment_id": outcome_payment_id,
                "outcome_time": outcome_time or now_iso(),
                "amount_recovered": float(amount_recovered or 0),
            }
        )
        updated_record = record
        break

    if updated_record is None:
        return None

    customer["last_outcome"] = outcome
    customer["last_outcome_time"] = updated_record["outcome_time"]
    if outcome == "RECOVERED":
        customer["recovery_count"] = int(
            customer.get("recovery_count", 0)
        ) + 1
        customer["recovered_amount"] = round(
            float(customer.get("recovered_amount", 0))
            + float(amount_recovered or 0),
            2,
        )

    customer["action_history"] = history[-MAX_ACTION_HISTORY:]
    memory[customer_id] = customer
    save_memory(memory)
    return updated_record


def get_last_action(customer_id: str) -> str | None:
    return get_customer_memory(customer_id).get("last_action")


def get_last_event(customer_id: str) -> str | None:
    return get_customer_memory(customer_id).get("last_event_id")


if __name__ == "__main__":
    memory = load_memory()
    print("=" * 70)
    print("             AGENT MEMORY")
    print("=" * 70)
    print(f"Memory file: {MEMORY_FILE}")
    print(f"Customers stored: {len(memory)}")
    for customer_id, data in memory.items():
        print(
            f"{customer_id}: action={data.get('last_action')}, "
            f"outcome={data.get('last_outcome')}, "
            f"recovered={data.get('recovered_amount', 0)}"
        )
