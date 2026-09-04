from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import recovery_policy  # noqa: E402
from dashboard_server import DashboardHandler  # noqa: E402


class DashboardPolicyApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_policy_file = recovery_policy.POLICY_FILE
        recovery_policy.POLICY_FILE = (
            Path(self.temp_dir.name) / "merchant_policy.local.json"
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        recovery_policy.POLICY_FILE = self.original_policy_file
        self.temp_dir.cleanup()

    def request(
        self,
        method: str,
        path: str,
        *,
        host: str = "localhost",
        payload: dict | None = None,
    ) -> tuple[int, dict]:
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=3
        )
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Host": host}
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        return response.status, result

    def test_policy_endpoint_returns_active_defaults(self) -> None:
        status, result = self.request("GET", "/api/policy")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ACTIVE")
        self.assertEqual(result["policy"]["policy_name"], "Trust-First Recovery")

    def test_local_dashboard_can_activate_a_versioned_policy(self) -> None:
        policy = recovery_policy.default_policy()
        policy["policy_name"] = "Judge Demo Policy"
        status, result = self.request("POST", "/api/policy", payload=policy)
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "SAVED")
        self.assertEqual(result["policy"]["version"], 2)
        self.assertEqual(recovery_policy.load_policy()["policy_name"], "Judge Demo Policy")

    def test_public_webhook_host_cannot_edit_policy(self) -> None:
        status, result = self.request(
            "POST",
            "/api/policy",
            host="public-demo-tunnel.ngrok-free.app",
            payload=recovery_policy.default_policy(),
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["status"], "LOCAL_EDIT_ONLY")
        self.assertFalse(recovery_policy.POLICY_FILE.exists())

    def test_counterfactual_endpoint_compares_without_saving(self) -> None:
        proposed = recovery_policy.default_policy()
        proposed["thresholds"]["high_risk_below"] = 50
        status, result = self.request(
            "POST",
            "/api/simulate-policy",
            host="public-demo-tunnel.ngrok-free.app",
            payload={
                "scenario": {
                    "subscription_id": "S005",
                    "health_score": 45,
                    "previous_health_score": 50,
                    "recent_contacts": 0,
                    "systemic_incident": False,
                },
                "proposed_policy": proposed,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["active"]["action"], "PAYMENT_REMINDER")
        self.assertEqual(result["proposed"]["action"], "HIGH_PRIORITY_RECOVERY")
        self.assertFalse(recovery_policy.POLICY_FILE.exists())


if __name__ == "__main__":
    unittest.main()
