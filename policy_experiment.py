"""Paired synthetic benchmark of the adaptive policy against fixed reminders.

This module is an evidence harness, not a production-impact claim. Every trial
gives both strategies the same synthetic mandate cases and the same random
outcome draw. The only difference is the decision policy being evaluated.
"""

from __future__ import annotations

import json
import random
from math import sqrt
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Iterable

from policy_simulator import simulate_policy
from recovery_policy import load_policy, validate_policy


BASE_SEED = 20260904
DEFAULT_TRIALS = 30
DEFAULT_COHORT_SIZE = 500
OUTPUT_DIR = Path("experiment_output")

SCORE_POPULATION = (15, 30, 53, 76)
SCORE_WEIGHTS = (10, 25, 50, 15)
AMOUNTS = (299.0, 499.0, 599.0, 799.0, 999.0, 1299.0)
SYSTEMIC_SHARE = 0.12


def reminder_recovery_probability(score: int, systemic_incident: bool) -> float:
    """Explicit scenario assumption for a one-size-fits-all reminder."""

    if systemic_incident:
        return 0.02
    if score < 20:
        return 0.20
    if score < 40:
        return 0.35
    if score < 60:
        return 0.56
    return 0.30


def action_recovery_probability(
    action: str,
    score: int,
    systemic_incident: bool,
) -> float:
    """Return the declared synthetic recovery assumption for an agent action."""

    if action == "PAYMENT_REMINDER":
        return reminder_recovery_probability(score, systemic_incident)
    if action == "HIGH_PRIORITY_RECOVERY" and not systemic_incident:
        if score < 20:
            return 0.50
        if score < 40:
            return 0.70
        if score < 60:
            return 0.62
        return 0.40
    return 0.0


def generate_cases(
    seed: int,
    cohort_size: int = DEFAULT_COHORT_SIZE,
) -> list[dict[str, Any]]:
    """Create one reproducible cohort with an exact 12% systemic share."""

    if cohort_size < 1:
        raise ValueError("cohort_size must be at least 1")
    rng = random.Random(seed)
    incident_count = round(cohort_size * SYSTEMIC_SHARE)
    incident_indexes = set(rng.sample(range(cohort_size), incident_count))
    cases: list[dict[str, Any]] = []
    for index in range(cohort_size):
        score = rng.choices(SCORE_POPULATION, weights=SCORE_WEIGHTS, k=1)[0]
        cases.append(
            {
                "subscription_id": f"EXP-{seed}-{index + 1:04d}",
                "health_score": score,
                "previous_health_score": min(100, score + 5),
                "recent_contacts": 0,
                "systemic_incident": index in incident_indexes,
                "amount": rng.choice(AMOUNTS),
                # A common outcome draw makes the comparison paired: both
                # strategies face the same underlying simulated customer.
                "outcome_draw": rng.random(),
            }
        )
    return cases


def _rate(numerator: float, denominator: float) -> float:
    return round((numerator / denominator * 100) if denominator else 0.0, 4)


