# Changes in this version

- Added a paired Agent-vs-Fixed-Reminder evidence harness using 30 reproducible
  trials of 500 identical synthetic cases per strategy.
- Applied common random numbers so both strategies face the same customer,
  amount, failure type, and outcome draw in each comparison.
- Added recovery, intervention-efficiency, systemic-contact, human-review, and
  revenue metrics with 95% simulation confidence intervals and raw run data.
- Added a dashboard evidence panel with direct Adaptive-versus-Fixed bars.
- Kept every recovery probability and limitation visible; results are labelled
  synthetic policy evidence rather than production or causal lift.
- Added five benchmark fairness/reproducibility tests; 40 tests now pass.

- Added a Counterfactual Recovery Lab to compare the active constitution with
  a proposed draft on the exact same failed-payment scenario.
- Added side-by-side final actions, priorities, contact paths, reasons, and
  guardrails with a clear decision-difference summary.
- Reused the production decision and guardrail functions through a
  side-effect-free preview path; the simulator does not write payments,
  actions, memory, metrics, policy, or revenue forecasts.
- Added a read-only `/api/simulate-policy` endpoint that remains usable in the
  judge-facing tunnel while policy activation stays restricted to localhost.
- Added seven counterfactual and API safety tests; the complete suite now has
  35 passing tests.

- Added a functional Merchant Recovery Constitution to the command center.
  Merchants can version health thresholds, contact limits/windows, automated
  action permissions, recovery stopping behaviour, incident handling, and the
  post-failure approval rule.
- Compiled the saved constitution directly into the deterministic action
  engine; it is not a decorative dashboard form.
- Restricted policy writes to the localhost dashboard so the public webhook
  tunnel cannot change decision rules.
- Added policy name/version to new action decisions and audit records.
- Corrected a stale-memory edge case: a second successful payment with no
  pending intervention now reports `CURRENT_PAYMENT_SUCCESS` and
  `NO_ACTION_ON_SUCCESS`, rather than reusing an earlier recovery label.
- Expanded the suite from 17 to 28 tests, including policy validation,
  versioning, enforcement, localhost authorization, and stale-outcome safety.

- Removed hard-coded MySQL credentials from every Python file.
- Added shared environment/local-file configuration and Git exclusions.
- Kept the original 30/25/15/15/15 health-scoring model.
- Separated `attempt_id` from `payment_id` throughout the new pipeline.
- Corrected payment-timeline logic to use the latest attempt for each payment.
- Added previous-action outcome attribution before the next decision.
- Added complete, idempotent action history instead of overwriting memory.
- Fixed cooldown so the executed action is `MONITOR`, not another reminder.
- Added escalation after a failed reminder and stop-after-success behaviour.
- Aligned diagnosis and action thresholds so moderate deterioration does not
  prematurely trigger high-priority recovery.
- Added two-contact/72-hour and human-approval guardrails.
- Added cohort technical-failure detection and customer-contact suppression.
- Made the live agent process only the subscription that triggered the event.
- Added simulated INR-at-risk and INR-recovered metrics.
- Added a standalone adaptive-loop demo that requires no database.
- Added a deterministic 100-subscription evaluation with an exception list.
- Added a read-only Streamlit command center for live scores, adaptive action
  history, guardrails, audit IDs, and clearly labelled recovery metrics.
- Added portfolio-health, recovery-economics, and adaptive-score charts with a
  denser command-center layout for faster evaluation.
- Added a polished hosted-style local command center with responsive charts,
  selectable risk anatomy, adaptive timeline, and live CSV/JSON refresh. It
  runs with one Python command and adds no external API or Node.js dependency.
- Added optional Razorpay Test Mode subscription webhook ingestion with raw-body
  HMAC-SHA256 verification, event-ID deduplication, safe subscription mapping,
  MySQL audit retention, and normalisation into the existing closed loop.
- Added a Razorpay gateway panel showing integration state, verified event
  history, mapping status, and the local attempt generated for each webhook.
- Added twelve webhook tests; the suite now contains seventeen focused tests.
- Added a genuine Test Mode Payment Link fallback for accounts where a test
  subscription cannot become active. Signed `payment.failed` and
  `payment.captured` events now enter the same mandate-recovery pipeline.
- Added safe local-mandate mapping through Razorpay entity notes and optional
  order/Payment Link mappings, without weakening signature or event-ID checks.
- Added reproducible MySQL schema and seed data.
- Added five automated tests and complete setup/documentation.
