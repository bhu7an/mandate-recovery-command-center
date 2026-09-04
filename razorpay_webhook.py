"""Secure Razorpay Test Mode webhook ingestion.

Verified subscription lifecycle events and Payment Link payment outcomes are
normalised into the existing ``payments`` and ``payment_attempts`` tables. The
recovery agent therefore uses exactly the same pipeline for Razorpay events
and manual SQL events.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_CONFIG_FILE = PROJECT_DIR / "razorpay_config.local.json"
SUBSCRIPTION_EVENTS = {
    "subscription.charged": "success",
    "subscription.pending": "failed",
    "subscription.halted": "failed",
}
PAYMENT_EVENTS = {
    "payment.captured": "success",
    "payment.failed": "failed",
}
SUPPORTED_EVENTS = {**SUBSCRIPTION_EVENTS, **PAYMENT_EVENTS}


def mysql_connect(db_config: dict[str, Any]) -> Any:
    """Import the optional runtime dependency only when MySQL is required."""

    import mysql.connector  # type: ignore[import-untyped]

    return mysql.connector.connect(**db_config)


class WebhookRequestError(Exception):
    """A safe HTTP-facing error raised before database processing."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def load_razorpay_config() -> dict[str, Any]:
    """Load Test Mode settings without exposing secrets to the dashboard."""

    config: dict[str, Any] = {
        "mode": "test",
        "webhook_secret": os.getenv("RAZORPAY_WEBHOOK_SECRET", ""),
        "subscription_map": {},
        "payment_link_map": {},
    }
    if LOCAL_CONFIG_FILE.exists():
        try:
            with LOCAL_CONFIG_FILE.open("r", encoding="utf-8") as file:
                local = json.load(file)
            if isinstance(local, dict):
                for key in (
                    "mode",
                    "webhook_secret",
                    "subscription_map",
                    "payment_link_map",
                ):
                    if key in local:
                        config[key] = local[key]
        except (OSError, json.JSONDecodeError):
            # A malformed private file must never make the normal dashboard
            # unavailable. Webhook requests will report that setup is missing.
            pass

    if os.getenv("RAZORPAY_WEBHOOK_SECRET"):
        config["webhook_secret"] = os.environ["RAZORPAY_WEBHOOK_SECRET"]
    if not isinstance(config.get("subscription_map"), dict):
        config["subscription_map"] = {}
    if not isinstance(config.get("payment_link_map"), dict):
        config["payment_link_map"] = {}
    return config


def public_config_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return non-secret configuration details for the dashboard."""

    config = config or load_razorpay_config()
    secret = str(config.get("webhook_secret") or "")
    configured = bool(secret and "REPLACE" not in secret.upper())
    subscription_map = config.get("subscription_map") or {}
    payment_link_map = config.get("payment_link_map") or {}
    return {
        "mode": str(config.get("mode") or "test").lower(),
        "configured": configured,
        "mapping_count": len(subscription_map) + len(payment_link_map),
        "webhook_path": "/webhooks/razorpay",
    }


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Validate ``X-Razorpay-Signature`` against the untouched request body."""

    if not raw_body or not signature or not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def compact_identifier(prefix: str, value: str) -> str:
    """Create a deterministic identifier that fits existing VARCHAR(20) keys."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix[:2].upper()}{digest}"


def event_identifier(header_value: str | None, raw_body: bytes) -> str:
    """Use Razorpay's unique event header, with a deterministic safe fallback."""

    if header_value and header_value.strip():
        return header_value.strip()
    return "body_" + hashlib.sha256(raw_body).hexdigest()