def evaluate_cases(
    cases: Iterable[dict[str, Any]],
    policy_candidate: dict[str, Any],
) -> dict[str, dict[str, float]]:
    """Evaluate adaptive and fixed-reminder strategies on identical cases."""

    policy = validate_policy(policy_candidate)
    rows = list(cases)
    if not rows:
        raise ValueError("At least one case is required")

    totals: dict[str, dict[str, float]] = {
        "adaptive_agent": {
            "recovered_customers": 0.0,
            "amount_recovered": 0.0,
            "interventions": 0.0,
            "systemic_contacts": 0.0,
            "human_escalations": 0.0,
        },
        "fixed_reminder_baseline": {
            "recovered_customers": 0.0,
            "amount_recovered": 0.0,
            "interventions": 0.0,
            "systemic_contacts": 0.0,
            "human_escalations": 0.0,
        },
    }
    revenue_at_risk = sum(float(row["amount"]) for row in rows)

    for row in rows:
        scenario = {
            "subscription_id": row["subscription_id"],
            "health_score": row["health_score"],
            "previous_health_score": row["previous_health_score"],
            "recent_contacts": row.get("recent_contacts", 0),
            "systemic_incident": row["systemic_incident"],
        }
        decision = simulate_policy(scenario, policy)
        action = decision["action"]
        adaptive_probability = action_recovery_probability(
            action,
            int(row["health_score"]),
            bool(row["systemic_incident"]),
        )
        if decision["customer_contact"]:
            totals["adaptive_agent"]["interventions"] += 1
            if row["systemic_incident"]:
                totals["adaptive_agent"]["systemic_contacts"] += 1
        if decision["human_review"]:
            totals["adaptive_agent"]["human_escalations"] += 1
        if float(row["outcome_draw"]) < adaptive_probability:
            totals["adaptive_agent"]["recovered_customers"] += 1
            totals["adaptive_agent"]["amount_recovered"] += float(row["amount"])

        baseline_probability = reminder_recovery_probability(
            int(row["health_score"]),
            bool(row["systemic_incident"]),
        )
        totals["fixed_reminder_baseline"]["interventions"] += 1
        if row["systemic_incident"]:
            totals["fixed_reminder_baseline"]["systemic_contacts"] += 1
        if float(row["outcome_draw"]) < baseline_probability:
            totals["fixed_reminder_baseline"]["recovered_customers"] += 1
            totals["fixed_reminder_baseline"]["amount_recovered"] += float(
                row["amount"]
            )

    result: dict[str, dict[str, float]] = {}
    cohort_size = len(rows)
    for strategy, values in totals.items():
        interventions = values["interventions"]
        result[strategy] = {
            **{key: round(value, 2) for key, value in values.items()},
            "customer_recovery_rate_percent": _rate(
                values["recovered_customers"], cohort_size
            ),
            "revenue_recovery_rate_percent": _rate(
                values["amount_recovered"], revenue_at_risk
            ),
            "interventions_per_100": _rate(interventions, cohort_size),
            "recoveries_per_100_interventions": _rate(
                values["recovered_customers"], interventions
            ),
            "systemic_contacts_per_100": _rate(
                values["systemic_contacts"], cohort_size
            ),
            "human_escalations_per_100": _rate(
                values["human_escalations"], cohort_size
            ),
        }
    return result


def _summary(values: list[float]) -> dict[str, float]:
    average = mean(values)
    margin = 0.0 if len(values) == 1 else 1.96 * stdev(values) / sqrt(len(values))
    return {
        "mean": round(average, 2),
        "ci95_low": round(average - margin, 2),
        "ci95_high": round(average + margin, 2),
        "observed_low": round(min(values), 2),
        "observed_high": round(max(values), 2),
    }


