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

def _escrow_is_in_mortgage(row) -> bool:
    """Default True (most common); empty / missing treated as True."""
    val = row.get("escrow_in_mortgage")
    if pd.isna(val):
        return True
    return str(val).strip().lower() not in ("false", "no", "0", "f", "n")


def per_property_cashflow(row):
    """Returns monthly cash flow for a row, or None if mortgage data is missing."""
    rent = row.get("actual_rent")
    pay = row.get("mortgage_payment")
    if pd.isna(rent) or pd.isna(pay):
        return None
    hoa = row.get("hoa_monthly") or 0
    maint_pct = row.get("maintenance_pct") if pd.notna(row.get("maintenance_pct")) else 1.0
    vac_pct = row.get("vacancy_pct") or 0
    cur = row.get("zestimate") or 0
    maint = cur * maint_pct / 100 / 12
    vacancy_loss = rent * vac_pct / 100
    # If escrow ISN'T in the mortgage payment, subtract tax + insurance separately
    extra_tax_ins = 0
    if not _escrow_is_in_mortgage(row):
        tax = row.get("property_tax_annual") or 0
        ins = row.get("insurance_annual") or 0
        extra_tax_ins = (tax + ins) / 12
    return rent - pay - hoa - maint - vacancy_loss - extra_tax_ins


def per_property_noi(row):
    """Annual NOI for cap-rate purposes. Excludes mortgage. None if tax/insurance missing."""
    rent = row.get("actual_rent")
    tax = row.get("property_tax_annual")
    ins = row.get("insurance_annual")
    if pd.isna(rent) or pd.isna(tax) or pd.isna(ins):
        return None
    hoa = row.get("hoa_monthly") or 0
    maint_pct = row.get("maintenance_pct") if pd.notna(row.get("maintenance_pct")) else 1.0
    vac_pct = row.get("vacancy_pct") or 0
    cur = row.get("zestimate") or 0
    return rent * 12 * (1 - vac_pct / 100) - tax - ins - hoa * 12 - cur * maint_pct / 100


latest["_cash_flow"] = latest.apply(per_property_cashflow, axis=1)
latest["_noi"] = latest.apply(per_property_noi, axis=1)