def _entity(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get("payload", {}).get(name, {})
    if isinstance(value, dict):
        entity = value.get("entity", {})
        if isinstance(entity, dict):
            return entity
    return {}


def normalise_event(
    payload: dict[str, Any],
    event_id: str,
    subscription_map: dict[str, Any] | None = None,
    payment_link_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a supported Razorpay webhook into a local payment event.

    Subscription events use ``subscription_map``. Payment Link outcomes should
    carry ``local_subscription_id`` in their notes; an optional
    ``payment_link_map`` can also map a Payment Link ID or reference ID.
    """

    event_type = str(payload.get("event") or "")
    if event_type not in SUPPORTED_EVENTS:
        return {
            "event_type": event_type or "unknown",
            "supported": False,
            "processing_status": "IGNORED_UNSUPPORTED",
        }

    subscription = _entity(payload, "subscription")
    payment = _entity(payload, "payment")
    payment_link = _entity(payload, "payment_link")
    order = _entity(payload, "order")
    razorpay_subscription_id = str(
        subscription.get("id")
        or payment.get("subscription_id")
        or ""
    )
    razorpay_payment_id = str(payment.get("id") or event_id)

    mapping: dict[str, Any] = {}
    configured_subscription_map = subscription_map or {}
    configured_payment_link_map = payment_link_map or {}
    if event_type in SUBSCRIPTION_EVENTS:
        candidate = configured_subscription_map.get(razorpay_subscription_id, {})
        if isinstance(candidate, dict):
            mapping = candidate
    else:
        mapping_keys = (
            payment_link.get("id"),
            payment_link.get("reference_id"),
            order.get("id"),
            payment.get("order_id"),
        )
        for key in mapping_keys:
            candidate = configured_payment_link_map.get(str(key or ""), {})
            if isinstance(candidate, dict) and candidate:
                mapping = candidate
                break
    if not isinstance(mapping, dict):
        mapping = {}

    notes: dict[str, Any] = {}
    for source in (
        order.get("notes"),
        payment_link.get("notes"),
        subscription.get("notes"),
        payment.get("notes"),
    ):
        if isinstance(source, dict):
            notes.update(source)

    local_subscription_id = str(
        mapping.get("local_subscription_id")
        or mapping.get("subscription_id")
        or notes.get("local_subscription_id")
        or notes.get("subscription_id")
        or ""
    )
    amount_paise = payment.get("amount")
    if amount_paise in (None, ""):
        amount = float(mapping.get("amount") or 0)
    else:
        try:
            amount = float(amount_paise) / 100
        except (TypeError, ValueError):
            amount = float(mapping.get("amount") or 0)

    status = SUPPORTED_EVENTS[event_type]
    failure_reason = None
    if status == "failed":
        failure_reason = str(
            payment.get("error_reason")
            or payment.get("error_description")
            or event_type.replace(".", "_")
        )[:100]

    return {
        "event_type": event_type,
        "supported": True,
        "processing_status": (
            "READY" if local_subscription_id else "UNMAPPED"
        ),
        "razorpay_subscription_id": razorpay_subscription_id,
        "razorpay_payment_id": razorpay_payment_id,
        "local_subscription_id": local_subscription_id,
        "local_payment_id": compact_identifier("RP", razorpay_payment_id),
        "local_attempt_id": compact_identifier("RA", event_id),
        "amount": amount,
        "status": status,
        "failure_reason": failure_reason,
    }


EVENT_TABLE_SQL = """
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
)
"""


def ensure_event_table(connection: Any) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(EVENT_TABLE_SQL)
        connection.commit()
    finally:
        cursor.close()


def process_verified_event(
    payload: dict[str, Any],
    raw_body: bytes,
    event_id: str,
    db_config: dict[str, Any],
    razorpay_config: dict[str, Any],
) -> dict[str, Any]:
    """Persist one verified event and, when mapped, its local payment attempt."""

    normalised = normalise_event(
        payload,
        event_id,
        razorpay_config.get("subscription_map") or {},
        razorpay_config.get("payment_link_map") or {},
    )
    connection = mysql_connect(db_config)
    try:
        ensure_event_table(connection)
        cursor = connection.cursor(dictionary=True)
        try:
            connection.start_transaction()
            cursor.execute(
                "SELECT processing_status FROM razorpay_events WHERE event_id = %s",
                (event_id,),
            )
            existing = cursor.fetchone()
            if existing:
                connection.rollback()
                return {
                    "status": "DUPLICATE_IGNORED",
                    "event_id": event_id,
                    "previous_status": existing.get("processing_status"),
                    "http_status": 200,
                }

            cursor.execute(
                """
                INSERT INTO razorpay_events (
                    event_id, event_type, mode, signature_verified,
                    processing_status, razorpay_subscription_id,
                    razorpay_payment_id, local_subscription_id,
                    local_payment_id, local_attempt_id, amount, payload_json
                ) VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event_id,
                    normalised.get("event_type", "unknown"),
                    str(razorpay_config.get("mode") or "test"),
                    normalised.get("processing_status"),
                    normalised.get("razorpay_subscription_id"),
                    normalised.get("razorpay_payment_id"),
                    normalised.get("local_subscription_id"),
                    normalised.get("local_payment_id"),
                    normalised.get("local_attempt_id"),
                    normalised.get("amount"),
                    raw_body.decode("utf-8"),
                ),
            )

            if not normalised.get("supported"):
                connection.commit()
                return {
                    "status": "IGNORED_UNSUPPORTED",
                    "event_id": event_id,
                    "event_type": normalised.get("event_type"),
                    "http_status": 202,
                }

            local_subscription_id = normalised.get("local_subscription_id")
            if not local_subscription_id:
                connection.commit()
                return {
                    "status": "UNMAPPED",
                    "event_id": event_id,
                    "razorpay_subscription_id": normalised.get(
                        "razorpay_subscription_id"
                    ),
                    "razorpay_payment_id": normalised.get(
                        "razorpay_payment_id"
                    ),
                    "http_status": 202,
                }

            cursor.execute(
                "SELECT customer_id FROM subscriptions WHERE subscription_id = %s",
                (local_subscription_id,),
            )
            subscription = cursor.fetchone()
            if not subscription:
                cursor.execute(
                    """
                    UPDATE razorpay_events
                    SET processing_status = 'INVALID_MAPPING',
                        error_message = %s
                    WHERE event_id = %s
                    """,
                    ("Local subscription does not exist", event_id),
                )
                connection.commit()
                return {
                    "status": "INVALID_MAPPING",
                    "event_id": event_id,
                    "http_status": 202,
                }

            customer_id = subscription["customer_id"]
            amount = float(normalised.get("amount") or 0)
            if amount <= 0:
                cursor.execute(
                    """
                    SELECT amount FROM payments
                    WHERE subscription_id = %s
                    ORDER BY payment_date DESC LIMIT 1
                    """,
                    (local_subscription_id,),
                )
                previous_payment = cursor.fetchone()
                amount = float((previous_payment or {}).get("amount") or 0)

            now = datetime.utcnow().replace(microsecond=0)
            local_payment_id = normalised["local_payment_id"]
            local_attempt_id = normalised["local_attempt_id"]
            cursor.execute(
                """
                INSERT INTO payments (
                    payment_id, subscription_id, customer_id, amount,
                    status, payment_date, failure_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    amount = VALUES(amount),
                    status = VALUES(status),
                    payment_date = VALUES(payment_date),
                    failure_reason = VALUES(failure_reason)
                """,
                (
                    local_payment_id,
                    local_subscription_id,
                    customer_id,
                    amount,
                    normalised["status"],
                    now,
                    normalised["failure_reason"],
                ),
            )
            cursor.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0) + 1 AS next_attempt
                FROM payment_attempts WHERE payment_id = %s
                """,
                (local_payment_id,),
            )
            attempt_number = int(cursor.fetchone()["next_attempt"])
            cursor.execute(
                """
                INSERT INTO payment_attempts (
                    attempt_id, payment_id, subscription_id, attempt_number,
                    attempt_time, status, failure_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    local_attempt_id,
                    local_payment_id,
                    local_subscription_id,
                    attempt_number,
                    now,
                    normalised["status"],
                    normalised["failure_reason"],
                ),
            )
            cursor.execute(
                """
                UPDATE razorpay_events
                SET processing_status = 'PROCESSED', processed_at = %s, amount = %s
                WHERE event_id = %s
                """,
                (now, amount, event_id),
            )
            connection.commit()
            return {
                "status": "PROCESSED",
                "event_id": event_id,
                "event_type": normalised["event_type"],
                "local_subscription_id": local_subscription_id,
                "local_payment_id": local_payment_id,
                "local_attempt_id": local_attempt_id,
                "http_status": 200,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def handle_webhook(
    raw_body: bytes,
    signature: str | None,
    event_header: str | None,
    db_config: dict[str, Any],
) -> dict[str, Any]:
    """Validate, decode and process one HTTP webhook request."""

    config = load_razorpay_config()
    secret = str(config.get("webhook_secret") or "")
    if not public_config_status(config)["configured"]:
        raise WebhookRequestError(
            "Razorpay webhook secret is not configured", 503
        )
    if not verify_signature(raw_body, signature or "", secret):
        raise WebhookRequestError("Invalid Razorpay webhook signature", 401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WebhookRequestError("Webhook body is not valid JSON", 400) from error
    if not isinstance(payload, dict):
        raise WebhookRequestError("Webhook payload must be a JSON object", 400)

    event_id = event_identifier(event_header, raw_body)
    return process_verified_event(
        payload, raw_body, event_id, db_config, config
    )


def recent_events(db_config: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    """Return recent verified event metadata without returning raw payloads."""

    config_status = public_config_status()
    if not config_status["configured"]:
        return {"database_available": False, "events": [], **config_status}
    try:
        connection = mysql_connect(db_config)
        try:
            ensure_event_table(connection)
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    """
                    SELECT event_id, event_type, mode, signature_verified,
                           processing_status, razorpay_subscription_id,
                           razorpay_payment_id, local_subscription_id,
                           local_payment_id, local_attempt_id, amount,
                           received_at, processed_at, error_message
                    FROM razorpay_events
                    ORDER BY received_at DESC
                    LIMIT %s
                    """,
                    (max(1, min(int(limit), 20)),),
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()
        finally:
            connection.close()
    except Exception:
        return {"database_available": False, "events": [], **config_status}

    for row in rows:
        for key in ("received_at", "processed_at"):
            if isinstance(row.get(key), datetime):
                row[key] = row[key].isoformat(sep=" ", timespec="seconds")
        if row.get("amount") is not None:
            row["amount"] = float(row["amount"])
        row["signature_verified"] = bool(row.get("signature_verified"))
    return {"database_available": True, "events": rows, **config_status}
