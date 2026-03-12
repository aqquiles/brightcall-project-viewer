import requests
import pandas as pd
import streamlit as st

BASE_URL = "https://api.dialer.brightcall.ai/api/v1/projects"


st.set_page_config(
    page_title="Brightcall Project Viewer",
    layout="wide",
)

st.title("Brightcall Project Viewer")
st.caption("Grouped by Status → Tag → Transfer Number → Project")


def get_api_key() -> str:
    secret_key = st.secrets.get("BRIGHTCALL_API_KEY", "")
    return secret_key


def get_tag(project: dict) -> str:
    top_level = str(project.get("aiAgentDialerProjectTag") or "").strip()
    nested = str(
        ((project.get("aiInfoV2") or {}).get("aiAgentDialerProjectTag")) or ""
    ).strip()
    return top_level or nested or "(blank)"


def get_transfer_number(project: dict) -> str:
    return str(project.get("aiAgentTransferPhoneNumber") or "").strip() or "(missing)"


def get_status(project: dict) -> str:
    return "Running" if project.get("isPlaying") is True else "Not running"


@st.cache_data(ttl=300)
def fetch_projects(api_key: str):
    response = requests.get(
        BASE_URL,
        params={"api-key": api_key},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if isinstance(data.get("projects"), list):
            return data["projects"]
        if isinstance(data.get("data"), list):
            return data["data"]

    raise ValueError("Unexpected API response format.")


def normalize_projects(projects: list[dict]) -> pd.DataFrame:
    rows = []

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

    status_order = {"Running": 0, "Not running": 1}
    df["status_sort"] = df["Status"].map(status_order).fillna(99)

    df = df.sort_values(
        by=["status_sort", "Tag", "Transfer Number", "Project"],
        ascending=[True, True, True, True],
        kind="stable",
    ).drop(columns=["status_sort"])

    return df.reset_index(drop=True)


api_key = get_api_key()

with st.sidebar:
    st.header("Settings")

    manual_key = st.text_input(
        "API Key",
        value="",
        type="password",
        help="Optional. If blank, the app will try BRIGHTCALL_API_KEY from Streamlit secrets.",
    )

    include_missing = st.checkbox("Include missing transfer number", value=True)

    show_summary_only = st.checkbox("Show summary only", value=False)

    refresh = st.button("Refresh data")

if manual_key:
    api_key = manual_key

if not api_key:
    st.warning(
        "No API key found. Add BRIGHTCALL_API_KEY to Streamlit secrets or paste it in the sidebar."
    )
    st.stop()

if refresh:
    fetch_projects.clear()

try:
    projects = fetch_projects(api_key)
    df = normalize_projects(projects)

    if not include_missing:
        df = df[df["Transfer Number"] != "(missing)"].copy()

    running_count = int((df["Status"] == "Running").sum())
    not_running_count = int((df["Status"] == "Not running").sum())
    missing_count = int((df["Transfer Number"] == "(missing)").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Projects", len(df))
    c2.metric("Running", running_count)
    c3.metric("Not running", not_running_count)
    c4.metric("Missing Number", missing_count)

    summary_df = (
        df.groupby(["Status", "Tag", "Transfer Number"], dropna=False)
        .size()
        .reset_index(name="Projects")
        .sort_values(by=["Status", "Tag", "Transfer Number"], kind="stable")
    )

    st.subheader("Summary")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    if not show_summary_only:
        st.subheader("Projects")
        st.dataframe(df, use_container_width=True, hide_index=True)

        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_data,
            file_name="brightcall_projects.csv",
            mime="text/csv",
        )

except requests.HTTPError as e:
    st.error(f"HTTP error: {e}")
except requests.RequestException as e:
    st.error(f"Request error: {e}")
except Exception as e:
    st.error(f"Unexpected error: {e}")