def run_experiment(
    policy_candidate: dict[str, Any],
    *,
    trials: int = DEFAULT_TRIALS,
    cohort_size: int = DEFAULT_COHORT_SIZE,
    base_seed: int = BASE_SEED,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a reproducible, paired multi-trial policy benchmark."""

    if trials < 1 or trials > 500:
        raise ValueError("trials must be between 1 and 500")
    if cohort_size < 1 or cohort_size > 100_000:
        raise ValueError("cohort_size must be between 1 and 100000")
    policy = validate_policy(policy_candidate)
    runs: list[dict[str, Any]] = []
    for trial in range(trials):
        seed = base_seed + trial
        metrics = evaluate_cases(generate_cases(seed, cohort_size), policy)
        adaptive = metrics["adaptive_agent"]
        baseline = metrics["fixed_reminder_baseline"]
        runs.append(
            {
                "trial": trial + 1,
                "seed": seed,
                **metrics,
                "paired_difference": {
                    "recovery_rate_percentage_points": round(
                        adaptive["customer_recovery_rate_percent"]
                        - baseline["customer_recovery_rate_percent"],
                        4,
                    ),
                    "revenue_recovery_percentage_points": round(
                        adaptive["revenue_recovery_rate_percent"]
                        - baseline["revenue_recovery_rate_percent"],
                        4,
                    ),
                    "interventions_avoided_per_100": round(
                        baseline["interventions_per_100"]
                        - adaptive["interventions_per_100"],
                        4,
                    ),
                    "systemic_contacts_prevented_per_100": round(
                        baseline["systemic_contacts_per_100"]
                        - adaptive["systemic_contacts_per_100"],
                        4,
                    ),
                    "recovery_efficiency_percentage_points": round(
                        adaptive["recoveries_per_100_interventions"]
                        - baseline["recoveries_per_100_interventions"],
                        4,
                    ),
                },
            }
        )

    metric_names = (
        "customer_recovery_rate_percent",
        "revenue_recovery_rate_percent",
        "interventions_per_100",
        "recoveries_per_100_interventions",
        "systemic_contacts_per_100",
        "human_escalations_per_100",
    )
    strategy_summary: dict[str, dict[str, dict[str, float]]] = {}
    for strategy in ("adaptive_agent", "fixed_reminder_baseline"):
        strategy_summary[strategy] = {
            metric: _summary([run[strategy][metric] for run in runs])
            for metric in metric_names
        }
    difference_names = tuple(runs[0]["paired_difference"])
    paired_summary = {
        metric: _summary(
            [run["paired_difference"][metric] for run in runs]
        )
        for metric in difference_names
    }

    benchmark = {
        "data_scope": "SYNTHETIC_PAIRED_POLICY_EXPERIMENT",
        "experiment_name": "Adaptive Agent vs Fixed Reminder",
        "protocol": {
            "trials": trials,
            "cohort_size_per_trial": cohort_size,
            "paired_scenarios_evaluated": trials * cohort_size,
            "strategy_decisions_evaluated": trials * cohort_size * 2,
            "base_seed": base_seed,
            "common_random_numbers": True,
            "summary_method": "Mean across trials with normal 95% simulation CI",
            "systemic_failure_share_percent": SYSTEMIC_SHARE * 100,
            "score_population": list(SCORE_POPULATION),
            "score_weights_percent": list(SCORE_WEIGHTS),
            "active_policy_name": policy["policy_name"],
            "active_policy_version": policy["version"],
            "baseline": "One fixed payment reminder for every failed mandate",
        },
        "adaptive_agent": strategy_summary["adaptive_agent"],
        "fixed_reminder_baseline": strategy_summary["fixed_reminder_baseline"],
        "paired_difference": paired_summary,
        "headline": (
            "Across identical seeded cases, the adaptive policy targets fewer "
            "customers, suppresses systemic-failure contacts, and measures "
            "recovery efficiency separately from raw recovery."
        ),
        "assumptions": {
            "fixed_reminder_recovery_probability": {
                "critical": 0.20,
                "high_risk": 0.35,
                "at_risk": 0.56,
                "stable": 0.30,
                "systemic_failure": 0.02,
            },
            "high_priority_recovery_probability": {
                "critical": 0.50,
                "high_risk": 0.70,
                "at_risk": 0.62,
                "stable": 0.40,
                "systemic_failure": 0.0,
            },
        },
        "limitations": [
            "All customers and outcomes are synthetic; this is not production recovery lift.",
            "Recovery probabilities are declared scenario assumptions, not trained estimates.",
            "The comparison evaluates first-action policy quality, not a clinical or causal model.",
            "Human-review outcomes are not counted as automatic recoveries inside this window.",
        ],
    }
    return benchmark, runs


def save_experiment(
    benchmark: dict[str, Any],
    runs: list[dict[str, Any]],
    output_dir: Path = OUTPUT_DIR,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("policy_benchmark.json", benchmark),
        ("experiment_runs.json", runs),
    ):
        with (output_dir / filename).open("w", encoding="utf-8") as file:
            json.dump(content, file, indent=4)
            file.write("\n")


def main() -> None:
    benchmark, runs = run_experiment(load_policy())
    save_experiment(benchmark, runs)
    adaptive = benchmark["adaptive_agent"]
    baseline = benchmark["fixed_reminder_baseline"]
    difference = benchmark["paired_difference"]
    print("=" * 84)
    print("         ADAPTIVE AGENT VS FIXED-REMINDER BENCHMARK")
    print("        SYNTHETIC · PAIRED · REPRODUCIBLE · API-FREE")
    print("=" * 84)
    print(
        "Trials / cohort          : "
        f"{benchmark['protocol']['trials']} × "
        f"{benchmark['protocol']['cohort_size_per_trial']}"
    )
    print(
        "Customer recovery rate  : "
        f"Agent {adaptive['customer_recovery_rate_percent']['mean']}% | "
        f"Fixed {baseline['customer_recovery_rate_percent']['mean']}%"
    )
    print(
        "Interventions per 100   : "
        f"Agent {adaptive['interventions_per_100']['mean']} | "
        f"Fixed {baseline['interventions_per_100']['mean']}"
    )
    print(
        "Recovery efficiency     : "
        f"Agent {adaptive['recoveries_per_100_interventions']['mean']} | "
        f"Fixed {baseline['recoveries_per_100_interventions']['mean']}"
    )
    print(
        "Systemic contacts / 100 : "
        f"Agent {adaptive['systemic_contacts_per_100']['mean']} | "
        f"Fixed {baseline['systemic_contacts_per_100']['mean']}"
    )
    print(
        "Interventions avoided   : "
        f"{difference['interventions_avoided_per_100']['mean']} per 100"
    )
    print("=" * 84)
    print(f"Results saved under     : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
