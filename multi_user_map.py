import streamlit as st
import pandas as pd
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from geopy.geocoders import Nominatim
import pydeck as pdk
from streamlit_geolocation import streamlit_geolocation

# ------------------------- CONFIG -------------------------
st.set_page_config(page_title="Multi-User Geolocation Map", layout="wide")
PH_TIMEZONE = ZoneInfo("Asia/Manila")
geolocator = Nominatim(user_agent="geo_app")
FILE_ID = st.secrets["gdrive"]["file_id"]

def default_origin():
    return 14.64171, 121.05078

# ------------------------- HELPERS -------------------------
def get_elevation(lat, lon):
    try:
        r = requests.get(f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}", timeout=5)
        if r.status_code == 200:
            return r.json()["results"][0]["elevation"]
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    try:
        loc = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return loc.address if loc else None
    except:
        return None

# ------------------------- GOOGLE SHEET LOGGING -------------------------
@st.cache_resource
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict({
        "type": "service_account",
        "project_id": st.secrets["gdrive"]["project_id"],
        "private_key_id": st.secrets["gdrive"]["private_key_id"],
        "private_key": st.secrets["gdrive"]["private_key"].replace('\\n', '\n'),
        "client_email": st.secrets["gdrive"]["client_email"],
        "client_id": st.secrets["gdrive"]["client_id"],
        "token_uri": st.secrets["gdrive"]["token_uri"]
    }, scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(FILE_ID)
    try:
        return sh.worksheet("multi_geolocator_log")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="multi_geolocator_log", rows="1000", cols="10")
        headers = ["Email", "Timestamp", "Latitude", "Longitude", "Elevation", "Address", "Mode", "SharedCode", "SOS"]
        ws.insert_row(headers, 1)
        return ws

def append_to_sheet(record):
    sheet = get_sheet()
    headers = sheet.row_values(1)
    row = [record.get(h, "") for h in headers]
    if any(row):
        sheet.append_row(row, value_input_option="USER_ENTERED")

@st.cache_data(ttl=60)
def fetch_latest_locations():
    sheet = get_sheet()
    df = pd.DataFrame(sheet.get_all_records())
    df.columns = [c.strip() for c in df.columns]
    if "Timestamp" not in df.columns:
        return pd.DataFrame()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce").dt.tz_localize(PH_TIMEZONE)
    df = df.dropna(subset=["Latitude", "Longitude", "Email"])
    df["Age"] = datetime.now(PH_TIMEZONE) - df["Timestamp"]
    df["Active"] = df["Age"] < timedelta(minutes=15)
    df = df.sort_values("Timestamp").groupby("Email", as_index=False).tail(1)
    return df.rename(columns={"Latitude": "lat", "Longitude": "lon"})

# ------------------------- MAIN APP -------------------------
st.title("📍 Multi-User Geolocation Tracker")
st.sidebar.header("User Settings")

# Manual refresh
refresh_loc = st.sidebar.button("📍 Refresh My Location")
if refresh_loc:
    st.session_state["streamlit_geolocation"] = None

# Sidebar fields
email = st.sidebar.text_input("Enter your email:")
mode = st.sidebar.selectbox("Visibility Mode", ["Public", "Private"])
share_code = st.sidebar.text_input("Shared Code (for private group):")
sos = st.sidebar.checkbox("🚨 Emergency SOS")

# Get coordinates
data = streamlit_geolocation()
origin_lat, origin_lon = default_origin()

if data:
    lat = data.get("latitude")
    lon = data.get("longitude")
    st.sidebar.write(f"📌 Lat: `{lat}` / Lon: `{lon}`")

# Log location if email and coords present
if email and data:
    lat, lon = data["latitude"], data["longitude"]
    if lat and lon:
        now = datetime.now(PH_TIMEZONE)
        elev = get_elevation(lat, lon)
        addr = reverse_geocode(lat, lon)
        record = {
            "Email": email,
            "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "Latitude": lat,
            "Longitude": lon,
            "Elevation": elev,
            "Address": addr,
            "Mode": "SOS" if sos else mode,
            "SharedCode"
