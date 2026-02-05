import streamlit as st

st.set_page_config(page_title="Richard 投資儀表板", layout="wide")

st.title("投資儀表板")
st.write("請從左側選單選擇要查看的頁面：Richard / Family")
st.info("資料來源：data/family_data.xlsx（不同頁面讀取不同 sheet）")