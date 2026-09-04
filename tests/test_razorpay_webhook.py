from __future__ import annotations

import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from razorpay_webhook import (  # noqa: E402
    compact_identifier,
    event_identifier,
    normalise_event,
    public_config_status,
    verify_signature,
)


def payload(event: str, payment_status: str = "captured") -> dict:
    return {
        "event": event,
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_TEST123",
                    "notes": {},
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_TEST456",
                    "amount": 59900,
                    "status": payment_status,
                    "error_reason": "insufficient_balance",
                }
            },
        },
    }


def payment_payload(
    event: str,
    payment_status: str,
    notes: dict | None = None,
) -> dict:
    return {
        "event": event,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_LINK456",
                    "order_id": "order_LINK123",
                    "amount": 59900,
                    "status": payment_status,
                    "notes": notes or {},
                    "error_reason": (
                        "insufficient_balance"
                        if payment_status == "failed"
                        else None
                    ),
                }
            }
        },
    }


class RazorpayWebhookTests(unittest.TestCase):
    def test_signature_uses_the_untouched_raw_body(self) -> None:
        raw = b'{"event":"subscription.charged"}'
        secret = "local-test-secret"
        signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature(raw, signature, secret))
        self.assertFalse(verify_signature(raw + b" ", signature, secret))

    def test_charged_event_becomes_successful_payment(self) -> None:
        result = normalise_event(
            payload("subscription.charged"),
            "evt_1",
            {"sub_TEST123": {"local_subscription_id": "S005"}},
        )
        self.assertTrue(result["supported"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["amount"], 599)
        self.assertEqual(result["local_subscription_id"], "S005")

    def test_pending_event_becomes_failed_payment(self) -> None:
        result = normalise_event(
            payload("subscription.pending", "failed"),
            "evt_2",
            {"sub_TEST123": {"local_subscription_id": "S005"}},
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "insufficient_balance")

    def test_unknown_subscription_is_retained_as_unmapped(self) -> None:
        result = normalise_event(
            payload("subscription.charged"), "evt_3", {}
        )
        self.assertEqual(result["processing_status"], "UNMAPPED")
        self.assertEqual(result["local_subscription_id"], "")

    def test_payment_link_failure_maps_from_payment_notes(self) -> None:
        result = normalise_event(
            payment_payload(
                "payment.failed",
                "failed",
                {"local_subscription_id": "S005"},
            ),
            "evt_payment_failed",
        )
        self.assertTrue(result["supported"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "insufficient_balance")
        self.assertEqual(result["local_subscription_id"], "S005")
        self.assertEqual(result["amount"], 599)

    def test_payment_link_capture_maps_from_payment_notes(self) -> None:
        result = normalise_event(
            payment_payload(
                "payment.captured",
                "captured",
                {"local_subscription_id": "S005"},
            ),
            "evt_payment_captured",
        )
        self.assertTrue(result["supported"])
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["local_subscription_id"], "S005")

    def test_payment_event_can_use_an_order_mapping(self) -> None:
        result = normalise_event(
            payment_payload("payment.failed", "failed"),
            "evt_order_map",
            {},
            {
                "order_LINK123": {
                    "local_subscription_id": "S004",
                    "amount": 499,
                }
            },
        )
        self.assertEqual(result["processing_status"], "READY")
        self.assertEqual(result["local_subscription_id"], "S004")

    def test_unmapped_payment_event_is_safely_retained(self) -> None:
        result = normalise_event(
            payment_payload("payment.captured", "captured"),
            "evt_unmapped_payment",
        )
        self.assertTrue(result["supported"])
        self.assertEqual(result["processing_status"], "UNMAPPED")

    def test_unsupported_event_does_not_create_a_payment(self) -> None:
        result = normalise_event(
            {"event": "order.paid", "payload": {}}, "evt_4", {}
        )
        self.assertFalse(result["supported"])
        self.assertEqual(result["processing_status"], "IGNORED_UNSUPPORTED")

    def test_local_identifiers_are_stable_and_fit_the_schema(self) -> None:
        first = compact_identifier("RP", "pay_long_external_identifier")
        second = compact_identifier("RP", "pay_long_external_identifier")
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 20)
        self.assertNotEqual(
            first, compact_identifier("RP", "pay_different_identifier")
        )

    def test_event_header_is_preferred_over_body_fallback(self) -> None:
        raw = json.dumps(payload("subscription.charged")).encode()
        self.assertEqual(event_identifier("evt_header", raw), "evt_header")
        self.assertTrue(event_identifier(None, raw).startswith("body_"))

    def test_public_status_counts_both_mapping_types(self) -> None:
        result = public_config_status(
            {
                "mode": "test",
                "webhook_secret": "configured-secret",
                "subscription_map": {"sub_1": {}},
                "payment_link_map": {"order_1": {}},
            }
        )
        self.assertTrue(result["configured"])
        self.assertEqual(result["mapping_count"], 2)


if __name__ == "__main__":
    unittest.main()
