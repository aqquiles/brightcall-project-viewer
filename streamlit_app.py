from __future__ import annotations

import html
import inspect
import json
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

DAILY_COLUMN_LABELS = {
    "userProject": "User/Project",
    "contactsAll": "Contacts All",
    "contactsFailed": "Contacts Failed",
    "contactsAvailable": "Contacts Available",
    "contactsReady": "Contacts Ready",
    "linesLimit": "Lines Limit",
    "callsNow": "Calls Now",
    "callsToday": "Calls Today",
    "newContacts": "New Contacts",
    "pp": "PP",
    "cpp": "CPP",
    "tr": "TR",
    "cptr": "CPTR",
    "qt": "QT",
    "cpqt": "CPQT",
    "sh": "SH",
    "cpsh": "CPSH",
    "limit": "Limit",
    "consumed": "Consumed",
    "hoursNow": "Hours Now",
    "timezone": "Timezone",
    "sN": "sN",
}

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TAG_RE = re.compile(r"<[^>]*>")
ROW_RE = re.compile(r"<tr[^>]*>([\s\S]*?)</tr>", re.IGNORECASE)
CELL_RE = re.compile(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", re.IGNORECASE)

st.set_page_config(page_title="Brightcall Project Viewer", layout="wide")
st.title("Brightcall Project Viewer")
st.caption("Operational project view + reusable daily client report")


# -----------------------------
# Project viewer helpers
# -----------------------------
def get_project_api_key() -> str:
    return str(st.secrets.get("BRIGHTCALL_API_KEY", "")).strip()


def get_daily_stats_api_key() -> str:
    return str(st.secrets.get("BRIGHTCALL_DAILY_STATS_API_KEY", "")).strip()


def get_default_report_account() -> str:
    return str(st.secrets.get("DEFAULT_DAILY_REPORT_ACCOUNT", "")).strip()


def get_tag(project: dict[str, Any]) -> str:
    top_level = str(project.get("aiAgentDialerProjectTag") or "").strip()
    nested = str(((project.get("aiInfoV2") or {}).get("aiAgentDialerProjectTag")) or "").strip()
    return top_level or nested or "(blank)"


def get_transfer_number(project: dict[str, Any]) -> str:
    return str(project.get("aiAgentTransferPhoneNumber") or "").strip() or "(missing)"


def get_status(project: dict[str, Any]) -> str:
    return "Running" if project.get("isPlaying") is True else "Not running"


@st.cache_data(ttl=300)
def fetch_projects(api_key: str) -> list[dict[str, Any]]:
    response = requests.get(PROJECTS_URL, params={"api-key": api_key}, timeout=60)
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("The projects API did not return valid JSON.") from exc

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("projects", "data", "result", "items", "rows"):
            if isinstance(data.get(key), list):
                return data[key]

    raise ValueError("Unexpected projects API response format.")


def normalize_projects(projects: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    for project in projects:
        rows.append(
            {
                "Status": get_status(project),
                "Tag": get_tag(project),
                "Transfer Number": get_transfer_number(project),
                "Project": str(project.get("name") or "(no name)").strip(),
                "Archived": "Yes" if project.get("isArchived") is True else "No",
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    status_order = {"Running": 0, "Not running": 1}
    df["status_sort"] = df["Status"].map(status_order).fillna(99)

    df = (
        df.sort_values(
            by=["status_sort", "Tag", "Transfer Number", "Project"],
            ascending=[True, True, True, True],
            kind="stable",
        )
        .drop(columns=["status_sort"])
        .reset_index(drop=True)
    )
    return df


def apply_project_filters(
    df: pd.DataFrame,
    include_missing: bool,
    selected_statuses: list[str],
    selected_tags: list[str],
    selected_numbers: list[str],
    project_search: str,
    archived_mode: str,
) -> pd.DataFrame:
    filtered = df.copy()

    if not include_missing:
        filtered = filtered[filtered["Transfer Number"] != "(missing)"]

    if selected_statuses:
        filtered = filtered[filtered["Status"].isin(selected_statuses)]

    if selected_tags:
        filtered = filtered[filtered["Tag"].isin(selected_tags)]

    if selected_numbers:
        filtered = filtered[filtered["Transfer Number"].isin(selected_numbers)]

    if archived_mode == "Active only":
        filtered = filtered[filtered["Archived"] == "No"]
    elif archived_mode == "Archived only":
        filtered = filtered[filtered["Archived"] == "Yes"]

    search_value = project_search.strip()
    if search_value:
        filtered = filtered[
            filtered["Project"].str.contains(search_value, case=False, na=False)
        ]

    return filtered.reset_index(drop=True)


def build_project_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Status", "Tag", "Transfer Number", "Projects"])

    summary = (
        df.groupby(["Status", "Tag", "Transfer Number"], dropna=False)
        .size()
        .reset_index(name="Projects")
    )

    status_order = {"Running": 0, "Not running": 1}
    summary["status_sort"] = summary["Status"].map(status_order).fillna(99)
    summary = (
        summary.sort_values(
            by=["status_sort", "Tag", "Transfer Number"],
            ascending=[True, True, True],
            kind="stable",
        )
        .drop(columns=["status_sort"])
        .reset_index(drop=True)
    )
    return summary


def build_running_summary(df: pd.DataFrame) -> pd.DataFrame:
    running_df = df[df["Status"] == "Running"].copy()
    if running_df.empty:
        return pd.DataFrame(columns=["Tag", "Transfer Number", "Running Projects"])

    return (
        running_df.groupby(["Tag", "Transfer Number"], dropna=False)
        .size()
        .reset_index(name="Running Projects")
        .sort_values(by=["Tag", "Transfer Number"], kind="stable")
        .reset_index(drop=True)
    )


def render_project_metrics(df: pd.DataFrame) -> None:
    total_projects = len(df)
    running_count = int((df["Status"] == "Running").sum())
    not_running_count = int((df["Status"] == "Not running").sum())
    missing_count = int((df["Transfer Number"] == "(missing)").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Visible Projects", total_projects)
    c2.metric("Running", running_count)
    c3.metric("Not running", not_running_count)
    c4.metric("Missing Number", missing_count)


# -----------------------------
# Daily report helpers
# -----------------------------
@st.cache_data(ttl=300)
def fetch_daily_projects_html(api_key: str) -> str:
    response = requests.get(DAILY_PROJECTS_URL, params={"apiKey": api_key}, timeout=90)
    response.raise_for_status()
    return response.text


def clean_html_cell(cell_content: str) -> str:
    if not cell_content:
        return ""

    text = TAG_RE.sub("", cell_content)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_table_rows(html_string: str) -> list[list[str]]:
    rows: list[list[str]] = []

    for row_match in ROW_RE.finditer(html_string):
        row_content = row_match.group(1)
        cells = [clean_html_cell(cell.group(1)) for cell in CELL_RE.finditer(row_content)]
        if cells:
            rows.append(cells)

    return rows


def row_to_record(row: list[str]) -> dict[str, str]:
    return {
        column: row[index] if index < len(row) else ""
        for index, column in enumerate(DAILY_COLUMNS)
    }


def extract_email(value: str) -> str:
    match = EMAIL_PATTERN.search(value or "")
    return match.group(0).lower() if match else ""


def is_header_row(row: list[str]) -> bool:
    if not row:
        return False
    first = row[0].strip().lower()
    return "user / project" in first or first == "userproject"


def parse_daily_sections(html_string: str) -> dict[str, dict[str, Any]]:
    all_rows = extract_table_rows(html_string)
    sections: dict[str, dict[str, Any]] = {}

    current_email = ""
    current_account_total: dict[str, str] | None = None
    current_projects: list[dict[str, str]] = []

    for row in all_rows:
        if is_header_row(row):
            continue

        first_cell = row[0] if row else ""
        row_email = extract_email(first_cell)
        row_record = row_to_record(row)

        if row_email:
            if current_email and current_account_total is not None:
                sections[current_email] = {
                    "account_total": current_account_total,
                    "projects": current_projects,
                }

            current_email = row_email
            current_account_total = row_record
            current_projects = []
            continue

        if current_email and len(row) > 1:
            current_projects.append(row_record)

    if current_email and current_account_total is not None:
        sections[current_email] = {
            "account_total": current_account_total,
            "projects": current_projects,
        }

    return sections


def build_account_csv(account_total: dict[str, str] | None, projects: list[dict[str, str]]) -> str:
    lines = [",".join(DAILY_COLUMNS)]

    def escape_csv(value: str) -> str:
        safe_value = str(value or "").replace('"', '""')
        return f'"{safe_value}"'

    if account_total:
        lines.append(",".join(escape_csv(account_total.get(column, "")) for column in DAILY_COLUMNS))

    for project in projects:
        lines.append(",".join(escape_csv(project.get(column, "")) for column in DAILY_COLUMNS))

    return "\n".join(lines)


def display_daily_dataframe(
    records: list[dict[str, str]] | pd.DataFrame,
    *,
    use_container_width: bool = True,
    clipboard_key: str | None = None,
) -> None:
    if isinstance(records, pd.DataFrame):
        df = records.copy()
    else:
        df = pd.DataFrame(records)

    if df.empty:
        st.info("No data available.")
        return

    for column in DAILY_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df = df[DAILY_COLUMNS].rename(columns=DAILY_COLUMN_LABELS)
    if clipboard_key:
        render_clipboard_tools(df, key=clipboard_key)
    st.dataframe(df, use_container_width=use_container_width, hide_index=True)


def _render_html_table(columns: list[str], rows: list[dict[str, str]], account_row: bool = False) -> str:
    header_html = "".join(f"<th>{html.escape(DAILY_COLUMN_LABELS.get(column, column))}</th>" for column in columns)
    body_rows: list[str] = []

    row_class = " class=\"account-row\"" if account_row else ""
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns)
        body_rows.append(f"<tr{row_class}>{cells}</tr>")

    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def build_account_report_html(target_account: str, account_total: dict[str, str] | None, projects: list[dict[str, str]]) -> str:
    account_block = (
        _render_html_table(DAILY_COLUMNS, [account_total], account_row=True)
        if account_total
        else "<p class='no-data'>Selected account was not found in the response.</p>"
    )
    project_block = (
        _render_html_table(DAILY_COLUMNS, projects)
        if projects
        else "<p class='no-data'>No project rows were found for this account.</p>"
    )

    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
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
        "key": "daily_report_auto_refresh",
    }

    if "label_visibility" in inspect.signature(st.selectbox).parameters:
        selectbox_kwargs["label_visibility"] = "collapsed"
        return st.selectbox(**selectbox_kwargs)

    st.markdown("&nbsp;", unsafe_allow_html=True)
    selectbox_kwargs["label"] = " "
    return st.selectbox(**selectbox_kwargs)



def emit_clipboard_copy(text: str, *, key: str) -> None:
    return


def render_clipboard_tools(df: pd.DataFrame, *, key: str) -> None:
    return


# -----------------------------
# Rendering
# -----------------------------
def render_project_viewer() -> None:
    st.subheader("Project Viewer")

    project_api_key = get_project_api_key()

    with st.sidebar:
        st.header("Project Viewer Settings")

        manual_key = st.text_input(
            "Projects API Key",
            value="",
            type="password",
            help="Optional. If blank, the app uses BRIGHTCALL_API_KEY from Streamlit secrets.",
        )
        include_missing = st.checkbox("Include missing transfer number", value=True)
        refresh_projects = st.button("Refresh projects data")

    if manual_key:
        project_api_key = manual_key.strip()

    if not project_api_key:
        st.warning("Add BRIGHTCALL_API_KEY to Streamlit secrets or paste a projects API key in the sidebar.")
        return

    if refresh_projects:
        fetch_projects.clear()

    try:
        projects = fetch_projects(project_api_key)
        df = normalize_projects(projects)
    except requests.HTTPError as exc:
        st.error(f"HTTP error while calling the projects endpoint: {exc}")
        return
    except requests.RequestException as exc:
        st.error(f"Request error while calling the projects endpoint: {exc}")
        return
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Unexpected error while loading projects: {exc}")
        return

    if df.empty:
        st.info("The projects endpoint returned no projects.")
        return

    with st.sidebar:
        st.subheader("Project Filters")
        all_statuses = df["Status"].dropna().unique().tolist()
        all_tags = sorted(df["Tag"].dropna().unique().tolist())
        all_numbers = sorted(df["Transfer Number"].dropna().unique().tolist())

        selected_statuses = st.multiselect("Status", options=all_statuses, default=all_statuses)
        selected_tags = st.multiselect("Tag", options=all_tags, default=all_tags)
        selected_numbers = st.multiselect("Transfer number", options=all_numbers, default=all_numbers)
        project_search = st.text_input("Project search", value="", help="Search by project name.")
        archived_mode = st.radio(
            "Archived",
            options=["All", "Active only", "Archived only"],
            horizontal=False,
        )

    filtered_df = apply_project_filters(
        df=df,
        include_missing=include_missing,
        selected_statuses=selected_statuses,
        selected_tags=selected_tags,
        selected_numbers=selected_numbers,
        project_search=project_search,
        archived_mode=archived_mode,
    )

    render_project_metrics(filtered_df)

    running_tab, summary_tab, all_projects_tab = st.tabs(
        ["Running projects", "Grouped summary", "All projects"]
    )

    with running_tab:
        running_df = filtered_df[filtered_df["Status"] == "Running"].reset_index(drop=True)
        running_summary_df = build_running_summary(filtered_df)

        st.caption("Use this view to identify the exact live projects that may need changes.")

        if running_df.empty:
            st.info("No running projects match the current filters.")
        else:
            left, right = st.columns([1, 2])

            with left:
                st.markdown("**Running by tag and transfer number**")
                render_clipboard_tools(running_summary_df, key="running_summary")
                st.dataframe(running_summary_df, use_container_width=True, hide_index=True)

            with right:
                st.markdown("**Exact running projects**")
                exact_running_df = running_df[["Tag", "Transfer Number", "Project", "Archived"]].copy()
                render_clipboard_tools(exact_running_df, key="exact_running_projects")
                st.dataframe(
                    exact_running_df,
                    use_container_width=True,
                    hide_index=True,
                )

            running_csv = running_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download running projects CSV",
                data=running_csv,
                file_name="brightcall_running_projects.csv",
                mime="text/csv",
            )

    with summary_tab:
        summary_df = build_project_summary(filtered_df)
        st.caption("Grouped by Status → Tag → Transfer Number")
        render_clipboard_tools(summary_df, key="grouped_summary")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    with all_projects_tab:
        st.caption("Sorted by Running first, then Tag, Transfer Number, and Project.")
        render_clipboard_tools(filtered_df, key="all_projects")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

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

    if "daily_report_manual_refresh_nonce" not in st.session_state:
        st.session_state["daily_report_manual_refresh_nonce"] = 0

    toolbar_left, toolbar_mid, toolbar_right = st.columns([1.15, 1.2, 2.65])
    with toolbar_left:
        refresh_daily = st.button("Refresh daily report data", use_container_width=True)
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
        st.caption("Daily stats API key is read from Streamlit secrets.")

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
        st.session_state["daily_report_manual_refresh_nonce"] += 1
        fetch_daily_projects_html.clear()

    if auto_refresh_seconds > 0 and not supports_fragment_auto_refresh():
        st.caption("Your Streamlit version does not support fragment auto-refresh, so timed refresh may still reload the page.")

    run_every_value = auto_refresh_seconds if auto_refresh_seconds > 0 and supports_fragment_auto_refresh() else None

    def _render_daily_report_content() -> None:
        if auto_refresh_seconds > 0:
            fetch_daily_projects_html.clear()

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
        default_index = account_options.index(default_account.lower()) if default_account and default_account.lower() in account_options else 0

        selector_col, input_col = st.columns([1, 1])
        with selector_col:
            selected_account = st.selectbox(
                "Select account email",
                options=account_options,
                index=default_index,
                key="daily_report_selected_account",
            )
        with input_col:
            manual_account = st.text_input(
                "Or type account email",
                value=default_account,
                help="Use this when you want to jump directly to a specific client email.",
                key="daily_report_manual_account",
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
        html_report = build_account_report_html(target_account, account_total, projects)

        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
        m1.metric("Projects", len(projects))
        m2.metric("Lines Running", (account_total or {}).get("callsNow", ""))
        m3.metric("Calls Today", (account_total or {}).get("callsToday", ""))
        m4.metric("TR", (account_total or {}).get("tr", ""))
        m5.metric("QT", (account_total or {}).get("qt", ""))
        m6.metric("CPTR", (account_total or {}).get("cptr", ""))
        m7.metric("CPQT", (account_total or {}).get("cpqt", ""))

        st.markdown("### Account Total")
        if account_total:
            display_daily_dataframe(account_total_df, clipboard_key="daily_account_total")
        else:
            st.info("No account total row was found for this account.")

        st.markdown(f"### Projects ({len(projects)})")
        if projects:
            display_daily_dataframe(projects_df, clipboard_key="daily_projects")
        else:
            st.info("No project rows were found for this account.")

        json_content = json.dumps(
            {
                "account": target_account,
                "account_total": account_total,
                "projects": projects,
            },
            indent=2,
            ensure_ascii=False,
        )

        st.markdown("### Report exports")
        export_left, export_mid, export_right = st.columns(3)
        with export_left:
            st.download_button(
                "Download account CSV",
                data=csv_content.encode("utf-8"),
                file_name=f"{target_account.replace('@', '_at_')}_daily_report.csv",
                mime="text/csv",
            )
        with export_mid:
            st.download_button(
                "Download HTML report",
                data=html_report.encode("utf-8"),
                file_name=f"{target_account.replace('@', '_at_')}_daily_report.html",
                mime="text/html",
            )
        with export_right:
            st.download_button(
                "Download JSON",
                data=json_content.encode("utf-8"),
                file_name=f"{target_account.replace('@', '_at_')}_daily_report.json",
                mime="application/json",
            )

        with st.expander("Show discovered account emails"):
            st.write(account_options)

        with st.expander("Show raw response preview"):
            st.code(html_payload[:5000], language="html")

    if run_every_value is not None:
        @st.fragment(run_every=run_every_value)
        def _auto_refreshing_fragment() -> None:
            _render_daily_report_content()

        _auto_refreshing_fragment()
    else:
        _render_daily_report_content()


def main() -> None:
    viewer_tab, daily_report_tab = st.tabs(["Project viewer", "Daily client report"])

    with viewer_tab:
        render_project_viewer()

    with daily_report_tab:
        render_daily_client_report()


if __name__ == "__main__":
    main()
