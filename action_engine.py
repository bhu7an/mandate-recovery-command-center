"""Outcome-aware, bounded action policy for mandate recovery."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_memory import (
    calculate_health_change,
    get_customer_memory,
    update_customer_memory,
)
from recovery_policy import (
    CONTACT_ACTIONS,
    PolicyValidationError,
    default_policy,
    load_policy,
)


INPUT_FILE = Path("ai_agent_results.json")
OUTPUT_FILE = Path("action_engine_results.json")


def load_ai_results() -> list[dict[str, Any]]:
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} was not found. Run ai_agent.py first.")
        return []
    with INPUT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, list) else []


def determine_base_action(
    customer: dict[str, Any],
    health_change: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """Choose a base decision using the active merchant constitution."""

    policy = policy or default_policy()
    thresholds = policy["thresholds"]
    allowed_actions = set(policy["allowed_automated_actions"])
    health_score = int(customer["health_score"])
    score_change = int(health_change["change"])
    previous_score = health_change["previous_score"]

    if health_score < thresholds["critical_below"]:
        return "ESCALATE", "CRITICAL", "REQUIRES_HUMAN_INTERVENTION"
    if previous_score is not None and score_change <= -15:
        if "HIGH_PRIORITY_RECOVERY" in allowed_actions:
            return "HIGH_PRIORITY_RECOVERY", "HIGH", "ACTION_REQUIRED"
        return "ESCALATE", "HIGH", "AUTOMATION_NOT_PERMITTED"
    if health_score < thresholds["high_risk_below"]:
        if "HIGH_PRIORITY_RECOVERY" in allowed_actions:
            return "HIGH_PRIORITY_RECOVERY", "HIGH", "ACTION_REQUIRED"
        return "ESCALATE", "HIGH", "AUTOMATION_NOT_PERMITTED"
    if health_score < thresholds["at_risk_below"]:
        if "PAYMENT_REMINDER" in allowed_actions:
            return "PAYMENT_REMINDER", "MEDIUM", "REMINDER_REQUIRED"
        return "MONITOR", "LOW", "AUTOMATION_NOT_PERMITTED"
    if health_score < thresholds["monitor_below"]:
        return "MONITOR", "LOW", "MONITOR_ONLY"
    return "NO_INTERVENTION", "LOW", "NO_ACTION_REQUIRED"


def _recent_contact_count(
    memory: dict[str, Any],
    contact_window_hours: int,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=contact_window_hours)
    count = 0
    for record in memory.get("action_history", []):
        if record.get("action_type") not in CONTACT_ACTIONS:
            continue
        try:
            executed_at = datetime.fromisoformat(record["executed_at"])
            if executed_at.tzinfo is None:
                executed_at = executed_at.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        if executed_at >= cutoff:
            count += 1
    return count


def _pending_action(memory: dict[str, Any]) -> dict[str, Any] | None:
    for action in reversed(memory.get("action_history", [])):
        if action.get("outcome") == "PENDING":
            return action
    return None


def _latest_intervention(memory: dict[str, Any]) -> dict[str, Any] | None:
    for action in reversed(memory.get("action_history", [])):
        if action.get("action_type") in CONTACT_ACTIONS:
            return action
    return None


def apply_outcome_policy(
    customer_id: str,
    base_decision: tuple[str, str, str],
    memory: dict[str, Any],
    systemic_incident_reason: str | None = None,
    legacy_same_event: bool = False,
    policy: dict[str, Any] | None = None,
    current_outcome: str | None = None,
    evaluation_status: str | None = None,
    current_event_status: str | None = None,
) -> tuple[str, str, str, str, str | None]:
    """Adapt the next action using measured outcomes and guardrails."""

    policy = policy or default_policy()
    base_action, priority, action_status = base_decision
    # Read only from the supplied memory snapshot. This keeps the exact same
    # policy function usable by the live engine and by side-effect-free
    # counterfactual previews.
    pending = _pending_action(memory)
    latest_intervention = _latest_intervention(memory)
    last_outcome = memory.get("last_outcome")
    current_event_status = str(current_event_status or "").strip().lower()

    if pending is not None:
        return (
            "MONITOR",
            "LOW",
            "COOLDOWN_MONITORING",
            "A previous intervention is still awaiting an outcome.",
            "PENDING_ACTION_COOLDOWN",
        )

    if legacy_same_event and base_action in CONTACT_ACTIONS:
        return (
            "MONITOR",
            "LOW",
            "COOLDOWN_MONITORING",
            "A legacy record shows this intervention already ran for this event.",
            "LEGACY_SAME_EVENT_COOLDOWN",
        )

    if (
        evaluation_status == "NO_PENDING_ACTION"
        and current_event_status == "success"
    ):
        return (
            "NO_INTERVENTION",
            "LOW",
            "CURRENT_PAYMENT_SUCCESS",
            "The current payment succeeded and no recovery action was pending.",
            "NO_ACTION_ON_SUCCESS",
        )

    if systemic_incident_reason:
        if not policy["suppress_contacts_during_systemic_incident"]:
            return (
                "ESCALATE",
                "HIGH",
                "SYSTEMIC_INCIDENT_REVIEW",
                "The merchant policy routes systemic incidents to human review.",
                "NO_AUTOMATED_CONTACT_DURING_INCIDENT",
            )
        return (
            "MONITOR",
            "HIGH",
            "SYSTEMIC_INCIDENT_HOLD",
            (
                "A cohort-level technical failure spike was detected; "
                "customer contact is suppressed."
            ),
            "SYSTEMIC_FAILURE_SUPPRESSION",
        )

    using_current_evaluation = current_outcome is not None or evaluation_status is not None
    effective_outcome = current_outcome if using_current_evaluation else last_outcome

    if effective_outcome == "RECOVERED":
        if not policy["stop_after_success"]:
            return (
                "MONITOR",
                "LOW",
                "RECOVERY_MONITORING",
                "Recovery succeeded; the merchant policy keeps passive monitoring open.",
                "NO_CONTACT_ON_SUCCESS",
            )
        return (
            "NO_INTERVENTION",
            "LOW",
            "RECOVERY_CONFIRMED",
            "The previous intervention was followed by a successful payment.",
            "STOP_AFTER_SUCCESS",
        )

    if effective_outcome == "FAILED_AFTER_ACTION" and latest_intervention:
        previous_action = latest_intervention.get("action_type")
        if previous_action == "PAYMENT_REMINDER":
            if "HIGH_PRIORITY_RECOVERY" not in set(
                policy["allowed_automated_actions"]
            ):
                return (
                    "ESCALATE",
                    "HIGH",
                    "AUTOMATION_NOT_PERMITTED",
                    "The reminder failed and high-priority automation is disabled.",
                    "MERCHANT_ACTION_ALLOWLIST",
                )
            return (
                "HIGH_PRIORITY_RECOVERY",
                "HIGH",
                "ESCALATED_AFTER_FAILED_REMINDER",
                "The reminder did not recover the payment, so the policy escalated.",
                "NO_DUPLICATE_REMINDER",
            )
        if previous_action == "HIGH_PRIORITY_RECOVERY":
            if not policy["human_approval_after_failed_recovery"]:
                return (
                    "MONITOR",
                    "HIGH",
                    "RECOVERY_EXHAUSTED_MONITORING",
                    "Automated recovery failed; policy blocks further action without opening an approval case.",
                    "NO_FURTHER_AUTOMATION",
                )
            return (
                "ESCALATE",
                "CRITICAL",
                "REQUIRES_HUMAN_INTERVENTION",
                "Automated recovery failed; further action requires human approval.",
                "HUMAN_APPROVAL_GATE",
            )

    if (
        base_action in CONTACT_ACTIONS
        and _recent_contact_count(memory, policy["contact_window_hours"])
        >= policy["max_customer_contacts"]
    ):
        return (
            "ESCALATE",
            "HIGH",
            "CONTACT_LIMIT_REACHED",
            (
                f"The {policy['contact_window_hours']}-hour customer-contact "
                "limit was reached."
            ),
            (
                f"MAX_{policy['max_customer_contacts']}_CONTACTS_"
                f"{policy['contact_window_hours']}H"
            ),
        )

    return (
        base_action,
        priority,
        action_status,
        "The final action follows the explainable health-risk policy.",
        None,
    )


def build_message(customer_id: str, action: str, action_status: str) -> str:
    if action_status == "COOLDOWN_MONITORING":
        return f"No duplicate contact will be sent to {customer_id}; monitor the outcome."
    if action_status == "RECOVERY_CONFIRMED":
        return f"Payment recovery is confirmed for {customer_id}; stop interventions."
    if action_status == "CURRENT_PAYMENT_SUCCESS":
        return f"Payment succeeded for {customer_id}; no recovery action is needed."
    if action_status == "RECOVERY_MONITORING":
        return f"Recovery succeeded for {customer_id}; continue passive monitoring only."
    if action_status == "SYSTEMIC_INCIDENT_HOLD":
        return (
            f"Customer contact for {customer_id} is paused because the "
            "failure appears systemic."
        )
    messages = {
        "ESCALATE": (
            f"Customer {customer_id} requires approved human recovery intervention."
        ),
        "HIGH_PRIORITY_RECOVERY": (
            f"High-priority recovery is required for customer {customer_id}."
        ),
        "PAYMENT_REMINDER": (
            f"One bounded payment reminder should be sent to customer {customer_id}."
        ),
        "MONITOR": (
            f"Customer {customer_id} will be monitored without customer contact."
        ),
        "NO_INTERVENTION": (
            f"Customer {customer_id} requires no intervention."
        ),
    }
    return messages.get(action, f"Monitor customer {customer_id}.")


def build_next_step(action: str, action_status: str) -> str:
    if action_status == "COOLDOWN_MONITORING":
        return "Wait for the next payment outcome; do not repeat the reminder."
    if action_status == "RECOVERY_CONFIRMED":
        return "Close the recovery case and continue normal monitoring."
    if action_status == "CURRENT_PAYMENT_SUCCESS":
        return "Continue normal monitoring; do not open a recovery case."
    if action_status == "RECOVERY_MONITORING":
        return "Keep passive monitoring open without contacting the customer."
    if action_status == "SYSTEMIC_INCIDENT_HOLD":
        return "Monitor the incident and retry only after the technical spike clears."
    steps = {
        "ESCALATE": "Create a human-approval case; do not contact automatically.",
        "HIGH_PRIORITY_RECOVERY": "Run one high-priority simulated recovery attempt.",
        "PAYMENT_REMINDER": "Send one simulated reminder and await the next event.",
        "MONITOR": "Continue monitoring future payment behaviour.",
        "NO_INTERVENTION": "No intervention required.",
    }
    return steps.get(action, "Continue monitoring.")


def process_customer(customer: dict[str, Any]) -> dict[str, Any]:
    customer_id = str(customer["subscription_id"])
    health_score = int(customer["health_score"])
    health_status = str(customer["health_status"])
    attempt_id = customer.get("attempt_id")
    payment_id = customer.get("payment_id") or customer.get("event_id")
    amount = float(customer.get("amount") or 0)

    health_change = calculate_health_change(customer_id, health_score)
    memory = get_customer_memory(customer_id)
    previous_action = memory.get("last_action")
    previous_attempt_id = memory.get("last_attempt_id")
    previous_payment_id = memory.get("last_payment_id") or memory.get(
        "last_event_id"
    )

    policy_error = None
    try:
        policy = load_policy()
    except PolicyValidationError as error:
        policy = default_policy()
        policy_error = str(error)

    base_decision = determine_base_action(customer, health_change, policy)
    incident_reason = os.getenv("MANDATE_SYSTEMIC_INCIDENT_REASON")
    customer_failure_reason = str(
        customer.get("failure_reason") or ""
    ).strip().lower()
    matching_incident_reason = (
        incident_reason
        if incident_reason
        and customer_failure_reason == incident_reason.strip().lower()
        else None
    )
    current_event_ids = {
        str(value)
        for value in (attempt_id, payment_id)
        if value is not None
    }
    legacy_same_event = (
        not memory.get("action_history")
        and memory.get("last_action") == base_decision[0]
        and str(memory.get("last_event_id")) in current_event_ids
    )
    current_outcome = os.getenv("MANDATE_CURRENT_OUTCOME")
    evaluation_status = os.getenv("MANDATE_OUTCOME_EVALUATION_STATUS")
    current_event_status = os.getenv("MANDATE_CURRENT_EVENT_STATUS")
    (
        action,
        priority,
        action_status,
        decision_reason,
        guardrail_applied,
    ) = apply_outcome_policy(
        customer_id,
        base_decision,
        memory,
        matching_incident_reason,
        legacy_same_event,
        policy,
        current_outcome,
        evaluation_status,
        current_event_status,
    )

    update_customer_memory(
        customer_id=customer_id,
        health_score=health_score,
        health_status=health_status,
        action=action,
        event_id=attempt_id or payment_id,
        attempt_id=attempt_id,
        payment_id=payment_id,
        action_status=action_status,
    )

    return {
        "subscription_id": customer_id,
        "attempt_id": attempt_id,
        "payment_id": payment_id,
        "amount": amount,
        "previous_attempt_id": previous_attempt_id,
        "previous_payment_id": previous_payment_id,
        "health_score": health_score,
        "health_status": health_status,
        "previous_health_score": health_change["previous_score"],
        "health_score_change": health_change["change"],
        "health_deteriorated": health_change["deteriorated"],
        "previous_action": previous_action,
        "last_measured_outcome": current_outcome or memory.get("last_outcome"),
        "ai_recommended_action": customer.get("recommended_action"),
        "action_type": action,
        "priority": priority,
        "action_status": action_status,
        "decision_reason": decision_reason,
        "guardrail_applied": guardrail_applied,
        "policy_name": policy["policy_name"],
        "policy_version": policy["version"],
        "policy_load_error": policy_error,
        "message": build_message(customer_id, action, action_status),
        "next_step": build_next_step(action, action_status),
    }


def main() -> None:
    print("=" * 100)
    print("         MANDATE HEALTH - OUTCOME-AWARE ACTION ENGINE")
    print("=" * 100)
    customers = load_ai_results()
    active_subscription = os.getenv("MANDATE_ACTIVE_SUBSCRIPTION_ID")
    if active_subscription:
        customers = [
            customer
            for customer in customers
            if str(customer.get("subscription_id")) == active_subscription
        ]
    if not customers:
        print("No matching customer records found.")
        return

    results = [process_customer(customer) for customer in customers]
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=4)

    for result in results:
        print("-" * 100)
        print(f"Subscription       : {result['subscription_id']}")
        print(f"Attempt / Payment  : {result['attempt_id']} / {result['payment_id']}")
        print(f"Health             : {result['health_score']} ({result['health_status']})")
        print(f"Measured outcome   : {result['last_measured_outcome']}")
        print(f"AI recommendation  : {result['ai_recommended_action']}")
        print(f"Final action       : {result['action_type']}")
        print(f"Action status      : {result['action_status']}")
        print(f"Guardrail          : {result['guardrail_applied']}")
        print(f"Reason             : {result['decision_reason']}")
    print("-" * 100)
    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
