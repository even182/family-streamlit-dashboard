import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import numpy as np

st.set_page_config(page_title="Family Portfolio Dashboard", layout="wide")

DATA_DIR = Path(__file__).parent / "data"
XLSX_PATH = DATA_DIR / "family_data.xlsx"

# ====== 管理者驗證（用 Streamlit Secrets：ADMIN_PASSWORD）======
def is_admin() -> bool:
    """只有輸入正確管理者密碼才回傳 True。
    登入狀態會存在 session_state，同一個瀏覽器 session 不用一直重打。
    """
    if st.session_state.get("is_admin", False):
        return True

    # 沒設定 Secrets 就直接關閉管理者功能（安全預設）
    admin_pw = st.secrets.get("ADMIN_PASSWORD", "Xeng4351..")
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

def _clean_text(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return str(x).strip()

def _infer_market_from_code_or_name(code: str, name: str) -> str:
    code = _clean_text(code)
    name = _clean_text(name)

    # Prefer code: digits => TW
    if code:
        if code.isdigit():
            return "台股"
        # Some US tickers might include dots, hyphens; treat as US if contains letters
        if any(ch.isalpha() for ch in code):
            return "美股"

    # Fallback to name heuristic
    if any(ch.isalpha() for ch in name):
        return "美股"
    return "台股"

@st.cache_data(show_spinner=False)
def load_data(xlsx_path: Path):
    xls = pd.ExcelFile(xlsx_path)
    richard = pd.read_excel(xls, "Richard")
    acct = pd.read_excel(xls, "Richard-帳戶紀錄")
    return richard, acct

def compute_kpi(richard: pd.DataFrame):
    invested_col = "成交金額"
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"

    invested = to_num(richard[invested_col]) if invested_col in richard.columns else pd.Series([0.0])
    realized = to_num(richard[realized_col]) if realized_col in richard.columns else pd.Series([0.0])
    unrealized = to_num(richard[unrealized_col]) if unrealized_col in richard.columns else pd.Series([0.0])

    total_invested = float(invested.sum())
    total_realized = float(realized.sum())
    total_unrealized = float(unrealized.sum())
    total_pnl = total_realized + total_unrealized
    ret = (total_pnl / total_invested) if total_invested else 0.0

    return total_invested, total_realized, total_unrealized, total_pnl, ret

def _filter_trade_like_rows(df: pd.DataFrame) -> pd.DataFrame:
    """避免把底部『分析/總計』之類的區塊一起算進股票排行。"""
    d = df.copy()

    code_col = "股票代號" if "股票代號" in d.columns else None
    name_col = "股票名稱" if "股票名稱" in d.columns else ("股票" if "股票" in d.columns else None)

    if code_col:
        code = d[code_col].astype(str).str.strip()
        mask = code.notna() & (code != "") & (code.str.lower() != "nan")
        # 排除一些明顯不是股票列的字樣
        mask &= ~code.isin(["分類", "總計", "分析"])
        d = d[mask]
    elif name_col:
        name = d[name_col].astype(str).str.strip()
        mask = name.notna() & (name != "") & (name.str.lower() != "nan")
        mask &= ~name.isin(["分類", "總計", "分析"])
        d = d[mask]

    return d

def make_rank_chart_by_market(richard: pd.DataFrame, market: str, top_n: int = 10):
    """
    1) Top N
    2) 依台股/美股分開
    """
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"

    df = _filter_trade_like_rows(richard)

    code_col = "股票代號" if "股票代號" in df.columns else None
    name_col = "股票名稱" if "股票名稱" in df.columns else ("股票" if "股票" in df.columns else None)
    if name_col is None:
        return None

    # 計算總損益
    df["已實現損益"] = to_num(df[realized_col]) if realized_col in df.columns else 0.0
    df["未實現損益"] = to_num(df[unrealized_col]) if unrealized_col in df.columns else 0.0
    df["總損益"] = df["已實現損益"] + df["未實現損益"]

    # 推斷市場
    df["_market"] = [
        _infer_market_from_code_or_name(
            df.iloc[i][code_col] if code_col else "",
            df.iloc[i][name_col] if name_col else ""
        )
        for i in range(len(df))
    ]

    df_m = df[df["_market"] == market].copy()
    if df_m.empty:
        return None

    agg = (
        df_m.groupby(name_col, dropna=True)["總損益"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index()
        .rename(columns={name_col: "股票", "總損益": "總損益"})
    )

    fig = px.bar(
        agg,
        x="總損益",
        y="股票",
        orientation="h",
        title=f"{market} 股票別總損益 Top {top_n}"
    )
    fig.update_layout(height=520, yaxis={"categoryorder": "total ascending"})
    return fig

def extract_allocation_from_analysis_block(richard: pd.DataFrame):
    """
    依你附圖的『分析』區塊抓資產配置：
    - 找到含『分類』、『參考現值』（若沒有參考現值就用『成交金額』）的那一列當表頭
    - 讀到『總計』那列為止
    - 回傳 DataFrame: 分類 / 金額
    """
    arr = richard.to_numpy(dtype=object)
    nrows, ncols = arr.shape

    def find_header_row():
        for r in range(nrows):
            row_text = [_clean_text(arr[r, c]) for c in range(ncols)]
            if "分類" in row_text and ("參考現值" in row_text or "成交金額" in row_text):
                return r, row_text
        return None, None

    header_r, header_row = find_header_row()
    if header_r is None:
        return None

    # 定位欄位索引
    cat_idx = header_row.index("分類") if "分類" in header_row else None
    val_key = "參考現值" if "參考現值" in header_row else "成交金額"
    val_idx = header_row.index(val_key) if val_key in header_row else None

    if cat_idx is None or val_idx is None:
        return None

    items = []
    for r in range(header_r + 1, nrows):
        cat = _clean_text(arr[r, cat_idx])
        if not cat:
            continue
        if cat == "總計":
            break

        val_raw = arr[r, val_idx]
        val = pd.to_numeric(str(val_raw).replace(",", "").strip(), errors="coerce")
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

def make_timeseries(acct: pd.DataFrame):
    date_col = "日期" if "日期" in acct.columns else acct.columns[0]
    candidates = ["結餘", "台幣本金", "美金本金"]
    value_col = next((c for c in candidates if c in acct.columns), None)
    if value_col is None:
        return None

    df = acct[[date_col, value_col]].copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = to_num(df[value_col])
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    fig = px.line(df, x=date_col, y=value_col, title=f"資產曲線（來源：帳戶紀錄 / {value_col}）")
    fig.update_layout(height=450)
    return fig

# ====== 側邊欄：管理者上傳（只有輸入密碼才會出現） ======
st.sidebar.title("設定")
if is_admin():
    st.sidebar.markdown("### 管理者操作")
    st.sidebar.info("上傳後會覆蓋 data/family_data.xlsx（只有你能做這件事）")
    uploaded = st.sidebar.file_uploader("上傳新版 Excel (.xlsx)", type=["xlsx"])
    if uploaded is not None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        XLSX_PATH.write_bytes(uploaded.getbuffer())
        st.sidebar.success("已更新 Excel！請重新整理頁面。")
        st.cache_data.clear()

st.title("家庭投資儀表板（只讀）")

if not XLSX_PATH.exists():
    st.error("找不到 data/family_data.xlsx。請由管理者登入後上傳 Excel。")
    st.stop()

richard, acct = load_data(XLSX_PATH)

# ====== KPI ======
total_invested, total_realized, total_unrealized, total_pnl, ret = compute_kpi(richard)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("投入金額", f"{total_invested:,.0f}")
c2.metric("已實現損益", f"{total_realized:,.0f}")
c3.metric("未實現損益", f"{total_unrealized:,.0f}")
c4.metric("總損益", f"{total_pnl:,.0f}")
c5.metric("報酬率", f"{ret*100:,.2f}%")

st.divider()

# ====== 圖表（依你的需求：上台股、下美股、第三張資產配置圓餅；不要併排） ======
tw_fig = make_rank_chart_by_market(richard, market="台股", top_n=10)
if tw_fig is not None:
    st.plotly_chart(tw_fig, use_container_width=True)
else:
    st.info("沒有找到可用的台股資料（Top 10）。")

us_fig = make_rank_chart_by_market(richard, market="美股", top_n=10)
if us_fig is not None:
    st.plotly_chart(us_fig, use_container_width=True)
else:
    st.info("沒有找到可用的美股資料（Top 10）。")

pie = make_allocation_pie_from_analysis(richard)
if pie is not None:
    st.plotly_chart(pie, use_container_width=True)
else:
    st.warning("找不到 Excel 內『分析』區塊（含『分類』與『參考現值』）或該區塊資料為空。")

st.divider()

ts = make_timeseries(acct)
if ts is not None:
    st.plotly_chart(ts, use_container_width=True)
