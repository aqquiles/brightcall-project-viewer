from __future__ import annotations

import html
import inspect
import re
from typing import Any

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

PROJECTS_URL = "https://api.dialer.brightcall.ai/api/v1/projects"
DAILY_PROJECTS_URL = "https://api.dialer.brightcall.ai/api/v1/stat/daily-projects"

DAILY_COLUMNS = [
    "userProject",
    "contactsAll",
    "contactsFailed",
    "contactsAvailable",
    "contactsReady",
    "linesLimit",
    "callsNow",
    "callsToday",
    "newContacts",
    "pp",
    "cpp",
    "tr",
    "cptr",
@@ -417,50 +418,66 @@ def build_account_report_html(target_account: str, account_total: dict[str, str]
</style>
</head>
<body>
    <h1>Brightcall Daily Client Report</h1>
    <div class=\"subtitle\">Account: {html.escape(target_account)}</div>

    <div class=\"cards\">
        <div class=\"card\"><div class=\"label\">Projects</div><div class=\"value\">{len(projects)}</div></div>
        <div class=\"card\"><div class=\"label\">Calls Today</div><div class=\"value\">{html.escape(str((account_total or {{}}).get('callsToday', '')))}</div></div>
        <div class=\"card\"><div class=\"label\">TR</div><div class=\"value\">{html.escape(str((account_total or {{}}).get('tr', '')))}</div></div>
        <div class=\"card\"><div class=\"label\">QT</div><div class=\"value\">{html.escape(str((account_total or {{}}).get('qt', '')))}</div></div>
        <div class=\"card\"><div class=\"label\">CPTR</div><div class=\"value\">{html.escape(str((account_total or {{}}).get('cptr', '')))}</div></div>
        <div class=\"card\"><div class=\"label\">CPQT</div><div class=\"value\">{html.escape(str((account_total or {{}}).get('cpqt', '')))}</div></div>
    </div>

    <h2>Account Total</h2>
    {account_block}

    <h2>Projects ({len(projects)})</h2>
    {project_block}
</body>
</html>
""".strip()


def render_auto_refresh_selectbox(options: list[str]) -> str:
    selectbox_kwargs = {
        "label": "Auto-refresh interval",
        "options": options,
        "index": 0,
    }

    if "label_visibility" in inspect.signature(st.selectbox).parameters:
        selectbox_kwargs["label_visibility"] = "collapsed"
        return st.selectbox(**selectbox_kwargs)

    st.markdown("&nbsp;", unsafe_allow_html=True)
    selectbox_kwargs["label"] = " "
    return st.selectbox(**selectbox_kwargs)


def enable_auto_refresh(interval_seconds: int, *, key: str = "auto_refresh") -> None:
    if interval_seconds <= 0:
        return

    refresh_ms = interval_seconds * 1000
    components.html(
        f"""
        <script>
            const timerKey = "{key}";
            if (window[timerKey]) {{
                clearTimeout(window[timerKey]);
            }}
            window[timerKey] = setTimeout(function() {{
                window.parent.location.reload();
            }}, {refresh_ms});
        </script>
        """,
        height=0,
    )


# -----------------------------
# Rendering
# -----------------------------
def render_project_viewer() -> None:
@@ -584,64 +601,72 @@ def render_project_viewer() -> None:

        csv_data = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download visible projects CSV",
            data=csv_data,
            file_name="brightcall_projects.csv",
            mime="text/csv",
        )


def render_daily_client_report() -> None:
    st.subheader("Daily Client Report")
    st.caption("Build a reusable client report from the daily-projects endpoint, using account email as the selector.")

    daily_api_key = get_daily_stats_api_key()
    default_account = get_default_report_account()

    if not daily_api_key:
        st.warning("Add BRIGHTCALL_DAILY_STATS_API_KEY to Streamlit secrets to enable this report.")
        return

    toolbar_left, toolbar_mid, toolbar_right = st.columns([1.1, 1, 3.2])
    with toolbar_left:
        refresh_daily = st.button("Refresh daily report data")
    with toolbar_mid:
        auto_refresh_label = render_auto_refresh_selectbox(
            [
                "Off",
                "30 seconds",
                "1 minute",
                "5 minutes",
                "10 minutes",
                "15 minutes",
                "30 minutes",
            ]
        )
    with toolbar_right:
        st.empty()

    auto_refresh_seconds = {
        "Off": 0,
        "30 seconds": 30,
        "1 minute": 60,
        "5 minutes": 300,
        "10 minutes": 600,
        "15 minutes": 900,
        "30 minutes": 1800,
    }[auto_refresh_label]

    if refresh_daily or auto_refresh_seconds > 0:
        fetch_daily_projects_html.clear()

    if auto_refresh_seconds > 0:
        enable_auto_refresh(auto_refresh_seconds, key="daily_client_report_refresh")

    st.caption("Daily stats API key is read from Streamlit secrets.")

    try:
        html_payload = fetch_daily_projects_html(daily_api_key)
        sections = parse_daily_sections(html_payload)
    except requests.HTTPError as exc:
        st.error(f"HTTP error while calling the daily-projects endpoint: {exc}")
        return
    except requests.RequestException as exc:
        st.error(f"Request error while calling the daily-projects endpoint: {exc}")
        return
    except Exception as exc:
        st.error(f"Unexpected error while building the daily client report: {exc}")
        return

    if not sections:
        st.warning("No account sections were found in the daily-projects HTML response.")
