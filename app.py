import streamlit as st

st.set_page_config(page_title="投資儀表板", layout="wide")

# 左側選單 / 外部連結
with st.sidebar:
    st.markdown("### 外部連結")
    st.link_button(
        "🌍 全球市場總覽",
        "https://ai-monitor-center-8erctuqrzujpfuqgacqx2u.streamlit.app/global_market",
        use_container_width=True,
    )

st.title("投資儀表板")
st.write("請從左側選單選擇要查看的頁面：Richard / Family")
st.info("資料來源：data/family_data.xlsx（不同頁面讀取不同 sheet）")
