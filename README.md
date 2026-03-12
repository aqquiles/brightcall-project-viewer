# Brightcall Project Viewer

Small Streamlit app to inspect Brightcall projects by:
- Status
- Tag
- Transfer Number
- Project name

## What the app shows

The app calls the Brightcall projects endpoint and builds a table with:
- **Status**: `Running` when `isPlaying = true`, otherwise `Not running`
- **Tag**: `aiAgentDialerProjectTag`, or `aiInfoV2.aiAgentDialerProjectTag`, or `(blank)`
- **Transfer Number**: `aiAgentTransferPhoneNumber`, or `(missing)`
- **Project**: project name, or `(no name)`

It also shows:
- summary metrics
- grouped summary table
- detailed project table
- CSV download
- sidebar filters

## Files

- `streamlit_app.py`
- `requirements.txt`
- `.gitignore`
- `.streamlit/secrets.toml.example`

## Setup

Create a virtual environment if you want:

```bash
python -m venv .venv
```

Activate it:

### Windows (PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Secrets

Create this file locally:

```text
.streamlit/secrets.toml
```

Put your API key inside it:

```toml
BRIGHTCALL_API_KEY = "your_real_api_key_here"
```

Do **not** commit that file. The `.gitignore` already excludes it.

## Run locally

```bash
streamlit run streamlit_app.py
```

## Notes

- The app caches API results for 5 minutes.
- You can override the API key manually in the sidebar.
- You can include or exclude missing transfer numbers.
- You can filter by status, tag, and transfer number.
