from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from policy_experiment import (  # noqa: E402
    evaluate_cases,
    generate_cases,
    run_experiment,
    save_experiment,
)
from recovery_policy import default_policy  # noqa: E402


class PolicyExperimentTests(unittest.TestCase):
    def test_seeded_experiment_is_reproducible(self) -> None:
        first, first_runs = run_experiment(
            default_policy(), trials=3, cohort_size=60, base_seed=1234
        )
        second, second_runs = run_experiment(
            default_policy(), trials=3, cohort_size=60, base_seed=1234
        )
        self.assertEqual(first, second)
        self.assertEqual(first_runs, second_runs)

    def test_both_strategies_receive_the_same_generated_cases(self) -> None:
        self.assertEqual(generate_cases(77, 25), generate_cases(77, 25))
        self.assertNotEqual(generate_cases(77, 25), generate_cases(78, 25))

    def test_systemic_cases_are_suppressed_only_by_adaptive_policy(self) -> None:
        cases = [
            {
                "subscription_id": f"SYS-{index}",
                "health_score": 53,
                "previous_health_score": 58,
                "recent_contacts": 0,
                "systemic_incident": True,
                "amount": 599.0,
                "outcome_draw": 0.99,
            }
            for index in range(10)
        ]
        result = evaluate_cases(cases, default_policy())
        self.assertEqual(result["adaptive_agent"]["systemic_contacts"], 0)
        self.assertEqual(
            result["fixed_reminder_baseline"]["systemic_contacts"], 10
        )
        self.assertEqual(
            result["fixed_reminder_baseline"]["interventions_per_100"], 100
        )

    def test_report_keeps_assumptions_and_limitations_visible(self) -> None:
        report, _ = run_experiment(
            default_policy(), trials=2, cohort_size=40, base_seed=91
        )
        self.assertEqual(
            report["data_scope"], "SYNTHETIC_PAIRED_POLICY_EXPERIMENT"
        )
        self.assertTrue(report["protocol"]["common_random_numbers"])
        self.assertIn("fixed_reminder_recovery_probability", report["assumptions"])
        self.assertGreaterEqual(len(report["limitations"]), 4)

    def test_saved_report_contains_summary_and_raw_runs(self) -> None:
        report, runs = run_experiment(
            default_policy(), trials=2, cohort_size=30, base_seed=55
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            save_experiment(report, runs, output)
            saved_report = json.loads(
                (output / "policy_benchmark.json").read_text(encoding="utf-8")
            )
            saved_runs = json.loads(
                (output / "experiment_runs.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved_report, report)
            self.assertEqual(saved_runs, runs)


if __name__ == "__main__":
    unittest.main()
