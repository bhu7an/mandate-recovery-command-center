from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import agent_memory  # noqa: E402
import outcome_evaluator  # noqa: E402
import recovery_metrics  # noqa: E402
from action_engine import process_customer  # noqa: E402
from action_simulator import simulate_action  # noqa: E402
from ai_agent import determine_action  # noqa: E402
from incident_detector import detect_incident  # noqa: E402


def customer(
    subscription_id: str,
    attempt_id: str,
    payment_id: str,
    health_score: int = 53,
) -> dict[str, object]:
    return {
        "subscription_id": subscription_id,
        "attempt_id": attempt_id,
        "payment_id": payment_id,
        "event_id": attempt_id,
        "amount": 499.0,
        "health_score": health_score,
        "health_status": "At Risk" if health_score < 60 else "Stable",
        "recommended_action": "PAYMENT_REMINDER"
        if health_score < 60
        else "MONITOR",
    }


class AdaptiveRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temp_dir.name)
        agent_memory.MEMORY_FILE = str(temporary_path / "agent_memory.json")
        outcome_evaluator.OUTCOME_HISTORY_FILE = (
            temporary_path / "outcome_history.json"
        )
        recovery_metrics.OUTPUT_FILE = temporary_path / "recovery_metrics.json"
        agent_memory.save_memory({})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pending_reminder_is_suppressed_by_cooldown(self) -> None:
        agent_memory.register_action_execution(
            "S100",
            "PAYMENT_REMINDER",
            "REMINDER_REQUIRED",
            attempt_id="A100",
            payment_id="P100",
            amount_at_risk=499,
        )

        decision = process_customer(customer("S100", "A100", "P100"))

        self.assertEqual(decision["action_type"], "MONITOR")
        self.assertEqual(decision["action_status"], "COOLDOWN_MONITORING")
        simulation = simulate_action(decision)
        self.assertEqual(simulation["simulation_type"], "COOLDOWN_MONITORING")
        self.assertFalse(simulation["customer_contacted"])

    def test_ai_uses_the_strong_deterioration_threshold_consistently(self) -> None:
        row = {
            "health_score": 58,
            "unresolved_failures": 1,
            "consecutive_failure_risk": 5,
            "deterioration_risk": 10,
            "recovery_delay_risk": 15,
        }
        self.assertEqual(determine_action(row), "PAYMENT_REMINDER")

        row["deterioration_risk"] = 12
        self.assertEqual(determine_action(row), "HIGH_PRIORITY_RECOVERY")

    def test_failed_reminder_escalates_then_success_stops_actions(self) -> None:
        agent_memory.register_action_execution(
            "S200",
            "PAYMENT_REMINDER",
            "REMINDER_REQUIRED",
            attempt_id="A200",
            payment_id="P200",
            amount_at_risk=799,
        )

        failure = outcome_evaluator.evaluate_payment_event(
            {
                "subscription_id": "S200",
                "attempt_id": "A201",
                "payment_id": "P201",
                "status": "failed",
                "amount": 799,
            }
        )
        self.assertEqual(failure["outcome"], "FAILED_AFTER_ACTION")

        escalated = process_customer(customer("S200", "A201", "P201", 45))
        self.assertEqual(escalated["action_type"], "HIGH_PRIORITY_RECOVERY")
        self.assertEqual(
            escalated["action_status"], "ESCALATED_AFTER_FAILED_REMINDER"
        )

        agent_memory.register_action_execution(
            "S200",
            escalated["action_type"],
            escalated["action_status"],
            attempt_id="A201",
            payment_id="P201",
            amount_at_risk=799,
        )
        recovered = outcome_evaluator.evaluate_payment_event(
            {
                "subscription_id": "S200",
                "attempt_id": "A202",
                "payment_id": "P202",
                "status": "success",
                "amount": 799,
            }
        )
        self.assertEqual(recovered["outcome"], "RECOVERED")
        self.assertEqual(recovered["amount_recovered"], 799)

        stopped = process_customer(customer("S200", "A202", "P202", 76))
        self.assertEqual(stopped["action_type"], "NO_INTERVENTION")
        self.assertEqual(stopped["action_status"], "RECOVERY_CONFIRMED")

        metrics = recovery_metrics.calculate_metrics()
        self.assertEqual(metrics["successful_recoveries"], 1)
        self.assertEqual(metrics["failed_recoveries"], 1)
        self.assertEqual(metrics["amount_recovered"], 799)

    def test_action_history_is_idempotent(self) -> None:
        first = agent_memory.register_action_execution(
            "S300",
            "PAYMENT_REMINDER",
            "REMINDER_REQUIRED",
            attempt_id="A300",
            payment_id="P300",
            amount_at_risk=299,
        )
        second = agent_memory.register_action_execution(
            "S300",
            "PAYMENT_REMINDER",
            "REMINDER_REQUIRED",
            attempt_id="A300",
            payment_id="P300",
            amount_at_risk=299,
        )
        self.assertEqual(first["action_id"], second["action_id"])
        memory = json.loads(Path(agent_memory.MEMORY_FILE).read_text())
        self.assertEqual(len(memory["S300"]["action_history"]), 1)

    def test_systemic_timeout_spike_suppresses_customer_contact(self) -> None:
        incident = detect_incident(
            [
                {"status": "failed", "failure_reason": "bank_timeout"},
                {"status": "failed", "failure_reason": "bank_timeout"},
                {"status": "failed", "failure_reason": "bank_timeout"},
                {"status": "success", "failure_reason": None},
            ]
        )
        self.assertTrue(incident["incident_active"])
        self.assertEqual(incident["reason"], "bank_timeout")

        os.environ["MANDATE_SYSTEMIC_INCIDENT_REASON"] = "bank_timeout"
        try:
            decision = process_customer(
                {
                    **customer("S400", "A400", "P400", 45),
                    "failure_reason": "bank_timeout",
                }
            )
        finally:
            os.environ.pop("MANDATE_SYSTEMIC_INCIDENT_REASON", None)
        self.assertEqual(decision["action_type"], "MONITOR")
        self.assertEqual(decision["action_status"], "SYSTEMIC_INCIDENT_HOLD")

        # Ordinary insufficient-balance failures must never be classified as
        # an infrastructure incident.
        normal_failures = detect_incident(
            [
                {"status": "failed", "failure_reason": "insufficient_balance"}
                for _ in range(10)
            ]
        )
        self.assertFalse(normal_failures["incident_active"])


if __name__ == "__main__":
    unittest.main()
