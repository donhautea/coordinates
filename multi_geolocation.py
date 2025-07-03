import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Multi-User Geolocation Tracker", layout="wide")

# ---------------- GOOGLE SHEETS ACCESS ----------------
@st.cache_resource
def get_worksheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_dict = st.secrets["gdrive"]
    credentials_dict["private_key"] = credentials_dict["private_key"].replace("\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    gc = gspread.authorize(creds)
    try:
        sheet = gc.open_by_key(st.secrets["gdrive"]["file_id"]).worksheet("multi_geolocator_log")
    except gspread.WorksheetNotFound:
        st.warning("⚠️ 'multi_geolocator_log' not found. Using first worksheet.")
        sheet = gc.open_by_key(st.secrets["gdrive"]["file_id"]).sheet1
    return sheet

def append_to_sheet(entry: dict):
    sheet = get_worksheet()
    headers = sheet.row_values(1)
    if not headers:
        headers = list(entry.keys())
        sheet.insert_row(headers, index=1)
    row = [entry.get(h, "") for h in headers]
    sheet.append_row(row, value_input_option="USER_ENTERED")

@st.cache_data(ttl=60)
def fetch_latest_user_locations():
    sheet = get_worksheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    if "Timestamp" not in df.columns:
        st.error("🛑 'Timestamp' column missing in your Google Sheet.")
        st.stop()

    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    return df

# ---------------- APP UI ----------------
st.title("📍 Multi-User Geolocation Tracker")

email = st.text_input("Enter your email (used as identifier)")
latitude = st.number_input("Latitude", format="%.6f")
longitude = st.number_input("Longitude", format="%.6f")
submit = st.button("Log My Location")

if submit:
    if email and latitude and longitude:
        now = datetime.now(ZoneInfo("Asia/Manila"))
        record = {
            "Email": email,
            "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "Latitude": latitude,
            "Longitude": longitude,
            "Address": ""
        }
        append_to_sheet(record)
        st.success("✅ Location logged.")
    else:
        st.warning("⚠️ All fields must be filled in.")

# ---------------- MAP ----------------
if st.checkbox("🗺 Show all logged locations"):
    df = fetch_latest_user_locations()
    if not df.empty:
        st.map(df.rename(columns={"Latitude": "lat", "Longitude": "lon"}))
    else:
        st.info("ℹ️ No coordinates recorded yet.")
