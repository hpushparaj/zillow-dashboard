# Home Valuations Dashboard

Personal dashboard that pulls Zillow valuations for a list of addresses and charts them over time.

## Architecture

```
properties.txt  ──►  GitHub Action (daily cron)  ──►  fetch_data.py  ──►  data/snapshots.csv
                                                                               │
                                                                               ▼
                                                                           app.py (Streamlit)
                                                                               │
                                                                               ▼
                                                                     Streamlit Community Cloud
```

History is stored in `data/snapshots.csv` (committed to git), so Streamlit Cloud's ephemeral filesystem isn't an issue.

## One-time setup

### 1. Get a RapidAPI key for Zillow

1. Sign up at https://rapidapi.com (free).
2. Subscribe to the **Real Estate Zillow** API (host: `real-estate-zillow-com.p.rapidapi.com`). Free tier covers ~100 requests/month — plenty for 1–10 properties on a daily schedule.
3. Copy your `X-RapidAPI-Key`.

> If you choose a different Zillow API on RapidAPI, update `RAPIDAPI_HOST`, `RAPIDAPI_URL`, and the field names in `fetch_data.py:extract_row`.

### 1b. Find ZPIDs for your properties

The API takes a Zillow Property ID (ZPID), not an address. To find one:

1. Search the property on https://www.zillow.com.
2. Open the property detail page.
3. The URL looks like `https://www.zillow.com/homedetails/123-Main-St-City-CA/54770934_zpid/` — the ZPID is just the number (e.g. `54770934`), without the `_zpid` suffix.
4. Add it to `properties.txt` as `ZPID,label` (label is optional, just for nicer dashboard display).

### 2. Push to GitHub

```bash
cd ~/zillow-dashboard
git init
git add .
git commit -m "initial commit"
gh repo create zillow-dashboard --public --source=. --push
```

Then add your key as a repo secret:

```bash
gh secret set RAPIDAPI_KEY
```

### 3. Deploy to Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. **New app** → pick your `zillow-dashboard` repo → main file `app.py`.
3. **Advanced settings → Secrets**, paste:
   ```
   RAPIDAPI_KEY = "your-key-here"
   ```
4. Deploy. You'll get a public URL like `https://<your-app>.streamlit.app`.

### 4. (Optional) Trigger first fetch immediately

```bash
gh workflow run "Fetch valuations"
```

The action will pull data and commit `data/snapshots.csv`, which Streamlit will then render.

## Local development

```bash
cd ~/zillow-dashboard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# fetch (writes data/snapshots.csv)
RAPIDAPI_KEY=xxx python fetch_data.py

# run dashboard
streamlit run app.py
```

## Adding / removing properties

Edit `properties.txt`, commit, push. The next scheduled run will start tracking the new ZPIDs.

## Cost

$0. Streamlit Community Cloud is free, GitHub Actions free tier is well above what this needs, RapidAPI Zillow free tier covers ~100 req/month.
