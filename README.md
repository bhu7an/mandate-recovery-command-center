# Mandate Health & Recovery Optimizer

An outcome-aware recovery agent for recurring payments. Its deterministic core
runs locally and it can optionally ingest signature-verified Razorpay Test Mode
subscription webhooks or Payment Link outcomes. It calculates an explainable
0–100 mandate-health score, chooses a bounded intervention, observes the next
payment outcome, and changes its next decision.

## What makes this more than failure detection

```text
Payment event
    -> evaluate the previous action's outcome
    -> detect cohort-level technical failure spikes
    -> calculate health score
    -> diagnose the risk
    -> apply outcome-aware policy and guardrails
    -> execute a safe simulation
    -> store an idempotent audit record
    -> report INR at risk and recovered
```

The deterministic health model remains explainable:

| Risk component | Maximum |
|---|---:|
| Failure risk | 30 |
| Consecutive-failure risk | 25 |
| Retry risk | 15 |
| Recovery-delay risk | 15 |
| Deterioration risk | 15 |

`Health score = 100 - total risk`

## Adaptive paths demonstrated

1. `reminder -> success -> RECOVERED -> NO_INTERVENTION`
2. `reminder -> failure -> HIGH_PRIORITY_RECOVERY`
3. `recovery attempt -> failure -> human approval escalation`
4. `pending action -> duplicate reminder suppressed -> MONITOR`

Guardrails include a pending-action cooldown, a merchant-configured contact
limit and time window, stop-after-success, idempotent action IDs, and an
optional human-approval gate after automated recovery fails.

The cohort detector is the key product differentiator: several technical
failures with the same reason inside a 15-minute window are treated as a
possible infrastructure incident. Customer reminders are paused instead of
blaming every affected subscriber. Ordinary `insufficient_balance` failures
are explicitly excluded from this incident rule.

## Safe execution model

The decision engine uses no paid LLM or messaging API. Customer messages,
retries, and escalation cases remain simulated. The optional Razorpay adapter
accepts only Test Mode webhooks; it does not initiate charges. This keeps the
decision trail reproducible and prevents accidental financial or customer
actions. Output metrics are labelled `LOCAL_SIMULATION` or
`SYNTHETIC_BATCH_SIMULATION` and must not be presented as real merchant revenue.

## Project structure

| File | Responsibility |
|---|---|
| `scoring_engine.py` | Deterministic health and risk calculation |
| `ai_agent.py` | API-free diagnosis and initial recommendation |
| `outcome_evaluator.py` | Attributes the next event to the previous action |
| `incident_detector.py` | Detects systemic technical-failure cohorts |
| `action_engine.py` | Outcome-aware final policy and guardrails |
| `recovery_policy.py` | Validates and versions the merchant recovery constitution |
| `policy_simulator.py` | Runs side-effect-free active-versus-draft policy comparisons |
| `policy_experiment.py` | Benchmarks the adaptive policy against fixed reminders on paired synthetic cases |
| `merchant_policy.local.json` | Local thresholds, contact limits, permissions, and stopping rules |
| `action_simulator.py` | Executes only the final approved simulated action |
| `agent_memory.py` | State, action history, outcomes, and audit IDs |
| `recovery_metrics.py` | Recovery rate and INR recovery metrics |
| `batch_recovery_evaluation.py` | Deterministic 100-subscription evaluation |
| `live_agent.py` | Polls MySQL and runs the complete six-stage loop |
| `razorpay_webhook.py` | Verifies, deduplicates, audits, and normalises subscription or Payment Link Test Mode events |
| `dashboard_server.py` | Hosted-style local command center using Python only |
| `dashboard_web/index.html` | Responsive command-center interface and charts |
| `dashboard.py` | Streamlit fallback dashboard |

## Setup on Windows

Requirements: Python 3.10+, MySQL, and the packages in `requirements.txt`.

```powershell
py -m pip install -r requirements.txt
Copy-Item db_config.example.json db_config.local.json
notepad db_config.local.json
```

Enter the local MySQL password in `db_config.local.json`. That file is ignored
by Git and must never be uploaded.

Run `schema.sql` and `seed_demo_data.sql` in MySQL Workbench. The seed creates
five deterministic subscriptions covering Healthy, Stable, At Risk, High Risk,
and Critical behaviour.

## Run the pipeline once

```powershell
py scoring_engine.py
py ai_agent.py
py action_engine.py
py action_simulator.py
py recovery_metrics.py
```

## Run the live closed loop

```powershell
py live_agent.py
```

## Run the local dashboard

The dashboard reads the latest CSV and JSON files produced by the pipeline. It
does not write payment data to MySQL or execute any customer/payment action.
Its one local write capability is the versioned Merchant Recovery Constitution.

```powershell
py dashboard_server.py
```

It opens `http://localhost:8502` automatically and needs no Node.js, React, or
extra dashboard package. Keep the live agent running in one terminal and the
dashboard in another. Use **Refresh data** after a payment event to display the
newest score, decision, outcome, guardrail, and audit entry.

