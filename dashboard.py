"""Local Streamlit dashboard for the mandate-recovery agent.

The dashboard is read-only. It visualizes files produced by the existing
pipeline and never sends messages, retries payments, or changes MySQL data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
HEALTH_FILE = PROJECT_DIR / "customer_health_scores.csv"
AI_FILE = PROJECT_DIR / "ai_agent_results.json"
ACTION_FILE = PROJECT_DIR / "action_engine_results.json"
MEMORY_FILE = PROJECT_DIR / "agent_memory.json"
AUDIT_FILE = PROJECT_DIR / "simulated_actions.json"
LOCAL_METRICS_FILE = PROJECT_DIR / "recovery_metrics.json"
BATCH_METRICS_FILE = PROJECT_DIR / "batch_output" / "batch_metrics.json"
DEMO_TRACE_FILE = PROJECT_DIR / "demo_output" / "adaptive_trace.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def load_health_scores() -> pd.DataFrame:
    try:
        return pd.read_csv(HEALTH_FILE)
    except (FileNotFoundError, pd.errors.EmptyDataError, OSError):
        return pd.DataFrame()


def as_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def find_subscription(
    records: list[dict[str, Any]], subscription_id: str
) -> dict[str, Any]:
    return next(
        (
            item
            for item in records
            if str(item.get("subscription_id")) == subscription_id
        ),
        {},
    )


def money(value: Any) -> str:
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return "₹0"


def render_metric_cards(scope: str) -> None:
    local = load_json(LOCAL_METRICS_FILE, {})
    batch = load_json(BATCH_METRICS_FILE, {})

    if scope == "Local simulation":
        metrics = [
            (
                "Revenue at risk",
                money(local.get("revenue_at_risk", 0)),
                f"{local.get('customers_monitored', 0)} customers monitored",
            ),
            (
                "Amount recovered",
                money(local.get("amount_recovered", 0)),
                f"{local.get('successful_recoveries', 0)} recoveries confirmed",
            ),
            (
                "Revenue recovery",
                f"{float(local.get('revenue_recovery_percent', 0)):.2f}%",
                "Controlled local events",
            ),
            (
                "Interventions",
                str(local.get("interventions_executed", 0)),
                f"{float(local.get('recovery_rate_percent', 0)):.2f}% action recovery",
            ),
        ]
    else:
        metrics = [
            (
                "Revenue at risk",
                money(batch.get("revenue_at_risk", 0)),
                f"{batch.get('subscriptions_evaluated', 0)} subscriptions evaluated",
            ),
            (
                "Amount recovered",
                money(batch.get("amount_recovered", 0)),
                f"{batch.get('customers_recovered', 0)} customers recovered",
            ),
            (
                "Revenue recovery",
                f"{float(batch.get('revenue_recovery_rate_percent', 0)):.1f}%",
                "Deterministic synthetic batch",
            ),
            (
                "Contacts held",
                str(batch.get("contacts_suppressed_for_systemic_incident", 0)),
                "Systemic incident protection",
            ),
        ]

    columns = st.columns(4)
    for column, (label, value, help_text) in zip(columns, metrics):
        with column:
            st.metric(label, value, help=help_text)


def render_portfolio_charts(health: pd.DataFrame, scope: str) -> None:
    chart_data = health.copy()
    chart_data["subscription_id"] = chart_data["subscription_id"].astype(str)
    chart_data["health_score"] = pd.to_numeric(
        chart_data.get("health_score", 0), errors="coerce"
    ).fillna(0)
    if "health_status" not in chart_data.columns:
        chart_data["health_status"] = "Unknown"

    status_domain = ["Critical", "High Risk", "At Risk", "Stable", "Healthy"]
    status_colors = ["#ff7b75", "#ff9e78", "#f6c35b", "#65e6b4", "#61d9ff"]

    local = load_json(LOCAL_METRICS_FILE, {})
    batch = load_json(BATCH_METRICS_FILE, {})
    if scope == "Local simulation":
        revenue_at_risk = float(local.get("revenue_at_risk", 0) or 0)
        amount_recovered = float(local.get("amount_recovered", 0) or 0)
        evidence_label = "Controlled local events"
    else:
        revenue_at_risk = float(batch.get("revenue_at_risk", 0) or 0)
        amount_recovered = float(batch.get("amount_recovered", 0) or 0)
        evidence_label = "100-subscription synthetic batch"

    unresolved = max(revenue_at_risk - amount_recovered, 0)
    economics = pd.DataFrame(
        {
            "outcome": ["Recovered", "Unresolved"],
            "amount": [amount_recovered, unresolved],
        }
    )

    portfolio_column, economics_column = st.columns([1.3, 0.7], gap="large")
    with portfolio_column:
        with st.container(border=True):
            st.markdown("### Portfolio health distribution")
            st.caption("Select customers below to inspect why their scores differ.")
            health_chart = (
                alt.Chart(chart_data)
                .mark_bar(cornerRadiusEnd=7, size=28)
                .encode(
                    x=alt.X(
                        "health_score:Q",
                        title="Health score",
                        scale=alt.Scale(domain=[0, 100]),
                    ),
                    y=alt.Y(
                        "subscription_id:N",
                        title=None,
                        sort=alt.EncodingSortField(
                            field="health_score", order="ascending"
                        ),
                    ),
                    color=alt.Color(
                        "health_status:N",
                        title="Status",
                        scale=alt.Scale(
                            domain=status_domain,
                            range=status_colors,
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("subscription_id:N", title="Subscription"),
                        alt.Tooltip("health_score:Q", title="Health score"),
                        alt.Tooltip("health_status:N", title="Status"),
                    ],
                )
                .properties(height=285)
                .configure_view(strokeOpacity=0)
                .configure_axis(
                    gridColor="#23354b",
                    domainColor="#354a63",
                    labelColor="#aebfd2",
                    titleColor="#aebfd2",
                )
                .configure_legend(
                    labelColor="#aebfd2",
                    titleColor="#aebfd2",
                    orient="bottom",
                )
            )
            st.altair_chart(health_chart, width="stretch", theme=None)

    with economics_column:
        with st.container(border=True):
            st.markdown("### Recovery economics")
            st.caption(evidence_label)
            recovery_chart = (
                alt.Chart(economics)
                .mark_arc(innerRadius=72, outerRadius=108, cornerRadius=6)
                .encode(
                    theta=alt.Theta("amount:Q"),
                    color=alt.Color(
                        "outcome:N",
                        scale=alt.Scale(
                            domain=["Recovered", "Unresolved"],
                            range=["#65e6b4", "#263a52"],
                        ),
                        legend=alt.Legend(orient="bottom", title=None),
                    ),
                    tooltip=[
                        alt.Tooltip("outcome:N", title="Outcome"),
                        alt.Tooltip("amount:Q", title="Amount", format=",.0f"),
                    ],
                )
                .properties(height=250)
                .configure_view(strokeOpacity=0)
                .configure_legend(labelColor="#aebfd2")
            )
            st.altair_chart(recovery_chart, width="stretch", theme=None)
            recovered_column, unresolved_column = st.columns(2)
            recovered_column.metric("Recovered", money(amount_recovered))
            unresolved_column.metric("Unresolved", money(unresolved))


def render_adaptive_score_chart() -> None:
    trace = as_records(load_json(DEMO_TRACE_FILE, []))
    points: list[dict[str, Any]] = []
    for index, item in enumerate(trace, start=1):
        decision = item.get("decision", {})
        if not isinstance(decision, dict):
            continue
        points.append(
            {
                "order": index,
                "event": decision.get("attempt_id", f"Step {index}"),
                "health_score": decision.get("health_score", 0),
                "action": decision.get("action_type", "UNKNOWN"),
                "status": decision.get("health_status", "Unknown"),
            }
        )

    if len(points) < 2:
        return

    data = pd.DataFrame(points)
    line = (
        alt.Chart(data)
        .mark_line(point=alt.OverlayMarkDef(size=95), strokeWidth=3)
        .encode(
            x=alt.X("event:N", title="Payment event", sort=alt.SortField("order")),
            y=alt.Y(
                "health_score:Q",
                title="Health score",
                scale=alt.Scale(domain=[0, 100]),
            ),
            color=alt.value("#61d9ff"),
            tooltip=[
                alt.Tooltip("event:N", title="Event"),
                alt.Tooltip("health_score:Q", title="Health score"),
                alt.Tooltip("action:N", title="Final action"),
                alt.Tooltip("status:N", title="Health status"),
            ],
        )
    )
    area = (
        alt.Chart(data)
        .mark_area(line=False, color="#61d9ff", opacity=0.12)
        .encode(
            x=alt.X("event:N", sort=alt.SortField("order")),
            y=alt.Y("health_score:Q", scale=alt.Scale(domain=[0, 100])),
        )
    )
    chart = (
        (area + line)
        .properties(height=250)
        .configure_view(strokeOpacity=0)
        .configure_axis(
            gridColor="#23354b",
            domainColor="#354a63",
            labelColor="#aebfd2",
            titleColor="#aebfd2",
        )
    )

    with st.container(border=True):
        heading, result = st.columns([3, 1])
        with heading:
            st.markdown("### Adaptive health-score response")
            st.caption(
                "Reproducible path: reminder → failed outcome → escalation → recovery → stop."
            )
        with result:
            first_score = int(data.iloc[0]["health_score"])
            final_score = int(data.iloc[-1]["health_score"])
            st.metric("Net health change", f"{final_score - first_score:+d} points")
        st.altair_chart(chart, width="stretch", theme=None)


def render_risk_breakdown(row: pd.Series) -> None:
    components = [
        ("Failure risk", "failure_risk", 30),
        ("Consecutive failures", "consecutive_failure_risk", 25),
        ("Retry risk", "retry_risk", 15),
        ("Recovery delay", "recovery_delay_risk", 15),
        ("Deterioration", "deterioration_risk", 15),
    ]

    st.markdown("#### Explainable risk anatomy")
    for label, key, maximum in components:
        raw_value = row.get(key, 0)
        value = 0 if pd.isna(raw_value) else int(raw_value)
        left, right = st.columns([5, 1])
        with left:
            st.caption(label)
            st.progress(
                min(max(value / maximum, 0), 1),
                text=f"{value} of {maximum}",
            )
        with right:
            st.markdown(f"<div class='risk-number'>{value}</div>", unsafe_allow_html=True)


def render_timeline(
    subscription_id: str, memory: dict[str, Any]
) -> None:
    customer_memory = memory.get(subscription_id, {})
    history = customer_memory.get("action_history", [])

    st.markdown("#### Closed-loop action timeline")
    if not history:
        st.info("No action history is recorded for this subscription yet.")
        return

    for index, action in enumerate(history, start=1):
        action_type = action.get("action_type", "UNKNOWN")
        outcome = action.get("outcome", "PENDING")
        status = action.get("action_status", "")
        amount_recovered = float(action.get("amount_recovered", 0) or 0)

        with st.container(border=True):
            top_left, top_right = st.columns([3, 1])
            with top_left:
                st.markdown(f"**{index}. `{action_type}`**")
                st.caption(
                    f"{action.get('source_attempt_id') or 'No attempt ID'} · "
                    f"{action.get('source_payment_id') or 'No payment ID'}"
                )
            with top_right:
                st.markdown(f"**{outcome}**")
                if amount_recovered:
                    st.caption(f"Recovered {money(amount_recovered)}")
            st.code(action.get("action_id", "No audit ID"), language=None)
            if status:
                st.caption(f"Decision status: {status}")


def render_audit(subscription_id: str) -> None:
    records = as_records(load_json(AUDIT_FILE, []))
    filtered = [
        record
        for record in records
        if str(record.get("subscription_id")) == subscription_id
    ]

    st.markdown("#### Idempotent audit trail")
    if not filtered:
        st.info("No simulated execution record is available for this subscription.")
        return

    audit = pd.DataFrame(filtered)
    visible_columns = [
        column
        for column in [
            "action_id",
            "attempt_id",
            "health_score",
            "ai_recommended_action",
            "final_action",
            "action_status",
            "guardrail_applied",
            "outcome_status",
        ]
        if column in audit.columns
    ]
    st.dataframe(
        audit[visible_columns],
        hide_index=True,
        width="stretch",
    )


def main() -> None:
    st.set_page_config(
        page_title="Mandate Recovery Command Center",
        page_icon="↗",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at 82% 0%, rgba(72,118,255,.17), transparent 30rem),
                #07111f;
            color: #edf4fb;
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stMetric"] {
            background: linear-gradient(145deg, rgba(24,39,59,.96), rgba(11,23,39,.96));
            border: 1px solid rgba(170,195,224,.15);
            border-radius: 16px;
            padding: 18px;
        }
        [data-testid="stMetricValue"] { color: #edf4fb; }
        [data-testid="stMetricLabel"], .stCaption { color: #9aacbf !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(170,195,224,.15) !important;
            background: rgba(17,29,46,.72);
        }
        .hero-label { color:#61d9ff; font-size:.72rem; font-weight:800; letter-spacing:.16em; }
        .hero-title { font-size:clamp(2.2rem,5vw,4.8rem); line-height:.95; letter-spacing:-.045em; font-weight:750; max-width:980px; margin:.65rem 0 1rem; }
        .hero-title span { color:#61d9ff; }
        .hero-copy { color:#9aacbf; max-width:760px; font-size:1rem; line-height:1.65; }
        .safe-pill { display:inline-block; color:#65e6b4; border:1px solid rgba(101,230,180,.25); background:rgba(101,230,180,.07); padding:.4rem .7rem; border-radius:999px; font-size:.72rem; }
        .risk-number { text-align:right; color:#61d9ff; font-family:monospace; font-weight:700; padding-top:1.9rem; }
        [data-testid="stVegaLiteChart"] {
            background: linear-gradient(180deg, rgba(8,19,33,.25), rgba(8,19,33,.05));
            border-radius: 12px;
            padding: .3rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMetric"] {
            box-shadow: none;
        }
        code { color:#bcd0e8 !important; }
        hr { border-color:rgba(170,195,224,.13) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    header_left, header_right = st.columns([4, 1])
    with header_left:
        st.markdown("<div class='hero-label'>MANDATE HEALTH · RECOVERY COMMAND CENTER</div>", unsafe_allow_html=True)
        st.markdown("<div class='hero-title'>Revenue recovery that <span>knows when to stop.</span></div>", unsafe_allow_html=True)
        st.markdown("<div class='hero-copy'>MySQL → Outcome → Scoring → Decision → Guarded simulation → Memory. Inspect why each action was selected and how the next payment changes the policy.</div>", unsafe_allow_html=True)
    with header_right:
        st.markdown("<div class='safe-pill'>● SAFE SIMULATION</div>", unsafe_allow_html=True)
        st.caption("No real messages, retries, escalations, or payments are executed.")
        if st.button("Refresh generated files", width="stretch"):
            st.rerun()

    st.divider()
    scope = st.radio(
        "Evidence scope",
        ["Local simulation", "100-subscription batch"],
        horizontal=True,
        label_visibility="collapsed",
    )
    render_metric_cards(scope)
    if scope == "100-subscription batch":
        st.caption(
            "SYNTHETIC_BATCH_SIMULATION — outcomes are seeded scenario assumptions, "
            "not production Razorpay recovery claims."
        )

    health = load_health_scores()
    if health.empty or "subscription_id" not in health.columns:
        st.warning(
            "No customer health file is available. Run `python scoring_engine.py` "
            "or process a live payment event, then refresh this dashboard."
        )
        return

    render_portfolio_charts(health, scope)

    st.divider()
    left, right = st.columns([1.45, 0.8], gap="large")

    with left:
        st.markdown("### Mandate health queue")
        queue_columns = [
            column
            for column in [
                "subscription_id",
                "latest_attempt_id",
                "latest_payment_id",
                "latest_payment_status",
                "health_score",
                "health_status",
                "unresolved_failures",
            ]
            if column in health.columns
        ]
        st.dataframe(
            health[queue_columns],
            hide_index=True,
            width="stretch",
            column_config={
                "health_score": st.column_config.ProgressColumn(
                    "Health score", min_value=0, max_value=100, format="%d"
                )
            },
        )
        choices = health["subscription_id"].astype(str).tolist()
        default_index = choices.index("S001") if "S001" in choices else 0
        selected_id = st.selectbox(
            "Inspect a subscription",
            choices,
            index=default_index,
        )

    selected_rows = health[
        health["subscription_id"].astype(str) == selected_id
    ]
    selected_row = selected_rows.iloc[0]
    ai_records = as_records(load_json(AI_FILE, []))
    action_records = as_records(load_json(ACTION_FILE, []))
    ai_result = find_subscription(ai_records, selected_id)
    action_result = find_subscription(action_records, selected_id)

    with right:
        score = int(selected_row.get("health_score", 0))
        status = str(selected_row.get("health_status", "Unknown"))
        score_left, score_right = st.columns(2)
        score_left.metric("Health score", f"{score}/100")
        score_right.metric("Status", status)
        render_risk_breakdown(selected_row)

    st.divider()
    decision_left, decision_right = st.columns(2, gap="large")
    with decision_left:
        st.markdown("### Explainable agent decision")
        diagnosis = ai_result.get(
            "primary_problem", "Run the AI agent to generate a diagnosis."
        )
        recommendation = ai_result.get("recommended_action", "NOT_AVAILABLE")
        final_action = action_result.get("action_type", recommendation)
        st.info(f"**Primary diagnosis:** {diagnosis}")
        decision_a, decision_b = st.columns(2)
        decision_a.metric("AI recommendation", recommendation)
        decision_b.metric("Final guarded action", final_action)
        explanation = ai_result.get("risk_explanation", [])
        if explanation:
            st.markdown("**Risk explanation**")
            for item in explanation:
                st.markdown(f"- {item}")
        st.caption(action_result.get("decision_reason", ai_result.get("reason", "")))

    with decision_right:
        st.markdown("### Policy and guardrails")
        guardrail = action_result.get("guardrail_applied") or "No guardrail needed"
        outcome = action_result.get("last_measured_outcome") or "Awaiting outcome"
        st.success(f"**Guardrail:** `{guardrail}`")
        st.metric("Measured previous outcome", outcome)
        st.write(action_result.get("message", "No current action message."))
        st.caption(action_result.get("next_step", "Continue normal monitoring."))

    st.divider()
    render_adaptive_score_chart()

    st.divider()
    memory = load_json(MEMORY_FILE, {})
    timeline_column, audit_column = st.columns([0.8, 1.2], gap="large")
    with timeline_column:
        render_timeline(selected_id, memory)
    with audit_column:
        render_audit(selected_id)

    st.divider()
    batch = load_json(BATCH_METRICS_FILE, {})
    protection_left, protection_right = st.columns([2, 1])
    with protection_left:
        st.markdown("### Cohort-level customer protection")
        st.write(
            "When several technical failures share a reason inside the incident "
            "window, customer contact is held instead of treating every subscriber "
            "as individually at fault. `insufficient_balance` is explicitly excluded."
        )
    with protection_right:
        st.metric(
            "Systemic contacts held",
            batch.get("contacts_suppressed_for_systemic_incident", 0),
            help="Measured in the deterministic 100-subscription batch.",
        )

    st.caption(
        "Data scope: local and synthetic simulation only. This dashboard is read-only "
        "and does not claim real merchant revenue recovery."
    )


if __name__ == "__main__":
    main()
