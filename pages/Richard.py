import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import numpy as np
import datetime
import re
#import time
#BUILD_TAG = "re-import-fix-" + str(int(time.time()))

st.set_page_config(page_title="Family Portfolio Dashboard", layout="wide")


# =========================
# OneDrive Excel 同步（與上傳並存）
# Secrets 需設定：
# ONEDRIVE_XLSX_URL = "https://1drv.ms/...."
# =========================
def ensure_excel_from_onedrive(xlsx_path: Path) -> bool:
    url = st.secrets.get("ONEDRIVE_XLSX_URL", "")
    if not isinstance(url, str) or not url.strip():
        return False
    url = url.strip()

    def add_download_param(u: str) -> str:
        if "download=1" in u:
            return u
        return u + ("&" if "?" in u else "?") + "download=1"

    candidates = [url, add_download_param(url)]
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)

    last_err = None
    for u in candidates:
        try:
            r = requests.get(
                u,
                timeout=45,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.raise_for_status()
            content = r.content or b""
            # xlsx 是 zip，檔頭通常是 PK；避免抓到 OneDrive 預覽 HTML
            if not content.startswith(b"PK"):
                last_err = RuntimeError(f"下載內容不是 Excel（前 20 bytes={content[:20]!r}）")
                continue
            xlsx_path.write_bytes(content)
            return True
        except Exception as e:
            last_err = e
            continue

    # 失敗不報錯中斷：仍可用既有檔案或上傳
    if last_err:
        st.sidebar.warning(f"OneDrive 下載失敗，將使用既有/上傳檔案：{last_err}")
    return False


# =========================
# Google Drive / Google Sheets Excel 同步（與上傳並存）
# Secrets 其一即可：
# GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/<ID>/edit?..."
# 或
# GDRIVE_FILE_URL = "https://drive.google.com/file/d/<ID>/view?..."
# =========================
def _to_gdrive_xlsx_download_url(u: str) -> str | None:
    if not isinstance(u, str):
        return None
    u = u.strip()
    if not u:
        return None

    # Google Sheets: .../spreadsheets/d/<ID>/...
    m = re.search(r"/spreadsheets/d/([^/]+)/", u)
    if m:
        sid = m.group(1)
        return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"

    # Google Drive file: .../file/d/<ID>/...
    m = re.search(r"/file/d/([^/]+)/", u)
    if m:
        fid = m.group(1)
        return f"https://drive.google.com/uc?export=download&id={fid}"

    # 直接給 uc?export=download&id=...
    if "drive.google.com/uc" in u and "id=" in u:
        return u

    return None


def ensure_excel_from_gdrive(xlsx_path: Path) -> bool:
    raw = st.secrets.get("GOOGLE_SHEETS_URL", "") or st.secrets.get("GDRIVE_FILE_URL", "")
    if not isinstance(raw, str) or not raw.strip():
        return False

    url = _to_gdrive_xlsx_download_url(raw)
    if not url:
        st.sidebar.warning("Google Drive 連結格式無法辨識，請確認是 Google Sheets 或 Drive 檔案分享連結。")
        return False

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        r = requests.get(url, timeout=45, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        content = r.content or b""

        # xlsx 是 zip，檔頭通常是 PK；避免抓到 Google 登入/預覽 HTML
        if not content.startswith(b"PK"):
            raise RuntimeError(f"下載內容不是 Excel（前 20 bytes={content[:20]!r}）")

        xlsx_path.write_bytes(content)
        return True
    except Exception as e:
        st.sidebar.warning(f"Google Drive 下載失敗，將使用既有/上傳檔案：{e}")
        return False

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
XLSX_PATH = DATA_DIR / "family_data.xlsx"

# ====== 管理者驗證（用 Streamlit Secrets：ADMIN_PASSWORD）======
# ====== 小工具：把文字數字清乾淨 ======
def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str)
         .str.replace(",", "", regex=False)
         .str.replace(" ", "", regex=False)
         .replace({"nan": None, "": None}),
        errors="coerce"
    ).fillna(0.0)






# ====== 進階績效：IRR / 資金使用率 / 10年預測 ======
def _first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def _xnpv(rate: float, cashflows: list[tuple[pd.Timestamp, float]]) -> float:
    if not cashflows:
        return 0.0
    d0 = min(d for d, _ in cashflows)
    total = 0.0
    for d, cf in cashflows:
        days = (d - d0).days
        total += cf / ((1.0 + rate) ** (days / 365.0))
    return total


