import mysql.connector
import pandas as pd

from config import DB_CONFIG


# ============================================================
# MANDATE HEALTH - SCORING ENGINE
# ============================================================

# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    return mysql.connector.connect(**DB_CONFIG)


# ============================================================
# LOAD DATA
# ============================================================

def load_payment_data():

    connection = get_connection()

    query = """
        SELECT
            p.payment_id,
            p.subscription_id,
            p.customer_id,
            p.amount,
            p.status AS payment_status,
            p.payment_date,
            p.failure_reason AS payment_failure_reason,

            a.attempt_id,
            a.attempt_number,
            a.attempt_time,
            a.status AS attempt_status,
            a.failure_reason AS attempt_failure_reason

        FROM payments p

        LEFT JOIN payment_attempts a
            ON p.payment_id = a.payment_id

        ORDER BY
            p.subscription_id,
            COALESCE(a.attempt_time, p.payment_date),
            a.attempt_number
    """

    try:

        cursor = connection.cursor(
            dictionary=True
        )

        cursor.execute(query)

        rows = cursor.fetchall()

        cursor.close()

        return pd.DataFrame(rows)

    finally:

        connection.close()


# ============================================================
# BUILD SUBSCRIPTION PAYMENT TIMELINE
# ============================================================

def build_payment_timeline(group):
    if group.empty:
        return []
    group = group.copy()
    group["event_time"] = (
        group["attempt_time"]
        .fillna(group["payment_date"])
    )
    payments = []
    for payment_id, payment_rows in group.groupby(
        "payment_id",
        sort=False
    ):
        # A payment may have several attempts.  The latest attempt is the
        # authoritative result for that payment; the previous code selected
        # the first attempt and could therefore report a recovered payment as
        # failed.
        payment_rows = payment_rows.sort_values("event_time")
        row = payment_rows.iloc[-1]
        payment_status = str(row["payment_status"]).lower()
        attempt_status = str(row["attempt_status"]).lower()
        if attempt_status in {"success", "failed"}:
            status = attempt_status
        elif payment_status in {"success", "failed"}:
            status = payment_status
        else:
            status = "unknown"

        attempt_id = row.get("attempt_id")
        if pd.isna(attempt_id):
            attempt_id = None
        failure_reason = row.get("attempt_failure_reason")
        if pd.isna(failure_reason):
            failure_reason = row.get("payment_failure_reason")
        if pd.isna(failure_reason):
            failure_reason = None

        payments.append(
            {
                "payment_id": payment_id,
                "attempt_id": attempt_id,
                "amount": float(row.get("amount") or 0),
                "time": row["event_time"],
                "status": status,
                "failure_reason": failure_reason,
            }
        )

    return sorted(payments, key=lambda payment: payment["time"])


# ============================================================
# DETERMINE RECOVERY
# ============================================================

def analyze_recovery(payments):

    if len(payments) == 0:

        return {
            "unresolved_failures": 0,
            "recovery_delays": []
        }

    unresolved = 0

    recovery_delays = []

    pending_failure = None

    for payment in payments:

        status = payment["status"]

        payment_time = payment["time"]

        # ----------------------------------------------------
        # FAILED PAYMENT
        # ----------------------------------------------------

        if status == "failed":

            if pending_failure is None:

                pending_failure = payment_time

            continue

        # ----------------------------------------------------
        # SUCCESS AFTER FAILURE
        # ----------------------------------------------------

        if (
            status == "success"
            and pending_failure is not None
        ):

            delay = (
                payment_time -
                pending_failure
            ).total_seconds() / 3600

            if delay >= 0:

                recovery_delays.append(
                    delay
                )

            pending_failure = None

    # --------------------------------------------------------
    # Last failure never recovered
    # --------------------------------------------------------

    if pending_failure is not None:

        unresolved = 1

    return {
        "unresolved_failures": unresolved,
        "recovery_delays": recovery_delays
    }


# ============================================================
# FAILURE RISK /30
# ============================================================

