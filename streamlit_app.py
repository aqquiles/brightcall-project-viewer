from __future__ import annotations

from typing import Any

import pandas as pd
import requests
import streamlit as st

BASE_URL = "https://api.dialer.brightcall.ai/api/v1/projects"


st.set_page_config(page_title="Brightcall Project Viewer", layout="wide")
st.title("Brightcall Project Viewer")
st.caption("Operational view for Brightcall projects")


def get_api_key() -> str:
    return st.secrets.get("BRIGHTCALL_API_KEY", "")


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
    response = requests.get(BASE_URL, params={"api-key": api_key}, timeout=60)
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("The API did not return valid JSON.") from exc

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if isinstance(data.get("projects"), list):
            return data["projects"]
        if isinstance(data.get("data"), list):
            return data["data"]

    raise ValueError("Unexpected API response format. Expected a list, projects, or data.")


def normalize_projects(projects: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    for project in projects:
        rows.append(
            {
                "Status": get_status(project),
                "Tag": get_tag(project),
                "Transfer Number": get_transfer_number(project),
                "Project": str(project.get("name") or "(no name)").strip(),
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


def apply_filters(
    df: pd.DataFrame,
    include_missing: bool,
    selected_statuses: list[str],
    selected_tags: list[str],
    selected_numbers: list[str],
    project_search: str,
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

    search_value = project_search.strip()
    if search_value:
        filtered = filtered[
            filtered["Project"].str.contains(search_value, case=False, na=False)
        ]

    return filtered.reset_index(drop=True)


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
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

    running_summary = (
        running_df.groupby(["Tag", "Transfer Number"], dropna=False)
        .size()
        .reset_index(name="Running Projects")
        .sort_values(by=["Tag", "Transfer Number"], kind="stable")
        .reset_index(drop=True)
    )
    return running_summary


def render_metrics(df: pd.DataFrame) -> None:
    total_projects = len(df)
    running_count = int((df["Status"] == "Running").sum())
    not_running_count = int((df["Status"] == "Not running").sum())
    missing_count = int((df["Transfer Number"] == "(missing)").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Visible Projects", total_projects)
    c2.metric("Running", running_count)
    c3.metric("Not Running", not_running_count)
    c4.metric("Missing Number", missing_count)


def render_running_tab(filtered_df: pd.DataFrame) -> None:
    running_df = filtered_df[filtered_df["Status"] == "Running"].reset_index(drop=True)
    running_summary_df = build_running_summary(filtered_df)

    st.subheader("Running Projects")
    st.caption("Use this view to identify the exact live projects that may need changes.")

    if running_df.empty:
        st.info("No running projects match the current filters.")
        return

    left, right = st.columns([1, 2])

    with left:
        st.markdown("**Running by tag and transfer number**")
        st.dataframe(
            running_summary_df,
            use_container_width=True,
            hide_index=True,
        )

    with right:
        st.markdown("**Exact running projects**")
        st.dataframe(
            running_df[["Tag", "Transfer Number", "Project"]],
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


def render_summary_tab(filtered_df: pd.DataFrame) -> None:
    summary_df = build_summary(filtered_df)
    st.subheader("Grouped Summary")
    st.caption("Grouped by Status → Tag → Transfer Number")

    st.dataframe(summary_df, use_container_width=True, hide_index=True)


def render_all_projects_tab(filtered_df: pd.DataFrame) -> None:
    st.subheader("All Visible Projects")
    st.caption("Sorted by Running first, then Tag, Transfer Number, and Project.")

    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    csv_data = filtered_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download visible projects CSV",
        data=csv_data,
        file_name="brightcall_projects.csv",
        mime="text/csv",
    )


def main() -> None:
    api_key = get_api_key()

    with st.sidebar:
        st.header("Settings")

        manual_key = st.text_input(
            "API Key",
            value="",
            type="password",
            help="Optional. If blank, the app uses BRIGHTCALL_API_KEY from Streamlit secrets.",
        )
        include_missing = st.checkbox("Include missing transfer number", value=True)
        refresh = st.button("Refresh data")

    if manual_key:
        api_key = manual_key.strip()

    if not api_key:
        st.warning("Add BRIGHTCALL_API_KEY to Streamlit secrets or paste an API key in the sidebar.")
        st.stop()

    if refresh:
        fetch_projects.clear()

    try:
        projects = fetch_projects(api_key)
        df = normalize_projects(projects)
    except requests.HTTPError as exc:
        st.error(f"HTTP error while calling Brightcall: {exc}")
        st.stop()
    except requests.RequestException as exc:
        st.error(f"Request error while calling Brightcall: {exc}")
        st.stop()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
        st.stop()

    if df.empty:
        st.info("The API returned no projects.")
        st.stop()

    with st.sidebar:
        st.subheader("Filters")

        all_statuses = df["Status"].dropna().unique().tolist()
        all_tags = sorted(df["Tag"].dropna().unique().tolist())
        all_numbers = sorted(df["Transfer Number"].dropna().unique().tolist())

        selected_statuses = st.multiselect("Status", options=all_statuses, default=all_statuses)
        selected_tags = st.multiselect("Tag", options=all_tags, default=all_tags)
        selected_numbers = st.multiselect(
            "Transfer number",
            options=all_numbers,
            default=all_numbers,
        )
        project_search = st.text_input(
            "Project search",
            value="",
            help="Search by project name.",
        )

    filtered_df = apply_filters(
        df=df,
        include_missing=include_missing,
        selected_statuses=selected_statuses,
        selected_tags=selected_tags,
        selected_numbers=selected_numbers,
        project_search=project_search,
    )

    render_metrics(filtered_df)

    running_tab, summary_tab, all_projects_tab = st.tabs(
        ["Running projects", "Grouped summary", "All projects"]
    )

    with running_tab:
        render_running_tab(filtered_df)

    with summary_tab:
        render_summary_tab(filtered_df)

    with all_projects_tab:
        render_all_projects_tab(filtered_df)


if __name__ == "__main__":
    main()
