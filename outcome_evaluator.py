"""Attribute a new payment event to the most recent pending intervention."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_memory import (
    get_pending_action,
    now_iso,
    update_action_outcome,
)
from recovery_metrics import save_metrics


OUTCOME_HISTORY_FILE = Path("outcome_history.json")


def _append_history(result: dict[str, Any]) -> None:
    history: list[dict[str, Any]] = []
    if OUTCOME_HISTORY_FILE.exists():
        try:
            with OUTCOME_HISTORY_FILE.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, list):
                history = loaded
        except (json.JSONDecodeError, OSError):
            history = []

    audit_key = (
        result.get("action_id"),
        result.get("outcome_attempt_id"),
    )
    existing_keys = {
        (item.get("action_id"), item.get("outcome_attempt_id"))
        for item in history
    }
    if audit_key not in existing_keys:
        history.append(result)
        with OUTCOME_HISTORY_FILE.open("w", encoding="utf-8") as file:
            json.dump(history, file, indent=4)


def evaluate_payment_event(event: dict[str, Any]) -> dict[str, Any]:
    subscription_id = str(event["subscription_id"])
    attempt_id = event.get("attempt_id")
    payment_id = event.get("payment_id")
    status = str(event.get("status", "")).strip().lower()
    pending_action = get_pending_action(subscription_id)

    if pending_action is None:
        return {
            "evaluated_at": now_iso(),
            "subscription_id": subscription_id,
            "outcome_attempt_id": attempt_id,
            "outcome_payment_id": payment_id,
            "evaluation_status": "NO_PENDING_ACTION",
            "outcome": "NOT_APPLICABLE",
        }

    if attempt_id and attempt_id == pending_action.get("source_attempt_id"):
        return {
            "evaluated_at": now_iso(),
            "subscription_id": subscription_id,
            "action_id": pending_action["action_id"],
            "outcome_attempt_id": attempt_id,
            "outcome_payment_id": payment_id,
            "evaluation_status": "SOURCE_EVENT_IGNORED",
            "outcome": "PENDING",
        }

    if status == "success":
        outcome = "RECOVERED"
        amount_recovered = float(
            event.get("amount") or pending_action.get("amount_at_risk") or 0
        )
    elif status == "failed":
        outcome = "FAILED_AFTER_ACTION"
        amount_recovered = 0.0
    else:
        return {
            "evaluated_at": now_iso(),
            "subscription_id": subscription_id,
            "action_id": pending_action["action_id"],
            "outcome_attempt_id": attempt_id,
            "outcome_payment_id": payment_id,
            "evaluation_status": "NON_TERMINAL_EVENT",
            "outcome": "PENDING",
        }

    updated = update_action_outcome(
        subscription_id,
        pending_action["action_id"],
        outcome,
        outcome_attempt_id=attempt_id,
        outcome_payment_id=payment_id,
        amount_recovered=amount_recovered,
        outcome_time=now_iso(),
    )
    result = {
        "evaluated_at": now_iso(),
        "subscription_id": subscription_id,
        "action_id": pending_action["action_id"],
        "previous_action": pending_action["action_type"],
        "source_attempt_id": pending_action.get("source_attempt_id"),
        "source_payment_id": pending_action.get("source_payment_id"),
        "outcome_attempt_id": attempt_id,
        "outcome_payment_id": payment_id,
        "evaluation_status": "OUTCOME_RECORDED" if updated else "NOT_UPDATED",
        "outcome": outcome,
        "amount_recovered": amount_recovered,
    }
    _append_history(result)
    save_metrics()
    return result


def display_evaluation(result: dict[str, Any]) -> None:
    print("=" * 100)
    print("                 PREVIOUS ACTION OUTCOME")
    print("=" * 100)
    print(f"Subscription       : {result.get('subscription_id')}")
    print(f"Previous action    : {result.get('previous_action', 'None')}")
    print(f"Outcome            : {result.get('outcome')}")
    print(f"Evaluation status  : {result.get('evaluation_status')}")
    if result.get("outcome") == "RECOVERED":
        print(f"Amount recovered   : INR {result.get('amount_recovered', 0):.2f}")
    print("=" * 100)


if __name__ == "__main__":
    print(
        "Import evaluate_payment_event(event) from live_agent.py; "
        "this module evaluates real incoming events rather than inventing one."
    )
