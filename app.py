"""Streamlit dashboard: rental portfolio investment analysis."""

import datetime as dt
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).parent
SNAPSHOTS_FILE = ROOT / "data" / "snapshots.csv"
PORTFOLIO_FILE = ROOT / "portfolio.csv"

st.set_page_config(page_title="H-Square Ventures LLC", page_icon="🏠", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 600; }
    [data-testid="stMetricLabel"] { font-size: 0.78rem; color: #6b7280; }
    .block-container { padding-top: 1.5rem; padding-bottom: 4rem; }
    h1 { font-weight: 700; letter-spacing: -0.02em; }
    h3 { margin-top: 0.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🏠 H-Square Ventures LLC")


def check_password():
    if st.session_state.get("authenticated"):
        return
    expected = st.secrets.get("APP_PASSWORD")
    if not expected:
        st.error("APP_PASSWORD secret is not set. Configure it in the app's secrets.")
        st.stop()
    pw = st.text_input("Password", type="password")
    if pw == expected:
        st.session_state.authenticated = True
        st.rerun()
    elif pw:
        st.error("Wrong password.")
    st.stop()


check_password()


@st.cache_data(ttl=300)
def load_data():
    if not SNAPSHOTS_FILE.exists() or not PORTFOLIO_FILE.exists():
        return None, None
    snaps = pd.read_csv(SNAPSHOTS_FILE, parse_dates=["fetched_at"])
    portfolio = pd.read_csv(PORTFOLIO_FILE, parse_dates=["purchase_date"])
    return snaps, portfolio


def fmt_dollars(v, sign=False):
    if pd.isna(v):
        return "—"
    s = f"${abs(v):,.0f}"
    return ("+" if v >= 0 else "−") + s if sign else s


def fmt_pct(v, sign=True):
    if pd.isna(v):
        return "—"
    return f"{v:+.2f}%" if sign else f"{v:.2f}%"


def years_held(purchase_date):
    if pd.isna(purchase_date):
        return None
    return (dt.datetime.utcnow() - purchase_date).days / 365.25


def annualized_return(current, purchase, years):
    if not all([current, purchase, years]) or purchase <= 0 or years <= 0:
        return None
    return ((current / purchase) ** (1 / years) - 1) * 100


snaps, portfolio = load_data()
if snaps is None or portfolio is None or snaps.empty:
    st.info("No data yet. Wait for the scheduled GitHub Action to populate `data/snapshots.csv`.")
    st.stop()

latest_snap = snaps.sort_values("fetched_at").groupby("zpid").tail(1)
latest = portfolio.merge(latest_snap, on="zpid", how="left", suffixes=("", "_snap"))

# Portfolio aggregates
total_value = latest["zestimate"].sum()
total_basis = latest["purchase_price"].sum()
total_appreciation = total_value - total_basis
total_appreciation_pct = (total_appreciation / total_basis * 100) if total_basis else 0
total_monthly_rent = latest["actual_rent"].sum()
total_annual_rent = total_monthly_rent * 12
blended_yield = (total_annual_rent / total_value * 100) if total_value else 0

# Weighted-average annualized return (by cost basis)
years_arr = latest["purchase_date"].apply(years_held)
basis_years = (years_arr * latest["purchase_price"]).sum()
avg_years = basis_years / total_basis if total_basis else None
portfolio_annualized = annualized_return(total_value, total_basis, avg_years) if avg_years else None

st.caption(
    f"Last refreshed: {snaps['fetched_at'].max().strftime('%b %d, %Y')}  ·  "
    f"{len(latest)} properties tracked"
)

# --- Portfolio summary ---
with st.container(border=True):
    st.markdown("#### Portfolio summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Total value",
        fmt_dollars(total_value),
        help="Sum of current Zestimates across all properties.",
    )
    c2.metric(
        "Cost basis",
        fmt_dollars(total_basis),
        help="Sum of purchase prices across all properties.",
    )
    c3.metric(
        "Appreciation",
        fmt_dollars(total_appreciation, sign=True),
        delta=fmt_pct(total_appreciation_pct),
        help="Total value − Cost basis. % = Appreciation ÷ Cost basis × 100.",
    )
    c4.metric(
        "Annualized return",
        fmt_pct(portfolio_annualized) if portfolio_annualized is not None else "—",
        help=(
            "Compound annual growth rate (CAGR): "
            "((Total value ÷ Cost basis)^(1 ÷ avg years held) − 1) × 100.  "
            f"Avg hold weighted by basis: {avg_years:.1f} years."
        ) if avg_years else "CAGR weighted by cost basis.",
    )

    c5, c6, c7, c8 = st.columns(4)
    c5.metric(
        "Monthly rent",
        fmt_dollars(total_monthly_rent),
        help="Sum of actual monthly rents (from portfolio.csv) across all properties.",
    )
    c6.metric(
        "Annual rent",
        fmt_dollars(total_annual_rent),
        help="Monthly rent × 12.",
    )
    c7.metric(
        "Blended gross yield",
        fmt_pct(blended_yield, sign=False),
        help="Annual rent ÷ Total value × 100. Pre-expense (no mortgage, taxes, or maintenance subtracted).",
    )
    c8.metric("Properties", str(len(latest)))

st.divider()

# --- Per-property cards ---
st.markdown("#### Properties")
for _, p in latest.iterrows():
    yrs = years_held(p["purchase_date"])
    cur = p.get("zestimate")
    cost = p.get("purchase_price")
    appreciation = (cur - cost) if pd.notna(cur) and pd.notna(cost) else None
    appreciation_pct = (appreciation / cost * 100) if appreciation is not None and cost else None
    annual_ret = annualized_return(cur, cost, yrs)
    annual_income = p["actual_rent"] * 12 if pd.notna(p.get("actual_rent")) else None
    gross_yield = (annual_income / cur * 100) if annual_income and pd.notna(cur) and cur else None
    market_rent = p.get("rent_zestimate")
    rent_vs_market = None
    if pd.notna(p.get("actual_rent")) and pd.notna(market_rent) and market_rent:
        rent_vs_market = (p["actual_rent"] - market_rent) / market_rent * 100

    with st.container(border=True):
        header_cols = st.columns([3, 1])
        with header_cols[0]:
            st.markdown(f"### {p['label']}")
            addr = p.get("address")
            if pd.notna(addr):
                st.caption(addr)
        with header_cols[1]:
            if pd.notna(p["purchase_date"]):
                st.caption(
                    f"Bought {p['purchase_date'].strftime('%b %Y')}  ·  "
                    f"Held {yrs:.1f} yrs" if yrs else ""
                )

        # Financial row
        f1, f2, f3, f4 = st.columns(4)
        f1.metric(
            "Current value",
            fmt_dollars(cur),
            help="Latest Zillow Zestimate from data/snapshots.csv.",
        )
        f2.metric(
            "Purchase price",
            fmt_dollars(cost),
            help="From portfolio.csv. Hover the caption above for purchase date and hold time.",
        )
        f3.metric(
            "Appreciation",
            fmt_dollars(appreciation, sign=True) if appreciation is not None else "—",
            delta=fmt_pct(appreciation_pct) if appreciation_pct is not None else None,
            help="Current value − Purchase price. % = Appreciation ÷ Purchase price × 100.",
        )
        f4.metric(
            "Annualized return",
            fmt_pct(annual_ret) if annual_ret is not None else "—",
            help=(
                "Compound annual growth rate (CAGR): "
                "((Current value ÷ Purchase price)^(1 ÷ years held) − 1) × 100."
                + (f"  Years held: {yrs:.2f}." if yrs else "")
            ),
        )

        # Rental row
        r1, r2, r3, r4 = st.columns(4)
        r1.metric(
            "Actual rent",
            f"{fmt_dollars(p['actual_rent'])}/mo" if pd.notna(p.get("actual_rent")) else "—",
            help="Current monthly rent collected (from portfolio.csv).",
        )
        r2.metric(
            "Market rent",
            f"{fmt_dollars(market_rent)}/mo" if pd.notna(market_rent) else "—",
            delta=f"{rent_vs_market:+.1f}% vs market" if rent_vs_market is not None else None,
            help=(
                "Zillow's Rent Zestimate (estimated market rent). "
                "Delta = (Actual rent − Market rent) ÷ Market rent × 100. "
                "Negative means you're charging below market."
            ),
        )
        r3.metric(
            "Annual income",
            fmt_dollars(annual_income) if annual_income else "—",
            help="Actual monthly rent × 12. Gross income, before expenses or vacancy.",
        )
        r4.metric(
            "Gross yield",
            fmt_pct(gross_yield, sign=False) if gross_yield is not None else "—",
            help="Annual income ÷ Current value × 100. Pre-expense yield.",
        )

st.divider()

# --- Time series ---
st.subheader("Portfolio value over time")
# Collapse to one snapshot per property per day (latest of the day)
chart_df = (
    snaps.dropna(subset=["zestimate"])
    .assign(date=lambda d: d["fetched_at"].dt.normalize())
    .sort_values("fetched_at")
    .groupby(["date", "zpid"], as_index=False)
    .tail(1)
    .drop(columns=["label"], errors="ignore")
    .merge(portfolio[["zpid", "label"]], on="zpid", how="left")
)
chart_df["label"] = chart_df["label"].fillna(chart_df["zpid"].astype(str))

# Forward-fill missing property values per date so the Total line is continuous
pivot = (
    chart_df.pivot_table(index="date", columns="label", values="zestimate", aggfunc="last")
    .sort_index()
    .ffill()
)
totals = pivot.sum(axis=1, min_count=len(portfolio)).dropna()

fig = px.line(
    chart_df,
    x="date",
    y="zestimate",
    color="label",
    markers=True,
    labels={"date": "", "zestimate": "Value"},
)
fig.add_scatter(
    x=totals.index,
    y=totals.values,
    mode="lines+markers",
    name="Total portfolio",
    line=dict(width=3, dash="dash", color="#374151"),
)

fig.update_traces(selector=dict(mode="lines+markers"), marker=dict(size=8))
fig.update_layout(
    height=440,
    legend_title_text="",
    hovermode="x unified",
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor="rgba(0,0,0,0)",
)
fig.update_xaxes(tickformat="%b %d, %Y", showgrid=False)
fig.update_yaxes(tickformat="$,.0f", gridcolor="rgba(128,128,128,0.15)")

if chart_df.groupby("zpid").size().max() <= 1:
    series = pd.concat([chart_df["zestimate"], totals]) if len(totals) else chart_df["zestimate"]
    lo, hi = series.min(), series.max()
    pad = max(50_000, (hi - lo) * 0.1) if hi > lo else 50_000
    fig.update_yaxes(range=[lo - pad, hi + pad])

st.plotly_chart(fig, use_container_width=True)

with st.expander("Raw snapshots"):
    st.dataframe(
        snaps.sort_values("fetched_at", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
