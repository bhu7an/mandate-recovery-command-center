import mysql.connector
import pandas as pd

from config import DB_CONFIG

connection = mysql.connector.connect(**DB_CONFIG)

print("Connected to MySQL successfully!")

query = """
SELECT
    c.customer_id,
    c.name,
    s.subscription_id,
    s.status AS subscription_status,
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

print("\nPayment data:")
print(df)

connection.close()
