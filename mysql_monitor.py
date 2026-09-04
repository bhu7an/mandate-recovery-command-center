import mysql.connector
import time
from datetime import datetime

from config import DB_CONFIG


# ============================================================
# MANDATE HEALTH - MYSQL MONITOR
# ============================================================

CHECK_INTERVAL_SECONDS = 30


# ============================================================
# CONNECT TO MYSQL
# ============================================================

def get_connection():

    try:

        connection = mysql.connector.connect(**DB_CONFIG)

        return connection

    except mysql.connector.Error as error:

        print()
        print("MYSQL CONNECTION ERROR")
        print(error)
        print()

        return None


# ============================================================
# GET LATEST PAYMENT ATTEMPT
# ============================================================

def get_latest_attempt():

    connection = get_connection()

    if connection is None:

        return None


    cursor = connection.cursor(
        dictionary=True
    )


    query = """
        SELECT
            attempt_id,
            payment_id,
            subscription_id,
            attempt_number,
            attempt_time,
            status,
            failure_reason
        FROM payment_attempts
        ORDER BY attempt_time DESC, attempt_id DESC
        LIMIT 1
    """


    try:

        cursor.execute(query)

        result = cursor.fetchone()

        return result


    except mysql.connector.Error as error:

        print(
            "MYSQL QUERY ERROR:"
        )

        print(error)

        return None


    finally:

        cursor.close()

        connection.close()


# ============================================================
# GET CUSTOMER PAYMENT HISTORY
# ============================================================

def get_customer_history(
    subscription_id
):

    connection = get_connection()

    if connection is None:

        return []


    cursor = connection.cursor(
        dictionary=True
    )


    query = """
        SELECT
            p.payment_id,
            p.subscription_id,
            p.customer_id,
            p.amount,
            p.currency,
            p.status AS payment_status,
            p.payment_date,
            p.method,
            p.failure_reason AS payment_failure_reason,

            a.attempt_id,
            a.attempt_number,
            a.attempt_time,
            a.status AS attempt_status,
            a.failure_reason AS attempt_failure_reason

        FROM payments p

        LEFT JOIN payment_attempts a
            ON p.payment_id = a.payment_id

        WHERE p.subscription_id = %s

        ORDER BY
            COALESCE(
                a.attempt_time,
                p.payment_date
            ) ASC
    """


    try:

        cursor.execute(
            query,
            (subscription_id,)
        )

        results = cursor.fetchall()

        return results


    except mysql.connector.Error as error:

        print(
            "MYSQL QUERY ERROR:"
        )

        print(error)

        return []


    finally:

        cursor.close()

        connection.close()


# ============================================================
# GET CUSTOMER DETAILS
# ============================================================

def get_customer(
    subscription_id
):

    connection = get_connection()

    if connection is None:

        return None


    cursor = connection.cursor(
        dictionary=True
    )


    query = """
        SELECT
            c.customer_id,
            c.name,
            c.email,
            c.phone,

            s.subscription_id,
            s.plan_id,
            s.status AS subscription_status,
            s.amount,
            s.frequency,
            s.start_at,
            s.current_start,
            s.current_end,
            s.charge_at,
            s.total_count,
            s.paid_count,
            s.auth_attempts

        FROM subscriptions s

        INNER JOIN customers c
            ON c.customer_id = s.customer_id

        WHERE s.subscription_id = %s
    """


    try:

        cursor.execute(
            query,
            (subscription_id,)
        )

        result = cursor.fetchone()

        return result


    except mysql.connector.Error as error:

        print(
            "MYSQL QUERY ERROR:"
        )

        print(error)

        return None


    finally:

        cursor.close()

        connection.close()


# ============================================================
# PRINT CUSTOMER HISTORY
# ============================================================

