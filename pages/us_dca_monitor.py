import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import csv
import io
import json
import urllib.parse
import urllib.request
import pandas as pd
from streamlit_autorefresh import st_autorefresh


# =========================
# Page Config
# =========================

st.set_page_config(
    page_title="美股定期定額監控",
    page_icon="🌍",
    layout="wide"
)


# =========================
# Global CSS
# =========================

st.markdown("""
<style>

/* =========================
   全域字體
========================= */

html, body, [class*="css"] {
    font-size: 13px;
}

h1 { font-size: 26px !important; }
h2 { font-size: 20px !important; }
h3 { font-size: 16px !important; }
h4 { font-size: 14px !important; }

[data-testid="stMetricValue"] {
    font-size: 22px;
}

[data-testid="stMetricDelta"] {
    font-size: 13px;
}

[data-testid="stMetricLabel"] {
    font-size: 13px;
}

/* =========================
   版面寬度限制
   目標：左側與標題切齊，右側大約切齊刷新按鈕
   若仍覺得太寬，請調整 --dashboard-width
========================= */

:root {
    --dashboard-width: 1280px;
    --dashboard-left: 48px;
}

/* Streamlit 新版主要容器 */
[data-testid="stMainBlockContainer"] {
    max-width: var(--dashboard-width) !important;
    width: var(--dashboard-width) !important;
    margin-left: var(--dashboard-left) !important;
    margin-right: auto !important;
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}

/* Streamlit 舊版主要容器 */
[data-testid="stAppViewContainer"] > .main .block-container {
    max-width: var(--dashboard-width) !important;
    width: var(--dashboard-width) !important;
    margin-left: var(--dashboard-left) !important;
    margin-right: auto !important;
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}

section.main > div.block-container {
    max-width: var(--dashboard-width) !important;
    width: var(--dashboard-width) !important;
    margin-left: var(--dashboard-left) !important;
    margin-right: auto !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}

/* 小螢幕自動改為滿版，避免手機或窄視窗爆版 */
@media (max-width: 1350px) {
    [data-testid="stMainBlockContainer"],
    [data-testid="stAppViewContainer"] > .main .block-container,
    section.main > div.block-container {
        width: calc(100vw - 32px) !important;
        max-width: calc(100vw - 32px) !important;
        margin-left: 16px !important;
        margin-right: 16px !important;
    }
}
/* =========================
   隱藏 Streamlit Anchor Link
========================= */

[data-testid="stHeaderActionElements"] {
    display: none !important;
}

/* =========================
   小 i 提示符號
========================= */

.info-icon {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    width: 17px;
    height: 17px;
    min-width: 17px;

    border-radius: 50%;
    color: #8a94a6;
    cursor: help;
    line-height: 1;
    flex-shrink: 0;

    transition: color 0.12s ease, background 0.12s ease;
}

.info-icon:hover {
    color: #2563eb;
    background: rgba(37, 99, 235, 0.08);
}

.info-icon svg {
    width: 15px;
    height: 15px;
    display: block;
    stroke: currentColor;
    stroke-width: 2;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    shape-rendering: geometricPrecision;
}

.info-icon::after {
    content: attr(data-tooltip);
    position: absolute;
    left: 50%;
    bottom: calc(100% + 9px);
    transform: translateX(-50%);

    min-width: 260px;
    max-width: 360px;
    padding: 8px 10px;

    border-radius: 8px;
    background: rgba(15, 23, 42, 0.96);
    color: #ffffff;

    font-size: 12px;
    font-weight: 500;
    line-height: 1.5;
    white-space: normal;
    text-align: left;

    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.18);

    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    z-index: 9999;

    transition: opacity 0.05s ease;
}

.info-icon::before {
    content: "";
    position: absolute;
    left: 50%;
    bottom: calc(100% + 4px);
    transform: translateX(-50%);

    border-width: 5px 5px 0 5px;
    border-style: solid;
    border-color: rgba(15, 23, 42, 0.96) transparent transparent transparent;

    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    z-index: 9999;

    transition: opacity 0.05s ease;
}

.info-icon:hover::after,
.info-icon:hover::before {
    opacity: 1;
    visibility: visible;
}

.section-title {
    display: flex;
    align-items: center;
    gap: 4px;
    position: relative;
    overflow: visible;
}
            
/* =========================
   Header
========================= */

.header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}

.update-text {
    color: #8a94a6;
    font-size: 12px;
}

/* =========================
   間距
========================= */

hr {
    margin-top: 1rem;
    margin-bottom: 1rem;
}

/* =========================
   商品 & 外匯
========================= */

.market-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 9px 0;
    border-bottom: 1px solid rgba(180,180,180,0.18);
}

.market-name {
    font-size: 14px;
    font-weight: 600;
}

.market-value {
    text-align: right;
}

.market-price {
    font-size: 20px;
    font-weight: 700;
    line-height: 1.15;
}

.market-delta {
    font-size: 13px;
    font-weight: 600;
    line-height: 1.2;
}

/* =========================
   區間選擇按鈕
========================= */

[data-testid="stRadio"] label {
    font-size: 12px !important;
}

[data-testid="stRadio"] div[role="radiogroup"] {
    gap: 6px;
}

[data-testid="stRadio"] div[role="radiogroup"] label {
    padding: 2px 6px;
    border-radius: 6px;
}

</style>
""", unsafe_allow_html=True)


# =========================
# Auto Refresh
# =========================

st_autorefresh(
    interval=60 * 1000,
    key="global_market_refresh"
)


# =========================
# Watch Lists
# =========================

WATCHLIST = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "費城半導體": "^SOX",
    "道瓊工業": "^DJI",
    "日經 225": "^N225",
    "恆生指數": "^HSI",
    "DAX": "^GDAXI",
    "台灣加權": "^TWII",
}

BOND_LIST = {
    "10Y": "^TNX",
}

COMMODITY_LIST = {
    "黃金": "GC=F",
    "WTI 原油": "CL=F",
    "銅": "HG=F",
    "天然氣": "NG=F",
}

FX_LIST = {
    "美元指數 DXY": "DX-Y.NYB",
    "USD/TWD": "TWD=X",
    "USD/JPY": "JPY=X",
    "EUR/USD": "EURUSD=X",
}

OIL_CHART_LIST = {
    "布蘭特原油 Brent": "BZ=F",
    "西德州原油 WTI": "CL=F",
}

CRYPTO_LIST = {
    "BTC Bitcoin": "BTC-USD",
    "ETH Ethereum": "ETH-USD",
    "SOL Solana": "SOL-USD",
}

PERIOD_OPTIONS = {
    "1個月": "1mo",
    "3個月": "3mo",
    "6個月": "6mo",
    "1年": "12mo",
}

VIX_PERIOD_OPTIONS = {
    "1天": "1d",
    "5天": "5d",
    "1月": "1mo",
    "3月": "3mo",
}


# =========================
# Data Functions
# =========================

