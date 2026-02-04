import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Family 的投資儀表板", layout="wide")

XLSX_PATH = Path("data/family_data.xlsx")

st.title("Family 的投資儀表板")

if not XLSX_PATH.exists():
    st.error("找不到 Excel 資料檔")
    st.stop()

df = pd.read_excel(XLSX_PATH, sheet_name="Family")

st.success("Family 資料載入成功")
st.dataframe(df.head())
