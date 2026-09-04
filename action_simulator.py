"""Safely execute the action engine's final decision in simulation mode."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_memory import register_action_execution
from recovery_metrics import save_metrics


INPUT_FILE = Path("action_engine_results.json")
AI_INPUT_FILE = Path("ai_agent_results.json")
OUTPUT_FILE = Path("simulated_actions.json")


def load_json_file(filename: Path) -> Any:
    if not filename.exists():
        print(f"ERROR: {filename} was not found.")
        return None
    try:
        with filename.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        print(f"ERROR loading {filename}: {error}")
        return None


def simulate_action(customer: dict[str, Any]) -> dict[str, Any]:
    """Route only the final, guardrail-approved action."""

    action = customer["action_type"]
    subscription_id = customer["subscription_id"]
    action_status = customer.get("action_status")

    if action == "PAYMENT_REMINDER":
        return {
            "simulation_type": "PAYMENT_REMINDER",
            "recipient": subscription_id,
            "delivery_status": "SIMULATED_NOT_SENT",
            "message": (
                "Your recent payment could not be completed. Please review "
                "your payment method. This is the only reminder in this cycle."
            ),
        }
    if action == "HIGH_PRIORITY_RECOVERY":
        return {
            "simulation_type": "HIGH_PRIORITY_RECOVERY",
            "customer": subscription_id,
            "case_priority": "HIGH",
            "case_status": "SIMULATED",
            "next_step": "Create one bounded recovery attempt and await outcome.",
        }
    if action == "ESCALATE":
        return {
            "simulation_type": "HUMAN_ESCALATION",
            "customer": subscription_id,
            "case_priority": customer.get("priority"),
            "case_status": "SIMULATED_AWAITING_APPROVAL",
            "next_step": "A human must approve any further customer contact.",
        }
    if action == "MONITOR":
        if action_status == "SYSTEMIC_INCIDENT_HOLD":
            simulation_type = "SYSTEMIC_INCIDENT_HOLD"
            message = (
                "Customer contact was suppressed while the technical "
                "failure cohort is monitored."
            )
        elif action_status == "COOLDOWN_MONITORING":
            simulation_type = "COOLDOWN_MONITORING"
            message = "No duplicate customer communication was sent."
        else:
            simulation_type = "MONITOR"
            message = "No customer communication was sent."
        return {
            "simulation_type": simulation_type,
            "customer": subscription_id,
            "monitoring_status": "ACTIVE",
            "customer_contacted": False,
            "message": message,
        }
    return {
        "simulation_type": "NO_INTERVENTION",
        "customer": subscription_id,
        "action_status": "NO_ACTION",
        "customer_contacted": False,
        "message": "No intervention was executed.",
    }


def build_simulation_record(
    customer: dict[str, Any],
    primary_problem: str,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    simulation = simulate_action(customer)
    audit_record = register_action_execution(
        customer_id=customer["subscription_id"],
        action=customer["action_type"],
        action_status=customer.get("action_status", "UNKNOWN"),
        attempt_id=customer.get("attempt_id"),
        payment_id=customer.get("payment_id"),
        amount_at_risk=customer.get("amount"),
        timestamp=timestamp,
        policy_name=customer.get("policy_name"),
        policy_version=customer.get("policy_version"),
    )
    return {
        "timestamp": timestamp,
        "action_id": audit_record["action_id"],
        "subscription_id": customer["subscription_id"],
        "attempt_id": customer.get("attempt_id"),
        "payment_id": customer.get("payment_id"),
        "amount_at_risk": customer.get("amount", 0),
        "health_score": customer.get("health_score"),
        "health_status": customer.get("health_status"),
        "primary_problem": primary_problem,
        "ai_recommended_action": customer.get("ai_recommended_action"),
        "final_action": customer["action_type"],
        "action_status": customer.get("action_status"),
        "guardrail_applied": customer.get("guardrail_applied"),
        "policy_name": customer.get("policy_name"),
        "policy_version": customer.get("policy_version"),
        "outcome_status": audit_record["outcome"],
        "simulation": simulation,
    }


def main() -> None:
    print("=" * 100)
    print("         MANDATE HEALTH - GUARDED ACTION SIMULATOR")
    print("                   SAFE TEST MODE")
    print("=" * 100)
    print("No real messages, payments, retries, or escalations will be sent.")

    customers = load_json_file(INPUT_FILE)
    ai_results = load_json_file(AI_INPUT_FILE)
    if not isinstance(customers, list) or not isinstance(ai_results, list):
        return

    active_subscription = os.getenv("MANDATE_ACTIVE_SUBSCRIPTION_ID")
    if active_subscription:
        customers = [
            customer
            for customer in customers
            if str(customer.get("subscription_id")) == active_subscription
        ]

    ai_lookup = {
        str(customer.get("subscription_id")): customer for customer in ai_results
    }
    results = []
    for customer in customers:
        ai_customer = ai_lookup.get(str(customer["subscription_id"]), {})
        record = build_simulation_record(
            customer,
            ai_customer.get(
                "primary_problem", "No significant payment health problem"
            ),
        )
        results.append(record)
        print("-" * 100)
        print(f"Subscription       : {record['subscription_id']}")
        print(f"AI recommendation  : {record['ai_recommended_action']}")
        print(f"Final action       : {record['final_action']}")
        print(f"Action status      : {record['action_status']}")
        print(f"Outcome status     : {record['outcome_status']}")
        print(f"Audit ID           : {record['action_id']}")

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=4)
    save_metrics()
    print("-" * 100)
    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
