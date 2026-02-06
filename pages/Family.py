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

def _touch_reload_flag(source: str):
    st.session_state["_reload_source"] = source


DATA_DIR = Path(__file__).parent / "data"
XLSX_PATH = DATA_DIR / "family_data.xlsx"

# ====== 管理者驗證（用 Streamlit Secrets：ADMIN_PASSWORD）======
def is_admin() -> bool:
    if st.session_state.get("is_admin", False):
        return True

    admin_pw = st.secrets.get("ADMIN_PASSWORD", "")
    if not admin_pw:
        return False

    with st.sidebar.expander("管理者登入", expanded=False):
        pw = st.text_input("管理者密碼", type="password", key="admin_pw_input")
        if st.button("登入", key="admin_login_btn"):
            if pw == admin_pw:
                st.session_state["is_admin"] = True
                st.success("已進入管理者模式")
                st.rerun()
            else:
                st.error("密碼錯誤")
    return False

# ====== 小工具：把文字數字清乾淨 ======
def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str)
         .str.replace(",", "", regex=False)
         .str.replace(" ", "", regex=False)
         .replace({"nan": None, "": None}),
        errors="coerce"
    ).fillna(0.0)




# ====== 資產配置（移植自 app01：更穩定的『分析』區塊解析） ======
def _clean_text(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return str(x).strip()

def extract_allocation_from_analysis_block(Family: pd.DataFrame):
    """
    依你附圖的『分析』區塊抓資產配置（更貼近你的版型）：
    - 先找到含『分析』字樣的列（就算是合併儲存格也可）
    - 在該列附近分別找出『分類』欄與『參考現值』（若沒有則用『成交金額』）欄
    - 從分類資料列一路讀到『總計』為止
    - 回傳 DataFrame: 分類 / 金額
    """
    arr = Family.to_numpy(dtype=object)
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

def make_allocation_pie_from_analysis(Family: pd.DataFrame):
    alloc = extract_allocation_from_analysis_block(Family)
    if alloc is None or alloc.empty:
        return None

    fig = px.pie(alloc, names="分類", values="金額", title="資產配置（依 Excel『分析』區塊）")
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=520)
    return fig

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
def load_data(xlsx_path: Path):
    xls = pd.ExcelFile(xlsx_path)
    Family = pd.read_excel(xls, "Family")
    acct = pd.read_excel(xls, "Family-帳戶紀錄")
    return Family, acct

def compute_kpi(Family: pd.DataFrame):
    """
    KPI 統計只計入「有分類」的列（你說的 AB 欄有做分類）。
    - 用欄位名「分類」判斷是否有分類（去除空白後不可為空）
    - 同時排除 Excel 底部「分析/總計」區塊（透過 _filter_trade_like_rows）
    """
    df = Family.copy()

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



def make_rank_chart_by_market(Family: pd.DataFrame, market: str, top_n: int = 10):
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

    df = _filter_trade_like_rows(Family)

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


def make_yearly_return_combo(Family: pd.DataFrame, mode: str = "已實現"):
    """
    直條：年度收益
    折線：累積收益（含數字標籤）
    mode:
      - "已實現"：用「賣出日期」年度彙總「已實現損益」
      - "含未實現"：已實現 + 未實現。未實現（無賣出日期）歸入今年。
    """
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"
    sell_date_col = "賣出日期" if "賣出日期" in Family.columns else None
    if sell_date_col is None or realized_col not in Family.columns:
        return None

    df = _filter_trade_like_rows(Family).copy()
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
    fig.add_bar(x=yearly["年度"], y=yearly["年度收益"], name="年度收益", yaxis="y")
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
        height=520
    )
    return fig

# ====== 側邊欄：管理者上傳（只有輸入密碼才會出現） ======
view_mode = st.sidebar.radio("顯示內容", ["圖表", "交易明細"], index=0)
#st.sidebar.caption(f"BUILD_TAG: {BUILD_TAG}")


def render_trade_details(Family: pd.DataFrame):
    """右側顯示交易明細（可切換台股/美股）"""
    st.subheader("交易明細")

    if "分類" not in Family.columns:
        st.warning("找不到『分類』欄位，無法依台股/美股切換。")
        st.dataframe(Family, use_container_width=True)
        return

    market = st.radio("明細篩選", ["台股（含台股 ETF）", "美股", "全部"], horizontal=True)

    df = Family.copy()
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


st.sidebar.title("設定")
st.sidebar.button("重新載入資料（Google Drive）", on_click=_touch_reload_flag, args=("gdrive",))
st.sidebar.button("重新載入資料（OneDrive）", on_click=_touch_reload_flag, args=("onedrive",))
st.sidebar.caption(f"Google Drive：{'已設定' if (st.secrets.get('GOOGLE_SHEETS_URL') or st.secrets.get('GDRIVE_FILE_URL')) else '未設定'}")
st.sidebar.caption(f"OneDrive：{'已設定' if st.secrets.get('ONEDRIVE_XLSX_URL') else '未設定'}")

