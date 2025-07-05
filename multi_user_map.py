# maintenance_page.py

import streamlit as st

# Set page config
st.set_page_config(page_title="Under Maintenance", layout="centered")

# Big bold message
st.markdown(
    "<h1 style='text-align: center; font-size: 72px; color: red;'>🚧 This Page is Under Maintenance!! 🚧</h1>",
    unsafe_allow_html=True
)
