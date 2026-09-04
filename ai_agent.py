import json
import os
import pandas as pd


# ============================================================
# MANDATE HEALTH AI AGENT
# API-FREE VERSION
# ============================================================


# ============================================================
# LOAD CUSTOMER SCORES
# ============================================================

def load_customer_scores():

    file_name = "customer_health_scores.csv"

    if not os.path.exists(file_name):

        print()
        print("ERROR:")
        print(f"{file_name} was not found.")
        print()
        print("Run scoring_engine.py first.")
        print()

        return None

    df = pd.read_csv(
        file_name
    )

    return df


# ============================================================
# DETERMINE PRIMARY PROBLEM
# ============================================================

def determine_primary_problem(row):

    health_score = row[
        "health_score"
    ]

    failure_risk = row[
        "failure_risk"
    ]

    consecutive_risk = row[
        "consecutive_failure_risk"
    ]

    retry_risk = row[
        "retry_risk"
    ]

    recovery_risk = row[
        "recovery_delay_risk"
    ]

    deterioration_risk = row[
        "deterioration_risk"
    ]

    unresolved = row[
        "unresolved_failures"
    ]

    # --------------------------------------------------------
    # CRITICAL: MULTIPLE UNRESOLVED FAILURES
    # --------------------------------------------------------

    if unresolved >= 3:

        return (
            "Repeated unresolved payment failures"
        )

    # --------------------------------------------------------
    # HIGH CONSECUTIVE FAILURE PATTERN
    # --------------------------------------------------------

    if consecutive_risk >= 20:

        return (
            "Multiple consecutive payment failures"
        )

    # --------------------------------------------------------
    # STRONG DETERIORATION
    # --------------------------------------------------------

    if deterioration_risk >= 12:

        return (
            "Payment behaviour is strongly deteriorating"
        )

    # --------------------------------------------------------
    # SOME UNRESOLVED FAILURES
    # --------------------------------------------------------

    if unresolved > 0:

        return (
            "Payment failures are not being consistently recovered"
        )

    # --------------------------------------------------------
    # REPEATED RETRIES
    # --------------------------------------------------------

    if retry_risk >= 12:

        return (
            "Payments frequently require repeated retries"
        )

    # --------------------------------------------------------
    # HIGH FAILURE RATE
    # --------------------------------------------------------

    if failure_risk >= 24:

        return (
            "High payment failure rate"
        )

    # --------------------------------------------------------
    # RECOVERY DELAY
    # --------------------------------------------------------

    if recovery_risk >= 12:

        if failure_risk <= 12:

            return (
                "An isolated payment failure required "
                "a delayed recovery"
            )

        return (
            "Payment recovery is taking longer than expected"
        )

    # --------------------------------------------------------
    # HEALTHY
    # --------------------------------------------------------

    if health_score >= 80:

        return (
            "No significant payment health problem"
        )

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    return (
        "Moderate payment risk"
    )


# ============================================================
# BUILD RISK EXPLANATION
# ============================================================

def build_risk_explanation(row):

    explanations = []

    # --------------------------------------------------------
    # UNRESOLVED FAILURES
    # --------------------------------------------------------

    if row[
        "unresolved_failures"
    ] > 0:

        explanations.append(
            f"{int(row['unresolved_failures'])} "
            "failed payment(s) remain unresolved."
        )

    # --------------------------------------------------------
    # CONSECUTIVE FAILURES
    # --------------------------------------------------------

    if row[
        "consecutive_failure_risk"
    ] >= 20:

        explanations.append(
            "Multiple payment failures have occurred "
            "consecutively."
        )

    elif row[
        "consecutive_failure_risk"
    ] >= 10:

        explanations.append(
            "There is a pattern of consecutive "
            "payment failures."
        )

    # --------------------------------------------------------
    # FAILURE RATE
    # --------------------------------------------------------

    if row[
        "failure_risk"
    ] >= 24:

        explanations.append(
            "The customer has a high payment failure risk."
        )

    elif row[
        "failure_risk"
    ] >= 12:

        explanations.append(
            "The customer has experienced "
            "multiple payment failures."
        )

    # --------------------------------------------------------
    # RECOVERY DELAY
    # --------------------------------------------------------

    if (
        row["recovery_delay_risk"] >= 12
        and row["unresolved_failures"] == 0
    ):

        delay = row[
            "average_recovery_delay_hours"
        ]

        if pd.notna(delay):

            explanations.append(
                f"Successful payment recovery takes "
                f"an average of {float(delay):.1f} hours."
            )

    # --------------------------------------------------------
    # DETERIORATION
    # --------------------------------------------------------

    if row[
        "deterioration_risk"
    ] >= 12:

        explanations.append(
            "Recent payment behaviour is "
            "strongly deteriorating."
        )

    elif row[
        "deterioration_risk"
    ] >= 6:

        explanations.append(
            "Recent payment behaviour shows "
            "signs of deterioration."
        )

    # --------------------------------------------------------
    # RETRY
    # --------------------------------------------------------

    if (
        row["retry_risk"] >= 12
        and len(explanations) < 3
    ):

        explanations.append(
            "Failed payments frequently require "
            "additional retries."
        )

    # --------------------------------------------------------
    # HEALTHY
    # --------------------------------------------------------

    if len(explanations) == 0:

        explanations.append(
            "Payment behaviour is currently stable."
        )

    return explanations[:3]


