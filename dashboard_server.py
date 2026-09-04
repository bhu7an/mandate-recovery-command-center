"""Serve the local recovery command center with Python only.

The public webhook route accepts signature-verified Test Mode outcomes. The
merchant constitution can be edited only through the localhost dashboard; it
never executes a payment or sends a customer communication.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from config import DB_CONFIG
from policy_simulator import ScenarioValidationError, compare_policies
from razorpay_webhook import (
    WebhookRequestError,
    handle_webhook,
    recent_events,
)
from recovery_policy import (
    PolicyValidationError,
    default_policy,
    load_policy,
    save_policy,
)


PROJECT_DIR = Path(__file__).resolve().parent
WEB_DIR = PROJECT_DIR / "dashboard_web"


def load_json(relative_path: str, default: Any) -> Any:
    path = PROJECT_DIR / relative_path
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def load_csv(relative_path: str) -> list[dict[str, str]]:
    path = PROJECT_DIR / relative_path
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))
    except (FileNotFoundError, OSError, csv.Error):
        return []


def records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def number(value: Any, default: float = 0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    return int(round(number(value, default)))


def by_subscription(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("subscription_id")): item
        for item in items
        if item.get("subscription_id") is not None
    }


def build_dashboard_payload() -> dict[str, Any]:
    health = load_csv("customer_health_scores.csv")
    ai_items = records(load_json("ai_agent_results.json", []))
    action_items = records(load_json("action_engine_results.json", []))
    audit_items = records(load_json("simulated_actions.json", []))
    trace_items = records(load_json("demo_output/adaptive_trace.json", []))
    memory = load_json("agent_memory.json", {})
    local_metrics = load_json("recovery_metrics.json", {})
    batch_metrics = load_json("batch_output/batch_metrics.json", {})
    policy_benchmark = load_json("experiment_output/policy_benchmark.json", {})

    ai_map = by_subscription(ai_items)
    action_map = by_subscription(action_items)
    audit_map = by_subscription(audit_items)
    customers: list[dict[str, Any]] = []

    for row in health:
        subscription_id = str(row.get("subscription_id", "Unknown"))
        ai = ai_map.get(subscription_id, {})
        action = action_map.get(subscription_id, {})
        audit = audit_map.get(subscription_id, {})
        state = memory.get(subscription_id, {}) if isinstance(memory, dict) else {}

        customers.append(
            {
                "id": subscription_id,
                "payment": str(
                    action.get("payment_id")
                    or row.get("latest_payment_id")
                    or state.get("last_payment_id")
                    or "—"
                ),
                "attempt": str(
                    action.get("attempt_id")
                    or state.get("last_attempt_id")
                    or "—"
                ),
                "amount": number(action.get("amount") or audit.get("amount_at_risk")),
                "score": integer(row.get("health_score")),
                "status": str(row.get("health_status") or "Unknown"),
                "payment_status": (
                    "success"
                    if integer(row.get("unresolved_failures")) == 0
                    else "failed"
                ),
                "action": str(
                    action.get("action_type")
                    or ai.get("recommended_action")
                    or "MONITOR"
                ),
                "recommended_action": str(
                    ai.get("recommended_action") or action.get("ai_recommended_action") or "—"
                ),
                "action_status": str(action.get("action_status") or "—"),
                "guardrail": str(action.get("guardrail_applied") or "NONE"),
                "problem": str(ai.get("primary_problem") or audit.get("primary_problem") or "No diagnosis available"),
                "reason": str(action.get("decision_reason") or ai.get("reason") or "—"),
                "next_step": str(action.get("next_step") or "Continue monitoring."),
                "confidence": number(ai.get("confidence")),
                "risk": [
                    integer(row.get("failure_risk")),
                    integer(row.get("consecutive_failure_risk")),
                    integer(row.get("retry_risk")),
                    integer(row.get("recovery_delay_risk")),
                    integer(row.get("deterioration_risk")),
                ],
            }
        )

    customers.sort(key=lambda item: (item["score"], item["id"]))

    trace: list[dict[str, Any]] = []
    for index, item in enumerate(trace_items, start=1):
        decision = item.get("decision", {})
        outcome = item.get("outcome", {})
        execution = item.get("execution", {})
        if not isinstance(decision, dict):
            decision = {}
        if not isinstance(outcome, dict):
            outcome = {}
        if not isinstance(execution, dict):
            execution = {}
        trace.append(
            {
                "index": index,
                "step": str(item.get("step") or f"STEP_{index}"),
                "event": str(decision.get("attempt_id") or f"Step {index}"),
                "payment": str(decision.get("payment_id") or "—"),
                "score": integer(decision.get("health_score")),
                "status": str(decision.get("health_status") or "Unknown"),
                "action": str(decision.get("action_type") or "MONITOR"),
                "action_status": str(decision.get("action_status") or "—"),
                "guardrail": str(decision.get("guardrail_applied") or "NONE"),
                "outcome": str(outcome.get("outcome") or execution.get("outcome_status") or "PENDING"),
                "amount": number(decision.get("amount") or execution.get("amount_at_risk")),
                "reason": str(decision.get("decision_reason") or "—"),
                "next_step": str(decision.get("next_step") or "—"),
            }
        )

    audit: list[dict[str, Any]] = []
    for item in reversed(audit_items[-8:]):
        audit.append(
            {
                "time": str(item.get("timestamp") or "—"),
                "id": str(item.get("action_id") or "—"),
                "subscription": str(item.get("subscription_id") or "—"),
                "action": str(item.get("final_action") or "—"),
                "guardrail": str(item.get("guardrail_applied") or "NONE"),
                "outcome": str(item.get("outcome_status") or "—"),
                "policy_name": str(item.get("policy_name") or "—"),
                "policy_version": integer(item.get("policy_version")),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_generated_at": local_metrics.get("generated_at"),
        "local_metrics": local_metrics if isinstance(local_metrics, dict) else {},
        "batch_metrics": batch_metrics if isinstance(batch_metrics, dict) else {},
        "policy_benchmark": (
            policy_benchmark if isinstance(policy_benchmark, dict) else {}
        ),
        "customers": customers,
        "trace": trace,
        "audit": audit,
        "razorpay": recent_events(DB_CONFIG),
        "risk_labels": [
            "Failure risk",
            "Consecutive failure",
            "Retry risk",
            "Recovery delay",
            "Deterioration",
        ],
        "risk_maximums": [30, 25, 15, 15, 15],
    }


def build_policy_payload() -> dict[str, Any]:
    try:
        policy = load_policy()
        return {"status": "ACTIVE", "policy": policy, "error": None}
    except PolicyValidationError as error:
        return {
            "status": "DEFAULTED_INVALID_CONFIG",
            "policy": default_policy(),
            "error": str(error),
        }


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format_string: str, *args: Any) -> None:
        # Keep the terminal readable; only report actual HTTP errors.
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(format_string, *args)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            body = json.dumps(build_dashboard_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/policy":
            self._send_json(200, build_policy_payload())
            return

        requested = unquote(parsed.path)
        if requested in ("", "/"):
            self.path = "/index.html"
        elif ".." in Path(requested).parts:
            self.send_error(403, "Invalid path")
            return
        else:
            self.path = requested
        super().do_GET()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _is_local_dashboard_request(self) -> bool:
        raw_host = self.headers.get("Host", "").strip().lower()
        if raw_host.startswith("["):
            host = raw_host.split("]", 1)[0].lstrip("[")
        else:
            host = raw_host.rsplit(":", 1)[0]
        return host in {"localhost", "127.0.0.1", "::1"}

    def _read_json_body(self, maximum_bytes: int) -> dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise PolicyValidationError("Invalid Content-Length") from error
        if content_length <= 0:
            raise PolicyValidationError("Request body is empty")
        if content_length > maximum_bytes:
            raise PolicyValidationError("Policy payload is too large")
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise PolicyValidationError("Request body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise PolicyValidationError("Policy must be a JSON object")
        return payload

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        route = urlparse(self.path).path
        if route == "/api/simulate-policy":
            try:
                payload = self._read_json_body(64_000)
                result = compare_policies(
                    payload.get("scenario"),
                    payload.get("proposed_policy"),
                )
                self._send_json(200, result)
            except (PolicyValidationError, ScenarioValidationError) as error:
                self._send_json(
                    400,
                    {"status": "INVALID_SIMULATION", "message": str(error)},
                )
            return

        if route == "/api/policy":
            if not self._is_local_dashboard_request():
                self._send_json(
                    403,
                    {
                        "status": "LOCAL_EDIT_ONLY",
                        "message": "Open http://localhost to edit merchant policy",
                    },
                )
                return
            try:
                policy = save_policy(self._read_json_body(64_000))
                self._send_json(200, {"status": "SAVED", "policy": policy})
            except PolicyValidationError as error:
                self._send_json(
                    400,
                    {"status": "INVALID_POLICY", "message": str(error)},
                )
            except OSError:
                self._send_json(
                    500,
                    {"status": "SAVE_FAILED", "message": "Could not save policy"},
                )
            return

        if route != "/webhooks/razorpay":
            self._send_json(404, {"status": "NOT_FOUND"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(411, {"status": "INVALID_CONTENT_LENGTH"})
            return
        if content_length <= 0:
            self._send_json(400, {"status": "EMPTY_BODY"})
            return
        if content_length > 1_000_000:
            self._send_json(413, {"status": "PAYLOAD_TOO_LARGE"})
            return

        raw_body = self.rfile.read(content_length)
        try:
            result = handle_webhook(
                raw_body,
                self.headers.get("X-Razorpay-Signature"),
                self.headers.get("X-Razorpay-Event-Id"),
                DB_CONFIG,
            )
            status = int(result.pop("http_status", 200))
            self._send_json(status, result)
        except WebhookRequestError as error:
            self._send_json(
                error.status_code,
                {"status": "REJECTED", "message": str(error)},
            )
        except Exception:
            # Return a retryable error without leaking credentials, SQL or
            # private payload content into the response.
            self._send_json(
                500,
                {"status": "PROCESSING_ERROR", "message": "Webhook processing failed"},
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local recovery command center")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind")
    parser.add_argument("--port", default=8502, type=int, help="Port to use")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    args = parser.parse_args()

    if not (WEB_DIR / "index.html").exists():
        raise SystemExit("dashboard_web/index.html is missing")

    mimetypes.add_type("text/javascript", ".js")
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    url_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    url = f"http://{url_host}:{args.port}"

    print("=" * 78)
    print("             MANDATE RECOVERY COMMAND CENTER")
    print("=" * 78)
    print(f"Dashboard : {url}")
    print(f"Webhook   : {url}/webhooks/razorpay")
    print("Data      : generated files + verified Razorpay Test Mode events")
    print("Stop      : CTRL + C")
    print("=" * 78)

    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