@st.cache_data(ttl=60)
def get_market_data(symbol):

    ticker = yf.Ticker(symbol)

    daily = ticker.history(
        period="10d",
        interval="1d"
    )

    if daily.empty or len(daily) < 2:
        return None

    daily_close = daily["Close"].dropna()

    if len(daily_close) < 2:
        return None

    last_close = daily_close.iloc[-1]
    prev_close = daily_close.iloc[-2]

    change = last_close - prev_close
    change_pct = change / prev_close * 100

    intraday = ticker.history(
        period="5d",
        interval="5m"
    )

    if intraday.empty:
        hist = daily.reset_index()
    else:
        hist = intraday.reset_index()

    if "Datetime" in hist.columns:
        last_time = hist.iloc[-1]["Datetime"]
    elif "Date" in hist.columns:
        last_time = hist.iloc[-1]["Date"]
    else:
        last_time = None

    return {
        "price": float(last_close),
        "previous": float(prev_close),
        "change": float(change),
        "change_pct": float(change_pct),
        "hist": hist,
        "last_time": last_time
    }


@st.cache_data(ttl=60)
def get_bond_history(symbol="^TNX", period="6mo"):

    ticker = yf.Ticker(symbol)

    hist = ticker.history(
        period=period,
        interval="1d"
    )

    if hist.empty or len(hist) < 2:
        return None

    close = hist["Close"].dropna()

    if len(close) < 2:
        return None

    last = close.iloc[-1]
    prev = close.iloc[-2]

    return {
        "price": float(last),
        "previous": float(prev),
        "change": float(last - prev),
        "change_pct": float((last - prev) / prev * 100),
        "hist": hist,
        "last_time": hist.index[-1]
    }


@st.cache_data(ttl=60)
def get_currency_history(symbol, period="12mo"):

    ticker = yf.Ticker(symbol)

    hist = ticker.history(
        period=period,
        interval="1d"
    )

    if hist.empty or len(hist) < 2:
        return None

    return hist


@st.cache_data(ttl=60)
def get_oil_spread_data():

    brent = yf.Ticker("BZ=F").history(
        period="12mo",
        interval="1d"
    )

    wti = yf.Ticker("CL=F").history(
        period="12mo",
        interval="1d"
    )

    if brent.empty or wti.empty:
        return None

    brent_close = brent["Close"].dropna().rename("Brent")
    wti_close = wti["Close"].dropna().rename("WTI")

    merged = brent_close.to_frame().join(
        wti_close.to_frame(),
        how="inner"
    )

    if merged.empty or len(merged) < 2:
        return None

    merged["Spread"] = merged["Brent"] - merged["WTI"]

    return merged



def parse_fear_greed_rating(score):

    if score <= 25:
        return "Extreme Fear"
    if score <= 45:
        return "Fear"
    if score <= 55:
        return "Neutral"
    if score <= 75:
        return "Greed"
    return "Extreme Greed"


def rating_to_zh(rating):

    if rating is None:
        return "--"

    rating_lower = str(rating).strip().lower()

    mapping = {
        "extreme fear": "極度恐懼",
        "fear": "恐懼",
        "neutral": "中性",
        "greed": "貪婪",
        "extreme greed": "極度貪婪",
    }

    return mapping.get(rating_lower, str(rating))


def safe_float(value):

    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def nearest_history_value(history_rows, target_date):

    if not history_rows:
        return None

    valid_rows = [
        row for row in history_rows
        if row.get("date") is not None
        and row.get("score") is not None
        and row.get("date") <= target_date
    ]

    if not valid_rows:
        return None

    return valid_rows[-1].get("score")


def build_fear_greed_result(score, rating, history_rows, source):

    today = datetime.now().date()

    return {
        "score": float(score),
        "rating": rating_to_zh(rating or parse_fear_greed_rating(float(score))),
        "previous_close": nearest_history_value(
            history_rows,
            today - timedelta(days=1)
        ),
        "previous_1_week": nearest_history_value(
            history_rows,
            today - timedelta(days=7)
        ),
        "previous_1_month": nearest_history_value(
            history_rows,
            today - timedelta(days=30)
        ),
        "previous_1_year": nearest_history_value(
            history_rows,
            today - timedelta(days=365)
        ),
        "source": source,
    }


