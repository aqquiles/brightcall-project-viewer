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
    "qt",
    "cpqt",
    "sh",
    "cpsh",
    "limit",
    "consumed",
    "hoursNow",
    "timezone",
    "sN",
]

# ... keep the rest of your constants and functions above this point ...


def build_account_report_html(
    target_account: str,
    account_total: dict[str, str] | None,
    projects: list[dict[str, str]],
    account_block: str,
    project_block: str,
) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Brightcall Daily Report - {html.escape(target_account)}</title>
<style>
    body {{ font-family: Arial, sans-serif; padding: 20px; }}
    h1 {{ color: #333; margin-bottom: 6px; }}
    .subtitle {{ color: #555; margin-bottom: 24px; }}
    h2 {{ color: #333; margin-top: 32px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 15px; font-size: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background-color: #007bff; color: white; }}
    tr:nth-child(even) {{ background-color: #f9f9f9; }}
    .account-row {{ background-color: #e7f3ff !important; font-weight: bold; }}
    .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 14px 0 8px 0; }}
    .card {{ border: 1px solid #ddd; border-radius: 6px; padding: 10px 14px; min-width: 120px; }}
    .label {{ font-size: 12px; color: #666; }}
    .value {{ font-size: 24px; font-weight: bold; margin-top: 4px; }}
    .no-data {{ color: #999; font-style: italic; padding: 20px 0; }}
</style>
</head>
<body>
    <h1>Brightcall Daily Client Report</h1>
    <div class="subtitle">Account: {html.escape(target_account)}</div>

    <div class="cards">
        <div class="card"><div class="label">Projects</div><div class="value">{len(projects)}</div></div>
        <div class="card"><div class="label">Calls Today</div><div class="value">{html.escape(str((account_total or {}).get('callsToday', '')))}</div></div>
        <div class="card"><div class="label">TR</div><div class="value">{html.escape(str((account_total or {}).get('tr', '')))}</div></div>
        <div class="card"><div class="label">QT</div><div class="value">{html.escape(str((account_total or {}).get('qt', '')))}</div></div>
        <div class="card"><div class="label">CPTR</div><div class="value">{html.escape(str((account_total or {}).get('cptr', '')))}</div></div>
        <div class="card"><div class="label">CPQT</div><div class="value">{html.escape(str((account_total or {}).get('cpqt', '')))}</div></div>
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
        "key": "daily_report_auto_refresh",
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


def render_daily_client_report() -> None:
    st.subheader("Daily Client Report")
    st.caption("Build a reusable client report from the daily-projects endpoint, using account email as the selector.")

    daily_api_key = get_daily_stats_api_key()
    default_account = get_default_report_account()

    if not daily_api_key:
        st.warning("Add BRIGHTCALL_DAILY_STATS_API_KEY to Streamlit secrets to enable this report.")
        return

    toolbar_left, toolbar_mid, toolbar_right = st.columns([1.1, 1.2, 3.0])

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

    if refresh_daily:
        fetch_daily_projects_html.clear()

    if auto_refresh_seconds > 0:
        fetch_daily_projects_html.clear()
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
        with st.expander("Show raw response preview"):
            st.code(html_payload[:5000], language="html")
        return

    account_options = sorted(sections.keys())
    default_index = (
        account_options.index(default_account.lower())
        if default_account and default_account.lower() in account_options
        else 0
    )

    selector_col, input_col = st.columns([1, 1])

    with selector_col:
        selected_account = st.selectbox(
            "Select account email",
            options=account_options,
            index=default_index,
        )

    with input_col:
        manual_account = st.text_input(
            "Or type account email",
            value=default_account,
            help="Use this when you want to jump directly to a specific client email.",
        ).strip().lower()

    target_account = manual_account or selected_account
    account_section = sections.get(target_account)

    if account_section is None:
        st.error("That account email was not found in the current daily-projects response.")
        st.write("Available accounts:", ", ".join(account_options))
        return

    account_total = account_section.get("account_total")
    projects = account_section.get("projects", [])

    account_total_df = pd.DataFrame([account_total]) if account_total else pd.DataFrame(columns=DAILY_COLUMNS)
    projects_df = pd.DataFrame(projects) if projects else pd.DataFrame(columns=DAILY_COLUMNS)

    csv_content = build_account_csv(account_total, projects)

    account_block = account_total_df.to_html(index=False, escape=False) if not account_total_df.empty else "<p>No account total found.</p>"
    project_block = projects_df.to_html(index=False, escape=False) if not projects_df.empty else "<p>No projects found.</p>"

    html_report = build_account_report_html(
        target_account=target_account,
        account_total=account_total,
        projects=projects,
        account_block=account_block,
        project_block=project_block,
    )

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Projects", len(projects))
    m2.metric("Calls Today", (account_total or {}).get("callsToday", ""))
    m3.metric("TR", (account_total or {}).get("tr", ""))
    m4.metric("QT", (account_total or {}).get("qt", ""))
    m5.metric("CPTR", (account_total or {}).get("cptr", ""))
    m6.metric("CPQT", (account_total or {}).get("cpqt", ""))

    st.markdown("### Account Total")
    if account_total:
        st.dataframe(account_total_df, use_container_width=True, hide_index=True)
    else:
        st.info("No account total row was found for this account.")

    st.markdown(f"### Projects ({len(projects)})")
    if projects:
        st.dataframe(projects_df, use_container_width=True, hide_index=True)
    else:
        st.info("No project rows were found for this account.")

    st.markdown("### Report exports")
    export_left, export_right = st.columns(2)

    with export_left:
        st.download_button(
            "Download account CSV",
            data=csv_content.encode("utf-8"),
            file_name=f"{target_account.replace('@', '_at_')}_daily_report.csv",
            mime="text/csv",
        )

    with export_right:
        st.download_button(
            "Download HTML report",
            data=html_report.encode("utf-8"),
            file_name=f"{target_account.replace('@', '_at_')}_daily_report.html",
            mime="text/html",
        )

    with st.expander("Show discovered account emails"):
        st.write(account_options)

    with st.expander("Show raw tables"):
        st.markdown("**Account total row**")
        st.dataframe(account_total_df, use_container_width=True, hide_index=True)
        st.markdown("**Project rows**")
        st.dataframe(projects_df, use_container_width=True, hide_index=True)

    with st.expander("Show HTML report preview"):
        components.html(html_report, height=900, scrolling=True)

    with st.expander("Show raw response preview"):
        st.code(html_payload[:5000], language="html")