def calculate_failure_risk(payments):

    if len(payments) == 0:
        return 0

    failed = sum(
        1
        for payment in payments
        if payment["status"] == "failed"
    )

    total = len(payments)

    rate = failed / total

    if rate == 0:
        return 0

    elif rate <= 0.10:
        return 6

    elif rate <= 0.25:
        return 12

    elif rate <= 0.40:
        return 18

    elif rate <= 0.60:
        return 24

    else:
        return 30


# ============================================================
# CONSECUTIVE FAILURE RISK /25
# ============================================================

def calculate_consecutive_failure_risk(payments):

    if len(payments) == 0:
        return 0

    streak = 0

    for payment in reversed(payments):

        if payment["status"] == "failed":

            streak += 1

        else:

            break

    if streak == 0:
        return 0

    elif streak == 1:
        return 5

    elif streak == 2:
        return 10

    elif streak == 3:
        return 15

    elif streak == 4:
        return 20

    else:
        return 25


# ============================================================
# RETRY / RECOVERY RISK /15
# ============================================================

def calculate_retry_risk(
    payments,
    recovery_delays
):

    if len(recovery_delays) == 0:

        return 0

    failed_payments = sum(
        1
        for payment in payments
        if payment["status"] == "failed"
    )

    if failed_payments == 0:
        return 0

    recovery_rate = (
        len(recovery_delays) /
        failed_payments
    )

    if recovery_rate >= 0.90:
        return 0

    elif recovery_rate >= 0.75:
        return 3

    elif recovery_rate >= 0.50:
        return 6

    elif recovery_rate >= 0.25:
        return 10

    else:
        return 15


# ============================================================
# RECOVERY DELAY RISK /15
# ============================================================

def calculate_recovery_delay_risk(
    recovery_delays,
    unresolved
):

    if unresolved > 0:

        return 15

    if len(recovery_delays) == 0:

        return 0

    average_delay = (
        sum(recovery_delays) /
        len(recovery_delays)
    )

    if average_delay <= 0.5:

        return 3

    elif average_delay <= 2:

        return 6

    elif average_delay <= 6:

        return 9

    elif average_delay <= 24:

        return 12

    else:

        return 15


# ============================================================
# DETERIORATION RISK /15
# ============================================================

def calculate_deterioration_risk(payments):

    if len(payments) < 2:
        return 0

    midpoint = len(payments) // 2

    older = payments[:midpoint]

    recent = payments[midpoint:]

    older_failures = sum(
        1
        for p in older
        if p["status"] == "failed"
    )

    recent_failures = sum(
        1
        for p in recent
        if p["status"] == "failed"
    )

    older_rate = (
        older_failures /
        len(older)
    )

    recent_rate = (
        recent_failures /
        len(recent)
    )

    deterioration = (
        recent_rate -
        older_rate
    )

    risk = 0

    if deterioration <= 0:

        risk = 0

    elif deterioration <= 0.20:

        risk = 5

    elif deterioration <= 0.40:

        risk = 10

    else:

        risk = 15

    # --------------------------------------------------------
    # Recent streak
    # --------------------------------------------------------

    streak = 0

    for payment in reversed(recent):

        if payment["status"] == "failed":

            streak += 1

        else:

            break

    if streak >= 3:

        risk += 5

    elif streak == 2:

        risk += 3

    return min(
        risk,
        15
    )


# ============================================================
# HEALTH STATUS
# ============================================================

def get_health_status(score):

    if score >= 80:

        return "Healthy"

    elif score >= 60:

        return "Stable"

    elif score >= 40:

        return "At Risk"

    elif score >= 20:

        return "High Risk"

    else:

        return "Critical"


# ============================================================
# PROCESS CUSTOMER
# ============================================================

