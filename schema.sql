CREATE DATABASE IF NOT EXISTS mandate_health;
USE mandate_health;

CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    CONSTRAINT fk_subscription_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id VARCHAR(20) PRIMARY KEY,
    subscription_id VARCHAR(20) NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    payment_date DATETIME NOT NULL,
    failure_reason VARCHAR(100),
    CONSTRAINT fk_payment_subscription
        FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id),
    CONSTRAINT fk_payment_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS payment_attempts (
    attempt_id VARCHAR(20) PRIMARY KEY,
    payment_id VARCHAR(20) NOT NULL,
    subscription_id VARCHAR(20) NOT NULL,
    attempt_number INT NOT NULL,
    attempt_time DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    failure_reason VARCHAR(100),
    INDEX idx_attempt_time (attempt_time, attempt_id),
    INDEX idx_attempt_subscription (subscription_id, attempt_time),
    CONSTRAINT fk_attempt_payment
        FOREIGN KEY (payment_id) REFERENCES payments(payment_id),
    CONSTRAINT fk_attempt_subscription
        FOREIGN KEY (subscription_id) REFERENCES subscriptions(subscription_id)
);

-- Verified Razorpay Test Mode webhooks are retained separately from the
-- normalised payment records. Raw payloads provide an audit trail while local
-- IDs allow the existing agent to process the event without API-specific code.
CREATE TABLE IF NOT EXISTS razorpay_events (
    event_id VARCHAR(255) PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    mode VARCHAR(20) NOT NULL DEFAULT 'test',
    signature_verified BOOLEAN NOT NULL DEFAULT FALSE,
    processing_status VARCHAR(40) NOT NULL,
    razorpay_subscription_id VARCHAR(80),
    razorpay_payment_id VARCHAR(80),
    local_subscription_id VARCHAR(20),
    local_payment_id VARCHAR(20),
    local_attempt_id VARCHAR(20),
    amount DECIMAL(12, 2),
    payload_json LONGTEXT NOT NULL,
    error_message VARCHAR(255),
    received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at DATETIME,
    INDEX idx_razorpay_received (received_at),
    INDEX idx_razorpay_local_subscription (local_subscription_id, received_at)
);
