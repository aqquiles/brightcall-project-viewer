from __future__ import annotations

from typing import Any

import pandas as pd
import requests
import streamlit as st

BASE_URL = "https://api.dialer.brightcall.ai/api/v1/projects"


st.set_page_config(page_title="Brightcall Project Viewer", layout="wide")
st.title("Brightcall Project Viewer")
st.caption("Grouped by Status → Tag → Transfer Number → Project")


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
        all_statuses = df["Status"].dropna().unique().tolist()
        all_tags = sorted(df["Tag"].dropna().unique().tolist())
        all_numbers = sorted(df["Transfer Number"].dropna().unique().tolist())

        selected_statuses = st.multiselect("Filter by status", options=all_statuses, default=all_statuses)
        selected_tags = st.multiselect("Filter by tag", options=all_tags, default=all_tags)
        selected_numbers = st.multiselect(
            "Filter by transfer number",
            options=all_numbers,
            default=all_numbers,
        )

    filtered_df = apply_filters(
        df=df,
        include_missing=include_missing,
        selected_statuses=selected_statuses,
        selected_tags=selected_tags,
        selected_numbers=selected_numbers,
    )

    total_projects = len(filtered_df)
    running_count = int((filtered_df["Status"] == "Running").sum())
    not_running_count = int((filtered_df["Status"] == "Not running").sum())
    missing_count = int((filtered_df["Transfer Number"] == "(missing)").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Projects", total_projects)
    c2.metric("Running", running_count)
    c3.metric("Not running", not_running_count)
    c4.metric("Missing Number", missing_count)

    summary_df = build_summary(filtered_df)

    st.subheader("Summary")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.subheader("Projects")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    csv_data = filtered_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV",
        data=csv_data,
        file_name="brightcall_projects.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
