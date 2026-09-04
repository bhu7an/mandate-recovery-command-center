from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import agent_memory  # noqa: E402
import recovery_policy  # noqa: E402
from action_engine import apply_outcome_policy, determine_base_action  # noqa: E402


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temp_dir.name)
        self.original_policy_file = recovery_policy.POLICY_FILE
        self.original_memory_file = agent_memory.MEMORY_FILE
        recovery_policy.POLICY_FILE = temporary_path / "merchant_policy.local.json"
        agent_memory.MEMORY_FILE = str(temporary_path / "agent_memory.json")
        agent_memory.save_memory({})

    def tearDown(self) -> None:
        recovery_policy.POLICY_FILE = self.original_policy_file
        agent_memory.MEMORY_FILE = self.original_memory_file
        self.temp_dir.cleanup()

    def test_missing_policy_uses_safe_defaults(self) -> None:
        policy = recovery_policy.load_policy()
        self.assertEqual(policy["max_customer_contacts"], 2)
        self.assertEqual(policy["contact_window_hours"], 72)
        self.assertTrue(policy["stop_after_success"])

    def test_policy_is_saved_atomically_and_versioned(self) -> None:
        first = recovery_policy.save_policy(recovery_policy.default_policy())
        second = recovery_policy.save_policy(first)
        self.assertEqual(first["version"], 2)
        self.assertEqual(second["version"], 3)
        self.assertEqual(recovery_policy.load_policy(), second)
        self.assertFalse(
            recovery_policy.POLICY_FILE.with_suffix(".json.tmp").exists()
        )

    def test_unordered_thresholds_are_rejected(self) -> None:
        policy = recovery_policy.default_policy()
        policy["thresholds"]["high_risk_below"] = 70
        policy["thresholds"]["at_risk_below"] = 60
        with self.assertRaisesRegex(
            recovery_policy.PolicyValidationError, "strictly increasing"
        ):
            recovery_policy.validate_policy(policy)

    def test_unknown_automated_action_is_rejected(self) -> None:
        policy = recovery_policy.default_policy()
        policy["allowed_automated_actions"].append("CHARGE_CARD")
        with self.assertRaisesRegex(
            recovery_policy.PolicyValidationError, "Unsupported automated action"
        ):
            recovery_policy.validate_policy(policy)

    def test_action_allowlist_changes_the_base_decision(self) -> None:
        policy = recovery_policy.default_policy()
        policy["allowed_automated_actions"] = []
        customer = {"health_score": 50}
        change = {"change": 0, "previous_score": None}
        self.assertEqual(
            determine_base_action(customer, change, policy),
            ("MONITOR", "LOW", "AUTOMATION_NOT_PERMITTED"),
        )

    def test_configured_contact_cap_blocks_another_contact(self) -> None:
        policy = recovery_policy.default_policy()
        policy["max_customer_contacts"] = 1
        memory = {
            "action_history": [
                {
                    "action_type": "PAYMENT_REMINDER",
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        decision = apply_outcome_policy(
            "S_POLICY",
            ("PAYMENT_REMINDER", "MEDIUM", "REMINDER_REQUIRED"),
            memory,
            policy=policy,
        )
        self.assertEqual(decision[0], "ESCALATE")
        self.assertEqual(decision[2], "CONTACT_LIMIT_REACHED")
        self.assertEqual(decision[4], "MAX_1_CONTACTS_72H")

    def test_success_can_remain_passive_without_customer_contact(self) -> None:
        policy = recovery_policy.default_policy()
        policy["stop_after_success"] = False
        decision = apply_outcome_policy(
            "S_POLICY",
            ("PAYMENT_REMINDER", "MEDIUM", "REMINDER_REQUIRED"),
            {},
            policy=policy,
            current_outcome="RECOVERED",
            evaluation_status="OUTCOME_RECORDED",
            current_event_status="success",
        )
        self.assertEqual(decision[0], "MONITOR")
        self.assertEqual(decision[2], "RECOVERY_MONITORING")
        self.assertEqual(decision[4], "NO_CONTACT_ON_SUCCESS")

    def test_second_success_does_not_reuse_a_stale_recovery_label(self) -> None:
        decision = apply_outcome_policy(
            "S_POLICY",
            ("NO_INTERVENTION", "LOW", "NO_ACTION_REQUIRED"),
            {"last_outcome": "RECOVERED"},
            policy=recovery_policy.default_policy(),
            current_outcome="NOT_APPLICABLE",
            evaluation_status="NO_PENDING_ACTION",
            current_event_status="success",
        )
        self.assertEqual(decision[0], "NO_INTERVENTION")
        self.assertEqual(decision[2], "CURRENT_PAYMENT_SUCCESS")
        self.assertEqual(decision[4], "NO_ACTION_ON_SUCCESS")


if __name__ == "__main__":
    unittest.main()
