"""Calculate honest recovery metrics from the local action audit history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_memory import load_memory, now_iso


OUTPUT_FILE = Path("recovery_metrics.json")


def calculate_metrics(
    memory: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    memory = memory if memory is not None else load_memory()
    actions = [
        action
        for customer in memory.values()
        for action in customer.get("action_history", [])
    ]
    interventions = [
        action
        for action in actions
        if action.get("action_type")
        in {"PAYMENT_REMINDER", "HIGH_PRIORITY_RECOVERY"}
    ]
    recovered = [
        action for action in interventions if action.get("outcome") == "RECOVERED"
    ]
    failed = [
        action
        for action in interventions
        if action.get("outcome") == "FAILED_AFTER_ACTION"
    ]
    pending = [
        action for action in interventions if action.get("outcome") == "PENDING"
    ]

    exposure_by_payment: dict[str, float] = {}
    for action in interventions:
        payment_id = action.get("source_payment_id") or action.get("action_id")
        exposure_by_payment.setdefault(
            str(payment_id), float(action.get("amount_at_risk") or 0)
        )

    recovered_by_payment: dict[str, float] = {}
    for action in recovered:
        payment_id = action.get("outcome_payment_id") or action.get("source_payment_id")
        recovered_by_payment[str(payment_id)] = float(
            action.get("amount_recovered") or 0
        )

    resolved = len(recovered) + len(failed)
    revenue_at_risk = round(sum(exposure_by_payment.values()), 2)
    amount_recovered = round(sum(recovered_by_payment.values()), 2)

    return {
        "generated_at": now_iso(),
        "data_scope": "LOCAL_SIMULATION",
        "customers_monitored": len(memory),
        "total_decisions": len(actions),
        "interventions_executed": len(interventions),
        "resolved_interventions": resolved,
        "pending_interventions": len(pending),
        "successful_recoveries": len(recovered),
        "failed_recoveries": len(failed),
        "recovery_rate_percent": round(
            (len(recovered) / resolved * 100) if resolved else 0,
            2,
        ),
        "revenue_at_risk": revenue_at_risk,
        "amount_recovered": amount_recovered,
        "revenue_recovery_percent": round(
            (amount_recovered / revenue_at_risk * 100)
            if revenue_at_risk
            else 0,
            2,
        ),
        "reminders_suppressed_by_cooldown": sum(
            1
            for action in actions
            if action.get("action_status") == "COOLDOWN_MONITORING"
        ),
        "human_escalations": sum(
            1 for action in actions if action.get("action_type") == "ESCALATE"
        ),
    }


def save_metrics(metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics = metrics or calculate_metrics()
    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=4)
    return metrics


def display_metrics(metrics: dict[str, Any]) -> None:
    print("=" * 70)
    print("                 RECOVERY METRICS")
    print("=" * 70)
    print(f"Data scope                : {metrics['data_scope']}")
    print(f"Customers monitored       : {metrics['customers_monitored']}")
    print(f"Interventions executed    : {metrics['interventions_executed']}")
    print(f"Successful recoveries     : {metrics['successful_recoveries']}")
    print(f"Recovery rate             : {metrics['recovery_rate_percent']}%")
    print(f"Revenue at risk           : INR {metrics['revenue_at_risk']:.2f}")
    print(f"Amount recovered          : INR {metrics['amount_recovered']:.2f}")
    print(
        "Revenue recovery rate    : "
        f"{metrics['revenue_recovery_percent']}%"
    )
    print("=" * 70)


if __name__ == "__main__":
    display_metrics(save_metrics())
