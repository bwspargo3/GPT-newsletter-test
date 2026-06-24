"""
Economic data ingestion: Treasury yield curve + FRED series.
Stores results in the economic_data table.
"""

import os
import logging
import requests
from datetime import date

from src.database.db import upsert_economic_data, record_source_health

logger = logging.getLogger(__name__)

TREASURY_URL = (
    'https://api.fiscaldata.treasury.gov/services/api/fiscal_service'
    '/v2/accounting/od/avg_interest_rates'
    '?fields=record_date,security_desc,avg_interest_rate_amt'
    '&filter=record_date:gte:{date}'
    '&sort=-record_date&page[size]=50'
)

FRED_BASE = 'https://api.stlouisfed.org/fred/series/observations'

FRED_SERIES = [
    ('SOFR',      'SOFR',                    '%'),
    ('VIXCLS',    'VIX',                     'index'),
    ('BAMLH0A0HYM2', 'HY OAS Spread',        'bps'),
    ('DGS10',     '10Y Treasury',            '%'),
    ('DGS20',     '20Y Treasury',            '%'),
    ('DGS30',     '30Y Treasury',            '%'),
]

TREASURY_LABELS = {
    'Treasury Notes and Bonds, Total': None,   # skip aggregate
    '30-Year Treasury Constant Maturity': '30Y Treasury CMT',
    '10-Year Treasury Constant Maturity': '10Y Treasury CMT',
    '20-Year Treasury Constant Maturity': '20Y Treasury CMT',
}


# ── Treasury ─────────────────────────────────────────────────────────────────

def fetch_treasury():
    """Pull recent Treasury avg interest rates from FiscalData API."""
    today = date.today().isoformat()
    # Look back 10 days to ensure we get the most recent available data
    lookback = date.fromisoformat(today).replace(day=max(1, date.today().day - 10)).isoformat()
    url = TREASURY_URL.format(date=lookback)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json().get('data', [])

        seen = set()
        for row in data:
            desc = row.get('security_desc', '')
            if desc in TREASURY_LABELS:
                label = TREASURY_LABELS[desc]
                if label and desc not in seen:
                    seen.add(desc)
                    try:
                        value = float(row['avg_interest_rate_amt'])
                        upsert_economic_data(f'TREAS_{desc[:10]}', label, value, '%')
                    except (ValueError, KeyError):
                        pass

        record_source_health('Treasury FiscalData', 'api', success=True)
        logger.info("Treasury: fetched %d rate series", len(seen))

    except Exception as exc:
        record_source_health('Treasury FiscalData', 'api', success=False)
        logger.error("Treasury fetch failed: %s", exc)


# ── FRED ──────────────────────────────────────────────────────────────────────

def fetch_fred_series(series_id: str, label: str, unit: str):
    """Fetch the latest observation for one FRED series."""
    api_key = os.getenv('FRED_API_KEY')
    if not api_key:
        logger.warning("FRED_API_KEY not set — skipping %s", series_id)
        return

    try:
        resp = requests.get(FRED_BASE, params={
            'series_id': series_id,
            'api_key': api_key,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 5,          # last 5 observations; we take the first non-null
        }, timeout=30)
        resp.raise_for_status()
        observations = resp.json().get('observations', [])

        for obs in observations:
            val_str = obs.get('value', '.')
            if val_str != '.':
                value = float(val_str)
                # FRED HY spread is in percent; convert to bps for display
                if 'bps' in unit:
                    value = round(value * 100, 1)
                upsert_economic_data(series_id, label, value, unit)
                logger.info("FRED %s (%s): %.2f %s", series_id, obs['date'], value, unit)
                return

        logger.warning("FRED %s: no valid observations", series_id)

    except Exception as exc:
        logger.error("FRED %s failed: %s", series_id, exc)


def fetch_all_fred():
    """Fetch all configured FRED series."""
    success_count = 0
    for series_id, label, unit in FRED_SERIES:
        try:
            fetch_fred_series(series_id, label, unit)
            success_count += 1
        except Exception as exc:
            logger.error("FRED %s error: %s", series_id, exc)

    record_source_health('FRED', 'api', success=success_count > 0)
    logger.info("FRED: fetched %d/%d series", success_count, len(FRED_SERIES))


# ── Main entry ────────────────────────────────────────────────────────────────

def run_all():
    """Fetch Treasury and FRED economic data."""
    fetch_treasury()
    fetch_all_fred()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all()
