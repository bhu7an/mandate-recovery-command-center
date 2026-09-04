import mysql.connector
import pandas as pd

from config import DB_CONFIG


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = mysql.connector.connect(**DB_CONFIG)

    return connection


# ============================================================
# GET PAYMENT DATA
# ============================================================

def get_payment_data():

    connection = get_connection()

    query = """
    SELECT
        c.customer_id,
        c.name,
        s.subscription_id,
        p.payment_id,
        p.amount,
        p.status AS payment_status,
        p.payment_date,
        p.failure_reason
    FROM customers c
    JOIN subscriptions s
        ON c.customer_id = s.customer_id
    JOIN payments p
        ON s.subscription_id = p.subscription_id
    ORDER BY c.customer_id, p.payment_date;
    """

    df = pd.read_sql(query, connection)

    connection.close()

    return df


# ============================================================
# GET PAYMENT ATTEMPT DATA
# ============================================================

def get_payment_attempts():

    connection = get_connection()

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
    ORDER BY subscription_id, attempt_time;
    """

    df = pd.read_sql(query, connection)

    connection.close()

    return df


# ============================================================
# CLEAN PAYMENT DATA
# ============================================================

def clean_data(df):

    # Remove duplicate payment records
    df = df.drop_duplicates(
        subset=["payment_id"]
    )

    # Standardize payment status
    df["payment_status"] = (
        df["payment_status"]
        .str.lower()
        .str.strip()
    )

    # Convert payment date
    df["payment_date"] = pd.to_datetime(
        df["payment_date"]
    )

    # Convert amount to numeric
    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce"
    )

    # Remove records missing critical information
    df = df.dropna(
        subset=[
            "customer_id",
            "payment_id",
            "payment_status"
        ]
    )

    return df


# ============================================================
# CLEAN ATTEMPT DATA
# ============================================================

def clean_attempt_data(df):

    # Remove duplicate attempts
    df = df.drop_duplicates(
        subset=["attempt_id"]
    )

    # Standardize status
    df["status"] = (
        df["status"]
        .str.lower()
        .str.strip()
    )

    # Convert attempt number to numeric
    df["attempt_number"] = pd.to_numeric(
        df["attempt_number"],
        errors="coerce"
    )

    # Convert attempt time
    df["attempt_time"] = pd.to_datetime(
        df["attempt_time"]
    )

    # Remove invalid rows
    df = df.dropna(
        subset=[
            "attempt_id",
            "subscription_id",
            "attempt_number",
            "status"
        ]
    )

    return df


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("\nGetting payment data...")

    payments = get_payment_data()

    payments = clean_data(payments)

    print("Payments loaded:", len(payments))


    print("\nGetting payment attempt data...")

    attempts = get_payment_attempts()

    attempts = clean_attempt_data(attempts)

    print("Attempts loaded:", len(attempts))


    print("\nPayment Attempts:")
    print(
        attempts.to_string(index=False)
    )
