import mysql.connector
import subprocess
import time
import os
import json
import sys
from datetime import datetime

from config import DB_CONFIG
from incident_detector import detect_recent_incident, display_incident
from outcome_evaluator import display_evaluation, evaluate_payment_event


# ============================================================
# MANDATE HEALTH - LIVE CLOSED-LOOP AGENT
# ============================================================

CHECK_INTERVAL_SECONDS = 30

MEMORY_FILE = "live_agent_memory.json"

SCORING_FILE = "customer_health_scores.csv"
AI_RESULTS_FILE = "ai_agent_results.json"
ACTION_RESULTS_FILE = "action_engine_results.json"
SIMULATION_RESULTS_FILE = "simulated_actions.json"


# ============================================================
# MYSQL CONNECTION
# ============================================================

def get_connection():

    try:

        return mysql.connector.connect(**DB_CONFIG)

    except mysql.connector.Error as error:

        print()
        print("MYSQL CONNECTION ERROR")
        print(error)
        print()

        return None


# ============================================================
# LOAD LIVE AGENT MEMORY
# ============================================================

def load_live_memory():

    if not os.path.exists(MEMORY_FILE):

        return {
            "last_attempt_id": None,
            "last_processed_time": None
        }

    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return {
            "last_attempt_id": None,
            "last_processed_time": None
        }


# ============================================================
# SAVE LIVE AGENT MEMORY
# ============================================================