total_debt = latest.get("mortgage_balance", pd.Series(dtype=float)).sum(min_count=1)
total_equity = (total_value - total_debt) if pd.notna(total_debt) else None
total_monthly_cashflow = latest["_cash_flow"].sum(min_count=1)
total_noi = latest["_noi"].sum(min_count=1)
blended_cap_rate = (total_noi / latest.loc[latest["_noi"].notna(), "zestimate"].sum() * 100) if pd.notna(total_noi) and latest["_noi"].notna().any() else None

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
        delta=fmt_pct(total_appreciation_pct),
        help=(
            "Sum of current Zestimates. "
            f"Delta = appreciation vs cost basis of {fmt_dollars(total_basis)}."
        ),
    )
    c2.metric(
        "Total equity",
        fmt_dollars(total_equity) if total_equity is not None else "—",
        help="Total value − Mortgage balance. Only counts properties with mortgage data.",
    )
    c3.metric(
        "Monthly cash flow",
        fmt_dollars(total_monthly_cashflow, sign=True) if pd.notna(total_monthly_cashflow) else "—",
        help=(
            "Sum of (Rent − Mortgage payment − HOA − Maintenance − Vacancy loss). "
            "Property tax + insurance assumed escrowed in mortgage payment."
        ),
    )
    c4.metric(
        "Annualized return",
        fmt_pct(portfolio_annualized) if portfolio_annualized is not None else "—",
        help=(
            "CAGR weighted by cost basis: "
            "((Value ÷ Basis)^(1/avg years) − 1) × 100. "
            f"Avg hold: {avg_years:.1f} yrs." if avg_years else "CAGR weighted by basis."
        ),
    )

    with st.expander("More details"):
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Cost basis", fmt_dollars(total_basis), help="Sum of purchase prices.")
        d2.metric("Total debt", fmt_dollars(total_debt) if pd.notna(total_debt) else "—", help="Sum of current mortgage balances.")
        d3.metric(
            "Portfolio LTV",
            fmt_pct(total_debt / total_value * 100, sign=False) if total_value and pd.notna(total_debt) else "—",
            help="Total debt ÷ Total value × 100.",
        )
        d4.metric("Properties", str(len(latest)))

        d5, d6, d7, d8 = st.columns(4)
        d5.metric("Monthly rent", fmt_dollars(total_monthly_rent))
        d6.metric("Annual rent", fmt_dollars(total_annual_rent))
        d7.metric(
            "Blended gross yield",
            fmt_pct(blended_yield, sign=False),
            help="Annual rent ÷ Total value × 100. Pre-expense.",
        )
        d8.metric(
            "Blended cap rate",
            fmt_pct(blended_cap_rate, sign=False) if pd.notna(blended_cap_rate) else "—",
            help="NOI ÷ Value × 100. Unlevered. Only includes properties with full expense data.",
        )

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

    # Pre-compute mortgage / returns metrics for use in headline + details
    m_balance = p.get("mortgage_balance")
    m_payment = p.get("mortgage_payment")
    m_rate = p.get("mortgage_rate")
    equity = cur - m_balance if pd.notna(cur) and pd.notna(m_balance) else None
    ltv = m_balance / cur * 100 if pd.notna(cur) and pd.notna(m_balance) and cur else None
    cash_flow = p.get("_cash_flow")
    annual_cash_flow = cash_flow * 12 if pd.notna(cash_flow) else None
    cash_flow_pct = (cash_flow / p["actual_rent"] * 100) if pd.notna(cash_flow) and pd.notna(p.get("actual_rent")) and p["actual_rent"] else None
    noi = p.get("_noi")
    cap_rate = (noi / cur * 100) if pd.notna(noi) and pd.notna(cur) and cur else None
    down_pmt = p.get("down_payment")
    closing = p.get("closing_costs")
    cash_invested = (down_pmt or 0) + (closing or 0) if pd.notna(down_pmt) or pd.notna(closing) else None
    coc_return = (annual_cash_flow / cash_invested * 100) if annual_cash_flow is not None and cash_invested else None

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

        # Headline row — 5 vital signs
        h1, h2, h3, h4, h5 = st.columns(5)
        h1.metric(
            "Current value",
            fmt_dollars(cur),
            delta=fmt_pct(appreciation_pct) if appreciation_pct is not None else None,
            help=(
                "Latest Zillow Zestimate. "
                f"Delta = appreciation vs purchase price of {fmt_dollars(cost)}."
            ),
        )
        h2.metric(
            "Appreciation",
            fmt_dollars(appreciation, sign=True) if appreciation is not None else "—",
            delta=fmt_pct(appreciation_pct) if appreciation_pct is not None else None,
            help="Current value − Purchase price. % = Appreciation ÷ Purchase price × 100.",
        )
        h3.metric(
            "Cash flow",
            f"{fmt_dollars(cash_flow, sign=True)}/mo" if pd.notna(cash_flow) else "—",
            delta=fmt_pct(cash_flow_pct) if pd.notna(cash_flow_pct) else None,
            help=(
                "Rent − Mortgage payment − HOA − Maintenance reserve − Vacancy loss. "
                "Delta = Cash flow ÷ Rent × 100. "
                "Shows '—' if mortgage data isn't in portfolio.csv."
            ),
        )
        h4.metric(
            "Annualized return",
            fmt_pct(annual_ret) if annual_ret is not None else "—",
            help=(
                "Compound annual growth rate (CAGR) on property value: "
                "((Current value ÷ Purchase price)^(1 ÷ years held) − 1) × 100."
                + (f" Held {yrs:.1f} yrs." if yrs else "")
            ),
        )
        # 5th headline: cap rate if available, else gross yield as fallback
        if pd.notna(cap_rate):
            h5.metric(
                "Cap rate",
                fmt_pct(cap_rate, sign=False),
                help=(
                    "Unlevered yield. NOI ÷ Current value × 100. "
                    "NOI = Annual rent − Tax − Insurance − HOA − Maintenance − Vacancy loss. "
                    "Excludes mortgage. The real-estate industry's 'P/E' metric."
                ),
            )
        else:
            h5.metric(
                "Gross yield",
                fmt_pct(gross_yield, sign=False) if gross_yield is not None else "—",
                help=(
                    "Annual rent ÷ Current value × 100. Pre-expense. "
                    "Add property tax + insurance to portfolio.csv to upgrade to true cap rate."
                ),
            )

        # Details expander — everything else
        with st.expander("More details"):
            st.markdown("**Financials**")
            f1, f2, f3, f4 = st.columns(4)
            f1.metric("Purchase price", fmt_dollars(cost))
            f2.metric(
                "Appreciation",
                fmt_dollars(appreciation, sign=True) if appreciation is not None else "—",
                delta=fmt_pct(appreciation_pct) if appreciation_pct is not None else None,
            )
            f3.metric("Annual income", fmt_dollars(annual_income) if annual_income else "—")
            f4.metric("Annual cash flow", fmt_dollars(annual_cash_flow, sign=True) if pd.notna(annual_cash_flow) else "—")

            st.markdown("**Rental**")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric(
                "Actual rent",
                f"{fmt_dollars(p['actual_rent'])}/mo" if pd.notna(p.get("actual_rent")) else "—",
            )
            r2.metric(
                "Market rent",
                f"{fmt_dollars(market_rent)}/mo" if pd.notna(market_rent) else "—",
                delta=f"{rent_vs_market:+.1f}% vs market" if rent_vs_market is not None else None,
            )
            r3.metric(
                "Gross yield",
                fmt_pct(gross_yield, sign=False) if gross_yield is not None else "—",
                help=(
                    "Annual rent ÷ Current value × 100. Pre-expense — doesn't subtract "
                    "mortgage, tax, insurance, or maintenance. A quick comparability metric "
                    "between properties; cap rate above is more accurate."
                ),
            )
            beds = p.get("bedrooms")
            baths = p.get("bathrooms")
            sqft = p.get("living_area")
            details_str = ""
            if pd.notna(beds): details_str += f"{int(beds)} bd"
            if pd.notna(baths): details_str += f" / {baths:g} ba"
            if pd.notna(sqft): details_str += f" / {int(sqft):,} sqft"
            r4.metric("Property", details_str.strip(" /") or "—")

            if pd.notna(m_balance) or pd.notna(m_payment):
                st.markdown("**Loan**")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(
                    "Mortgage balance",
                    fmt_dollars(m_balance) if pd.notna(m_balance) else "—",
                    help="Remaining loan principal you still owe the bank.",
                )
                m2.metric(
                    "Mortgage payment",
                    f"{fmt_dollars(m_payment)}/mo" if pd.notna(m_payment) else "—",
                    help="Monthly payment to lender (P&I + escrow if applicable).",
                )
                m3.metric(
                    "Interest rate",
                    f"{m_rate:.3f}%" if pd.notna(m_rate) else "—",
                    help="Current mortgage interest rate. Watch for ARM adjustment dates.",
                )
                m4.metric(
                    "LTV",
                    fmt_pct(ltv, sign=False) if ltv is not None else "—",
                    help=(
                        "Loan-to-Value: Mortgage balance ÷ Current value × 100. "
                        "How much of the property is financed vs owned. "
                        "Banks watch this: <80% means no PMI; <50% gives refinance flexibility."
                    ),
                )

                # Your-money row
                st.markdown("**Your money**")
                e1, e2, e3, _ = st.columns(4)
                e1.metric(
                    "Equity",
                    fmt_dollars(equity) if equity is not None else "—",
                    help="The portion of the property you actually own. Current value − Mortgage balance.",
                )
                e2.metric(
                    "Cash invested",
                    fmt_dollars(cash_invested) if cash_invested is not None else "—",
                    help="Cash you put in at purchase: Down payment + Closing costs. The basis for cash-on-cash return.",
                )

                # Cash-on-cash with qualitative rating
                if pd.notna(coc_return):
                    if coc_return < 0:
                        rating = "Losing money"
                    elif coc_return < 4:
                        rating = "Weak"
                    elif coc_return < 8:
                        rating = "Typical"
                    elif coc_return < 12:
                        rating = "Strong"
                    else:
                        rating = "Exceptional"
                else:
                    rating = None
                e3.metric(
                    "Cash-on-cash",
                    fmt_pct(coc_return) if pd.notna(coc_return) else "—",
                    delta=rating,
                    delta_color="off",
                    help=(
                        "Annual cash flow ÷ Cash invested × 100. "
                        "The real cash return on the dollars you put down at purchase. "
                        "Rough benchmarks for residential rentals: "
                        "<0% losing money, 0–4% weak, 4–8% typical, 8–12% strong, >12% exceptional. "
                        "Doesn't include appreciation or principal paydown — those are wealth gains, not cash."
                    ),
                )

                # Operating costs row
                st.markdown("**Operating costs (annual)**")
                hoa_yr = (p.get("hoa_monthly") or 0) * 12
                maint_pct_val = p.get("maintenance_pct") if pd.notna(p.get("maintenance_pct")) else 1.0
                maint_yr = (cur or 0) * maint_pct_val / 100 if pd.notna(cur) else None
                vac_pct_val = p.get("vacancy_pct") or 0
                vac_yr = (p.get("actual_rent") or 0) * 12 * vac_pct_val / 100 if pd.notna(p.get("actual_rent")) else None

                o1, o2, o3, o4, o5 = st.columns(5)
                o1.metric(
                    "Property tax",
                    fmt_dollars(p.get("property_tax_annual")) if pd.notna(p.get("property_tax_annual")) else "—",
                    help="Annual property tax. Paid via escrow if escrow_in_mortgage is TRUE.",
                )
                o2.metric(
                    "Insurance",
                    fmt_dollars(p.get("insurance_annual")) if pd.notna(p.get("insurance_annual")) else "—",
                    help="Annual homeowners insurance premium.",
                )
                o3.metric(
                    "HOA",
                    fmt_dollars(hoa_yr) if hoa_yr else "—",
                    help="Annual HOA dues (monthly × 12). Usually paid separately, not through escrow.",
                )
                o4.metric(
                    "Maintenance reserve",
                    fmt_dollars(maint_yr) if maint_yr is not None else "—",
                    delta=f"{maint_pct_val:.1f}% of value/yr",
                    delta_color="off",
                    help=(
                        f"Reserve set aside for repairs and upkeep. Calculated as "
                        f"Current value × {maint_pct_val:.1f}%/yr. "
                        f"Subtracted from cash flow even though you don't write a check for it each month — "
                        f"it's an accrual against future maintenance. Adjust via maintenance_pct in portfolio.csv."
                    ),
                )
                o5.metric(
                    "Vacancy reserve",
                    fmt_dollars(vac_yr) if vac_yr is not None else "—",
                    delta=f"{vac_pct_val:.0f}% of rent",
                    delta_color="off",
                    help=(
                        f"Reserve for expected unrented months. Calculated as "
                        f"Annual rent × {vac_pct_val:.0f}%. "
                        f"Currently {vac_pct_val:.0f}% — change via vacancy_pct in portfolio.csv "
                        f"(typical assumption is 5–8% = ~half a month to a month per year)."
                    ),
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
