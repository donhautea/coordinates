import streamlit as st
import pandas as pd
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo
from geopy.geocoders import Nominatim
import pydeck as pdk
from streamlit_geolocation import streamlit_geolocation

# ------------------------- CONFIG -------------------------
st.set_page_config(page_title="Multi-User Geolocation Map", layout="wide")
PH_TIMEZONE = ZoneInfo("Asia/Manila")
geolocator = Nominatim(user_agent="geo_app")
FILE_ID = "1CPXH8IZVGXLzApaQNC2GvTkAETpGGAjQlfJ8SdtBbxc"

# ------------------------- HELPERS -------------------------
def get_elevation(lat, lon):
    try:
        r = requests.get(
            f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}",
            timeout=5
        )
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
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict({
        "type": "service_account",
        "project_id": "geolocator-bearing",
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
        ws = sh.add_worksheet(title="multi_geolocator_log", rows="1000", cols="6")
        headers = ["Email", "Timestamp", "Latitude", "Longitude", "Elevation", "Address"]
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
    if "Longtitude" in df.columns:
        df.rename(columns={"Longtitude": "Longitude"}, inplace=True)
    required = {"Email", "Latitude", "Longitude", "Timestamp"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    recent = df.sort_values("Timestamp").groupby("Email", as_index=False).tail(1)
    return recent.rename(columns={"Latitude": "lat", "Longitude": "lon"})

# ------------------------- MAIN APP -------------------------
st.title("📍 Multi-User Geolocation Tracker")
st.write("Detect your GPS location and log it by email.")

data = streamlit_geolocation()
email = st.text_input("Enter your email:")

center_lat = None
center_lon = None

if data and email:
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is not None and lon is not None:
        center_lat, center_lon = lat, lon
        now = datetime.now(PH_TIMEZONE)
        elev = get_elevation(lat, lon)
        addr = reverse_geocode(lat, lon)
        record = {
            "Email": email,
            "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "Latitude": lat,
            "Longitude": lon,
            "Elevation": elev,
            "Address": addr
        }
        append_to_sheet(record)
        st.success("📌 Location logged successfully!")
    else:
        st.error("Unable to retrieve GPS location.")

# ------------------------- MAP DISPLAY -------------------------
df_map = fetch_latest_locations()
if not df_map.empty:
    if center_lat is None or center_lon is None:
        center_lat = df_map["lat"].mean()
        center_lon = df_map["lon"].mean()

    view = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=12
    )
    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_fill_color=[255, 0, 0],
        get_radius=100,
        pickable=True
    )
    text = pdk.Layer(
        "TextLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_text="Email",
        get_size=16,
        get_color=[0, 0, 0],
        get_alignment_baseline='"bottom"'
    )
    st.pydeck_chart(pdk.Deck(
        layers=[scatter, text],
        initial_view_state=view,
        tooltip={"html": "<b>{Email}</b><br/>Lat: {lat}<br/>Lon: {lon}"}
    ))
else:
    st.info("No valid location data to display.")
