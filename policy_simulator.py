"""Side-effect-free counterfactual comparison for recovery policies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from action_engine import apply_outcome_policy, determine_base_action
from recovery_policy import CONTACT_ACTIONS, load_policy, validate_policy


class ScenarioValidationError(ValueError):
    """Raised when a counterfactual scenario cannot be evaluated safely."""


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ScenarioValidationError(f"{field} must be a whole number")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ScenarioValidationError(f"{field} must be a whole number") from error
    if parsed < minimum or parsed > maximum:
        raise ScenarioValidationError(
            f"{field} must be between {minimum} and {maximum}"
        )
    return parsed


def validate_scenario(candidate: Any) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ScenarioValidationError("Scenario must be a JSON object")

    subscription_id = str(candidate.get("subscription_id") or "").strip()
    if not subscription_id:
        raise ScenarioValidationError("subscription_id is required")
    if len(subscription_id) > 64:
        raise ScenarioValidationError("subscription_id must be 64 characters or fewer")

    previous_score_value = candidate.get("previous_health_score")
    previous_score = (
        None
        if previous_score_value in (None, "")
        else _integer(previous_score_value, "previous_health_score", 0, 100)
    )
    systemic_incident = candidate.get("systemic_incident", False)
    if not isinstance(systemic_incident, bool):
        raise ScenarioValidationError("systemic_incident must be true or false")

    return {
        "subscription_id": subscription_id,
        "health_score": _integer(
            candidate.get("health_score"), "health_score", 0, 100
        ),
        "previous_health_score": previous_score,
        "recent_contacts": _integer(
            candidate.get("recent_contacts", 0), "recent_contacts", 0, 10
        ),
        "systemic_incident": systemic_incident,
        "scenario_type": "FRESH_FAILED_PAYMENT",
    }


def _memory_snapshot(scenario: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    history = []
    for index in range(scenario["recent_contacts"]):
        history.append(
            {
                "action_id": f"COUNTERFACTUAL-CONTACT-{index + 1}",
                "action_type": "PAYMENT_REMINDER",
                "action_status": "COMPLETED",
                "executed_at": (
                    now - timedelta(minutes=index + 1)
                ).isoformat(timespec="seconds"),
                "outcome": "NOT_APPLICABLE",
            }
        )
    return {"action_history": history}


def simulate_policy(
    scenario_candidate: Any,
    policy_candidate: Any,
) -> dict[str, Any]:
    """Evaluate one failed-payment scenario without writing memory or actions."""

    scenario = validate_scenario(scenario_candidate)
    policy = validate_policy(policy_candidate)
    previous_score = scenario["previous_health_score"]
    score_change = (
        0 if previous_score is None else scenario["health_score"] - previous_score
    )
    health_change = {
        "previous_score": previous_score,
        "change": score_change,
        "deteriorated": score_change < 0,
    }
    base_decision = determine_base_action(
        {"health_score": scenario["health_score"]},
        health_change,
        policy,
    )
    memory = _memory_snapshot(scenario)
    final = apply_outcome_policy(
        scenario["subscription_id"],
        base_decision,
        memory,
        "bank_timeout" if scenario["systemic_incident"] else None,
        False,
        policy,
        "NOT_APPLICABLE",
        "NO_PENDING_ACTION",
        "failed",
    )
    action, priority, action_status, reason, guardrail = final
    customer_contact = action in CONTACT_ACTIONS
    human_review = action == "ESCALATE"

    return {
        "policy_name": policy["policy_name"],
        "policy_version": policy["version"],
        "base_action": base_decision[0],
        "action": action,
        "priority": priority,
        "action_status": action_status,
        "guardrail": guardrail or "NONE",
        "reason": reason,
        "customer_contact": customer_contact,
        "human_review": human_review,
        "decision_path": [
            (
                f"Health score {scenario['health_score']} evaluated against "
                f"{policy['policy_name']}"
            ),
            (
                f"Recent contacts: {scenario['recent_contacts']} / "
                f"{policy['max_customer_contacts']} within "
                f"{policy['contact_window_hours']} hours"
            ),
            (
                "Systemic incident protection evaluated"
                if scenario["systemic_incident"]
                else "No systemic incident applied"
            ),
            f"Final decision: {action}",
        ],
    }


def compare_policies(
    scenario_candidate: Any,
    proposed_policy_candidate: Any,
    active_policy_candidate: Any | None = None,
) -> dict[str, Any]:
    """Compare active and proposed policies against the exact same scenario."""

    scenario = validate_scenario(scenario_candidate)
    active_policy = validate_policy(active_policy_candidate or load_policy())
    proposed_policy = validate_policy(proposed_policy_candidate)
    active = simulate_policy(scenario, active_policy)
    proposed = simulate_policy(scenario, proposed_policy)

    changed_fields = [
        field
        for field in (
            "action",
            "priority",
            "action_status",
            "guardrail",
            "customer_contact",
            "human_review",
        )
        if active[field] != proposed[field]
    ]
    if active["action"] != proposed["action"]:
        summary = (
            f"The proposed policy moves {scenario['subscription_id']} from "
            f"{active['action']} to {proposed['action']}."
        )
    elif changed_fields:
        summary = "The final action stays the same, but its control path changes."
    else:
        summary = "The proposed policy does not change this scenario's decision."

    return {
        "simulation_mode": "READ_ONLY_COUNTERFACTUAL",
        "scenario": scenario,
        "active": active,
        "proposed": proposed,
        "changed_fields": changed_fields,
        "material_change": bool(changed_fields),
        "summary": summary,
        "disclaimer": (
            "Decision-policy comparison only; no payment, message, database row, "
            "or revenue forecast is created."
        ),
    }