def display_customer_history(
    subscription_id
):

    customer = get_customer(
        subscription_id
    )

    history = get_customer_history(
        subscription_id
    )


    print()

    print("=" * 100)

    print(
        f"CUSTOMER PAYMENT HISTORY - "
        f"{subscription_id}"
    )

    print("=" * 100)


    if customer:

        print()

        print(
            f"Customer ID : "
            f"{customer['customer_id']}"
        )

        print(
            f"Name        : "
            f"{customer['name']}"
        )

        print(
            f"Email       : "
            f"{customer['email']}"
        )

        print(
            f"Plan        : "
            f"{customer['plan_id']}"
        )

        print(
            f"Amount      : "
            f"{customer['amount']}"
        )

        print(
            f"Frequency   : "
            f"{customer['frequency']}"
        )


    print()

    print(
        "PAYMENT HISTORY"
    )

    print("-" * 100)


    for row in history:

        print(
            f"Payment: {row['payment_id']} | "
            f"Attempt: {row['attempt_number']} | "
            f"Time: {row['attempt_time']} | "
            f"Status: {row['attempt_status']}"
        )


    print("=" * 100)


# ============================================================
# MONITOR NEW PAYMENT EVENTS
# ============================================================

def monitor():

    print()

    print("=" * 100)

    print(
        "             MANDATE HEALTH MYSQL MONITOR"
    )

    print(
        "                    LIVE DATABASE"
    )

    print("=" * 100)

    print()

    print(
        f"Checking MySQL every "
        f"{CHECK_INTERVAL_SECONDS} seconds."
    )

    print()

    print(
        "Press CTRL + C to stop."
    )

    print()


    last_attempt_id = None


    while True:

        try:

            latest_attempt = (
                get_latest_attempt()
            )


            if latest_attempt is None:

                print(
                    "No payment attempts found."
                )

                time.sleep(
                    CHECK_INTERVAL_SECONDS
                )

                continue


            current_attempt_id = (
                latest_attempt[
                    "attempt_id"
                ]
            )


            # ------------------------------------------------
            # FIRST RUN
            # ------------------------------------------------

            if last_attempt_id is None:

                last_attempt_id = (
                    current_attempt_id
                )

                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    "Connected to MySQL."
                )

                print()

                print(
                    "Latest payment event:"
                )

                print(
                    latest_attempt
                )

                print()

                print(
                    "Monitoring for new payment events..."
                )


            # ------------------------------------------------
            # NEW EVENT
            # ------------------------------------------------

            elif (
                current_attempt_id
                != last_attempt_id
            ):

                print()

                print("=" * 100)

                print(
                    "NEW PAYMENT EVENT DETECTED"
                )

                print("=" * 100)

                print()

                print(
                    f"Attempt ID      : "
                    f"{latest_attempt['attempt_id']}"
                )

                print(
                    f"Payment ID      : "
                    f"{latest_attempt['payment_id']}"
                )

                print(
                    f"Subscription ID : "
                    f"{latest_attempt['subscription_id']}"
                )

                print(
                    f"Attempt Number  : "
                    f"{latest_attempt['attempt_number']}"
                )

                print(
                    f"Attempt Time    : "
                    f"{latest_attempt['attempt_time']}"
                )

                print(
                    f"Status          : "
                    f"{latest_attempt['status']}"
                )

                print()


                # --------------------------------------------
                # GET CUSTOMER
                # --------------------------------------------

                subscription_id = (
                    latest_attempt[
                        "subscription_id"
                    ]
                )


                customer = get_customer(
                    subscription_id
                )


                if customer:

                    print(
                        f"Customer: "
                        f"{customer['name']}"
                    )

                    print(
                        f"Customer ID: "
                        f"{customer['customer_id']}"
                    )

                    print()


                # --------------------------------------------
                # DISPLAY HISTORY
                # --------------------------------------------

                display_customer_history(
                    subscription_id
                )


                # --------------------------------------------
                # UPDATE LAST EVENT
                # --------------------------------------------

                last_attempt_id = (
                    current_attempt_id
                )


            time.sleep(
                CHECK_INTERVAL_SECONDS
            )


        except KeyboardInterrupt:

            print()

            print("=" * 100)

            print(
                "MYSQL MONITOR STOPPED"
            )

            print("=" * 100)

            print()

            break


        except Exception as error:

            print()

            print(
                "MONITORING ERROR:"
            )

            print(error)

            print(
                "Retrying..."
            )

            print()

            time.sleep(
                CHECK_INTERVAL_SECONDS
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    monitor()