### Merchant Recovery Constitution

Scroll to **Merchant Recovery Constitution** in the dashboard to control:

- the four health-score decision boundaries;
- maximum customer contacts and the contact-window length;
- stop-after-success versus passive post-recovery monitoring;
- human approval after an automated recovery fails;
- systemic-incident suppression versus human incident review; and
- whether reminders and high-priority recovery are permitted at all.

Select **Save & activate policy**. The next live-agent cycle reads the new
version automatically—no process restart is required. New action audit records
include the policy name and version used.

Policy writes are accepted only when the dashboard is opened through
`http://localhost:8502`. The public tunnel remains able to deliver Razorpay
webhooks but receives HTTP 403 if it attempts to change merchant policy.

The policy is also stored in `merchant_policy.local.json`. It is ignored by
Git so local merchant choices are not accidentally published. To recreate it:

```powershell
Copy-Item merchant_policy.example.json merchant_policy.local.json
```

If port 8502 is busy, choose another port:

```powershell
py dashboard_server.py --port 8503
```

### Counterfactual Recovery Lab

Scroll to **Counterfactual Recovery Lab** to test a policy change before
activating it. The lab runs the real deterministic decision engine twice on
the exact same fresh failed-payment scenario:

- **Active constitution** uses the currently saved merchant policy.
- **Proposed constitution** changes only the draft high-risk boundary and
  contact cap shown in the lab.

Choose a subscription, adjust its score, previous score, recent-contact count,
or systemic-incident switch, and select **Compare decisions**. The dashboard
shows both final actions, priorities, contact paths, and guardrails side by
side. The initial S005 example intentionally demonstrates how moving the
high-risk boundary can change `PAYMENT_REMINDER` into
`HIGH_PRIORITY_RECOVERY` without changing the customer or payment event.

This is a read-only counterfactual. It does not save the draft, insert a MySQL
row, create a payment, send a message, mutate agent memory, or forecast
revenue. After reviewing the difference, use **Merchant Recovery
Constitution** separately if you want to activate a policy.

### Paired Agent-vs-Baseline Evidence

Run the reproducible policy benchmark before opening the dashboard:

```powershell
py policy_experiment.py
```

It runs 30 trials of 500 failed-mandate scenarios. In every paired case, the
adaptive agent and a one-size-fits-all reminder baseline receive the same
health score, amount, systemic-failure flag, and random outcome draw. The
adaptive side calls the real policy simulator and guardrails; the baseline
sends one fixed reminder for every failure.

The included reference run produced:

| Mean metric | Adaptive agent | Fixed reminder |
|---|---:|---:|
| Customer recovery rate | 40.45% | 38.84% |
| Interventions per 100 failures | 65.89 | 100.00 |
| Recoveries per 100 interventions | 61.40 | 38.84 |
| Contacts during systemic failures per 100 | 0.00 | 12.00 |

The paired mean recovery-rate difference was +1.61 percentage points with a
95% simulation confidence interval of +1.09 to +2.14. More importantly for
the trust-first product goal, the agent avoided 34.11 interventions per 100
failures and prevented all contacts in the declared systemic cohort.

These figures are **synthetic policy-experiment results**, not measured
production lift. The recovery probabilities are visible scenario assumptions
inside `policy_experiment.py`, raw per-trial results are retained, and the
dashboard repeats this limitation instead of hiding it.

Generated evidence:

- `experiment_output/policy_benchmark.json`
- `experiment_output/experiment_runs.json`

The older Streamlit version remains available as a fallback:

```powershell
py -m streamlit run dashboard.py
```

## Connect Razorpay Test Mode

This stage needs only a **Test Mode webhook secret**. The Test Key ID and Key
Secret are not placed in this project because the adapter receives events and
does not create charges.

1. Create the private local configuration:

```powershell
Copy-Item razorpay_config.example.json razorpay_config.local.json
notepad razorpay_config.local.json
```

2. Put the same webhook secret that you configure in the Razorpay Test Mode
   Dashboard into `webhook_secret`. Native subscription events can map a
   Razorpay test subscription ID to an existing local subscription:

```json
{
    "mode": "test",
    "webhook_secret": "YOUR_PRIVATE_TEST_WEBHOOK_SECRET",
    "subscription_map": {
        "sub_YOUR_TEST_ID": {
            "local_subscription_id": "S005",
            "amount": 599
        }
    },
    "payment_link_map": {}
}
```

`razorpay_config.local.json` is ignored and must never be uploaded. Do not put
the secret in `razorpay_config.example.json`.

3. Run the same two processes in separate terminals:

```powershell
py live_agent.py
```

```powershell
py dashboard_server.py
```

4. Razorpay cannot call `localhost`. Expose port `8502` through a trusted HTTPS
   development tunnel, then configure this Test Mode webhook URL:

```text
https://YOUR-TUNNEL-DOMAIN/webhooks/razorpay
```

The receiver supports these native subscription events:

- `subscription.charged` — successful charge
- `subscription.pending` — failed charge awaiting retry
- `subscription.halted` — retries exhausted