def process_customer(
    subscription_id,
    group
):

    payments = build_payment_timeline(
        group
    )

    recovery = analyze_recovery(
        payments
    )

    unresolved = recovery[
        "unresolved_failures"
    ]

    recovery_delays = recovery[
        "recovery_delays"
    ]

    failure_risk = (
        calculate_failure_risk(
            payments
        )
    )

    consecutive_risk = (
        calculate_consecutive_failure_risk(
            payments
        )
    )

    retry_risk = (
        calculate_retry_risk(
            payments,
            recovery_delays
        )
    )

    recovery_risk = (
        calculate_recovery_delay_risk(
            recovery_delays,
            unresolved
        )
    )

    deterioration_risk = (
        calculate_deterioration_risk(
            payments
        )
    )

    # --------------------------------------------------------
    # TOTAL RISK
    # --------------------------------------------------------

    total_risk = (
        failure_risk
        +
        consecutive_risk
        +
        retry_risk
        +
        recovery_risk
        +
        deterioration_risk
    )

    total_risk = min(
        total_risk,
        100
    )

    score = (
        100 -
        total_risk
    )

    status = get_health_status(
        score
    )

    # --------------------------------------------------------
    # AVERAGE RECOVERY DELAY
    # --------------------------------------------------------

    if len(recovery_delays) > 0:

        average_delay = (
            sum(recovery_delays) /
            len(recovery_delays)
        )

        average_delay = round(
            average_delay,
            2
        )

    else:

        average_delay = None

    # --------------------------------------------------------
    # LATEST PAYMENT
    # --------------------------------------------------------

    if len(payments) > 0:
        latest_payment = payments[-1]
        latest_payment_id = latest_payment["payment_id"]
        latest_attempt_id = latest_payment["attempt_id"]
        latest_amount = latest_payment["amount"]
        latest_payment_status = latest_payment["status"]
        latest_failure_reason = latest_payment["failure_reason"]
    else:
        latest_payment_id = None
        latest_attempt_id = None
        latest_amount = 0
        latest_payment_status = "unknown"
        latest_failure_reason = None

    return {

        "subscription_id":
            subscription_id,

        "latest_payment_id":
            latest_payment_id,

        "latest_attempt_id":
            latest_attempt_id,

        "latest_amount":
            latest_amount,

        "latest_payment_status":
            latest_payment_status,

        "latest_failure_reason":
            latest_failure_reason,

        "failure_risk":
            failure_risk,

        "consecutive_failure_risk":
            consecutive_risk,

        "retry_risk":
            retry_risk,

        "average_recovery_delay_hours":
            average_delay,

        "unresolved_failures":
            unresolved,

        "recovery_delay_risk":
            recovery_risk,

        "deterioration_risk":
            deterioration_risk,

        "total_risk":
            total_risk,

        "health_score":
            score,

        "health_status":
            status
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 120)

    print(
        "                 MANDATE HEALTH - CUSTOMER RISK ANALYSIS"
    )

    print("=" * 120)

    print()

    try:

        df = load_payment_data()

    except Exception as error:

        print(
            "DATABASE ERROR:"
        )

        print(error)

        return

    if df.empty:

        print(
            "No payment data found."
        )

        return

    results = []

    for subscription_id, group in df.groupby(
        "subscription_id"
    ):

        result = process_customer(
            subscription_id,
            group.copy()
        )

        results.append(
            result
        )

    result_df = pd.DataFrame(
        results
    )

    result_df = result_df.sort_values(
        by="total_risk",
        ascending=False
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    result_df.to_csv(
        "customer_health_scores.csv",
        index=False
    )

    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    print(
        result_df.to_string(
            index=False
        )
    )

    print()

    print("=" * 120)

    print(
        "SCORING MODEL"
    )

    print("=" * 120)

    print(
        "Failure Risk Maximum          : 30"
    )

    print(
        "Consecutive Failure Maximum   : 25"
    )

    print(
        "Retry Risk Maximum            : 15"
    )

    print(
        "Recovery Delay Maximum        : 15"
    )

    print(
        "Deterioration Risk Maximum    : 15"
    )

    print(
        "Total Maximum Risk            : 100"
    )

    print(
        "Health Score                  : 100 - Total Risk"
    )

    print("=" * 120)

    print()

    print(
        "Saved: customer_health_scores.csv"
    )

    print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