@st.cache_data(ttl=300)
def get_fear_greed_data():

    # 先抓 CNN 官方 API。
    # 若 CNN API 暫時阻擋，再用 GitHub 上由 CNN API 更新的公開歷史資料作備援。
    start_date = (datetime.now() - timedelta(days=370)).strftime("%Y-%m-%d")

    cnn_urls = [
        f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start_date}",
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
    ]

    for url in cnn_urls:

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
                    "Origin": "https://edition.cnn.com",
                }
            )

            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read().decode("utf-8", errors="ignore")

            data = json.loads(raw)

            fear_greed = data.get("fear_and_greed", {})
            historical = data.get("fear_and_greed_historical", {})

            history_rows = []

            for item in historical.get("data", []):

                timestamp = item.get("x")
                score_value = safe_float(item.get("y"))

                if timestamp is None or score_value is None:
                    continue

                try:
                    row_date = datetime.fromtimestamp(
                        int(timestamp) / 1000
                    ).date()
                except Exception:
                    continue

                history_rows.append({
                    "date": row_date,
                    "score": score_value
                })

            history_rows = sorted(
                history_rows,
                key=lambda row: row["date"]
            )

            score = safe_float(
                fear_greed.get("score")
                or fear_greed.get("value")
            )

            rating = (
                fear_greed.get("rating")
                or fear_greed.get("status")
                or fear_greed.get("classification")
            )

            if score is None and history_rows:
                score = history_rows[-1]["score"]
                rating = parse_fear_greed_rating(score)

            if score is not None:
                return build_fear_greed_result(
                    score,
                    rating,
                    history_rows,
                    source="CNN API"
                )

        except Exception:
            continue

    # 備援：公開 GitHub CSV，欄位通常為 Date / Fear Greed / Rating。
    fallback_urls = [
        "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"
    ]

    for url in fallback_urls:

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/csv,text/plain,*/*",
                }
            )

            with urllib.request.urlopen(req, timeout=12) as response:
                raw_csv = response.read().decode("utf-8", errors="ignore")

            reader = csv.DictReader(io.StringIO(raw_csv))

            history_rows = []
            latest_rating = None

            for row in reader:

                date_text = (
                    row.get("Date")
                    or row.get("date")
                    or row.get("DATE")
                )

                score_text = (
                    row.get("Fear Greed")
                    or row.get("Fear Greed Index")
                    or row.get("fear_greed")
                    or row.get("score")
                    or row.get("Score")
                )

                rating_text = (
                    row.get("Rating")
                    or row.get("rating")
                    or row.get("Classification")
                )

                score_value = safe_float(score_text)

                if date_text is None or score_value is None:
                    continue

                try:
                    row_date = datetime.strptime(
                        date_text[:10],
                        "%Y-%m-%d"
                    ).date()
                except Exception:
                    continue

                history_rows.append({
                    "date": row_date,
                    "score": score_value
                })

                latest_rating = rating_text

            history_rows = sorted(
                history_rows,
                key=lambda row: row["date"]
            )

            if history_rows:
                latest_score = history_rows[-1]["score"]

                return build_fear_greed_result(
                    latest_score,
                    latest_rating,
                    history_rows,
                    source="GitHub fallback"
                )

        except Exception:
            continue

    return None


@st.cache_data(ttl=60)
def get_vix_data(period="1d"):

    # 使用 Yahoo Finance chart API，和 Yahoo 報價頁來源一致。
    # period="1d" 時使用 5 分 K，才能對齊 Yahoo 頁面的當日走勢與漲跌幅。
    symbol = urllib.parse.quote("^VIX", safe="")

    if period == "1d":
        yahoo_range = "1d"
        yahoo_interval = "5m"
    elif period == "5d":
        yahoo_range = "5d"
        yahoo_interval = "15m"
    else:
        yahoo_range = period
        yahoo_interval = "1d"

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={yahoo_range}&interval={yahoo_interval}&includePrePost=false"
    )

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
            }
        )

        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read().decode("utf-8", errors="ignore")

        data = json.loads(raw)
        result = data["chart"]["result"][0]

        meta = result.get("meta", {})
        timestamps = result.get("timestamp", [])
        quote = result.get("indicators", {}).get("quote", [{}])[0]

        close_values = quote.get("close", [])
        open_values = quote.get("open", [])
        high_values = quote.get("high", [])
        low_values = quote.get("low", [])

        rows = []

        for idx, timestamp in enumerate(timestamps):

            close_value = (
                close_values[idx]
                if idx < len(close_values)
                else None
            )

            if close_value is None:
                continue

            rows.append({
                "Datetime": datetime.fromtimestamp(timestamp),
                "Open": (
                    open_values[idx]
                    if idx < len(open_values)
                    and open_values[idx] is not None
                    else close_value
                ),
                "High": (
                    high_values[idx]
                    if idx < len(high_values)
                    and high_values[idx] is not None
                    else close_value
                ),
                "Low": (
                    low_values[idx]
                    if idx < len(low_values)
                    and low_values[idx] is not None
                    else close_value
                ),
                "Close": close_value,
            })

        if len(rows) < 2:
            raise ValueError("Not enough Yahoo VIX chart rows")

        hist = pd.DataFrame(rows).set_index("Datetime")

        # Yahoo 頁面的主數字使用 regularMarketPrice 與 chartPreviousClose
        price = safe_float(meta.get("regularMarketPrice"))
        previous = safe_float(meta.get("chartPreviousClose"))

        if price is None:
            price = float(hist["Close"].iloc[-1])

        if previous is None:
            previous = float(hist["Close"].iloc[-2])

        change = price - previous
        change_pct = change / previous * 100

        return {
            "price": float(price),
            "previous": float(previous),
            "change": float(change),
            "change_pct": float(change_pct),
            "hist": hist,
            "last_time": hist.index[-1],
            "open": float(hist["Open"].iloc[0] if period == "1d" else hist["Open"].iloc[-1]),
            "high": float(hist["High"].max() if period == "1d" else hist["High"].iloc[-1]),
            "low": float(hist["Low"].min() if period == "1d" else hist["Low"].iloc[-1]),
            "source": "Yahoo Finance",
        }

    except Exception:

        ticker = yf.Ticker("^VIX")

        if period in ("1d", "5d"):

            fallback_interval = "5m" if period == "1d" else "15m"

            hist = ticker.history(
                period=period,
                interval=fallback_interval
            )

            daily = ticker.history(
                period="5d",
                interval="1d"
            )

            if hist.empty or len(hist) < 2 or daily.empty or len(daily) < 2:
                return None

            price = hist["Close"].dropna().iloc[-1]
            previous = daily["Close"].dropna().iloc[-2]

            change = price - previous
            change_pct = change / previous * 100

            return {
                "price": float(price),
                "previous": float(previous),
                "change": float(change),
                "change_pct": float(change_pct),
                "hist": hist,
                "last_time": hist.index[-1],
                "open": float(hist["Open"].dropna().iloc[0]),
                "high": float(hist["High"].dropna().max()),
                "low": float(hist["Low"].dropna().min()),
                "source": "yfinance fallback",
            }

        hist = ticker.history(
            period=period,
            interval="1d"
        )

        if hist.empty or len(hist) < 2:
            return None

        close = hist["Close"].dropna()

        if len(close) < 2:
            return None

        last = close.iloc[-1]
        previous = close.iloc[-2]

        change = last - previous
        change_pct = change / previous * 100

        return {
            "price": float(last),
            "previous": float(previous),
            "change": float(change),
            "change_pct": float(change_pct),
            "hist": hist,
            "last_time": hist.index[-1],
            "open": float(hist["Open"].iloc[-1]),
            "high": float(hist["High"].iloc[-1]),
            "low": float(hist["Low"].iloc[-1]),
            "source": "yfinance fallback",
        }


# =========================
# Helper Functions
# =========================

def format_date(dt):

    if dt is None:
        return "--"

    try:
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(dt)


def tw_color_positive(positive):

    # 台股習慣：上漲紅色、下跌綠色
    return "red" if positive else "green"


def draw_sparkline(df, positive=True):

    color = tw_color_positive(positive)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        mode="lines",
        line=dict(color=color, width=2),
        showlegend=False
    ))

    fig.update_layout(
        height=70,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig


def draw_bond_curve(bond_data):

    if bond_data is None:
        return None

    hist = bond_data["hist"]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=hist.index,
        y=hist["Close"],
        mode="lines",
        line=dict(
            color="royalblue",
            width=2
        ),
        fill="tozeroy",
        fillcolor="rgba(65, 105, 225, 0.16)",
        showlegend=False
    ))

    close_min = hist["Close"].min()
    close_max = hist["Close"].max()
    padding = (close_max - close_min) * 0.25

    if padding == 0:
        padding = close_max * 0.01

    y_min = close_min - padding
    y_max = close_max + padding

    fig.update_layout(
        height=250,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(
            ticksuffix="%",
            range=[y_min, y_max],
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        font=dict(size=11),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig

def draw_currency_chart(df, title, positive=True):

    color = tw_color_positive(positive)

    close_min = df["Close"].min()
    close_max = df["Close"].max()

    padding = (close_max - close_min) * 0.25

    if padding == 0:
        padding = close_max * 0.01

    y_min = close_min - padding
    y_max = close_max + padding

    # DXY 固定顯示 95 / 100 / 105 關鍵區間
    if "美元指數 DXY" in title:
        y_min = min(y_min, 94)
        y_max = max(y_max, 106)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=(
            "rgba(220,0,0,0.10)"
            if positive
            else "rgba(0,150,120,0.12)"
        ),
        showlegend=False
    ))

    # =========================
    # 美元指數 DXY 警戒線
    # =========================

    if "美元指數 DXY" in title:

        fig.add_hline(
            y=100,
            line_color="red",
            line_width=2,
            line_dash="dash",

            annotation_text="DXY 100 警戒線",
            annotation_position="top left",

            annotation_font_color="red",
            annotation_bgcolor="rgba(255,255,255,0.75)"
        )
        #fig.add_hline(
        #    y=105,
        #    line_color="darkred",
        #    line_width=1,
        #    line_dash="dot",
        #    annotation_text="DXY 105 極限警戒",
        #    annotation_position="top right",
        #    annotation_font_color="darkred"
        #)
        #fig.add_hline(
        #    y=95,
        #    line_color="green",
        #    line_width=1,
        #    line_dash="dot",
        #    annotation_text="DXY 95 支撐區",
        #    annotation_position="bottom right",
        #    annotation_font_color="green"
        #)

    # =========================
    # 原油 90 美元警戒線
    # =========================

    if (
        "布蘭特原油" in title
        or "西德州原油" in title
    ):

        fig.add_hline(
            y=90,

            line_color="red",
            line_width=2,
            line_dash="dash",

            annotation_text="90 美元警戒線",
            annotation_position="top left",

            annotation_font_color="red",
            annotation_bgcolor="rgba(255,255,255,0.75)"
        )

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=14)
        ),
        height=250,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=11),
        xaxis=dict(
            title="",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        yaxis=dict(
            title="",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)",
            range=[y_min, y_max]
        )
    )

    return fig



def draw_oil_spread_chart(spread_data):

    if spread_data is None or spread_data.empty:
        return None

    spread = spread_data["Spread"]

    colors = [
        "rgba(218, 165, 32, 0.85)" if value >= 0 else "rgba(220, 0, 0, 0.75)"
        for value in spread
    ]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=spread.index,
        y=spread.values,
        marker_color=colors,
        showlegend=False
    ))

    fig.add_hline(
        y=0,
        line_color="gray",
        line_width=1,
        line_dash="dash"
    )

    fig.update_layout(
        title=dict(
            text="Brent - WTI 價差",
            font=dict(size=14)
        ),
        height=250,
        margin=dict(l=10, r=10, t=40, b=10),
        yaxis=dict(
            title="USD / bbl",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        font=dict(size=11),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig


def show_oil_spread_card():

    spread_data = get_oil_spread_data()

    with st.container(border=True):

        st.markdown(
            section_title_html(
                "🛢 Brent - WTI 價差",
                "布蘭特原油與西德州原油的價差，可觀察全球供需、地緣政治、運輸瓶頸與美國原油相對強弱。",
                font_size=16
            ),
            unsafe_allow_html=True
        )

        if spread_data is None:
            st.warning("原油價差資料讀取失敗")
            return

        last = spread_data["Spread"].iloc[-1]
        prev = spread_data["Spread"].iloc[-2]
        change = last - prev

        st.metric(
            label="",
            value=f"{last:,.2f}",
            delta=f"{change:+.2f}",
            delta_color="normal"
        )

        st.caption(
            f"Brent {spread_data['Brent'].iloc[-1]:,.2f}　WTI {spread_data['WTI'].iloc[-1]:,.2f}　資料日 {format_date(spread_data.index[-1])}"
        )

        fig = draw_oil_spread_chart(spread_data)

        if fig is not None:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False}
            )


def draw_fear_greed_gauge(score):

    fig = go.Figure()

    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=score,
        number={
            "valueformat": ".0f",
            "font": {
                "size": 42,
                "color": "#0f172a"
            }
        },
        gauge={
            "axis": {
                "range": [0, 100],
                "tickwidth": 0,
                "tickfont": {
                    "size": 10,
                    "color": "#94a3b8"
                }
            },
            "bar": {
                "color": "rgba(0,0,0,0)"
            },
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 25], "color": "rgba(220, 38, 38, 0.25)"},
                {"range": [25, 45], "color": "rgba(245, 158, 11, 0.25)"},
                {"range": [45, 55], "color": "rgba(148, 163, 184, 0.25)"},
                {"range": [55, 75], "color": "rgba(34, 197, 94, 0.25)"},
                {"range": [75, 100], "color": "rgba(22, 163, 74, 0.35)"},
            ],
            "threshold": {
                "line": {
                    "color": "#0f172a",
                    "width": 3
                },
                "thickness": 0.75,
                "value": score
            }
        },
        domain={
            "x": [0, 1],
            "y": [0, 1]
        }
    ))

    fig.update_layout(
        height=230,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig


def draw_vix_chart(hist, show_warning_lines=True):

    if hist is None or hist.empty:
        return None

    close = hist["Close"]

    positive = close.iloc[-1] >= close.iloc[0]
    color = tw_color_positive(positive)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=hist.index,
        y=close,
        mode="lines",
        line=dict(
            color=color,
            width=2
        ),
        fill="tozeroy",
        fillcolor=(
            "rgba(220,0,0,0.10)"
            if positive
            else "rgba(0,150,120,0.12)"
        ),
        showlegend=False
    ))

    if show_warning_lines:

        fig.add_hline(
            y=20,
            line_color="orange",
            line_width=1,
            line_dash="dash",
            annotation_text="VIX 20",
            annotation_position="right",
            annotation_font_color="orange",
            annotation_bgcolor="rgba(255,255,255,0.75)"
        )

        fig.add_hline(
            y=30,
            line_color="red",
            line_width=1,
            line_dash="dash",
            annotation_text="VIX 30",
            annotation_position="right",
            annotation_font_color="red",
            annotation_bgcolor="rgba(255,255,255,0.75)"
        )

    close_min = close.min()
    close_max = close.max()
    padding = (close_max - close_min) * 0.25

    if padding == 0:
        padding = close_max * 0.01

    y_min = max(0, close_min - padding)
    y_max = close_max + padding

    if show_warning_lines:
        y_max = max(y_max, 32)

    fig.update_layout(
        title=dict(
            text="VIX 指數走勢",
            font=dict(size=14)
        ),
        height=250,
        margin=dict(l=10, r=10, t=40, b=10),
        yaxis=dict(
            range=[y_min, y_max],
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        font=dict(size=11),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig


def show_fear_greed_card():

    data = get_fear_greed_data()

    with st.container(border=True):

        st.markdown(
            section_title_html(
                "CNN 恐懼與貪婪指數",
                "CNN Fear & Greed Index 以多項市場情緒指標衡量投資人偏恐懼或偏貪婪，通常可作為風險情緒參考。",
                font_size=16
            ),
            unsafe_allow_html=True
        )

        if data is None:
            st.warning("CNN 恐懼與貪婪指數資料讀取失敗")
            st.caption("若 CNN API 暫時阻擋連線，請稍後再刷新。")
            return

        score = round(data["score"])
        rating = data["rating"]

        st.plotly_chart(
            draw_fear_greed_gauge(score),
            use_container_width=True,
            config={"displayModeBar": False}
        )

        st.markdown(
            f"<div style='text-align:center;font-size:18px;font-weight:700;color:#16a34a;margin-top:-28px'>{rating}</div>",
            unsafe_allow_html=True
        )

        m1, m2, m3 = st.columns(3)

        with m1:
            st.caption("上週")
            st.markdown(f"**{round(data.get('previous_1_week')) if data.get('previous_1_week') is not None else '--'}**")

        with m2:
            st.caption("上月")
            st.markdown(f"**{round(data.get('previous_1_month')) if data.get('previous_1_month') is not None else '--'}**")

        with m3:
            st.caption("去年")
            st.markdown(f"**{round(data.get('previous_1_year')) if data.get('previous_1_year') is not None else '--'}**")

        st.caption(f"資料來源：{data.get('source', '--')}")


def show_vix_card(period="1d", selected_label="1天"):

    with st.container(border=True):

        vix_title_col, vix_period_col = st.columns([1, 1])

        with vix_title_col:

            st.markdown(
                section_title_html(
                    "VIX 恐慌指數",
                    "VIX 衡量市場對未來波動的預期，數值越高代表避險與恐慌情緒越強。20 以上需留意，30 以上通常代表高壓力市場。",
                    font_size=16
                ),
                unsafe_allow_html=True
            )

        with vix_period_col:

            selected_label = st.radio(
                "VIX 期間",
                list(VIX_PERIOD_OPTIONS.keys()),
                index=list(VIX_PERIOD_OPTIONS.keys()).index(selected_label),
                horizontal=True,
                label_visibility="collapsed",
                key="vix_period_selector"
            )

            period = VIX_PERIOD_OPTIONS[selected_label]

            data = get_vix_data(period)

        if data is None:
            st.warning("VIX 資料讀取失敗")
            return

        st.metric(
            label="",
            value=f"{data['price']:,.2f}",
            delta=f"{data['change']:+.2f} ({data['change_pct']:+.2f}%)",
            delta_color="inverse"
        )

        st.caption(
            f"開盤 {data['open']:,.2f}　最高 {data['high']:,.2f}　最低 {data['low']:,.2f}　資料日 {format_date(data['last_time'])}"
        )

        fig = draw_vix_chart(
            data["hist"],
            show_warning_lines=period in ("1mo", "3mo")
        )

        if fig is not None:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False}
            )

        st.caption(f"資料來源：{data.get('source', '--')}")



def draw_crypto_chart(hist, positive=True):

    if hist is None or hist.empty:
        return None

    color = tw_color_positive(positive)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=hist.index,
        y=hist["Close"],
        mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=(
            "rgba(220,0,0,0.10)"
            if positive
            else "rgba(0,150,120,0.12)"
        ),
        showlegend=False
    ))

    close_min = hist["Close"].min()
    close_max = hist["Close"].max()
    padding = (close_max - close_min) * 0.25

    if padding == 0:
        padding = close_max * 0.01

    fig.update_layout(
        height=250,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis=dict(
            range=[close_min - padding, close_max + padding],
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        font=dict(size=11),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig


def show_crypto_card(name, symbol):

    hist = get_currency_history(symbol, period="12mo")

    with st.container(border=True):

        tooltip_map = {
            "BTC Bitcoin": "Bitcoin 為加密貨幣市場代表性資產，可觀察市場風險偏好、美元流動性與投機情緒。",
            "ETH Ethereum": "Ethereum 為主要智能合約平台代幣，可觀察加密貨幣生態系與風險資產情緒。",
            "SOL Solana": "Solana 為高波動成長型公鏈代幣，可作為加密市場風險偏好的輔助觀察。"
        }

        st.markdown(
            section_title_html(
                f"₿ {name}",
                tooltip_map.get(name, ""),
                font_size=16
            ),
            unsafe_allow_html=True
        )

        if hist is None:
            st.warning(f"{name} 資料讀取失敗")
            return

        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]

        change = last - prev
        change_pct = change / prev * 100

        positive = change >= 0

        st.metric(
            label="",
            value=f"${last:,.0f}",
            delta=f"{change_pct:+.2f}%",
            delta_color="inverse"
        )

        st.caption(
            f"開盤 {hist['Open'].iloc[-1]:,.0f}　最高 {hist['High'].iloc[-1]:,.0f}　最低 {hist['Low'].iloc[-1]:,.0f}　資料日 {format_date(hist.index[-1])}"
        )

        fig = draw_crypto_chart(hist, positive)

        if fig is not None:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False}
            )



def info_icon_html(tooltip):
    safe_tooltip = (
        tooltip
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    return (
        f'<span class="info-icon" data-tooltip="{safe_tooltip}">'
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<circle cx="12" cy="12" r="10"></circle>'
        '<line x1="12" y1="16" x2="12" y2="12"></line>'
        '<line x1="12" y1="8" x2="12.01" y2="8"></line>'
        '</svg>'
        '</span>'
    )


def section_title_html(title, tooltip, font_size=20):
    return (
        '<div class="section-title">'
        f'<div style="font-size:{font_size}px;font-weight:700;line-height:1;">{title}</div>'
        f'{info_icon_html(tooltip)}'
        '</div>'
    )


# =========================
# UI Components
# =========================

def show_market_card(name, symbol, data):

    with st.container(border=True):

        c_title, c_date = st.columns([3, 2])

        with c_title:
            st.markdown(f"### {name}")
            st.caption(symbol)

        with c_date:

            if data is not None:

                st.markdown(
                    f"<div style='text-align:right;color:gray;font-size:12px'>{format_date(data['last_time'])}</div>",
                    unsafe_allow_html=True
                )

        if data is None:
            st.error("資料讀取失敗")
            return

        positive = data["change_pct"] >= 0

        st.metric(
            label="",
            value=f"{data['price']:,.2f}",
            delta=f"{data['change_pct']:+.2f}% / {data['change']:+,.1f}",
            delta_color="inverse"
        )

        st.plotly_chart(
            draw_sparkline(data["hist"], positive),
            use_container_width=True,
            config={"displayModeBar": False}
        )


def show_simple_row(name, symbol):

    data = get_market_data(symbol)

    if data is None:
        st.warning(f"{name} 資料讀取失敗")
        return

    positive = data["change_pct"] >= 0

    color = "red" if positive else "green"
    arrow = "▲" if positive else "▼"

    html = (
        f"<div class='market-row'>"
        f"<div class='market-name'>{name}</div>"
        f"<div class='market-value'>"
        f"<div class='market-price'>{data['price']:,.3f}</div>"
        f"<div class='market-delta' style='color:{color};'>{arrow} {data['change_pct']:+.2f}%</div>"
        f"</div>"
        f"</div>"
    )

    st.markdown(html, unsafe_allow_html=True)


def show_currency_chart_card(name, symbol, period="12mo"):

    hist = get_currency_history(symbol, period)

    with st.container(border=True):

        if hist is None:
            st.warning(f"{name} 資料讀取失敗")
            return

        last = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2]

        change = last - prev
        change_pct = change / prev * 100

        positive = change >= 0

        high = hist["High"].iloc[-1]
        low = hist["Low"].iloc[-1]
        open_price = hist["Open"].iloc[-1]

        tooltip_map = {
            "美元指數 DXY": "美元指數 DXY 代表美元對六大貨幣的強弱，通常會影響台股、黃金、外資與全球資金流向；美元強，則新興市場壓力大、避險程度高。",
            "USD/TWD 台幣匯率": "觀察美元與台幣強弱，可反映外資流向、台股資金動能與匯率避險需求。",
            "USD/JPY 日幣匯率": "日圓常被視為避險貨幣，可觀察全球風險情緒、日本央行政策與利差交易。",
            "布蘭特原油 Brent": "Brent 為國際油價重要基準，常反映全球能源供需、通膨壓力與地緣政治風險。",
            "西德州原油 WTI": "WTI 為美國原油重要基準，可觀察美國能源供需、庫存變化與通膨壓力。",
        }

        title_icon = "🛢" if "原油" in name else "💱"

        st.markdown(
            section_title_html(
                f"{title_icon} {name}",
                tooltip_map.get(name, ""),
                font_size=16
            ),
            unsafe_allow_html=True
        )

        st.metric(
            label="",
            value=f"{last:,.3f}",
            delta=f"{change:+.3f} ({change_pct:+.2f}%)",
            delta_color="inverse"
        )

        st.caption(
            f"開盤 {open_price:,.3f}　最高 {high:,.3f}　最低 {low:,.3f}　資料日 {format_date(hist.index[-1])}"
        )

        st.plotly_chart(
            draw_currency_chart(
                hist,
                f"{name} 走勢",
                positive
            ),
            use_container_width=True,
            config={"displayModeBar": False}
        )


# =========================
# US Stock DCA Monitor
# =========================

STOCK_DCA_LIST = {
    "QQQ": "QQQ",
    "MSFT": "MSFT",
    "ASML": "ASML",
    "LLY": "LLY",
    "TSLA": "TSLA",
}

@st.cache_data(ttl=300)
def get_stock_dca_data(symbol, period="6mo"):

    ticker = yf.Ticker(symbol)

    hist = ticker.history(
        period=period,
        interval="1d"
    )

    if hist.empty or len(hist) < 25:
        return None

    hist = hist.dropna(subset=["Close"])

    if hist.empty or len(hist) < 25:
        return None

    latest_date = hist.index[-1]
    latest_price = float(hist["Close"].iloc[-1])

    # 用最近交易日往前約一個月作為上月參考價。
    # 若該日是假日或無資料，取目標日前最近一個交易日。
    target_date = latest_date - pd.Timedelta(days=30)
    previous_month_hist = hist[hist.index <= target_date]

    if previous_month_hist.empty:
        previous_month_price = float(hist["Close"].iloc[0])
        previous_month_date = hist.index[0]
    else:
        previous_month_price = float(previous_month_hist["Close"].iloc[-1])
        previous_month_date = previous_month_hist.index[-1]

    change = latest_price - previous_month_price
    change_pct = change / previous_month_price * 100

    day_change = 0.0
    day_change_pct = 0.0

    if len(hist) >= 2:
        prev_close = float(hist["Close"].iloc[-2])
        day_change = latest_price - prev_close
        day_change_pct = day_change / prev_close * 100

    return {
        "symbol": symbol,
        "price": latest_price,
        "previous_month_price": previous_month_price,
        "previous_month_date": previous_month_date,
        "month_change": change,
        "month_change_pct": change_pct,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "hist": hist,
        "last_time": latest_date,
    }


def draw_stock_dca_chart(hist, positive=True):

    if hist is None or hist.empty:
        return None

    color = tw_color_positive(positive)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=hist.index,
        y=hist["Close"],
        mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=(
            "rgba(220,0,0,0.10)"
            if positive
            else "rgba(0,150,120,0.12)"
        ),
        showlegend=False
    ))

    close_min = hist["Close"].min()
    close_max = hist["Close"].max()
    padding = (close_max - close_min) * 0.25

    if padding == 0:
        padding = close_max * 0.01

    fig.update_layout(
        height=210,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis=dict(
            range=[close_min - padding, close_max + padding],
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        xaxis=dict(
            title="",
            tickfont=dict(size=10),
            gridcolor="rgba(180,180,180,0.25)"
        ),
        font=dict(size=11),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig


def show_stock_dca_card(symbol, data, is_pick=False):

    with st.container(border=True):

        badge = (
            "<span style='background:#dc2626;color:white;border-radius:999px;"
            "padding:3px 9px;font-size:12px;font-weight:700;margin-left:6px;'>"
            "本月扣款</span>"
            if is_pick else ""
        )

        st.markdown(
            f"<div style='font-size:16px;font-weight:800;'>📈 {symbol}{badge}</div>",
            unsafe_allow_html=True
        )

        if data is None:
            st.warning(f"{symbol} 資料讀取失敗")
            return

        month_positive = data["month_change_pct"] >= 0

        st.metric(
            label="現價",
            value=f"${data['price']:,.2f}",
            delta=f"今日 {data['day_change']:+.2f} ({data['day_change_pct']:+.2f}%)",
            delta_color="inverse"
        )

        month_color = "red" if month_positive else "green"
        month_arrow = "▲" if month_positive else "▼"

        st.markdown(
            f"<div style='font-size:13px;color:#64748b;'>"
            f"上月參考價（{format_date(data['previous_month_date'])}）："
            f"<b>${data['previous_month_price']:,.2f}</b>"
            f"</div>"
            f"<div style='font-size:15px;font-weight:800;color:{month_color};margin-top:4px;'>"
            f"與上月比較：{month_arrow} {data['month_change_pct']:+.2f}% "
            f"({data['month_change']:+.2f})"
            f"</div>",
            unsafe_allow_html=True
        )

        fig = draw_stock_dca_chart(data["hist"], positive=month_positive)

        if fig is not None:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False}
            )

        st.caption(f"資料日 {format_date(data['last_time'])}")


def show_stock_dca_section():

    st.divider()

    st.markdown(
        section_title_html(
            "📈 美股定期定額監控",
            "追蹤 QQQ、MSFT、ASML、LLY、TSLA 的近期走勢，並比較今日價格與約一個月前價格。跌幅最大者標示為本月扣款；若全部上漲，預設扣款 QQQ 作為核心資產。",
            font_size=20
        ),
        unsafe_allow_html=True
    )

    stock_data = {
        name: get_stock_dca_data(symbol)
        for name, symbol in STOCK_DCA_LIST.items()
    }

    valid_items = {
        name: data for name, data in stock_data.items()
        if data is not None
    }

    pick_symbol = "QQQ"
    pick_reason = "若全部上漲，預設扣款核心 ETF：QQQ"

    negative_items = {
        name: data for name, data in valid_items.items()
        if data["month_change_pct"] < 0
    }

    if negative_items:
        pick_symbol = min(
            negative_items,
            key=lambda name: negative_items[name]["month_change_pct"]
        )
        pick_reason = "本月與上月相比跌幅最大"

    if pick_symbol in valid_items:
        pick_data = valid_items[pick_symbol]
        st.success(
            f"本月建議扣款：{pick_symbol}　"
            f"與上月比較 {pick_data['month_change_pct']:+.2f}%　"
            f"理由：{pick_reason}"
        )
    else:
        st.warning("目前無法判斷本月扣款標的，請稍後刷新。")

    summary_rows = []

    for name, data in valid_items.items():
        summary_rows.append({
            "股票": name,
            "現價": round(data["price"], 2),
            "上月參考價": round(data["previous_month_price"], 2),
            "與上月比較": f"{data['month_change_pct']:+.2f}%",
            "本月扣款": "✅" if name == pick_symbol else "",
        })

    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(
            summary_df,
            use_container_width=True,
            hide_index=True
        )

    cards = list(STOCK_DCA_LIST.keys())

    for row_start in range(0, len(cards), 3):
        cols = st.columns(3)

        for col, name in zip(cols, cards[row_start:row_start + 3]):
            with col:
                show_stock_dca_card(
                    name,
                    stock_data.get(name),
                    is_pick=(name == pick_symbol)
                )



# =========================
# Brokerage Lump-Sum Monitor
# =========================

BROKERAGE_ETF_LIST = {
    "QQQ": "QQQ",
    "VT": "VT",
}


@st.cache_data(ttl=300)
def get_brokerage_etf_data(symbol, period="18mo"):

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval="1d")

    if hist.empty:
        return None

    hist = hist.dropna(subset=["Close"]).copy()

    if len(hist) < 220:
        return None

    latest_date = hist.index[-1]
    latest_price = float(hist["Close"].iloc[-1])

    # 約一個月前最近交易日，與上方 DCA 區塊維持一致。
    target_date = latest_date - pd.Timedelta(days=30)
    previous_hist = hist[hist.index <= target_date]

    if previous_hist.empty:
        previous_price = float(hist["Close"].iloc[0])
        previous_date = hist.index[0]
    else:
        previous_price = float(previous_hist["Close"].iloc[-1])
        previous_date = previous_hist.index[-1]

    month_change = latest_price - previous_price
    month_change_pct = month_change / previous_price * 100

    ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
    distance_200ma_pct = (latest_price / ma200 - 1) * 100

    delta = hist["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    latest_rsi = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0

    return {
        "symbol": symbol,
        "price": latest_price,
        "previous_price": previous_price,
        "previous_date": previous_date,
        "month_change": month_change,
        "month_change_pct": month_change_pct,
        "ma200": ma200,
        "distance_200ma_pct": distance_200ma_pct,
        "rsi": latest_rsi,
        "hist": hist.tail(130),
        "last_time": latest_date,
    }


def calc_brokerage_score(data, vix_value=None, fear_greed_value=None):
    """滿分 100；前 80 分為標的價格面，後 20 分為共通市場情緒。"""

    # 1) 一個月相對跌幅：跌 15% 以上得滿分；上漲不加分。
    decline = max(0.0, -data["month_change_pct"])
    decline_score = min(35.0, decline / 15.0 * 35.0)

    # 2) 距離 200MA：低於年線越多，分數越高；高於 15% 幾乎不加分。
    distance = data["distance_200ma_pct"]
    if distance <= -10:
        ma_score = 25.0
    elif distance <= 0:
        ma_score = 15.0 + (-distance / 10.0) * 10.0
    elif distance <= 15:
        ma_score = max(0.0, 15.0 - distance)
    else:
        ma_score = 0.0

    # 3) RSI：偏低代表短期較不熱；RSI 30 以下滿分，70 以上零分。
    rsi = data["rsi"]
    if rsi <= 30:
        rsi_score = 20.0
    elif rsi >= 70:
        rsi_score = 0.0
    else:
        rsi_score = (70.0 - rsi) / 40.0 * 20.0

    # 4) VIX：市場越恐慌，整體加碼環境分數越高。
    if vix_value is None:
        vix_score = 5.0
    elif vix_value >= 30:
        vix_score = 10.0
    elif vix_value <= 15:
        vix_score = 2.0
    else:
        vix_score = 2.0 + (vix_value - 15.0) / 15.0 * 8.0

    # 5) Fear & Greed：越恐懼，分數越高。
    if fear_greed_value is None:
        fg_score = 5.0
    else:
        fg_score = max(0.0, min(10.0, (100.0 - fear_greed_value) / 10.0))

    total = decline_score + ma_score + rsi_score + vix_score + fg_score

    return {
        "跌幅分數": decline_score,
        "200MA分數": ma_score,
        "RSI分數": rsi_score,
        "VIX分數": vix_score,
        "情緒分數": fg_score,
        "總分": min(100.0, total),
    }


def show_brokerage_monitor_section():

    st.divider()

    st.markdown(
        section_title_html(
            "🎯 複委託單筆投入監控",
            "每月比較 QQQ 與 VT 的一個月漲跌、距離 200 日均線、RSI，以及市場情緒，選出本月較適合投入的 ETF，並依最低一股限制估算可買股數。",
            font_size=20
        ),
        unsafe_allow_html=True
    )

    setting_col1, setting_col2 = st.columns([1, 1])

    with setting_col1:
        monthly_budget = st.number_input(
            "本月複委託投入預算（USD）",
            min_value=0,
            value=1250,
            step=50,
            key="brokerage_monthly_budget",
            help="依目前規劃預設為 1,250 美元，可在每月評估時調整。"
        )

    with setting_col2:
        st.metric(
            "評估方式",
            "QQQ vs VT",
            delta="最低買進 1 股",
            delta_color="off"
        )

    etf_data = {
        name: get_brokerage_etf_data(symbol)
        for name, symbol in BROKERAGE_ETF_LIST.items()
    }

    valid_data = {k: v for k, v in etf_data.items() if v is not None}

    if len(valid_data) < 2:
        st.warning("QQQ 或 VT 資料不足，目前無法完成複委託比較，請稍後刷新。")
        return

    vix_data = get_vix_data("1mo")
    fear_greed_data = get_fear_greed_data()

    vix_value = vix_data.get("price") if vix_data else None
    fear_greed_value = fear_greed_data.get("score") if fear_greed_data else None

    score_data = {
        symbol: calc_brokerage_score(
            data,
            vix_value=vix_value,
            fear_greed_value=fear_greed_value
        )
        for symbol, data in valid_data.items()
    }

    # 若總分相同，優先選一個月表現較弱者。
    pick_symbol = max(
        valid_data.keys(),
        key=lambda symbol: (
            score_data[symbol]["總分"],
            -valid_data[symbol]["month_change_pct"]
        )
    )

    pick_data = valid_data[pick_symbol]
    shares = int(monthly_budget // pick_data["price"]) if monthly_budget > 0 else 0
    estimated_amount = shares * pick_data["price"]
    remaining_cash = monthly_budget - estimated_amount

    if shares >= 1:
        st.success(
            f"本月複委託建議：{pick_symbol}｜AI 評分 {score_data[pick_symbol]['總分']:.1f}｜"
            f"預算 ${monthly_budget:,.0f} 可買 {shares} 股，預估投入 ${estimated_amount:,.2f}。"
        )
    else:
        st.warning(
            f"本月評分較高的是 {pick_symbol}，但預算 ${monthly_budget:,.0f} 不足買進 1 股；"
            f"目前至少需要約 ${pick_data['price']:,.2f}。"
        )

    card_cols = st.columns(2)

    for col, symbol in zip(card_cols, ["QQQ", "VT"]):
        data = valid_data[symbol]
        scores = score_data[symbol]
        is_pick = symbol == pick_symbol
        symbol_shares = int(monthly_budget // data["price"]) if monthly_budget > 0 else 0
        symbol_amount = symbol_shares * data["price"]
        symbol_cash = monthly_budget - symbol_amount

        with col:
            with st.container(border=True):
                badge = (
                    "<span style='background:#2563eb;color:white;border-radius:999px;"
                    "padding:3px 9px;font-size:12px;font-weight:700;margin-left:6px;'>"
                    "本月建議</span>"
                    if is_pick else ""
                )

                st.markdown(
                    f"<div style='font-size:18px;font-weight:800;'>📌 {symbol}{badge}</div>",
                    unsafe_allow_html=True
                )

                m1, m2 = st.columns(2)
                m1.metric("現價", f"${data['price']:,.2f}")
                m2.metric("AI 評分", f"{scores['總分']:.1f}")

                st.markdown(
                    f"上次參考（{format_date(data['previous_date'])}）："
                    f"**${data['previous_price']:,.2f}**  \n"
                    f"一個月比較：**{data['month_change_pct']:+.2f}%**  \n"
                    f"200 日均線：**${data['ma200']:,.2f}**（距離 {data['distance_200ma_pct']:+.2f}%）  \n"
                    f"RSI(14)：**{data['rsi']:.1f}**"
                )

                fig = draw_stock_dca_chart(
                    data["hist"],
                    positive=data["month_change_pct"] >= 0
                )
                if fig is not None:
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        config={"displayModeBar": False},
                        key=f"brokerage_chart_{symbol}"
                    )

                if symbol_shares >= 1:
                    st.info(
                        f"預算 ${monthly_budget:,.0f}：可買 **{symbol_shares} 股**｜"
                        f"預估 ${symbol_amount:,.2f}｜剩餘 ${symbol_cash:,.2f}"
                    )
                else:
                    st.info(
                        f"預算 ${monthly_budget:,.0f}：不足買進 1 股，尚差約 "
                        f"${data['price'] - monthly_budget:,.2f}"
                    )

    score_rows = []
    for symbol in ["QQQ", "VT"]:
        scores = score_data[symbol]
        score_rows.append({
            "ETF": symbol,
            "一個月漲跌": f"{valid_data[symbol]['month_change_pct']:+.2f}%",
            "距200MA": f"{valid_data[symbol]['distance_200ma_pct']:+.2f}%",
            "RSI(14)": f"{valid_data[symbol]['rsi']:.1f}",
            "價格面分數": f"{scores['跌幅分數'] + scores['200MA分數'] + scores['RSI分數']:.1f}",
            "市場情緒分數": f"{scores['VIX分數'] + scores['情緒分數']:.1f}",
            "AI總分": f"{scores['總分']:.1f}",
            "本月建議": "✅" if symbol == pick_symbol else "",
        })

    st.dataframe(
        pd.DataFrame(score_rows),
        use_container_width=True,
        hide_index=True
    )

    context_cols = st.columns(3)
    context_cols[0].metric(
        "VIX",
        f"{vix_value:.2f}" if vix_value is not None else "--"
    )
    context_cols[1].metric(
        "Fear & Greed",
        f"{fear_greed_value:.0f}" if fear_greed_value is not None else "--"
    )
    context_cols[2].metric(
        "預算剩餘",
        f"${remaining_cash:,.2f}" if shares >= 1 else f"${monthly_budget:,.2f}"
    )

    st.caption(
        "評分用途是協助每月在 QQQ 與 VT 之間作相對比較，不代表預測最低點。"
        "若兩檔總分接近，仍可依長期目標配置比例決定。"
    )

# =========================
# Header
# =========================

st.title("美股定期定額監控")
st.caption("AI 定期定額監控｜複委託單筆投入｜匯率走勢｜市場情緒")

col_time, col_btn = st.columns([5, 1])

with col_time:
    st.caption(
        f"🕒 最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

with col_btn:
    if st.button("刷新"):
        st.cache_data.clear()
        st.rerun()

st.divider()


# =========================
# 1. AI Stock DCA Monitor
# =========================

show_stock_dca_section()


# =========================
# 2. Brokerage Lump-Sum Monitor
# =========================

show_brokerage_monitor_section()


# =========================
# 3. Currency Trend
# =========================

st.divider()

currency_title_col, currency_period_col = st.columns([3, 2])

with currency_title_col:

    st.markdown(
        section_title_html(
            "💱 匯率走勢",
            "可切換 1 個月、3 個月、6 個月與 1 年區間，觀察美元、台幣與日圓的趨勢變化。",
            font_size=20
        ),
        unsafe_allow_html=True
    )

with currency_period_col:

    selected_period_label = st.radio(
        "匯率走勢期間",
        list(PERIOD_OPTIONS.keys()),
        index=3,
        horizontal=True,
        label_visibility="collapsed",
        key="currency_period_selector"
    )

currency_period = PERIOD_OPTIONS[selected_period_label]

fx_col1, fx_col2, fx_col3 = st.columns(3)

with fx_col1:
    show_currency_chart_card(
        "美元指數 DXY",
        "DX-Y.NYB",
        period=currency_period
    )

with fx_col2:
    show_currency_chart_card(
        "USD/TWD 台幣匯率",
        "TWD=X",
        period=currency_period
    )

with fx_col3:
    show_currency_chart_card(
        "USD/JPY 日幣匯率",
        "JPY=X",
        period=currency_period
    )


# =========================
# 4. Market Sentiment
# =========================

st.divider()

sentiment_title_col, vix_period_col = st.columns([3, 2])

with sentiment_title_col:

    st.markdown(
        section_title_html(
            "市場情緒",
            "整合 CNN 恐懼與貪婪指數與 VIX 恐慌指數，觀察市場風險偏好與避險情緒。",
            font_size=20
        ),
        unsafe_allow_html=True
    )

sentiment_col1, sentiment_col2 = st.columns([1, 1])

with sentiment_col1:
    show_fear_greed_card()

with sentiment_col2:
    show_vix_card(
        period="1d",
        selected_label="1天"
    )