### Payment Link fallback for restricted test accounts

Some Test Mode accounts cannot move a dashboard-created recurring subscription
into an active state. In that case, use a Standard Payment Link to produce
genuine Razorpay-signed payment outcomes while keeping the native subscription
adapter ready for production-enabled accounts.

1. Edit the existing webhook and also enable:

   - `payment.failed`
   - `payment.captured`

2. Create a **Test Mode Standard Payment Link** for INR 599. Use a unique
   reference such as `MHR-S005-DEMO` and add this note:

```text
local_subscription_id = S005
```

3. Keep `live_agent.py`, `dashboard_server.py`, and the HTTPS tunnel running.
   Open the link and choose a failed Test Mode outcome. Razorpay sends
   `payment.failed`; the verified event becomes a failed attempt for `S005`.

4. Retry the link with a successful Test Mode outcome. Razorpay sends
   `payment.captured`; the same agent observes the recovery and stops further
   intervention.

The note is the safest demo mapping because it travels with the payment event.
As a fallback, `payment_link_map` can map a Razorpay order or Payment Link
identifier to a local subscription:

```json
{
    "payment_link_map": {
        "order_YOUR_TEST_ORDER_ID": {
            "local_subscription_id": "S005",
            "amount": 599
        }
    }
}
```

This fallback proves the real Razorpay webhook transport, signature,
idempotency, database ingestion, and closed-loop decision path. Describe it as
a **Test Mode payment-outcome simulation**, not as evidence that a live UPI
Autopay mandate was charged.

The receiver validates `X-Razorpay-Signature` against the untouched request
body, deduplicates `X-Razorpay-Event-Id`, retains an audit row, and inserts a
normalised payment attempt. The live agent detects that attempt within 30
seconds. Unknown subscriptions and payment events without a safe mapping are
retained as `UNMAPPED` instead of being assigned to the wrong customer.

The dashboard's **Razorpay Test Mode gateway** shows configuration state,
mapping count, signature verification, processing status, and the local event
IDs. Manual SQL remains available as an offline fallback.

The live agent processes only the subscription belonging to the new event. It
does not repeat actions for all customers whenever one customer pays.

To demonstrate S005 recovering after a reminder, insert a new successful
payment and attempt from MySQL Workbench after the reminder cycle:

```sql
USE mandate_health;

INSERT INTO payments
    (payment_id, subscription_id, customer_id, amount, status, payment_date, failure_reason)
VALUES
    ('P038', 'S005', 'C005', 599, 'success', NOW(), NULL);

INSERT INTO payment_attempts
    (attempt_id, payment_id, subscription_id, attempt_number, attempt_time, status, failure_reason)
VALUES
    ('A038', 'P038', 'S005', 1, NOW(), 'success', NULL);
```

The next cycle should show:

```text
Previous action : PAYMENT_REMINDER
Outcome         : RECOVERED
Amount recovered: INR 599.00
Final action    : NO_INTERVENTION
Guardrail       : STOP_AFTER_SUCCESS
```

Use different unused IDs if `P038` or `A038` already exists.

## Tests

The tests do not require MySQL and do not send anything externally.

```powershell
py -m unittest discover -s tests -v
```

The 40 tests verify cooldown enforcement, configurable decision boundaries and
contact caps, policy validation/versioning, local-only policy writes,
side-effect-free counterfactual comparisons, public read-only simulation,
paired experiment reproducibility, baseline fairness, visible assumptions,
systemic-contact suppression, stale-outcome protection, escalation after a failed reminder,
stop-after-success, recovery metrics, idempotent audit history, webhook
signatures, subscription and Payment Link normalisation, notes/order mapping,
unsupported events, and stable local identifiers.

## Reproducible 100-subscription evaluation

```powershell
py batch_recovery_evaluation.py
```

This runs the real local policy, memory, outcome evaluator, guardrails, and
audit functions across a deterministic synthetic cohort. It produces:

- `batch_output/batch_metrics.json`
- `batch_output/batch_results.json`
- `batch_output/exception_list.json`

The random seed and limitations are written into the metrics. Results are
explicitly labelled `SYNTHETIC_BATCH_SIMULATION`; they are evidence that the
workflow behaves across a batch, not a claim about real Razorpay recovery.

## Generated audit files

- `agent_memory.json`: state plus per-subscription action history
- `outcome_history.json`: action-to-outcome attribution
- `action_engine_results.json`: recommended versus final action
- `simulated_actions.json`: final executed simulation
- `recovery_metrics.json`: clearly labelled simulated recovery metrics

## Current limitation

All actions and batch/experiment outcomes are simulated. Razorpay Test Mode provides a
realistic signed event source but does not prove production recovery lift. A
Payment Link fallback proves webhook transport and payment-outcome ingestion;
it is not evidence that a live recurring mandate was charged. The paired
fixed-reminder benchmark is reproducible scenario evidence, not causal proof.
The next evidence step is validation on consented historical data followed by
a controlled merchant pilot.
