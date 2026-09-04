import time
import os
import subprocess
from datetime import datetime


# ============================================================
# MANDATE HEALTH - MONITORING AGENT
# ============================================================

CHECK_INTERVAL_SECONDS = 30


# ============================================================
# PRINT HEADER
# ============================================================

def print_header():

    print()
    print("=" * 100)
    print("              MANDATE HEALTH MONITORING AGENT")
    print("=" * 100)
    print()


# ============================================================
# RUN SCRIPT
# ============================================================

def run_script(script_name):

    print()
    print("-" * 100)

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"Running {script_name}"
    )

    print("-" * 100)

    try:

        result = subprocess.run(
            ["python", script_name],
            capture_output=True,
            text=True
        )

        if result.stdout:

            print(result.stdout)

        if result.stderr:

            print(result.stderr)

        if result.returncode != 0:

            print(
                f"ERROR: {script_name} failed."
            )

            return False

        return True

    except Exception as error:

        print(
            f"ERROR running {script_name}: "
            f"{error}"
        )

        return False


# ============================================================
# CHECK DATABASE OUTPUT
# ============================================================

def get_file_modified_time(file_name):

    if not os.path.exists(file_name):

        return None

    return os.path.getmtime(file_name)


# ============================================================
# PROCESS CUSTOMER HEALTH
# ============================================================

def process_customer_health():

    print()
    print("=" * 100)
    print("                  PROCESSING PAYMENT HEALTH")
    print("=" * 100)


    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    success = run_script(
        "scoring_engine.py"
    )

    if not success:

        return False


    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    success = run_script(
        "ai_agent.py"
    )

    if not success:

        return False


    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    success = run_script(
        "action_engine.py"
    )

    if not success:

        return False


    return True


# ============================================================
# MONITOR DATABASE
# ============================================================

def monitor():

    print_header()

    print(
        "Monitoring system started."
    )

    print(
        f"Checking every "
        f"{CHECK_INTERVAL_SECONDS} seconds."
    )

    print()

    print(
        "Press CTRL + C to stop."
    )

    print()


    previous_database_time = None


    while True:

        try:

            # ------------------------------------------------
            # Detect database-generated score file
            # ------------------------------------------------

            current_time = (
                get_file_modified_time(
                    "customer_health_scores.csv"
                )
            )


            # ------------------------------------------------
            # First run
            # ------------------------------------------------

            if previous_database_time is None:

                print(
                    "Initial health analysis..."
                )

                process_customer_health()

                previous_database_time = (
                    get_file_modified_time(
                        "customer_health_scores.csv"
                    )
                )


            # ------------------------------------------------
            # New data detected
            # ------------------------------------------------

            elif (
                current_time is not None
                and current_time != previous_database_time
            ):

                print()

                print(
                    "=" * 100
                )

                print(
                    "NEW PAYMENT DATA DETECTED"
                )

                print(
                    "=" * 100
                )

                print()


                process_customer_health()


                previous_database_time = (
                    current_time
                )


            # ------------------------------------------------
            # Wait
            # ------------------------------------------------

            time.sleep(
                CHECK_INTERVAL_SECONDS
            )


        except KeyboardInterrupt:

            print()

            print(
                "=" * 100
            )

            print(
                "MONITORING AGENT STOPPED"
            )

            print(
                "=" * 100
            )

            print()

            break


        except Exception as error:

            print()

            print(
                f"Monitoring error: {error}"
            )

            print(
                "Retrying..."
            )

            print()

            time.sleep(
                CHECK_INTERVAL_SECONDS
            )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    monitor()