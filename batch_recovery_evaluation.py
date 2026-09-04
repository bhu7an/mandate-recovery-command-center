"""Deterministic 100-subscription evaluation of the real local policy.

This is a synthetic simulation, not a claim about production revenue. It runs
the same action, memory, outcome, guardrail, and audit functions used by the
live agent and produces an honest exception list.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any

import agent_memory
import outcome_evaluator
import recovery_metrics
from action_engine import process_customer
from action_simulator import build_simulation_record


SEED = 20260829
COHORT_SIZE = 100
OUTPUT_DIR = Path("batch_output")


def make_customer(
    subscription_id: str,
    attempt_id: str,
    payment_id: str,
    amount: float,
    health_score: int,
    failure_reason: str | None,
    payment_status: str,
) -> dict[str, Any]:
    if health_score < 20:
        health_status = "Critical"
        recommendation = "ESCALATE"
    elif health_score < 40:
        health_status = "High Risk"
        recommendation = "HIGH_PRIORITY_RECOVERY"
    elif health_score < 60:
        health_status = "At Risk"
        recommendation = "PAYMENT_REMINDER"
    elif health_score < 80:
        health_status = "Stable"
        recommendation = "MONITOR"
    else:
        health_status = "Healthy"
        recommendation = "NO_INTERVENTION"
    return {
        "subscription_id": subscription_id,
        "attempt_id": attempt_id,
        "payment_id": payment_id,
        "event_id": attempt_id,
        "amount": amount,
        "payment_status": payment_status,
        "failure_reason": failure_reason,
        "health_score": health_score,
        "health_status": health_status,
        "recommended_action": recommendation,
    }


def execute_decision(
    customer: dict[str, Any],
    primary_problem: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    decision = process_customer(customer)
    execution = build_simulation_record(decision, primary_problem)
    return decision, execution


def main() -> None:
    rng = random.Random(SEED)
    OUTPUT_DIR.mkdir(exist_ok=True)
    agent_memory.MEMORY_FILE = str(OUTPUT_DIR / "agent_memory.json")
    outcome_evaluator.OUTCOME_HISTORY_FILE = OUTPUT_DIR / "outcome_history.json"
    recovery_metrics.OUTPUT_FILE = OUTPUT_DIR / "recovery_metrics.json"
    agent_memory.save_memory({})
    for path in OUTPUT_DIR.glob("*.json"):
        if path.name != "agent_memory.json":
            path.unlink()

    results: list[dict[str, Any]] = []
    revenue_at_risk = 0.0
    incident_customers = set(range(1, 13))

    for number in range(1, COHORT_SIZE + 1):
        subscription_id = f"BS{number:03d}"
        amount = float(rng.choice([299, 499, 599, 799, 999, 1299]))
        revenue_at_risk += amount
        failure_reason = (
            "bank_timeout"
            if number in incident_customers
            else "insufficient_balance"
        )
        health_score = rng.choices(
            [15, 30, 53, 76],
            weights=[10, 25, 50, 15],
            k=1,
        )[0]
        first_customer = make_customer(
            subscription_id,
            f"BA{number:03d}1",
            f"BP{number:03d}1",
            amount,
            health_score,
            failure_reason,
            "failed",
        )

        if failure_reason == "bank_timeout":
            os.environ["MANDATE_SYSTEMIC_INCIDENT_REASON"] = "bank_timeout"
        try:
            first_decision, first_execution = execute_decision(
                first_customer,
                "Synthetic failed recurring payment",
            )
        finally:
            os.environ.pop("MANDATE_SYSTEMIC_INCIDENT_REASON", None)

        record: dict[str, Any] = {
            "subscription_id": subscription_id,
            "amount_at_risk": amount,
            "failure_reason": failure_reason,
            "initial_health_score": health_score,
            "first_decision": first_decision,
            "first_execution": first_execution,
            "outcome": "NOT_AUTOMATICALLY_RESOLVED",
            "amount_recovered": 0.0,
            "final_status": first_decision["action_status"],
        }

        action = first_decision["action_type"]
        if action in {"PAYMENT_REMINDER", "HIGH_PRIORITY_RECOVERY"}:
            success_probability = (
                0.56 if action == "PAYMENT_REMINDER" else 0.70
            )
            outcome_status = (
                "success" if rng.random() < success_probability else "failed"
            )
            outcome = outcome_evaluator.evaluate_payment_event(
                {
                    "subscription_id": subscription_id,
                    "attempt_id": f"BA{number:03d}2",
                    "payment_id": f"BP{number:03d}2",
                    "status": outcome_status,
                    "failure_reason": None
                    if outcome_status == "success"
                    else "insufficient_balance",
                    "amount": amount,
                }
            )
            next_score = min(100, health_score + 23) if outcome_status == "success" else max(0, health_score - 5)
            next_customer = make_customer(
                subscription_id,
                f"BA{number:03d}2",
                f"BP{number:03d}2",
                amount,
                next_score,
                None if outcome_status == "success" else "insufficient_balance",
                outcome_status,
            )
            next_decision, next_execution = execute_decision(
                next_customer,
                "Measured result of the previous simulated intervention",
            )
            record.update(
                {
                    "measured_outcome": outcome,
                    "next_decision": next_decision,
                    "next_execution": next_execution,
                    "outcome": outcome["outcome"],
                    "amount_recovered": outcome.get("amount_recovered", 0),
                    "final_status": next_decision["action_status"],
                }
            )

        results.append(record)

    memory = agent_memory.load_memory()
    action_history = [
        action
        for customer_memory in memory.values()
        for action in customer_memory.get("action_history", [])
    ]
    recovered_amount = round(
        sum(float(result["amount_recovered"]) for result in results),
        2,
    )
    recovered_customers = sum(
        1 for result in results if result["outcome"] == "RECOVERED"
    )
    exceptions = [
        {
            "subscription_id": result["subscription_id"],
            "amount_at_risk": result["amount_at_risk"],
            "failure_reason": result["failure_reason"],
            "final_status": result["final_status"],
        }
        for result in results
        if result["outcome"] != "RECOVERED"
    ]
    metrics = {
        "data_scope": "SYNTHETIC_BATCH_SIMULATION",
        "random_seed": SEED,
        "subscriptions_evaluated": COHORT_SIZE,
        "revenue_at_risk": round(revenue_at_risk, 2),
        "customers_recovered": recovered_customers,
        "amount_recovered": recovered_amount,
        "customer_recovery_rate_percent": round(
            recovered_customers / COHORT_SIZE * 100,
            2,
        ),
        "revenue_recovery_rate_percent": round(
            recovered_amount / revenue_at_risk * 100,
            2,
        ),
        "customer_contacts_executed": sum(
            1
            for action in action_history
            if action.get("action_type")
            in {"PAYMENT_REMINDER", "HIGH_PRIORITY_RECOVERY"}
        ),
        "contacts_suppressed_for_systemic_incident": sum(
            1
            for action in action_history
            if action.get("action_status") == "SYSTEMIC_INCIDENT_HOLD"
        ),
        "human_escalations": sum(
            1
            for action in action_history
            if action.get("action_type") == "ESCALATE"
        ),
        "unresolved_or_gated_exceptions": len(exceptions),
        "limitations": [
            "Outcomes are seeded synthetic simulations, not production payments.",
            "Recovery probabilities are scenario assumptions, not trained estimates.",
            "The exception list is retained instead of hiding failed cases.",
        ],
    }

    outputs = {
        "batch_results.json": results,
        "batch_metrics.json": metrics,
        "exception_list.json": exceptions,
    }
    for filename, content in outputs.items():
        with (OUTPUT_DIR / filename).open("w", encoding="utf-8") as file:
            json.dump(content, file, indent=4)

    print("=" * 90)
    print("        100-SUBSCRIPTION RECOVERY EVALUATION")
    print("             SYNTHETIC, DETERMINISTIC, API-FREE")
    print("=" * 90)
    print(f"Revenue at risk       : INR {metrics['revenue_at_risk']:.2f}")
    print(f"Customers recovered   : {metrics['customers_recovered']}")
    print(f"Amount recovered      : INR {metrics['amount_recovered']:.2f}")
    print(
        "Revenue recovery rate : "
        f"{metrics['revenue_recovery_rate_percent']}%"
    )
    print(
        "Systemic contacts held : "
        f"{metrics['contacts_suppressed_for_systemic_incident']}"
    )
    print(f"Exception cases       : {len(exceptions)}")
    print("=" * 90)
    print(f"Results saved under   : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