def save_live_memory(memory):

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            memory,
            file,
            indent=4
        )


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
            a.attempt_id,
            a.payment_id,
            a.subscription_id,
            a.attempt_number,
            a.attempt_time,
            a.status,
            a.failure_reason,
            p.amount
        FROM payment_attempts a
        JOIN payments p
            ON p.payment_id = a.payment_id
        ORDER BY
            a.attempt_time DESC,
            a.attempt_id DESC
        LIMIT 1
    """

    try:

        cursor.execute(query)

        return cursor.fetchone()

    except mysql.connector.Error as error:

        print()
        print("MYSQL QUERY ERROR")
        print(error)
        print()

        return None

    finally:

        cursor.close()
        connection.close()


# ============================================================
# RUN PYTHON SCRIPT
# ============================================================

def run_script(script_name, subscription_id=None, extra_environment=None):

    print()
    print("-" * 100)

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"Running {script_name}"
    )

    print("-" * 100)

    try:

        child_environment = os.environ.copy()
        if subscription_id:
            child_environment[
                "MANDATE_ACTIVE_SUBSCRIPTION_ID"
            ] = str(subscription_id)
        if extra_environment:
            child_environment.update(
                {
                    str(key): str(value)
                    for key, value in extra_environment.items()
                    if value is not None
                }
            )

        result = subprocess.run(
            [
                sys.executable,
                script_name
            ],
            text=True,
            env=child_environment
        )

        if result.returncode != 0:

            print()
            print(
                f"ERROR: {script_name} failed."
            )

            return False

        return True

    except Exception as error:

        print()
        print(
            f"Could not run {script_name}:"
        )

        print(error)

        return False


# ============================================================
# LOAD JSON RESULT
# ============================================================

def load_json_file(file_name):

    if not os.path.exists(file_name):

        return None

    try:

        with open(
            file_name,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception as error:

        print(
            f"Could not read {file_name}: {error}"
        )

        return None


# ============================================================
# FIND CUSTOMER RESULT
# ============================================================

def find_customer_result(
    results,
    subscription_id
):

    if not isinstance(results, list):

        return None

    for result in results:

        if (
            result.get("subscription_id")
            == subscription_id
        ):

            return result

    return None


# ============================================================
# DISPLAY FINAL DECISION
# ============================================================

def display_final_decision(
    subscription_id
):

    action_results = load_json_file(
        ACTION_RESULTS_FILE
    )

    if action_results is None:

        print(
            "Could not load action results."
        )

        return

    result = find_customer_result(
        action_results,
        subscription_id
    )

    if result is None:

        print(
            f"No action result found for "
            f"{subscription_id}."
        )

        return

    print()
    print("=" * 100)
    print("                 CLOSED-LOOP DECISION")
    print("=" * 100)

    print()

    print(
        f"Customer              : "
        f"{result.get('subscription_id')}"
    )

    print(
        f"Health Score          : "
        f"{result.get('health_score')}/100"
    )

    print(
        f"Health Status         : "
        f"{result.get('health_status')}"
    )

    print(
        f"Previous Health Score : "
        f"{result.get('previous_health_score')}"
    )

    print(
        f"Health Change         : "
        f"{result.get('health_score_change')}"
    )

    print(
        f"Previous Action       : "
        f"{result.get('previous_action')}"
    )

    print(
        f"Measured Outcome      : "
        f"{result.get('last_measured_outcome')}"
    )

    print(
        f"New Action            : "
        f"{result.get('action_type')}"
    )

    print(
        f"Priority              : "
        f"{result.get('priority')}"
    )

    print(
        f"Action Status         : "
        f"{result.get('action_status')}"
    )

    print(
        f"Guardrail Applied     : "
        f"{result.get('guardrail_applied')}"
    )

    print()

    print(
        f"Message               : "
        f"{result.get('message')}"
    )

    print(
        f"Next Step             : "
        f"{result.get('next_step')}"
    )

    print()

    print("=" * 100)


# ============================================================
# DISPLAY SIMULATION RESULT
# ============================================================

def display_simulation_result(
    subscription_id
):

    results = load_json_file(
        SIMULATION_RESULTS_FILE
    )

    if results is None:

        print(
            "Simulation results not found."
        )

        return

    result = find_customer_result(
        results,
        subscription_id
    )

    if result is None:

        print(
            f"No simulation result found "
            f"for {subscription_id}."
        )

        return

    print()
    print("=" * 100)
    print("                 ACTION EXECUTION")
    print("=" * 100)

    print()

    for key, value in result.items():

        print(
            f"{key:<25}: {value}"
        )

    print()

    print("=" * 100)


# ============================================================
# PROCESS PAYMENT EVENT
# ============================================================

def process_payment_event(
    payment_event
):

    subscription_id = (
        payment_event["subscription_id"]
    )

    print()
    print("=" * 100)
    print("                 NEW PAYMENT EVENT")
    print("=" * 100)

    print()

    print(
        f"Attempt ID      : "
        f"{payment_event['attempt_id']}"
    )

    print(
        f"Payment ID      : "
        f"{payment_event['payment_id']}"
    )

    print(
        f"Subscription ID : "
        f"{subscription_id}"
    )

    print(
        f"Attempt Number  : "
        f"{payment_event['attempt_number']}"
    )

    print(
        f"Attempt Time    : "
        f"{payment_event['attempt_time']}"
    )

    print(
        f"Status          : "
        f"{payment_event['status']}"
    )

    print(
        f"Failure Reason  : "
        f"{payment_event['failure_reason']}"
    )

    print(
        f"Amount          : INR "
        f"{float(payment_event.get('amount') or 0):.2f}"
    )

    print()

    # ========================================================
    # STEP 1 - MEASURE PREVIOUS ACTION OUTCOME
    # ========================================================

    print(
        "STEP 1/6 -> OUTCOME EVALUATOR"
    )

    outcome_result = evaluate_payment_event(
        payment_event
    )
    display_evaluation(
        outcome_result
    )

    # ========================================================
    # STEP 2 - COHORT INCIDENT DETECTION
    # ========================================================

    print(
        "STEP 2/6 -> COHORT DEGRADATION DETECTOR"
    )
    try:
        incident_result = detect_recent_incident()
    except Exception as error:
        print(f"Incident detection unavailable: {error}")
        incident_result = {
            "incident_active": False,
            "events_analyzed": 0,
            "reason": None,
        }
    display_incident(incident_result)

    incident_reason = None
    if (
        incident_result.get("incident_active")
        and str(payment_event.get("failure_reason") or "").lower()
        == str(incident_result.get("reason") or "").lower()
    ):
        incident_reason = incident_result.get("reason")

    # ========================================================
    # STEP 3 - SCORING
    # ========================================================

    print(
        "STEP 3/6 -> SCORING ENGINE"
    )

    if not run_script(
        "scoring_engine.py"
    ):

        print(
            "Scoring failed."
        )

        return False

    # ========================================================
    # STEP 4 - AI
    # ========================================================

    print()
    print(
        "STEP 4/6 -> AI AGENT"
    )

    if not run_script(
        "ai_agent.py",
        subscription_id
    ):

        print(
            "AI analysis failed."
        )

        return False

    # ========================================================
    # STEP 5 - ACTION
    # ========================================================

    print()
    print(
        "STEP 5/6 -> ACTION ENGINE"
    )

    if not run_script(
        "action_engine.py",
        subscription_id,
        {
            "MANDATE_SYSTEMIC_INCIDENT_REASON":
                incident_reason,
            "MANDATE_CURRENT_EVENT_STATUS":
                payment_event.get("status"),
            "MANDATE_CURRENT_OUTCOME":
                outcome_result.get("outcome"),
            "MANDATE_OUTCOME_EVALUATION_STATUS":
                outcome_result.get("evaluation_status"),
        }
    ):

        print(
            "Action engine failed."
        )

        return False

    # ========================================================
    # DISPLAY DECISION
    # ========================================================

    display_final_decision(
        subscription_id
    )

    # ========================================================
    # STEP 6 - ACTION SIMULATOR
    # ========================================================

    print()
    print(
        "STEP 6/6 -> ACTION SIMULATOR"
    )

    if not run_script(
        "action_simulator.py",
        subscription_id
    ):

        print(
            "Action simulation failed."
        )

        return False

    # ========================================================
    # DISPLAY EXECUTION
    # ========================================================

    display_simulation_result(
        subscription_id
    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print()
    print("=" * 100)
    print("              AGENT CYCLE COMPLETED")
    print("=" * 100)

    print()

    print(
        f"Customer {subscription_id} "
        "has been processed through the complete "
        "closed-loop pipeline."
    )

    print()

    return True


# ============================================================
# INITIALIZE LIVE AGENT
# ============================================================

def initialize_agent():

    memory = load_live_memory()

    latest_attempt = get_latest_attempt()

    if latest_attempt is None:

        print(
            "No payment attempts found in MySQL."
        )

        return memory

    # --------------------------------------------------------
    # FIRST START
    # --------------------------------------------------------

    if memory["last_attempt_id"] is None:

        memory["last_attempt_id"] = (
            latest_attempt["attempt_id"]
        )

        memory["last_processed_time"] = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        save_live_memory(memory)

        print(
            "Initial MySQL state recorded."
        )

        print(
            f"Current latest attempt: "
            f"{latest_attempt['attempt_id']}"
        )

        print(
            "Waiting for the next NEW payment event..."
        )

    return memory


# ============================================================
# MAIN LIVE MONITOR
# ============================================================

def main():

    print()
    print("=" * 100)
    print("                 MANDATE HEALTH")
    print("              LIVE CLOSED-LOOP AGENT")
    print("=" * 100)

    print()

    print(
        "Architecture:"
    )

    print(
        "MySQL"
        " -> "
        "Outcome"
        " -> "
        "Scoring"
        " -> "
        "AI"
        " -> "
        "Action"
        " -> "
        "Simulation"
        " -> "
        "Memory"
    )

    print()

    print(
        f"Checking for new payment events "
        f"every {CHECK_INTERVAL_SECONDS} seconds."
    )

    print()

    print(
        "Press CTRL + C to stop."
    )

    print()

    memory = initialize_agent()

    print()

    print(
        "LIVE AGENT IS RUNNING..."
    )

    print()

    while True:

        try:

            latest_attempt = (
                get_latest_attempt()
            )

            if latest_attempt is None:

                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    "No payment attempts found."
                )

                time.sleep(
                    CHECK_INTERVAL_SECONDS
                )

                continue

            current_attempt_id = (
                latest_attempt["attempt_id"]
            )

            last_attempt_id = (
                memory["last_attempt_id"]
            )

            # =================================================
            # NEW EVENT
            # =================================================

            if (
                current_attempt_id
                != last_attempt_id
            ):

                print()

                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    "NEW EVENT DETECTED"
                )

                print(
                    f"Previous attempt : "
                    f"{last_attempt_id}"
                )

                print(
                    f"New attempt      : "
                    f"{current_attempt_id}"
                )

                # -------------------------------------------------
                # PROCESS EVENT
                # -------------------------------------------------

                success = process_payment_event(
                    latest_attempt
                )

                # -------------------------------------------------
                # UPDATE MEMORY ONLY AFTER PROCESSING
                # -------------------------------------------------

                if success:

                    memory["last_attempt_id"] = (
                        current_attempt_id
                    )

                    memory["last_processed_time"] = (
                        datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    )

                    save_live_memory(
                        memory
                    )

                    print()

                    print(
                        "Live agent memory updated."
                    )

                else:

                    print()

                    print(
                        "Cycle failed."
                    )

                    print(
                        "Event will be retried."
                    )

            else:

                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"No new event. "
                    f"Last attempt: {last_attempt_id}"
                )

            time.sleep(
                CHECK_INTERVAL_SECONDS
            )

        except KeyboardInterrupt:

            print()
            print("=" * 100)
            print("             LIVE AGENT STOPPED")
            print("=" * 100)
            print()

            break

        except Exception as error:

            print()
            print("=" * 100)
            print("             LIVE AGENT ERROR")
            print("=" * 100)

            print()

            print(error)

            print()

            print(
                f"Retrying in "
                f"{CHECK_INTERVAL_SECONDS} seconds..."
            )

            print()

            time.sleep(
                CHECK_INTERVAL_SECONDS
            )


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    main()