if is_admin():
    st.sidebar.markdown("### 管理者操作")
    st.sidebar.info("上傳後會覆蓋 data/family_data.xlsx（只有你能做這件事）")
    uploaded = st.sidebar.file_uploader("上傳新版 Excel (.xlsx)", type=["xlsx"])
    if uploaded is not None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        XLSX_PATH.write_bytes(uploaded.getbuffer())
        st.sidebar.success("已更新 Excel！請重新整理頁面。")
        st.cache_data.clear()

st.title("Family 的投資儀表板")
if XLSX_PATH.exists():
    st.caption(f"資料最後更新時間：{pd.to_datetime(XLSX_PATH.stat().st_mtime, unit='s')}")



# 嘗試自動同步：首次沒有檔案，或按了「重新載入資料」才會從 OneDrive 抓
# 嘗試自動同步：首次沒有檔案，或按了「重新載入」才會從雲端抓（Google Drive 優先，其次 OneDrive）
source = st.session_state.pop("_reload_source", None)
need_fetch = (not XLSX_PATH.exists()) or (source in ("gdrive", "onedrive"))
if need_fetch:
    fetched = False
    # 1) 指定來源
    if source == "gdrive":
        fetched = ensure_excel_from_gdrive(XLSX_PATH)
        if (not fetched) and st.secrets.get("ONEDRIVE_XLSX_URL"):
            fetched = ensure_excel_from_onedrive(XLSX_PATH)
    elif source == "onedrive":
        fetched = ensure_excel_from_onedrive(XLSX_PATH)
        if (not fetched) and (st.secrets.get("GOOGLE_SHEETS_URL") or st.secrets.get("GDRIVE_FILE_URL")):
            fetched = ensure_excel_from_gdrive(XLSX_PATH)
    else:
        # 2) 未指定：有設定 Google Drive 就先試，失敗再試 OneDrive
        if st.secrets.get("GOOGLE_SHEETS_URL") or st.secrets.get("GDRIVE_FILE_URL"):
            fetched = ensure_excel_from_gdrive(XLSX_PATH)
        if (not fetched) and st.secrets.get("ONEDRIVE_XLSX_URL"):
            fetched = ensure_excel_from_onedrive(XLSX_PATH)

if not XLSX_PATH.exists():
    st.error("找不到 data/family_data.xlsx。請由管理者登入後上傳 Excel。")
    st.stop()

Family, acct = load_data(XLSX_PATH)

# ====== KPI ======
total_invested, total_realized, total_unrealized, total_pnl, ret = compute_kpi(Family)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("投入金額", f"{total_invested:,.0f}")
c2.metric("已實現損益", f"{total_realized:,.0f}")
c3.metric("未實現損益", f"{total_unrealized:,.0f}")
c4.metric("總損益", f"{total_pnl:,.0f}")
c5.metric("報酬率", f"{ret*100:,.2f}%")

st.divider()

if view_mode == "圖表":
    # ====== 圖表順序（由上至下）：投資收益、資產配置、台幣現金水位圖、台股Top10、美股Top10 ======
    mode = st.radio("年度收益模式", ["已實現", "含未實現"], horizontal=True)

    yearly_fig = make_yearly_return_combo(Family, mode=mode)
    if yearly_fig is not None:
        st.plotly_chart(yearly_fig, use_container_width=True)
    else:
        st.info("無法產生『投資收益（年度 vs 累積）』圖表（請確認 Excel 有『賣出日期 / 已實現損益』）。")

    pie = make_allocation_pie_from_analysis(Family)
    if pie is not None:
        st.plotly_chart(pie, use_container_width=True)
    else:
        st.warning("找不到 Excel 內『分析』區塊（含『分類』與『參考現值』）或該區塊資料為空。")

    ts = make_timeseries(acct)
    if ts is not None:
        st.plotly_chart(ts, use_container_width=True)
    else:
        st.warning("帳戶紀錄缺少台幣現金相關欄位（台幣現金/台幣本金/結餘），無法畫台幣現金水位圖。")

    # ④ 台股/美股 Top10（可切換）
    top_market = st.radio("Top10 類型", ["台股（含台股 ETF）", "美股"], horizontal=True)

    if top_market.startswith("台股"):
        top_fig = make_rank_chart_by_market(Family, market="台股", top_n=10)
        if top_fig is not None:
            st.plotly_chart(top_fig, use_container_width=True)
        else:
            st.info("沒有找到可用的台股資料（Top 10）。")
    else:
        top_fig = make_rank_chart_by_market(Family, market="美股", top_n=10)
        if top_fig is not None:
            st.plotly_chart(top_fig, use_container_width=True)
        else:
            st.info("沒有找到可用的美股資料（Top 10）。")
else:
    render_trade_details(Family)