import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="Family Portfolio Dashboard", layout="wide")

DATA_DIR = Path(__file__).parent / "data"
XLSX_PATH = DATA_DIR / "family_data.xlsx"

# ====== 小工具：把文字數字清乾淨 ======
def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str)
         .str.replace(",", "", regex=False)
         .str.replace(" ", "", regex=False)
         .replace({"nan": None, "": None}),
        errors="coerce"
    ).fillna(0.0)

@st.cache_data(show_spinner=False)
def load_data(xlsx_path: Path):
    xls = pd.ExcelFile(xlsx_path)
    richard = pd.read_excel(xls, "Richard")
    acct = pd.read_excel(xls, "Richard-帳戶紀錄")
    return richard, acct

def compute_kpi(richard: pd.DataFrame):
    # 依你的檔案欄位（你畫面上已用過這些）
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

def make_rank_chart(richard: pd.DataFrame):
    name_col = "股票名稱" if "股票名稱" in richard.columns else "股票代號"
    realized_col = "已實現損益"
    unrealized_col = "未實現損益"

    df = richard.copy()
    df["已實現損益"] = to_num(df[realized_col]) if realized_col in df.columns else 0.0
    df["未實現損益"] = to_num(df[unrealized_col]) if unrealized_col in df.columns else 0.0
    df["總損益"] = df["已實現損益"] + df["未實現損益"]

    agg = (df.groupby(name_col, dropna=True)["總損益"]
             .sum()
             .sort_values(ascending=False)
             .reset_index()
             .rename(columns={name_col: "股票", "總損益": "總損益"}))

    fig = px.bar(agg.head(30), x="總損益", y="股票", orientation="h", title="股票別總損益 Top 30")
    fig.update_layout(height=700, yaxis={"categoryorder": "total ascending"})
    return fig

def make_allocation_pie(richard: pd.DataFrame):
    if "分類" not in richard.columns or "成交金額" not in richard.columns:
        return None
    df = richard.copy()
    df["成交金額"] = to_num(df["成交金額"])
    alloc = (df.groupby("分類")["成交金額"]
               .sum()
               .sort_values(ascending=False)
               .reset_index()
               .rename(columns={"成交金額": "金額"}))
    fig = px.pie(alloc, names="分類", values="金額", title="資金配置：分類")
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=450)
    return fig

def make_timeseries(acct: pd.DataFrame):
    # 先用帳戶紀錄做曲線最穩（你檔案通常有：日期、結餘、台幣本金、美金本金）
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

# ====== 側邊欄：你專用上傳（可關） ======
st.sidebar.title("設定")
admin_mode = st.sidebar.toggle("管理者模式（上傳 Excel）", value=False)

if admin_mode:
    st.sidebar.info("上傳後會覆蓋 data/family_data.xlsx（只有你做這件事）")
    uploaded = st.sidebar.file_uploader("上傳新版 Excel (.xlsx)", type=["xlsx"])
    if uploaded is not None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        XLSX_PATH.write_bytes(uploaded.getbuffer())
        st.sidebar.success("已更新 Excel！請按上方『Rerun』或重新整理頁面。")
        st.cache_data.clear()

st.title("家庭投資儀表板（只讀）")

if not XLSX_PATH.exists():
    st.error("找不到 data/family_data.xlsx。請先把你的 Excel 放進 data/，或開啟管理者模式上傳。")
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

# ====== 圖表區 ======
left, right = st.columns([2, 1])

with left:
    st.plotly_chart(make_rank_chart(richard), use_container_width=True)

with right:
    pie = make_allocation_pie(richard)
    if pie is not None:
        st.plotly_chart(pie, use_container_width=True)
    else:
        st.warning("找不到『分類』或『成交金額』欄位，無法畫分類配置圓餅。")

    ts = make_timeseries(acct)
    if ts is not None:
        st.plotly_chart(ts, use_container_width=True)
    else:
        st.warning("帳戶紀錄缺少可用欄位（日期/結餘/本金），無法畫資產曲線。")
