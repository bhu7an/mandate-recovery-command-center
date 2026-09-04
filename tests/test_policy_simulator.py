from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import agent_memory  # noqa: E402
from policy_simulator import (  # noqa: E402
    ScenarioValidationError,
    compare_policies,
)
from recovery_policy import default_policy  # noqa: E402


def scenario(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "subscription_id": "S005",
        "health_score": 45,
        "previous_health_score": 50,
        "recent_contacts": 0,
        "systemic_incident": False,
    }
    result.update(overrides)
    return result


class PolicySimulatorTests(unittest.TestCase):
    def test_threshold_change_moves_same_customer_to_recovery(self) -> None:
        active = default_policy()
        proposed = default_policy()
        proposed["policy_name"] = "Earlier Recovery Draft"
        proposed["thresholds"]["high_risk_below"] = 50

        result = compare_policies(scenario(), proposed, active)

        self.assertEqual(result["active"]["action"], "PAYMENT_REMINDER")
        self.assertEqual(result["proposed"]["action"], "HIGH_PRIORITY_RECOVERY")
        self.assertTrue(result["material_change"])
        self.assertIn("action", result["changed_fields"])

    def test_contact_cap_can_replace_contact_with_human_review(self) -> None:
        active = default_policy()
        proposed = default_policy()
        proposed["max_customer_contacts"] = 1

        result = compare_policies(
            scenario(recent_contacts=1), proposed, active
        )

        self.assertEqual(result["active"]["action"], "PAYMENT_REMINDER")
        self.assertEqual(result["proposed"]["action"], "ESCALATE")
        self.assertEqual(
            result["proposed"]["action_status"], "CONTACT_LIMIT_REACHED"
        )
        self.assertFalse(result["proposed"]["customer_contact"])

    def test_identical_policy_reports_no_material_change(self) -> None:
        policy = default_policy()
        result = compare_policies(scenario(), policy, policy)
        self.assertFalse(result["material_change"])
        self.assertEqual(result["changed_fields"], [])

    def test_systemic_incident_toggle_changes_control_path(self) -> None:
        active = default_policy()
        proposed = default_policy()
        proposed["suppress_contacts_during_systemic_incident"] = False

        result = compare_policies(
            scenario(systemic_incident=True), proposed, active
        )

        self.assertEqual(result["active"]["action"], "MONITOR")
        self.assertEqual(
            result["active"]["guardrail"], "SYSTEMIC_FAILURE_SUPPRESSION"
        )
        self.assertEqual(result["proposed"]["action"], "ESCALATE")
        self.assertTrue(result["proposed"]["human_review"])

    def test_invalid_score_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ScenarioValidationError, "health_score must be between 0 and 100"
        ):
            compare_policies(
                scenario(health_score=101), default_policy(), default_policy()
            )

    def test_counterfactual_does_not_mutate_agent_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            original_file = agent_memory.MEMORY_FILE
            try:
                memory_path = Path(temporary_directory) / "agent_memory.json"
                agent_memory.MEMORY_FILE = str(memory_path)
                sentinel = {"S005": {"last_outcome": "RECOVERED"}}
                agent_memory.save_memory(sentinel)

                compare_policies(
                    scenario(), default_policy(), default_policy()
                )

                self.assertEqual(json.loads(memory_path.read_text()), sentinel)
            finally:
                agent_memory.MEMORY_FILE = original_file


if __name__ == "__main__":
    unittest.main()
