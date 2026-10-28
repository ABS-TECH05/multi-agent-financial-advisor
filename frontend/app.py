import json
import os
from datetime import date

import requests
import streamlit as st

st.set_page_config(
    page_title="INTELLIVEST",
    page_icon="📈",
    layout="wide",
)

st.title("📈 INTELLIVEST")
st.caption(
    "Multi-Agent Financial Advisor | Portfolio Analysis and Risk Assessment"
)

DEFAULT_API_URL = os.getenv("INTELLIVEST_API_URL", "https://multi-agent-financial-advisor.onrender.com")
api_url = st.sidebar.text_input("Backend API URL", DEFAULT_API_URL).rstrip("/")


def get_api(path: str):
    response = requests.get(f"{api_url}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def post_api(path: str, payload: dict):
    response = requests.post(
        f"{api_url}{path}",
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


try:
    health = get_api("/health")
    universe = get_api("/universe")
    example = get_api("/profiles/example")
    st.sidebar.success("Backend connected")
except requests.RequestException as exc:
    st.error(
        "Cannot connect to the INTELLIVEST backend. Check its URL and deployment status."
    )
    st.code(str(exc))
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Backend", health.get("status", "Connected"))
col2.metric("Available assets", health.get("universe_size", len(universe)))
col3.metric("LLM enabled", str(health.get("llm_enabled", False)))

st.divider()
st.header("Investor profile")

with st.form("advisor_form"):
    left, right = st.columns(2)

    with left:
        investor_id = st.text_input(
            "Investor ID", value=str(example.get("investor_id", "DEMO-001"))
        )
        age = st.number_input(
            "Age", min_value=18, max_value=100,
            value=int(example.get("age", 34)),
        )
        horizon_years = st.number_input(
            "Investment horizon (years)", min_value=1, max_value=80,
            value=int(example.get("horizon_years", 12)),
        )
        risk_tolerance = st.slider(
            "Risk tolerance", min_value=1, max_value=5,
            value=max(1, min(5, int(example.get("risk_tolerance", 4)))),
        )
        loss_tolerance_pct = st.number_input(
            "Loss tolerance (fraction; 0.20 = 20%)",
            min_value=0.01,
            max_value=1.0,
            value=float(example.get("loss_tolerance_pct", 0.20)),
            step=0.01,
            format="%.2f",
        )

    with right:
        goal_options = [
            "growth", "balanced_growth", "income", "capital_preservation"
        ]
        default_goal = str(example.get("goal", "growth"))
        goal = st.selectbox(
            "Investment goal",
            goal_options,
            index=goal_options.index(default_goal)
            if default_goal in goal_options else 0,
        )

        liquidity_options = ["low", "medium", "high"]
        default_liquidity = str(example.get("liquidity_need", "low"))
        liquidity_need = st.selectbox(
            "Liquidity requirement",
            liquidity_options,
            index=liquidity_options.index(default_liquidity)
            if default_liquidity in liquidity_options else 0,
        )

        try:
            default_date = date.fromisoformat(str(example.get("as_of", date.today().isoformat())))
        except ValueError:
            default_date = date.today()
        as_of = st.date_input("Decision date", value=default_date)
        notes = st.text_area("Additional notes", value=str(example.get("notes", "")))

    holdings_text = st.text_area(
        "Current holdings (JSON)",
        value=json.dumps(example.get("current_holdings", {}), indent=2),
        height=150,
        help="Use asset symbols as keys and numeric weights as values.",
    )
    exclusions_text = st.text_input(
        "Excluded assets (comma-separated)",
        value=", ".join(example.get("exclusions", [])),
    )
    submitted = st.form_submit_button(
        "Analyze portfolio", type="primary", use_container_width=True
    )

if submitted:
    try:
        current_holdings = json.loads(holdings_text)
        if not isinstance(current_holdings, dict):
            raise ValueError("Current holdings must be a JSON object.")
        if not all(isinstance(key, str) for key in current_holdings):
            raise ValueError("Every holding key must be an asset symbol.")
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in current_holdings.values()
        ):
            raise ValueError("Every holding weight must be numeric.")
        if not investor_id.strip():
            raise ValueError("Investor ID cannot be empty.")

        payload = {
            "investor_id": investor_id.strip(),
            "as_of": as_of.isoformat(),
            "age": int(age),
            "horizon_years": int(horizon_years),
            "risk_tolerance": int(risk_tolerance),
            "loss_tolerance_pct": float(loss_tolerance_pct),
            "goal": goal,
            "liquidity_need": liquidity_need,
            "current_holdings": current_holdings,
            "exclusions": [
                item.strip()
                for item in exclusions_text.split(",")
                if item.strip()
            ],
            "notes": notes,
        }

        with st.spinner("Running the multi-agent advisory pipeline..."):
            result = post_api("/advise", payload)
        st.session_state["advice_result"] = result

    except json.JSONDecodeError:
        st.error("Current holdings must be valid JSON.")
    except requests.HTTPError as exc:
        st.error(f"The backend rejected the request: {exc}")
        if exc.response is not None:
            st.code(exc.response.text)
    except (requests.RequestException, ValueError) as exc:
        st.error(str(exc))

if "advice_result" in st.session_state:
    result = st.session_state["advice_result"]
    st.divider()
    st.header("Analysis results")

    trace_id = result.get("trace_id")
    if trace_id:
        st.write("**Audit trace ID:**", trace_id)

    recommendation = result.get("recommendation", {})
    st.subheader("Portfolio recommendation")
    st.json(recommendation, expanded=True)

    # Display a chart only when the response contains recognizable weights.
    if isinstance(recommendation, dict):
        for key in ("weights", "target_weights", "portfolio_weights", "allocation"):
            weights = recommendation.get(key)
            if isinstance(weights, dict) and weights:
                try:
                    import pandas as pd

                    chart_data = pd.DataFrame(
                        [
                            {"Asset": str(asset), "Weight": float(weight)}
                            for asset, weight in weights.items()
                        ]
                    ).set_index("Asset")
                    st.subheader("Portfolio allocation")
                    st.bar_chart(chart_data)
                except (TypeError, ValueError):
                    st.info("Allocation values were returned but could not be charted.")
                break

    with st.expander("Agent findings"):
        st.json(result.get("agents", []), expanded=True)
    with st.expander("Explanation"):
        st.json(result.get("explanation", {}), expanded=True)
    with st.expander("Decision steps"):
        st.json(result.get("steps", []), expanded=True)
    with st.expander("Full API response"):
        st.json(result, expanded=True)

    if trace_id and st.button("Load audit trace"):
        try:
            st.session_state["loaded_trace"] = get_api(f"/trace/{trace_id}")
        except requests.RequestException as exc:
            st.error(f"Could not load audit trace: {exc}")

    if "loaded_trace" in st.session_state:
        with st.expander("Audit trace", expanded=True):
            st.json(st.session_state["loaded_trace"], expanded=True)

    if st.button("Verify audit chain"):
        try:
            verification = get_api("/audit/verify")
            if verification.get("ok"):
                st.success(verification.get("message", "Audit verification passed."))
            else:
                st.warning(verification.get("message", "Audit verification did not pass."))
            st.json(verification)
        except requests.RequestException as exc:
            st.error(f"Audit verification failed: {exc}")

with st.expander("Available assets"):
    st.json(universe, expanded=True)

with st.expander("Backend health details"):
    st.json(health, expanded=True)

st.divider()
st.caption(
    "Research prototype only. Outputs are estimates and are not guaranteed "
    "returns or professional financial advice."
)