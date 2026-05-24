"""Streamlit dashboard for Zillow valuations.

Reads data/snapshots.csv produced by fetch_data.py and renders:
  - latest valuation per address
  - historical chart
  - property details
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).parent
SNAPSHOTS_FILE = ROOT / "data" / "snapshots.csv"

st.set_page_config(page_title="Home Valuations", layout="wide")
st.title("🏠 Home Valuations")


@st.cache_data(ttl=300)
def load_snapshots() -> pd.DataFrame:
    if not SNAPSHOTS_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(SNAPSHOTS_FILE, parse_dates=["fetched_at"])
    return df.sort_values("fetched_at")


df = load_snapshots()

if df.empty:
    st.info(
        "No snapshots yet. Run `python fetch_data.py` locally (with `RAPIDAPI_KEY` set) "
        "or wait for the scheduled GitHub Action to commit `data/snapshots.csv`."
    )
    st.stop()

group_key = "label" if "label" in df.columns else "zpid"
latest = df.sort_values("fetched_at").groupby(group_key).tail(1).reset_index(drop=True)

st.subheader("Latest valuations")
cols = st.columns(min(len(latest), 4) or 1)
for i, row in latest.iterrows():
    with cols[i % len(cols)]:
        zest = row.get("zestimate")
        st.metric(
            label=row[group_key],
            value=f"${zest:,.0f}" if pd.notna(zest) else "—",
            help=row.get("address"),
        )

st.divider()

st.subheader("History")
fig = px.line(
    df.dropna(subset=["zestimate"]),
    x="fetched_at",
    y="zestimate",
    color=group_key,
    markers=True,
    labels={"fetched_at": "Date", "zestimate": "Zestimate ($)"},
)
fig.update_layout(height=450, legend_title_text="")
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Property details")
detail_cols = [
    "label",
    "address",
    "bedrooms",
    "bathrooms",
    "living_area",
    "year_built",
    "home_type",
    "last_sold_price",
    "last_sold_date",
    "rent_zestimate",
]
st.dataframe(
    latest[[c for c in detail_cols if c in latest.columns]],
    use_container_width=True,
    hide_index=True,
)

with st.expander("Raw snapshots"):
    st.dataframe(df, use_container_width=True, hide_index=True)
