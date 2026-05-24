"""Streamlit dashboard for Zillow valuations."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).parent
SNAPSHOTS_FILE = ROOT / "data" / "snapshots.csv"

st.set_page_config(page_title="Home Valuations", page_icon="🏠", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] { font-size: 2.0rem; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; color: #6b7280; }
    .block-container { padding-top: 2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🏠 Home Valuations")


@st.cache_data(ttl=300)
def load_snapshots() -> pd.DataFrame:
    if not SNAPSHOTS_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(SNAPSHOTS_FILE, parse_dates=["fetched_at"])
    return df.sort_values("fetched_at")


def fmt_dollars(v) -> str:
    return f"${v:,.0f}" if pd.notna(v) else "—"


def fmt_int(v) -> str:
    return f"{int(v):,}" if pd.notna(v) else "—"


df = load_snapshots()

if df.empty:
    st.info(
        "No snapshots yet. Wait for the scheduled GitHub Action to commit "
        "`data/snapshots.csv`, or run `python fetch_data.py` locally."
    )
    st.stop()

group_key = "label" if "label" in df.columns else "zpid"
latest = df.sort_values("fetched_at").groupby(group_key).tail(1).reset_index(drop=True)

last_update = df["fetched_at"].max()
st.caption(f"Last refreshed: {last_update.strftime('%b %d, %Y')} · {len(latest)} properties tracked")

# Per-property cards
for _, prop in latest.iterrows():
    history = df[df[group_key] == prop[group_key]].sort_values("fetched_at")
    zest = prop.get("zestimate")
    rent = prop.get("rent_zestimate")
    sqft = prop.get("living_area")
    sold = prop.get("last_sold_price")

    # Delta vs previous snapshot
    delta_str = None
    if len(history) >= 2 and pd.notna(zest):
        prev = history.iloc[-2].get("zestimate")
        if pd.notna(prev) and prev != 0:
            change = zest - prev
            pct = change / prev * 100
            delta_str = f"{change:+,.0f} ({pct:+.2f}%)"

    with st.container(border=True):
        st.markdown(f"### {prop[group_key]}")
        addr = prop.get("address")
        if pd.notna(addr):
            st.caption(addr)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Zestimate", fmt_dollars(zest), delta=delta_str)
        c2.metric("Rent Zestimate", f"{fmt_dollars(rent)}/mo" if pd.notna(rent) else "—")

        if pd.notna(zest) and pd.notna(rent):
            yield_pct = rent * 12 / zest * 100
            c3.metric("Gross yield", f"{yield_pct:.2f}%")
        else:
            c3.metric("Gross yield", "—")

        if pd.notna(zest) and pd.notna(sold) and sold > 0:
            appreciation = (zest - sold) / sold * 100
            c4.metric("Vs last sold", f"{appreciation:+.1f}%", delta=fmt_dollars(zest - sold))
        else:
            c4.metric("Vs last sold", "—")

        c5, c6, c7, c8 = st.columns(4)
        beds = prop.get("bedrooms")
        baths = prop.get("bathrooms")
        c5.metric("Bedrooms", fmt_int(beds))
        c6.metric("Bathrooms", f"{baths:g}" if pd.notna(baths) else "—")
        c7.metric("Living area", f"{fmt_int(sqft)} sqft" if pd.notna(sqft) else "—")
        if pd.notna(zest) and pd.notna(sqft) and sqft > 0:
            c8.metric("$ / sqft", fmt_dollars(zest / sqft))
        else:
            c8.metric("$ / sqft", "—")

st.divider()

# History chart
st.subheader("Valuation history")

hist = df.dropna(subset=["zestimate"]).copy()
fig = px.line(
    hist,
    x="fetched_at",
    y="zestimate",
    color=group_key,
    markers=True,
    labels={"fetched_at": "", "zestimate": "Zestimate"},
)
fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
fig.update_layout(
    height=420,
    legend_title_text="",
    hovermode="x unified",
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor="rgba(0,0,0,0)",
)
fig.update_xaxes(tickformat="%b %d, %Y", showgrid=False)
fig.update_yaxes(tickformat="$,.0f", gridcolor="rgba(128,128,128,0.15)")

# If history is sparse, expand y range so a single point doesn't look like a flat horizon
if hist.groupby(group_key).size().max() <= 1:
    lo, hi = hist["zestimate"].min(), hist["zestimate"].max()
    pad = max(50_000, (hi - lo) * 0.5) if hi > lo else 50_000
    fig.update_yaxes(range=[lo - pad, hi + pad])

st.plotly_chart(fig, use_container_width=True)

with st.expander("Raw snapshots"):
    st.dataframe(
        df.sort_values("fetched_at", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
