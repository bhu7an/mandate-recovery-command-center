"""Merchant-editable recovery policy with strict validation and safe defaults."""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
POLICY_FILE = Path(
    os.getenv(
        "MANDATE_POLICY_FILE",
        str(PROJECT_DIR / "merchant_policy.local.json"),
    )
)
POLICY_LOCK = threading.Lock()

CONTACT_ACTIONS = {"PAYMENT_REMINDER", "HIGH_PRIORITY_RECOVERY"}

DEFAULT_POLICY: dict[str, Any] = {
    "policy_name": "Trust-First Recovery",
    "version": 1,
    "thresholds": {
        "critical_below": 20,
        "high_risk_below": 40,
        "at_risk_below": 60,
        "monitor_below": 80,
    },
    "max_customer_contacts": 2,
    "contact_window_hours": 72,
    "stop_after_success": True,
    "human_approval_after_failed_recovery": True,
    "suppress_contacts_during_systemic_incident": True,
    "allowed_automated_actions": [
        "PAYMENT_REMINDER",
        "HIGH_PRIORITY_RECOVERY",
    ],
}


class PolicyValidationError(ValueError):
    """Raised when a merchant policy is incomplete or unsafe to interpret."""


def default_policy() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_POLICY)


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise PolicyValidationError(f"{field} must be a whole number")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise PolicyValidationError(f"{field} must be a whole number") from error
    if result < minimum or result > maximum:
        raise PolicyValidationError(
            f"{field} must be between {minimum} and {maximum}"
        )
    return result


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyValidationError(f"{field} must be true or false")
    return value


def validate_policy(candidate: Any) -> dict[str, Any]:
    """Return a canonical policy or raise a human-readable validation error."""

    if not isinstance(candidate, dict):
        raise PolicyValidationError("Policy must be a JSON object")

    name = str(candidate.get("policy_name") or "").strip()
    if not name:
        raise PolicyValidationError("policy_name is required")
    if len(name) > 80:
        raise PolicyValidationError("policy_name must be 80 characters or fewer")

    thresholds = candidate.get("thresholds")
    if not isinstance(thresholds, dict):
        raise PolicyValidationError("thresholds must be a JSON object")
    canonical_thresholds = {
        "critical_below": _integer(
            thresholds.get("critical_below"), "critical_below", 1, 96
        ),
        "high_risk_below": _integer(
            thresholds.get("high_risk_below"), "high_risk_below", 2, 97
        ),
        "at_risk_below": _integer(
            thresholds.get("at_risk_below"), "at_risk_below", 3, 98
        ),
        "monitor_below": _integer(
            thresholds.get("monitor_below"), "monitor_below", 4, 99
        ),
    }
    ordered = list(canonical_thresholds.values())
    if ordered != sorted(set(ordered)):
        raise PolicyValidationError(
            "Health thresholds must be strictly increasing: "
            "critical < high risk < at risk < monitor"
        )

    actions = candidate.get("allowed_automated_actions")
    if not isinstance(actions, list):
        raise PolicyValidationError("allowed_automated_actions must be a list")
    unknown_actions = {str(action) for action in actions} - CONTACT_ACTIONS
    if unknown_actions:
        raise PolicyValidationError(
            "Unsupported automated action: " + ", ".join(sorted(unknown_actions))
        )
    canonical_actions = [
        action
        for action in ("PAYMENT_REMINDER", "HIGH_PRIORITY_RECOVERY")
        if action in actions
    ]

    return {
        "policy_name": name,
        "version": _integer(candidate.get("version", 1), "version", 1, 999999),
        "thresholds": canonical_thresholds,
        "max_customer_contacts": _integer(
            candidate.get("max_customer_contacts"),
            "max_customer_contacts",
            0,
            10,
        ),
        "contact_window_hours": _integer(
            candidate.get("contact_window_hours"),
            "contact_window_hours",
            1,
            720,
        ),
        "stop_after_success": _boolean(
            candidate.get("stop_after_success"), "stop_after_success"
        ),
        "human_approval_after_failed_recovery": _boolean(
            candidate.get("human_approval_after_failed_recovery"),
            "human_approval_after_failed_recovery",
        ),
        "suppress_contacts_during_systemic_incident": _boolean(
            candidate.get("suppress_contacts_during_systemic_incident"),
            "suppress_contacts_during_systemic_incident",
        ),
        "allowed_automated_actions": canonical_actions,
    }


def load_policy() -> dict[str, Any]:
    """Load the local constitution, or return safe defaults when absent."""

    if not POLICY_FILE.exists():
        return default_policy()
    try:
        with POLICY_FILE.open("r", encoding="utf-8") as file:
            return validate_policy(json.load(file))
    except (json.JSONDecodeError, OSError) as error:
        raise PolicyValidationError(f"Could not read {POLICY_FILE.name}: {error}") from error


def save_policy(candidate: Any, *, increment_version: bool = True) -> dict[str, Any]:
    """Validate and atomically persist a new merchant constitution."""

    with POLICY_LOCK:
        canonical = validate_policy(candidate)
        if increment_version:
            try:
                current_version = load_policy()["version"]
            except PolicyValidationError:
                current_version = 0
            canonical["version"] = max(current_version + 1, canonical["version"])

        POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = POLICY_FILE.with_suffix(POLICY_FILE.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(canonical, file, indent=4)
            file.write("\n")
        temporary.replace(POLICY_FILE)
        return canonical