def calc_xirr(cashflows: list[tuple[pd.Timestamp, float]]) -> float | None:
    """用日期現金流估算 XIRR。需同時有正、負現金流。"""
    cfs = [(pd.to_datetime(d), float(v)) for d, v in cashflows if pd.notna(d) and abs(float(v)) > 1e-9]
    if not cfs or not any(v > 0 for _, v in cfs) or not any(v < 0 for _, v in cfs):
        return None

    # 先用多組區間尋找符號反轉，再二分法；避免 numpy_financial 相依性
    grid = [-0.999, -0.9, -0.75, -0.5, -0.25, -0.1, 0.0, 0.05, 0.1, 0.2, 0.4, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
    vals = []
    for r in grid:
        try:
            v = _xnpv(r, cfs)
            if np.isfinite(v):
                vals.append((r, v))
        except Exception:
            pass

    for (lo, vlo), (hi, vhi) in zip(vals, vals[1:]):
        if vlo == 0:
            return lo
        if vlo * vhi > 0:
            continue
        for _ in range(100):
            mid = (lo + hi) / 2
            vmid = _xnpv(mid, cfs)
            if abs(vmid) < 1e-5:
                return mid
            if vlo * vmid <= 0:
                hi, vhi = mid, vmid
            else:
                lo, vlo = mid, vmid
        return (lo + hi) / 2
    return None


def build_investment_cashflows(richard: pd.DataFrame) -> list[tuple[pd.Timestamp, float]]:
    """
    以交易明細估算 IRR：
    - 買進日：成交金額視為現金流出
    - 賣出日：成交金額 + 已實現損益 + 除息 視為現金流入
    - 未賣出部位：今天以參考現值 + 除息 當作期末價值
    """
    df = _filter_trade_like_rows(richard).copy()
    if "分類" in df.columns:
        cat = df["分類"].astype(str).str.strip()
        df = df[cat.notna() & (cat != "") & (cat.str.lower() != "nan")]

    buy_date_col = _first_existing_col(df, ["買進日期", "日期"])
    sell_date_col = _first_existing_col(df, ["賣出日期", "出場日期"])
    amount_col = _first_existing_col(df, ["成交金額", "投入金額", "買進金額"])
    realized_col = _first_existing_col(df, ["已實現損益"])
    value_col = _first_existing_col(df, ["參考現值", "市值"])
    dividend_col = _first_existing_col(df, ["除息", "股息", "配息"])

    if buy_date_col is None or amount_col is None:
        return []

    today = pd.Timestamp.today().normalize()
    cashflows: list[tuple[pd.Timestamp, float]] = []
    for _, row in df.iterrows():
        buy_date = pd.to_datetime(row.get(buy_date_col), errors="coerce")
        amount = pd.to_numeric(str(row.get(amount_col, 0)).replace(",", ""), errors="coerce")
        if pd.notna(buy_date) and pd.notna(amount) and amount > 0:
            cashflows.append((buy_date, -float(amount)))

        div = pd.to_numeric(str(row.get(dividend_col, 0)).replace(",", ""), errors="coerce") if dividend_col else 0.0
        div = 0.0 if pd.isna(div) else float(div)

        sell_date = pd.to_datetime(row.get(sell_date_col), errors="coerce") if sell_date_col else pd.NaT
        if pd.notna(sell_date):
            realized = pd.to_numeric(str(row.get(realized_col, 0)).replace(",", ""), errors="coerce") if realized_col else 0.0
            realized = 0.0 if pd.isna(realized) else float(realized)
            cashflows.append((sell_date, float(amount) + realized + div))
        else:
            value = pd.to_numeric(str(row.get(value_col, 0)).replace(",", ""), errors="coerce") if value_col else 0.0
            value = 0.0 if pd.isna(value) else float(value)
            if value > 0 or div > 0:
                cashflows.append((today, value + div))
    return cashflows


def compute_advanced_metrics(richard: pd.DataFrame, acct: pd.DataFrame):
    total_invested, total_realized, total_unrealized, total_pnl, simple_ret = compute_kpi(richard)

    df = _filter_trade_like_rows(richard).copy()
    if "分類" in df.columns:
        cat = df["分類"].astype(str).str.strip()
        df = df[cat.notna() & (cat != "") & (cat.str.lower() != "nan")]

    value_col = _first_existing_col(df, ["參考現值", "市值"])
    current_invested_value = float(to_num(df[value_col]).sum()) if value_col else max(total_invested + total_unrealized, 0.0)

    cash_candidates = ["台幣現金水位", "台幣現金", "現金水位", "台幣結餘", "結餘"]
    date_col = "日期" if "日期" in acct.columns else acct.columns[0]
    acct2 = acct.copy()
    acct2[date_col] = pd.to_datetime(acct2[date_col], errors="coerce")
    acct2 = acct2.dropna(subset=[date_col]).sort_values(date_col)
    cash_col = _first_existing_col(acct2, cash_candidates)
    cash_balance = 0.0
    if cash_col and not acct2.empty:
        cash_balance = float(to_num(acct2[cash_col]).iloc[-1])

    total_assets = current_invested_value + cash_balance

    # ===== 資產績效：扣除後續新增本金，避免把「入金」誤當成「報酬」 =====
    # 優先使用帳戶紀錄的「台幣本金」作為累積投入本金；若沒有，才退回「投入金額 + 現金」。
    principal_candidates = ["台幣本金", "TWD本金", "本金(台幣)", "初始資金", "本金"]
    principal_col = _first_existing_col(acct2, principal_candidates)

    first_date = acct2[date_col].iloc[0] if not acct2.empty else pd.Timestamp.today().normalize()
    last_date = acct2[date_col].iloc[-1] if not acct2.empty else pd.Timestamp.today().normalize()

    initial_capital = 0.0
    total_contribution = 0.0
    if not acct2.empty:
        if principal_col:
            principal_series = to_num(acct2[principal_col])
            initial_capital = float(principal_series.iloc[0])
            total_contribution = float(principal_series.iloc[-1])
        elif cash_col:
            cash_series = to_num(acct2[cash_col])
            initial_capital = float(cash_series.iloc[0])
            total_contribution = total_invested + cash_balance

    # 若帳戶紀錄抓不到本金，保守退回「目前投入 + 現金」避免除以 0。
    if total_contribution <= 0:
        total_contribution = total_invested + cash_balance
    if initial_capital <= 0:
        initial_capital = total_contribution

    capital_usage = current_invested_value / total_assets if total_assets > 0 else 0.0

    # 資產報酬率：用目前總資產扣掉累積本金，只看真正增值。
    asset_gain = total_assets - total_contribution
    asset_return = (asset_gain / total_contribution) if total_contribution > 0 else 0.0

    # 年化資產報酬：用扣本金後的資產報酬做近似年化；若期間太短，避免失真就顯示 None。
    years = max((last_date - first_date).days / 365.0, 0.0)
    asset_cagr = None
    if years >= 0.25 and total_contribution > 0 and total_assets > 0:
        asset_cagr = (total_assets / total_contribution) ** (1 / years) - 1

    cfs = build_investment_cashflows(richard)
    irr = calc_xirr(cfs)

    # ===== 10年預測用：納入資金使用率後的有效年化報酬率 =====
    # 投資部位用 IRR；現金部位目前先視為 0% 報酬。若未來要納入定存/貨幣基金，可在這裡加入 cash_rate。
    investment_rate = irr if irr is not None and np.isfinite(irr) else 0.08
    cash_rate = 0.00
    effective_return_rate = investment_rate * capital_usage + cash_rate * (1 - capital_usage)

    # ===== 進階版 10年預測用：以「有效報酬 = IRR × 資金使用率」為來源，再做長期收斂 =====
    # raw effective_return_rate 反映目前短期績效；projection_base_rate 是拿來做長期預測的動態基準。
    # 預設用 0.5 收斂係數，避免短期績效直接外推長期造成過度樂觀。
    projection_convergence = 0.50
    projection_min_rate = 0.03
    projection_max_rate = 0.15
    projection_base_rate_raw = effective_return_rate * projection_convergence
    projection_base_rate = min(max(projection_base_rate_raw, projection_min_rate), projection_max_rate)

    # Alpha：投資 IRR 與整體資產年化報酬的落差，用來觀察資金使用效率是否拖累成果。
    alpha = None
    if irr is not None and asset_cagr is not None:
        alpha = irr - asset_cagr

    return {
        "irr": irr,
        "current_invested_value": current_invested_value,
        "cash_balance": cash_balance,
        "total_assets": total_assets,
        "initial_capital": initial_capital,
        "total_contribution": total_contribution,
        "asset_gain": asset_gain,
        "asset_return": asset_return,
        "asset_cagr": asset_cagr,
        "capital_usage": capital_usage,
        "effective_return_rate": effective_return_rate,
        "projection_convergence": projection_convergence,
        "projection_base_rate_raw": projection_base_rate_raw,
        "projection_base_rate": projection_base_rate,
        "projection_min_rate": projection_min_rate,
        "projection_max_rate": projection_max_rate,
        "alpha": alpha,
        "simple_ret": simple_ret,
    }

def make_projection_chart(
    start_assets: float,
    effective_rate: float | None,
    annual_add: float = 0.0,
    convergence: float = 0.50,
    min_rate: float = 0.03,
    max_rate: float = 0.15,
    years: int = 20,
):
    """
    進階版長期資產預測：
    - 來源：有效年化報酬率 = IRR × 資金使用率 + 現金報酬 × 現金比例。
    - 長期預測基準：有效報酬 × 收斂係數，再套用上下限，避免短期 IRR 過度外推。
    - 三情境：保守 / 基準 / 樂觀，皆由動態基準推導，不再是固定寫死。
    """
    if start_assets <= 0:
        return None
    if effective_rate is None or not np.isfinite(effective_rate):
        effective_rate = 0.08

    dynamic_base_raw = effective_rate * convergence
    base_rate = min(max(dynamic_base_raw, min_rate), max_rate)
    conservative_rate = min(max(base_rate * 0.70, min_rate), max_rate)
    optimistic_rate = min(max(base_rate * 1.30, min_rate), max_rate)

    scenarios = {
        f"保守 {conservative_rate*100:.1f}%": conservative_rate,
        f"基準 {base_rate*100:.1f}%（有效報酬×{convergence:.2f}）": base_rate,
        f"樂觀 {optimistic_rate*100:.1f}%": optimistic_rate,
    }
    rows = []
    for name, r in scenarios.items():
        value = start_assets
        for y in range(0, years + 1):
            if y == 0:
                value = start_assets
            else:
                value = value * (1 + r) + annual_add
            rows.append({"年度": y, "情境": name, "預測資產": value})
    dfp = pd.DataFrame(rows)
    fig = px.line(
        dfp,
        x="年度",
        y="預測資產",
        color="情境",
        markers=True,
        title=f"{years}年資產預測（有效報酬動態基準 + 長期收斂）",
    )
    fig.update_layout(height=520, yaxis_title="資產金額", legend_title_text="")
    fig.update_yaxes(tickformat=",")
    return fig

# ====== 資產配置（移植自 app01：更穩定的『分析』區塊解析） ======
def _clean_text(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return str(x).strip()

def extract_allocation_from_analysis_block(richard: pd.DataFrame):
    """
    依你附圖的『分析』區塊抓資產配置（更貼近你的版型）：
    - 先找到含『分析』字樣的列（就算是合併儲存格也可）
    - 在該列附近分別找出『分類』欄與『參考現值』（若沒有則用『成交金額』）欄
    - 從分類資料列一路讀到『總計』為止
    - 回傳 DataFrame: 分類 / 金額
    """
    arr = richard.to_numpy(dtype=object)
    nrows, ncols = arr.shape

    def row_has(token: str, r: int) -> bool:
        for c in range(ncols):
            if _clean_text(arr[r, c]) == token:
                return True
        return False

    def find_first_row(token: str):
        for r in range(nrows):
            for c in range(ncols):
                if _clean_text(arr[r, c]) == token:
                    return r
        return None

    def find_token_near(token: str, r0: int, r1: int):
        for r in range(max(0, r0), min(nrows, r1 + 1)):
            for c in range(ncols):
                if _clean_text(arr[r, c]) == token:
                    return r, c
        return None, None

    # 1) 找『分析』作為區塊錨點
    anchor_r = find_first_row("分析")
    if anchor_r is None:
        return None

    # 2) 在錨點附近找『分類』欄位置
    cat_r, cat_c = find_token_near("分類", anchor_r - 3, anchor_r + 10)
    if cat_r is None:
        return None

    # 3) 在錨點附近找『參考現值』（或『成交金額』）欄位置
    val_r, val_c = find_token_near("參考現值", anchor_r - 3, anchor_r + 10)
    val_key = "參考現值"
    if val_r is None:
        val_r, val_c = find_token_near("成交金額", anchor_r - 3, anchor_r + 10)
        val_key = "成交金額"
    if val_r is None:
        return None

    # 4) 找分類資料起始列：分類表頭下一列往下找第一個非空分類
    start_r = cat_r + 1
    while start_r < nrows:
        cat = _clean_text(arr[start_r, cat_c])
        if cat and cat not in ["分類"]:
            break
        start_r += 1

    items = []
    for r in range(start_r, nrows):
        cat = _clean_text(arr[r, cat_c])
        if not cat:
            continue
        if cat == "總計":
            break

        raw = arr[r, val_c]
        val = pd.to_numeric(str(raw).replace(",", "").strip(), errors="coerce")
        if pd.isna(val) or val == 0:
            continue

        items.append({"分類": cat, "金額": float(val)})

    if not items:
        return None

    return pd.DataFrame(items)

def make_allocation_pie_from_analysis(richard: pd.DataFrame):
    alloc = extract_allocation_from_analysis_block(richard)
    if alloc is None or alloc.empty:
        return None

    fig = px.pie(alloc, names="分類", values="金額", title="資產配置（依 Excel『分析』區塊）")
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=520)
    return fig


def make_holding_distribution_pie(richard: pd.DataFrame, market: str | None = None):
    """
    持股分布圓餅圖：
    - 依 Excel 交易明細的「參考現值」欄位計算
    - 以「股票代號 + 股票名稱」彙總，同一檔股票多筆買進會合併
    - 只納入參考現值 > 0 的持股，避免已賣出或空白列被算入
    - market=None：全部持股；market="台股"：台股 + 台股 ETF；market="美股"：美股
    """
    value_col = "參考現值"
    cat_col = "分類"
    code_col = "股票代號" if "股票代號" in richard.columns else None
    name_col = "股票名稱" if "股票名稱" in richard.columns else ("股票" if "股票" in richard.columns else None)

    if value_col not in richard.columns or name_col is None:
        return None

    df = _filter_trade_like_rows(richard).copy()

    # 依分類切出台股 / 美股，避免台股與美股混在同一張圖
    if market is not None:
        if cat_col not in df.columns:
            return None
        cat = df[cat_col].astype(str).str.strip()
        if market == "台股":
            df = df[cat.isin(["台股", "台股 ETF"])]
        elif market == "美股":
            df = df[cat == "美股"]
        else:
            return None

    df[value_col] = to_num(df[value_col])
    df = df[df[value_col] > 0]

    if df.empty:
        return None

    df[name_col] = df[name_col].astype(str).str.strip()
    df = df[(df[name_col] != "") & (df[name_col].str.lower() != "nan")]

    # 顯示名稱：有股票代號就用「代號 名稱」，避免同名或 ETF 名稱不清楚
    if code_col is not None:
        df[code_col] = df[code_col].astype(str).str.strip()
        df["持股"] = np.where(
            (df[code_col] != "") & (df[code_col].str.lower() != "nan"),
            df[code_col] + " " + df[name_col],
            df[name_col]
        )
    else:
        df["持股"] = df[name_col]

    agg = (
        df.groupby("持股", dropna=True)[value_col]
          .sum()
          .reset_index()
          .sort_values(value_col, ascending=False)
    )

    if agg.empty:
        return None

    title = "持股分布（依參考現值）" if market is None else f"持股分布（{market}，依參考現值）"
    fig = px.pie(
        agg,
        names="持股",
        values=value_col,
        title=title,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=520)
    return fig


def _clean_stock_code_for_display(x) -> str:
    """
    將 Excel 讀進來的股票代號清成一致格式：
    - 2330.0 -> 2330
    - 2330 -> 2330
    - QQQ -> QQQ
    目的：避免同一檔股票因代號格式不同而被拆成兩筆。
    """
    s = _clean_text(x)
    if not s or s.lower() == "nan":
        return ""
    if re.fullmatch(r"\d+\.0+", s):
        return s.split(".")[0]
    return s

def build_holding_analysis_table(richard: pd.DataFrame, market: str | None = None):
    """
    建立目前持股的共同分析資料：
    - 只計入參考現值 > 0 的目前持股
    - 同一股票多筆買進自動合併
    - 持股投報率優先使用 Excel「投資報酬率」欄位，依成交金額加權
    - 對總資產貢獻 = 持股比重 × 持股投報率
    """
    required_cols = ["成交金額", "參考現值"]
    if any(c not in richard.columns for c in required_cols):
        return None

    code_col = "股票代號" if "股票代號" in richard.columns else None
    name_col = "股票名稱" if "股票名稱" in richard.columns else ("股票" if "股票" in richard.columns else None)
    cat_col = "分類" if "分類" in richard.columns else None
    if name_col is None:
        return None

    df = _filter_trade_like_rows(richard).copy()

    if market is not None:
        if cat_col is None:
            return None
        cat = df[cat_col].astype(str).str.strip()
        if market == "台股":
            df = df[cat.isin(["台股", "台股 ETF"])]
        elif market == "美股":
            df = df[cat == "美股"]
        else:
            return None

    numeric_cols = ["股數", "成交金額", "參考現值", "未實現損益", "除息", "投資報酬率"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = to_num(df[c])
        else:
            df[c] = 0.0

    df = df[df["參考現值"] > 0].copy()
    if df.empty:
        return None

    df[name_col] = df[name_col].astype(str).str.strip()
    df = df[(df[name_col] != "") & (df[name_col].str.lower() != "nan")].copy()
    if df.empty:
        return None

    if code_col is not None:
        df[code_col] = df[code_col].apply(_clean_stock_code_for_display)
        df["標的"] = np.where(
            (df[code_col] != "") & (df[code_col].str.lower() != "nan"),
            df[code_col] + " " + df[name_col],
            df[name_col],
        )
    else:
        df["標的"] = df[name_col]

    df["分類顯示"] = df[cat_col].astype(str).str.strip() if cat_col else ""
    df["投報率加權值"] = df["投資報酬率"] * df["成交金額"]

    # 同一檔股票只依「標的」合併，避免同股票因分類或格式差異被拆成多筆投報率。
    agg = (
        df.groupby("標的", dropna=False)
          .agg(
              分類=("分類顯示", lambda s: " / ".join(sorted(set([x for x in s.astype(str).str.strip() if x and x.lower() != "nan"])))),
              股數=("股數", "sum"),
              投入成本=("成交金額", "sum"),
              參考現值=("參考現值", "sum"),
              未實現損益=("未實現損益", "sum"),
              除息=("除息", "sum"),
              投報率加權值=("投報率加權值", "sum"),
          )
          .reset_index()
    )
    agg = agg[agg["投入成本"] > 0].copy()
    if agg.empty:
        return None

    fallback_return = (agg["未實現損益"] + agg["除息"]) / agg["投入成本"]
    weighted_return = agg["投報率加權值"] / agg["投入成本"]
    agg["持股投報率"] = np.where(np.isfinite(weighted_return), weighted_return, fallback_return)
    agg["持股損益"] = agg["持股投報率"] * agg["投入成本"]
    agg["持股比重"] = agg["參考現值"] / agg["參考現值"].sum()
    agg["對總資產貢獻"] = agg["持股比重"] * agg["持股投報率"]
    agg["損益狀態"] = np.where(agg["持股投報率"] >= 0, "獲利", "虧損")
    return agg.sort_values("對總資產貢獻", ascending=False)


def select_holding_analysis_market(key: str):
    market_label = st.radio(
        "分析篩選",
        ["台股（含台股 ETF）", "美股", "全部"],
        horizontal=True,
        key=key,
    )
    if market_label.startswith("台股"):
        return "台股"
    if market_label == "美股":
        return "美股"
    return None


def render_holding_analysis_summary(table: pd.DataFrame):
    total_cost = float(table["投入成本"].sum())
    total_value = float(table["參考現值"].sum())
    total_pnl = float(table["持股損益"].sum())
    total_return = total_pnl / total_cost if total_cost > 0 else 0.0
    top_contributor = table.sort_values("對總資產貢獻", ascending=False).iloc[0]
    largest_weight = table.sort_values("持股比重", ascending=False).iloc[0]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("目前持股成本", f"{total_cost:,.0f}")
    m2.metric("目前持股現值", f"{total_value:,.0f}")
    m3.metric("目前持股損益", f"{total_pnl:,.0f}", f"{total_return*100:.2f}%")
    m4.metric("最大影響 / 最大部位", f"{top_contributor['標的']}", f"最大部位：{largest_weight['標的']}")


def render_holding_analysis_table(table: pd.DataFrame, height: int = 360):
    table_view = table[[
        "標的", "分類", "股數", "投入成本", "參考現值", "持股比重",
        "持股投報率", "對總資產貢獻", "持股損益", "未實現損益", "除息"
    ]].copy()

    st.dataframe(
        table_view.style.format({
            "股數": "{:,.0f}",
            "投入成本": "{:,.0f}",
            "參考現值": "{:,.0f}",
            "持股比重": "{:.2%}",
            "持股投報率": "{:.2%}",
            "對總資產貢獻": "{:.2%}",
            "持股損益": "{:,.0f}",
            "未實現損益": "{:,.0f}",
            "除息": "{:,.0f}",
        }),
        use_container_width=True,
        height=height,
    )



def render_full_holding_analysis(richard: pd.DataFrame):
    st.subheader("持股健康度完整分析")
    market = select_holding_analysis_market("full_holding_market")
    table = build_holding_analysis_table(richard, market=market)
    if table is None or table.empty:
        st.info("沒有可用的目前持股分析資料。")
        return

    render_holding_analysis_summary(table)

    st.markdown("#### 1. 持股比重 × 投報率 Bubble Chart")
    size_mode = st.radio("氣泡大小", ["參考現值", "投入成本"], horizontal=True, key="full_bubble_size_mode")
    bubble_fig = px.scatter(
        table,
        x="持股比重",
        y="持股投報率",
        size=size_mode,
        color="損益狀態",
        color_discrete_map={"獲利": "#1f77b4", "虧損": "#ff99c8"},
        text="標的",
        hover_data={
            "標的": True,
            "分類": True,
            "投入成本": ":,.0f",
            "參考現值": ":,.0f",
            "持股比重": ":.2%",
            "持股投報率": ":.2%",
            "對總資產貢獻": ":.2%",
            "持股損益": ":,.0f",
            "損益狀態": False,
        },
        title="持股比重 × 投報率（看資金大小與報酬效率）",
    )
    bubble_fig.update_traces(textposition="top center")
    bubble_fig.update_layout(height=560, legend_title_text="")
    bubble_fig.update_xaxes(title="持股比重", tickformat=".0%", zeroline=True, zerolinewidth=1, zerolinecolor="gray")
    bubble_fig.update_yaxes(title="持股投報率", tickformat=".0%", zeroline=True, zerolinewidth=1, zerolinecolor="gray")
    st.plotly_chart(bubble_fig, use_container_width=True)

    st.markdown("#### 2. 對總資產貢獻排行")
    df = table.sort_values("對總資產貢獻", ascending=True)
    bar_colors = np.where(df["對總資產貢獻"] >= 0, "#1f77b4", "#ff99c8")
    contribution_fig = go.Figure()
    contribution_fig.add_bar(
        x=df["對總資產貢獻"],
        y=df["標的"],
        orientation="h",
        marker_color=bar_colors,
        text=df["對總資產貢獻"].map(lambda v: f"{v*100:.2f}%"),
        textposition="outside",
    )
    contribution_fig.update_layout(
        title="真正拉動或拖累整體績效的持股",
        height=max(420, min(700, 120 + len(df) * 38)),
        showlegend=False,
        margin=dict(t=70, r=90),
        xaxis_title="對總資產貢獻",
        yaxis_title="",
    )
    contribution_fig.update_xaxes(tickformat=".0%", zeroline=True, zerolinewidth=1, zerolinecolor="gray")
    st.plotly_chart(contribution_fig, use_container_width=True)

    st.markdown("#### 3. 資金效率排行榜")
    sort_option = st.radio(
        "表格排序",
        ["對總資產貢獻", "持股投報率", "持股比重", "參考現值", "持股損益"],
        horizontal=True,
        key="full_sort_option",
    )
    render_holding_analysis_table(table.sort_values(sort_option, ascending=False), height=520)


def _filter_trade_like_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    避免把 Excel 底部『分析/總計』等彙總區塊算進交易/持股。
    主要策略：要求股票名稱或代號必須是有效值，並排除明顯的標題字樣。
    """
    d = df.copy()
    code_col = "股票代號" if "股票代號" in d.columns else None
    name_col = "股票名稱" if "股票名稱" in d.columns else ("股票" if "股票" in d.columns else None)

    if code_col:
        code = d[code_col].astype(str).str.strip()
        mask = code.notna() & (code != "") & (code.str.lower() != "nan")
        mask &= ~code.isin(["分類", "總計", "分析"])
        d = d[mask]
    elif name_col:
        name = d[name_col].astype(str).str.strip()
        mask = name.notna() & (name != "") & (name.str.lower() != "nan")
        mask &= ~name.isin(["分類", "總計", "分析"])
        d = d[mask]

    return d

def _infer_market_from_code_or_name(code: str, name: str) -> str:
    code = _clean_text(code)
    name = _clean_text(name)

    if code:
        if code.isdigit():
            return "台股"
        if any(ch.isalpha() for ch in code):
            return "美股"

    if any(ch.isalpha() for ch in name):
        return "美股"
    return "台股"

@st.cache_data(show_spinner=False)
def load_data(xlsx_path: Path, mtime: float):
    xls = pd.ExcelFile(xlsx_path)
    richard = pd.read_excel(xls, "Richard")
    acct = pd.read_excel(xls, "Richard-帳戶紀錄")
    return richard, acct

def compute_kpi(richard: pd.DataFrame):
    """
    KPI 統計只計入「有分類」的列（你說的 AB 欄有做分類）。
    - 用欄位名「分類」判斷是否有分類（去除空白後不可為空）
    - 同時排除 Excel 底部「分析/總計」區塊（透過 _filter_trade_like_rows）
    """
    df = richard.copy()

    # 排除非交易列
    if "_filter_trade_like_rows" in globals():
        try:
            df = _filter_trade_like_rows(df)
        except Exception:
            pass

    # 只保留「分類」有值的列
    if "分類" in df.columns:
        cat = df["分類"].astype(str).str.strip()
        df = df[cat.notna() & (cat != "") & (cat.str.lower() != "nan")]

    invested_col = "成交金額"
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"

    invested = to_num(df[invested_col]) if invested_col in df.columns else pd.Series([0.0])
    realized = to_num(df[realized_col]) if realized_col in df.columns else pd.Series([0.0])
    unrealized = to_num(df[unrealized_col]) if unrealized_col in df.columns else pd.Series([0.0])

    total_invested = float(invested.sum())
    total_realized = float(realized.sum())
    total_unrealized = float(unrealized.sum())
    total_pnl = total_realized + total_unrealized
    ret = (total_pnl / total_invested) if total_invested else 0.0

    return total_invested, total_realized, total_unrealized, total_pnl, ret



def make_rank_chart_by_market(richard: pd.DataFrame, market: str, top_n: int = 10):
    """
    股票別總損益 Top N（嚴格依『分類』欄位過濾）：
    - 美股：只取 分類 == "美股"
    - 台股：取 分類 in {"台股", "台股 ETF"}
    其他分類（如台幣活儲/美金儲蓄/基金等）不納入股票 Top 圖表。

    顯示規則：
    - 總損益 >= 0：藍色
    - 總損益 < 0：紅色
    """
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"
    cat_col = "分類"

    df = _filter_trade_like_rows(richard)

    name_col = "股票名稱" if "股票名稱" in df.columns else ("股票" if "股票" in df.columns else None)
    if name_col is None:
        return None

    # 嚴格依分類過濾
    if cat_col in df.columns:
        cat = df[cat_col].astype(str).str.strip()
        if market == "美股":
            df = df[cat == "美股"]
        else:  # 台股
            df = df[cat.isin(["台股", "台股 ETF"])]
    else:
        # 沒有分類欄就不畫（避免誤判）
        return None

    if df.empty:
        return None

    # 計算總損益
    df["已實現損益"] = to_num(df[realized_col]) if realized_col in df.columns else 0.0
    df["未實現損益"] = to_num(df[unrealized_col]) if unrealized_col in df.columns else 0.0
    df["總損益"] = df["已實現損益"] + df["未實現損益"]

    agg = (
        df.groupby(name_col, dropna=True)["總損益"]
          .sum()
          .sort_values(ascending=False)
          .head(top_n)
          .reset_index()
          .rename(columns={name_col: "股票", "總損益": "總損益"})
    )

    if agg.empty:
        return None

    # 依正負設定顏色
    bar_colors = np.where(agg["總損益"] >= 0, "#1f77b4", "#d62728")
    bar_text = agg["總損益"].map(lambda v: f"{v:,.0f}")

    fig = go.Figure()
    fig.add_bar(
        x=agg["總損益"],
        y=agg["股票"],
        orientation="h",
        name="總損益",
        marker_color=bar_colors,
        text=bar_text,
        textposition="outside",
    )

    fig.update_layout(
        title=f"{market} 股票別總損益 Top {top_n}",
        height=520,
        margin=dict(t=70),
        showlegend=False,
    )
    fig.update_xaxes(title="總損益", zeroline=True, zerolinewidth=1, zerolinecolor="gray")
    fig.update_yaxes(title="股票", categoryorder="total ascending")
    return fig




def make_timeseries(acct: pd.DataFrame):
    """
    台幣現金水位圖：
    - 同時畫兩條線：台幣現金水位（若有） + 台幣本金（若有）
    - 若找不到「台幣現金水位」欄位，會退回畫單線（台幣本金/結餘）
    """
    date_col = "日期" if "日期" in acct.columns else acct.columns[0]
    df0 = acct.copy()
    df0[date_col] = pd.to_datetime(df0[date_col], errors="coerce")
    df0 = df0.dropna(subset=[date_col]).sort_values(date_col)

    # 欄位候選（依你口語：台幣本金 vs 台幣現金水位）
    principal_candidates = ["台幣本金", "TWD本金", "本金(台幣)"]
    cash_candidates = ["台幣現金水位", "台幣現金", "現金水位", "台幣結餘", "結餘"]

    principal_col = next((c for c in principal_candidates if c in df0.columns), None)
    cash_col = next((c for c in cash_candidates if c in df0.columns), None)

    if principal_col is None and cash_col is None:
        return None

    # 組成長表方便畫多線
    parts = []
    if cash_col is not None:
        tmp = df0[[date_col, cash_col]].copy()
        tmp["值"] = to_num(tmp[cash_col])
        tmp["項目"] = "台幣現金水位"
        parts.append(tmp[[date_col, "值", "項目"]])

    if principal_col is not None:
        tmp = df0[[date_col, principal_col]].copy()
        tmp["值"] = to_num(tmp[principal_col])
        tmp["項目"] = "台幣本金"
        parts.append(tmp[[date_col, "值", "項目"]])

    df = pd.concat(parts, ignore_index=True)

    # 若只有一條線，就維持原本標題語意
    if df["項目"].nunique() == 1:
        only = df["項目"].iloc[0]
        fig = px.line(df, x=date_col, y="值", title=f"台幣現金水位圖（來源：帳戶紀錄 / {only}）")
        fig.update_layout(height=450, yaxis_title=only, legend_title_text="")
        return fig

    fig = px.line(
        df,
        x=date_col,
        y="值",
        color="項目",
        title="台幣現金水位圖（台幣現金水位 vs 台幣本金）"
    )
    fig.update_layout(height=450, legend_title_text="")
    fig.update_yaxes(title_text="金額")
    return fig


def make_yearly_return_combo(richard: pd.DataFrame, mode: str = "已實現"):
    """
    直條：年度收益
    折線：累積收益（含數字標籤）
    mode:
      - "已實現"：用「賣出日期」年度彙總「已實現損益」
      - "含未實現"：已實現 + 未實現。未實現（無賣出日期）歸入今年。
    """
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"
    sell_date_col = "賣出日期" if "賣出日期" in richard.columns else None
    if sell_date_col is None or realized_col not in richard.columns:
        return None

    df = _filter_trade_like_rows(richard).copy()
    df[sell_date_col] = pd.to_datetime(df[sell_date_col], errors="coerce")

    sold = df[df[sell_date_col].notna()].copy()
    sold["年度"] = sold[sell_date_col].dt.year
    sold["年度收益"] = to_num(sold[realized_col])
    yearly_realized = sold.groupby("年度", as_index=False)["年度收益"].sum().sort_values("年度")

    if mode == "含未實現":
        open_pos = df[df[sell_date_col].isna()].copy()
        if unrealized_col in open_pos.columns and not open_pos.empty:
            current_year = datetime.date.today().year
            open_pos["年度"] = current_year
            open_pos["年度收益"] = to_num(open_pos[unrealized_col])
            yearly_unrealized = open_pos.groupby("年度", as_index=False)["年度收益"].sum().sort_values("年度")

            yearly = pd.concat([yearly_realized, yearly_unrealized], ignore_index=True)
            yearly = yearly.groupby("年度", as_index=False)["年度收益"].sum().sort_values("年度")
        else:
            yearly = yearly_realized
    else:
        yearly = yearly_realized

    if yearly.empty:
        return None

    yearly["累積收益"] = yearly["年度收益"].cumsum()
    yearly["累積標籤"] = yearly["累積收益"].map(lambda v: f"{v:,.0f}")

    fig = go.Figure()

    # 年度收益：正值/負值用不同顏色（獲利/虧損一眼看懂）
    bar_colors = np.where(yearly["年度收益"] >= 0, "#1f77b4", "#d62728")
    bar_text = yearly["年度收益"].map(lambda v: f"{v:,.0f}")
    fig.add_bar(
        x=yearly["年度"],
        y=yearly["年度收益"],
        name="年度收益",
        marker_color=bar_colors,
        text=bar_text,
        textposition="outside",
        yaxis="y",
    )

    fig.add_trace(go.Scatter(
        x=yearly["年度"], y=yearly["累積收益"],
        name="累積收益",
        mode="lines+markers+text",
        text=yearly["累積標籤"],
        textposition="top center",
        yaxis="y2"
    ))

    fig.update_layout(
        title=f"投資收益（年度 vs 累積）— {mode}",
        xaxis=dict(title="年度"),
        yaxis=dict(title="年度收益"),
        yaxis2=dict(title="累積收益", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        height=520,
        margin=dict(t=80)
    )
    return fig

# ====== 側邊欄：管理者上傳（只有輸入密碼才會出現） ======
view_mode = st.sidebar.radio("顯示內容", ["圖表", "交易明細"], index=0)
#st.sidebar.caption(f"BUILD_TAG: {BUILD_TAG}")


def render_trade_details(richard: pd.DataFrame):
    """右側顯示交易明細（可切換台股/美股）"""
    st.subheader("交易明細")

    if "分類" not in richard.columns:
        st.warning("找不到『分類』欄位，無法依台股/美股切換。")
        st.dataframe(richard, use_container_width=True)
        return

    market = st.radio("明細篩選", ["台股（含台股 ETF）", "美股", "全部"], horizontal=True)

    df = richard.copy()
    # 排除非交易列（分析/總計）
    try:
        df = _filter_trade_like_rows(df)
    except Exception:
        pass

    cat = df["分類"].astype(str).str.strip()
    if market.startswith("台股"):
        df = df[cat.isin(["台股", "台股 ETF"])]
    elif market == "美股":
        df = df[cat == "美股"]
    else:
        df = df[cat.notna() & (cat != "") & (cat.str.lower() != "nan")]

    # 常用欄位排序（有就顯示）
    preferred_cols = [
        "買進日期","賣出日期","股票代號","股票名稱","分類",
        "股數","買進價","賣出價",
        "成交金額","手續費","交易稅","除息",
        "已實現損益","未實現損益","參考現值",
        "買進原因","賣出原因","備註"
    ]
    cols = [c for c in preferred_cols if c in df.columns]
    if cols:
        df_view = df[cols]
    else:
        df_view = df

    # 日期欄轉型（如果存在）
    for dc in ["買進日期", "賣出日期"]:
        if dc in df_view.columns:
            df_view[dc] = pd.to_datetime(df_view[dc], errors="coerce")

    st.dataframe(df_view, use_container_width=True, height=560)

    # 下載
    csv = df_view.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("下載明細 CSV", data=csv, file_name="trades.csv", mime="text/csv")


st.title("Richard 的投資儀表板")
if XLSX_PATH.exists():
    st.caption(f"資料最後更新時間：{pd.to_datetime(XLSX_PATH.stat().st_mtime, unit='s')}")



# 嘗試自動同步：首次沒有檔案，或按了「重新載入資料」才會從 OneDrive 抓
# 嘗試自動同步：首次沒有檔案，或按了「重新載入」才會從雲端抓（Google Drive 優先，其次 OneDrive）
# 首次沒有檔案時，才嘗試從雲端抓一次（不顯示左側設定按鈕）
if not XLSX_PATH.exists():
    fetched = False
    if st.secrets.get("GOOGLE_SHEETS_URL") or st.secrets.get("GDRIVE_FILE_URL"):
        fetched = ensure_excel_from_gdrive(XLSX_PATH)
    if (not fetched) and st.secrets.get("ONEDRIVE_XLSX_URL"):
        fetched = ensure_excel_from_onedrive(XLSX_PATH)

    if fetched:
        st.cache_data.clear()
if not XLSX_PATH.exists():
    st.error("找不到 data/family_data.xlsx。請由管理者登入後上傳 Excel。")
    st.stop()

richard, acct = load_data(XLSX_PATH, XLSX_PATH.stat().st_mtime)

# ====== KPI ======
total_invested, total_realized, total_unrealized, total_pnl, ret = compute_kpi(richard)
adv = compute_advanced_metrics(richard, acct)

# ====== KPI 說明小工具 ======
# Streamlit 的 metric 支援 help 參數；滑鼠移到指標旁的 ? 可看到公式與用途。
def kpi_metric(col, label: str, value: str, help_text: str):
    try:
        col.metric(label, value, help=help_text)
    except TypeError:
        # 舊版 Streamlit 若不支援 help，仍可正常顯示數值。
        col.metric(label, value)

alpha_text = "資料不足" if adv["alpha"] is None else f"{adv['alpha']*100:,.2f}%"
irr_text = "資料不足" if adv["irr"] is None else f"{adv['irr']*100:,.2f}%"
asset_cagr_text = "資料不足" if adv["asset_cagr"] is None else f"{adv['asset_cagr']*100:,.2f}%"

c1, c2, c3, c4, c5 = st.columns(5)
kpi_metric(c1, "投入金額", f"{total_invested:,.0f}", "交易明細中的累積成交金額。公式：Σ 成交金額。用途：作為投資部位的投入本金基準。")
kpi_metric(c2, "已實現損益", f"{total_realized:,.0f}", "已賣出部位已經落袋的損益。公式：Σ 已實現損益。")
kpi_metric(c3, "未實現損益", f"{total_unrealized:,.0f}", "尚未賣出部位依目前參考現值估算的浮動損益。公式：Σ 未實現損益。")
kpi_metric(c4, "總損益", f"{total_pnl:,.0f}", "整體投資損益。公式：已實現損益 + 未實現損益。")
kpi_metric(c5, "報酬率", f"{ret*100:,.2f}%", "投資部位的簡單報酬率，不含時間因素。公式：總損益 ÷ 投入金額。")

c6, c7, c8, c9, c10 = st.columns(5)
kpi_metric(c6, "年化報酬率 IRR", irr_text, "投資現金流的年化報酬率，考慮買進日、賣出日與未賣出部位參考現值。用途：衡量投資操作能力。")
kpi_metric(c7, "總資產", f"{adv['total_assets']:,.0f}", "目前總資產。公式：投資部位現值 + 現金水位。")
kpi_metric(c8, "年化資產報酬", asset_cagr_text, "整體財富的年化成長速度，已扣除累積本金影響。公式概念：(總資產 ÷ 累積本金)^(1/年數) - 1。用途：衡量真正變有錢的速度。")
kpi_metric(c9, "資金使用率", f"{adv['capital_usage']*100:,.2f}%", "目前有多少資產實際投入市場。公式：投資部位現值 ÷ 總資產。")
kpi_metric(c10, "現金水位", f"{adv['cash_balance']:,.0f}", "帳戶紀錄中最新一筆台幣現金水位。用途：評估可加碼資金與防守能力。")

c11, c12, c13, c14, c15 = st.columns(5)
kpi_metric(c11, "累積本金", f"{adv['total_contribution']:,.0f}", "目前用來衡量資產成長的本金基準。通常取帳戶紀錄中的資金累積值，避免把後續入金誤算成投資報酬。")
kpi_metric(c12, "資產增值", f"{adv['asset_gain']:,.0f}", "扣除累積本金後真正增加的資產。公式：總資產 - 累積本金。")
kpi_metric(c13, "資產報酬率", f"{adv['asset_return']*100:,.2f}%", "整體資產相對累積本金的累積報酬，不年化。公式：資產增值 ÷ 累積本金。")
kpi_metric(c14, "有效年化報酬率", f"{adv['effective_return_rate']*100:,.2f}%", "把資金使用率納入後的投資效率。公式：IRR × 資金使用率。用途：避免只看投資部位 IRR 而忽略閒置現金。")
kpi_metric(c15, "IRR-資產年化差", alpha_text, "投資部位年化報酬與整體資產年化報酬的差距。公式：IRR - 年化資產報酬。差距越大，通常代表現金閒置或資金配置效率仍有改善空間。")

st.caption("註：滑鼠移到各項指標旁的說明圖示可查看公式與用途；資產預測來源為『有效年化報酬率 = IRR × 資金使用率』，再乘以收斂係數並套用上下限，避免短期 IRR 直接外推。")
st.divider()

if view_mode == "圖表":
    # ====== 圖表順序（由上至下）：投資收益、資產配置、持股分布、台幣現金水位圖、台股Top10、美股Top10 ======
    mode = st.radio("年度收益模式", ["已實現", "含未實現"], horizontal=True)

    yearly_fig = make_yearly_return_combo(richard, mode=mode)
    if yearly_fig is not None:
        st.plotly_chart(yearly_fig, use_container_width=True)
    else:
        st.info("無法產生『投資收益（年度 vs 累積）』圖表（請確認 Excel 有『賣出日期 / 已實現損益』）。")

    st.subheader("資產預測")
    default_monthly = 0
    monthly_add = st.number_input("每月新增投入金額（可自行調整）", min_value=0, value=default_monthly, step=1000)

    projection_years = st.radio("預測年數", [10, 20, 30, 40], horizontal=True, index=1)

    with st.expander("進階預測參數（可調整預測基準）", expanded=False):
        projection_convergence = st.slider(
            "有效報酬收斂係數",
            min_value=0.20,
            max_value=1.00,
            value=float(adv["projection_convergence"]),
            step=0.05,
            help="1.00 代表完全採用目前有效報酬；0.50 代表只採用一半，較適合長期預測。",
        )
        max_projection_rate_pct = st.slider(
            "預測報酬率上限",
            min_value=8.0,
            max_value=25.0,
            value=float(adv["projection_max_rate"] * 100),
            step=0.5,
            help="避免短期高 IRR 讓長期預測過度膨脹。",
        )
        min_projection_rate_pct = st.slider(
            "預測報酬率下限",
            min_value=0.0,
            max_value=8.0,
            value=float(adv["projection_min_rate"] * 100),
            step=0.5,
        )

        preview_base_raw = adv["effective_return_rate"] * projection_convergence
        preview_base = min(max(preview_base_raw, min_projection_rate_pct / 100), max_projection_rate_pct / 100)
        st.write(
            f"目前有效年化報酬率：{adv['effective_return_rate']*100:.2f}% → "
            f"收斂後原始基準：{preview_base_raw*100:.2f}% → "
            f"套用上下限後基準：{preview_base*100:.2f}%"
        )

    proj_fig = make_projection_chart(
        adv["total_assets"],
        adv["effective_return_rate"],
        annual_add=monthly_add * 12,
        convergence=projection_convergence,
        min_rate=min_projection_rate_pct / 100,
        max_rate=max_projection_rate_pct / 100,
        years=projection_years,
    )
    if proj_fig is not None:
        st.plotly_chart(proj_fig, use_container_width=True)
    else:
        st.info("總資產資料不足，無法產生資產預測。")

    pie = make_allocation_pie_from_analysis(richard)
    if pie is not None:
        st.plotly_chart(pie, use_container_width=True)
    else:
        st.warning("找不到 Excel 內『分析』區塊（含『分類』與『參考現值』）或該區塊資料為空。")

    # ====== 持股分布（台股 / 美股分開） ======
    st.subheader("持股分布")
    hold_col1, hold_col2 = st.columns(2)

    with hold_col1:
        holding_pie_tw = make_holding_distribution_pie(richard, market="台股")
        if holding_pie_tw is not None:
            st.plotly_chart(holding_pie_tw, use_container_width=True)
        else:
            st.info("沒有找到可用的台股『參考現值』持股資料。")

    with hold_col2:
        holding_pie_us = make_holding_distribution_pie(richard, market="美股")
        if holding_pie_us is not None:
            st.plotly_chart(holding_pie_us, use_container_width=True)
        else:
            st.info("沒有找到可用的美股『參考現值』持股資料。")

    render_full_holding_analysis(richard)

    ts = make_timeseries(acct)
    if ts is not None:
        st.plotly_chart(ts, use_container_width=True)
    else:
        st.warning("帳戶紀錄缺少台幣現金相關欄位（台幣現金/台幣本金/結餘），無法畫台幣現金水位圖。")

    # ④ 台股/美股 Top10（可切換）
    top_market = st.radio("Top10 類型", ["台股（含台股 ETF）", "美股"], horizontal=True)

    if top_market.startswith("台股"):
        top_fig = make_rank_chart_by_market(richard, market="台股", top_n=10)
        if top_fig is not None:
            st.plotly_chart(top_fig, use_container_width=True)
        else:
            st.info("沒有找到可用的台股資料（Top 10）。")
    else:
        top_fig = make_rank_chart_by_market(richard, market="美股", top_n=10)
        if top_fig is not None:
            st.plotly_chart(top_fig, use_container_width=True)
        else:
            st.info("沒有找到可用的美股資料（Top 10）。")
else:
    render_trade_details(richard)
