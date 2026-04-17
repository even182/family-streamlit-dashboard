import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import numpy as np
import datetime

st.set_page_config(page_title="Family Portfolio Dashboard", layout="wide")

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

def make_rank_chart_by_market(richard: pd.DataFrame, market: str, top_n: int = 10):
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"

    df = _filter_trade_like_rows(richard).copy()
    code_col = "股票代號" if "股票代號" in df.columns else None
    name_col = "股票名稱" if "股票名稱" in df.columns else ("股票" if "股票" in df.columns else None)
    if name_col is None:
        return None

    df["已實現損益"] = to_num(df[realized_col]) if realized_col in df.columns else 0.0
    df["未實現損益"] = to_num(df[unrealized_col]) if unrealized_col in df.columns else 0.0
    df["總損益"] = df["已實現損益"] + df["未實現損益"]

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



def make_timeseries(acct: pd.DataFrame):
    date_col = "日期" if "日期" in acct.columns else acct.columns[0]
    # 你想要「台幣現金水位」的話，優先找台幣相關欄位
    candidates = ["台幣現金", "台幣現金水位", "台幣本金", "結餘"]
    value_col = next((c for c in candidates if c in acct.columns), None)
    if value_col is None:
        return None

    df = acct[[date_col, value_col]].copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = to_num(df[value_col])
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    fig = px.line(df, x=date_col, y=value_col, title=f"台幣現金水位圖（來源：帳戶紀錄 / {value_col}）")
    fig.update_layout(height=450)
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

# ====== 圖表順序（由上至下）：投資收益、資產配置、台幣現金水位圖、台股Top10、美股Top10 ======
mode = st.radio("年度收益模式", ["已實現", "含未實現"], horizontal=True)

yearly_fig = make_yearly_return_combo(richard, mode=mode)
if yearly_fig is not None:
    st.plotly_chart(yearly_fig, use_container_width=True)
else:
    st.info("無法產生『投資收益（年度 vs 累積）』圖表（請確認 Excel 有『賣出日期 / 已實現損益』）。")

pie = make_allocation_pie_from_analysis(richard)
if pie is not None:
    st.plotly_chart(pie, use_container_width=True)
else:
    st.warning("找不到 Excel 內『分析』區塊（含『分類』與『參考現值』）或該區塊資料為空。")

ts = make_timeseries(acct)
if ts is not None:
    st.plotly_chart(ts, use_container_width=True)
else:
    st.warning("帳戶紀錄缺少台幣現金相關欄位（台幣現金/台幣本金/結餘），無法畫台幣現金水位圖。")

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
