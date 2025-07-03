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
# Fixed central origin (e.g. office) for routing
def default_origin():
    return 14.64171, 121.05078

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
st.title("📍 Multi-User Geolocation Tracker with Routes")
st.write("Detect your GPS location, log it by email, and see routes from the origin.")

data = streamlit_geolocation()
email = st.text_input("Enter your email:")

origin_lat, origin_lon = default_origin()

if data and email:
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is not None and lon is not None:
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
    df_lines = pd.DataFrame([
        {"start_lat": origin_lat, "start_lon": origin_lon, "end_lat": row.lat, "end_lon": row.lon}
        for _, row in df_map.iterrows()
    ])
    # Determine view based on user location or default origin
    user_view = df_map.iloc[0]  # Use first user for centering dynamic
    view = pdk.ViewState(
        latitude=user_view.lat,
        longitude=user_view.lon,
        zoom=12,
        pitch=0
    )
    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_fill_color=[255, 0, 0],
        get_radius=20,
        radiusUnits="pixels",
        pickable=True
    )
    text = pdk.Layer(
        "TextLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_text="Email",
        get_size=12,
        get_color=[0, 0, 0],
        get_alignment_baseline='"bottom"'
    )
    line = pdk.Layer(
        "LineLayer",
        data=df_lines,
        get_source_position=["start_lon", "start_lat"],
        get_target_position=["end_lon", "end_lat"],
        get_color=[0, 128, 255],
        get_width=3
    )
    st.pydeck_chart(pdk.Deck(
        layers=[scatter, text, line],
        initial_view_state=view,
        tooltip={"html": "<b>{Email}</b><br/>Lat: {lat}<br/>Lon: {lon}"},
        use_container_width=True
    ))
else:
    st.info("No valid location data to display.")
