import streamlit as st

st.set_page_config(page_title="投資儀表板", layout="wide")

st.title("投資儀表板")
st.markdown(
    """
請從左側選單選擇要查看的帳戶：

- **Family**
- **Richard**

每個頁面都是獨立帳戶的投資儀表板。
"""
)

st.info("提示：左側選單由 Streamlit 自動產生，點擊頁面名稱即可切換。")