# ============================================================
# DETERMINE RECOMMENDED ACTION
# ============================================================

def determine_action(row):

    health_score = row[
        "health_score"
    ]

    unresolved = row[
        "unresolved_failures"
    ]

    consecutive_risk = row[
        "consecutive_failure_risk"
    ]

    deterioration_risk = row[
        "deterioration_risk"
    ]

    recovery_risk = row[
        "recovery_delay_risk"
    ]

    # --------------------------------------------------------
    # CRITICAL
    # --------------------------------------------------------

    if health_score <= 19:

        if unresolved > 0:

            return "ESCALATE"

        return "HIGH_PRIORITY_RECOVERY"

    # --------------------------------------------------------
    # HIGH RISK
    # --------------------------------------------------------

    if health_score <= 39:

        if (
            unresolved > 0
            or consecutive_risk >= 20
        ):

            return "HIGH_PRIORITY_RECOVERY"

        return "PAYMENT_REMINDER"

    # --------------------------------------------------------
    # AT RISK
    # --------------------------------------------------------

    if health_score <= 59:

        if deterioration_risk >= 12:

            return "HIGH_PRIORITY_RECOVERY"

        if recovery_risk >= 12:

            return "PAYMENT_REMINDER"

        return "MONITOR"

    # --------------------------------------------------------
    # STABLE
    # --------------------------------------------------------

    if health_score <= 79:

        return "MONITOR"

    # --------------------------------------------------------
    # HEALTHY
    # --------------------------------------------------------

    return "NO_INTERVENTION"


# ============================================================
# DETERMINE PRIORITY
# ============================================================

def determine_priority(
    health_score,
    action
):

    if action == "ESCALATE":

        return "CRITICAL"

    if action == "HIGH_PRIORITY_RECOVERY":

        return "HIGH"

    if action == "PAYMENT_REMINDER":

        return "MEDIUM"

    if action == "MONITOR":

        return "LOW"

    return "LOW"


# ============================================================
# BUILD REASON
# ============================================================

def build_reason(
    row,
    action
):

    if action == "ESCALATE":

        return (
            "The customer has critical payment health "
            "with unresolved failures. Immediate "
            "intervention is recommended."
        )

    if action == "HIGH_PRIORITY_RECOVERY":

        return (
            "The customer's payment behaviour indicates "
            "significant recovery risk. A high-priority "
            "payment recovery intervention is recommended."
        )

    if action == "PAYMENT_REMINDER":

        return (
            "The customer shows moderate payment risk. "
            "A payment reminder can be used before "
            "the situation becomes more serious."
        )

    if action == "MONITOR":

        return (
            "The customer's payment health is currently "
            "stable but should continue to be monitored."
        )

    return (
        "The customer has healthy payment behaviour "
        "and does not currently require intervention."
    )


# ============================================================
# DETERMINE CONFIDENCE
# ============================================================

def determine_confidence(row):

    health_score = int(
        row["health_score"]
    )

    if health_score <= 19:

        return 0.95

    if health_score <= 39:

        return 0.90

    if health_score <= 59:

        return 0.85

    if health_score <= 79:

        return 0.80

    return 0.95


# ============================================================
# ANALYZE CUSTOMER
# ============================================================

