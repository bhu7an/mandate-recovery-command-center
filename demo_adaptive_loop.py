"""Run the complete adaptive logic without MySQL or external APIs.

All output is isolated under ``demo_output`` and labelled as simulation.
"""

from __future__ import annotations

import json
from pathlib import Path

import agent_memory
import outcome_evaluator
import recovery_metrics
from action_engine import process_customer
from action_simulator import build_simulation_record


OUTPUT_DIR = Path("demo_output")
TRACE_FILE = OUTPUT_DIR / "adaptive_trace.json"


def customer(
    attempt_id: str,
    payment_id: str,
    health_score: int,
    health_status: str,
) -> dict[str, object]:
    return {
        "subscription_id": "S-DEMO",
        "attempt_id": attempt_id,
        "payment_id": payment_id,
        "event_id": attempt_id,
        "amount": 599.0,
        "payment_status": "failed" if health_score < 60 else "success",
        "failure_reason": "insufficient_balance" if health_score < 60 else None,
        "health_score": health_score,
        "health_status": health_status,
        "recommended_action": "PAYMENT_REMINDER"
        if health_score < 60
        else "MONITOR",
    }


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    agent_memory.MEMORY_FILE = str(OUTPUT_DIR / "agent_memory.json")
    outcome_evaluator.OUTCOME_HISTORY_FILE = OUTPUT_DIR / "outcome_history.json"
    recovery_metrics.OUTPUT_FILE = OUTPUT_DIR / "recovery_metrics.json"
    agent_memory.save_memory({})
    for path in [outcome_evaluator.OUTCOME_HISTORY_FILE, TRACE_FILE]:
        if path.exists():
            path.unlink()

    trace = []

    reminder_decision = process_customer(
        customer("D001", "PD001", 53, "At Risk")
    )
    reminder_execution = build_simulation_record(
        reminder_decision,
        "Latest payment remains unresolved",
    )
    trace.append(
        {
            "step": "REMINDER_EXECUTED",
            "decision": reminder_decision,
            "execution": reminder_execution,
        }
    )

    failed_outcome = outcome_evaluator.evaluate_payment_event(
        {
            "subscription_id": "S-DEMO",
            "attempt_id": "D002",
            "payment_id": "PD002",
            "status": "failed",
            "failure_reason": "insufficient_balance",
            "amount": 599,
        }
    )
    escalated_decision = process_customer(
        customer("D002", "PD002", 45, "At Risk")
    )
    escalated_execution = build_simulation_record(
        escalated_decision,
        "Reminder did not recover the payment",
    )
    trace.append(
        {
            "step": "FAILED_REMINDER_ESCALATED",
            "outcome": failed_outcome,
            "decision": escalated_decision,
            "execution": escalated_execution,
        }
    )

    recovered_outcome = outcome_evaluator.evaluate_payment_event(
        {
            "subscription_id": "S-DEMO",
            "attempt_id": "D003",
            "payment_id": "PD003",
            "status": "success",
            "failure_reason": None,
            "amount": 599,
        }
    )
    stopped_decision = process_customer(
        customer("D003", "PD003", 76, "Stable")
    )
    stopped_execution = build_simulation_record(
        stopped_decision,
        "Payment recovered after high-priority intervention",
    )
    trace.append(
        {
            "step": "RECOVERY_CONFIRMED_AND_STOPPED",
            "outcome": recovered_outcome,
            "decision": stopped_decision,
            "execution": stopped_execution,
        }
    )

    metrics = recovery_metrics.save_metrics()
    with TRACE_FILE.open("w", encoding="utf-8") as file:
        json.dump(trace, file, indent=4)

    print("=" * 90)
    print("        ADAPTIVE RECOVERY DEMO - LOCAL SIMULATION")
    print("=" * 90)
    for item in trace:
        print(f"Step         : {item['step']}")
        print(f"Final action : {item['decision']['action_type']}")
        print(f"Status       : {item['decision']['action_status']}")
        print(f"Guardrail    : {item['decision']['guardrail_applied']}")
        print("-" * 90)
    recovery_metrics.display_metrics(metrics)
    print(f"Trace saved  : {TRACE_FILE}")


if __name__ == "__main__":
    main()