def analyze_customer(row):

    subscription_id = row[
        "subscription_id"
    ]

    latest_payment_id = row[
        "latest_payment_id"
    ]

    latest_attempt_id = row.get(
        "latest_attempt_id"
    )
    if pd.isna(latest_attempt_id):
        latest_attempt_id = None

    latest_amount = row.get(
        "latest_amount",
        0
    )
    if pd.isna(latest_amount):
        latest_amount = 0

    latest_payment_status = row.get(
        "latest_payment_status",
        "unknown"
    )

    latest_failure_reason = row.get(
        "latest_failure_reason"
    )
    if pd.isna(latest_failure_reason):
        latest_failure_reason = None

    health_score = int(
        row["health_score"]
    )

    health_status = row[
        "health_status"
    ]

    # --------------------------------------------------------
    # PRIMARY PROBLEM
    # --------------------------------------------------------

    primary_problem = (
        determine_primary_problem(
            row
        )
    )

    # --------------------------------------------------------
    # RISK EXPLANATION
    # --------------------------------------------------------

    risk_explanation = (
        build_risk_explanation(
            row
        )
    )

    # --------------------------------------------------------
    # ACTION
    # --------------------------------------------------------

    action = (
        determine_action(
            row
        )
    )

    # --------------------------------------------------------
    # PRIORITY
    # --------------------------------------------------------

    priority = (
        determine_priority(
            health_score,
            action
        )
    )

    # --------------------------------------------------------
    # REASON
    # --------------------------------------------------------

    reason = (
        build_reason(
            row,
            action
        )
    )

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    confidence = (
        determine_confidence(
            row
        )
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    result = {

        "subscription_id":
            subscription_id,

        "event_id":
            latest_attempt_id or latest_payment_id,

        "attempt_id":
            latest_attempt_id,

        "payment_id":
            latest_payment_id,

        "amount":
            float(latest_amount),

        "payment_status":
            latest_payment_status,

        "failure_reason":
            latest_failure_reason,

        "health_score":
            health_score,

        "health_status":
            health_status,

        "primary_problem":
            primary_problem,

        "risk_explanation":
            risk_explanation,

        "recommended_action":
            action,

        "priority":
            priority,

        "reason":
            reason,

        "confidence":
            confidence
    }

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 100)

    print(
        "              MANDATE HEALTH AI AGENT"
    )

    print(
        "                    API-FREE MODE"
    )

    print("=" * 100)

    print()

    # --------------------------------------------------------
    # LOAD CUSTOMER DATA
    # --------------------------------------------------------

    df = load_customer_scores()

    if df is None:

        return

    if df.empty:

        print(
            "customer_health_scores.csv is empty."
        )

        return

    active_subscription = os.getenv(
        "MANDATE_ACTIVE_SUBSCRIPTION_ID"
    )
    if active_subscription:
        df = df[
            df["subscription_id"].astype(str)
            == active_subscription
        ]

    print(
        f"Loaded {len(df)} customer(s)."
    )

    print()

    results = []

    # --------------------------------------------------------
    # ANALYZE EACH CUSTOMER
    # --------------------------------------------------------

    for _, row in df.iterrows():

        subscription_id = row[
            "subscription_id"
        ]

        print(
            f"Analyzing {subscription_id}..."
        )

        try:

            result = analyze_customer(
                row
            )

            results.append(
                result
            )

        except Exception as error:

            print(
                f"ERROR analyzing "
                f"{subscription_id}: {error}"
            )

    # --------------------------------------------------------
    # DISPLAY RESULTS
    # --------------------------------------------------------

    print()

    print("=" * 100)

    print(
        "                    AI AGENT RESULTS"
    )

    print("=" * 100)

    print()

    for result in results:

        print(
            f"Customer              : "
            f"{result['subscription_id']}"
        )

        print(
            f"Attempt / Payment     : "
            f"{result['attempt_id']} / "
            f"{result['payment_id']}"
        )

        print(
            f"Health Score          : "
            f"{result['health_score']}/100"
        )

        print(
            f"Health Status         : "
            f"{result['health_status']}"
        )

        print(
            f"Primary Problem       : "
            f"{result['primary_problem']}"
        )

        print()

        print(
            "Risk Explanation:"
        )

        for explanation in result[
            "risk_explanation"
        ]:

            print(
                f"  - {explanation}"
            )

        print()

        print(
            f"Recommended Action    : "
            f"{result['recommended_action']}"
        )

        print(
            f"Priority              : "
            f"{result['priority']}"
        )

        print(
            f"Reason                : "
            f"{result['reason']}"
        )

        print(
            f"Confidence            : "
            f"{result['confidence']}"
        )

        print()

        print(
            "-" * 100
        )

    # --------------------------------------------------------
    # SAVE JSON
    # --------------------------------------------------------

    output_file = (
        "ai_agent_results.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            indent=4
        )

    print()

    print(
        f"AI agent results saved to "
        f"{output_file}"
    )

    print()


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    main()
