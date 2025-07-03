import streamlit as st
import pandas as pd
import math
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

ORIGIN_LAT = 14.64171
ORIGIN_LON = 121.05078
geolocator = Nominatim(user_agent="geo_app")

# ------------------------- HELPERS -------------------------
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def initial_bearing(lat1, lon1, lat2, lon2):
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    θ = math.degrees(math.atan2(x, y))
    return (θ + 360) % 360

def get_elevation(lat, lon):
    try:
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()["results"][0]["elevation"]
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return location.address if location else None
    except:
        return None

def get_worksheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = {
        "type": "service_account",
        "project_id": "geolocator-bearing",
        "private_key_id": st.secrets["gdrive"]["private_key_id"],
        "private_key": st.secrets["gdrive"]["private_key"].replace('\\n', '\n'),
        "client_email": st.secrets["gdrive"]["client_email"],
        "client_id": st.secrets["gdrive"]["client_id"],
        "token_uri": st.secrets["gdrive"]["token_uri"]
    }
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(credentials)
    file = gc.open_by_key(st.secrets["gdrive"]["file_id"])
    try:
        return file.worksheet("multi_geolocator_log")
    except:
        st.warning("⚠️ 'multi_geolocator_log' not found. Using first worksheet.")
        return file.sheet1

def append_to_sheet(record):
    sheet = get_worksheet()
    headers = sheet.row_values(1)
    row = [record.get(col, "") for col in headers]
    if any(row):
        sheet.append_row(row, value_input_option="USER_ENTERED")

def fetch_latest_user_locations():
    sheet = get_worksheet()
    df = pd.DataFrame(sheet.get_all_records())
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.sort_values("Timestamp").dropna(subset=["Email"])
    return df.groupby("Email").tail(1)

# ------------------------- MAIN APP -------------------------
st.title("📍 Multi-User Geolocation Tracker")
st.write("Automatically detect and plot each user's latest location on the map with icons.")

user_data = streamlit_geolocation()
email = st.text_input("Enter your email to tag your location:")

if user_data and email:
    ph_time = datetime.now(ZoneInfo("Asia/Manila"))
    lat = user_data.get("latitude")
    lon = user_data.get("longitude")
    if lat and lon:
        elevation = get_elevation(lat, lon)
        address = reverse_geocode(lat, lon)

        record = {
            "Timestamp": ph_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Email": email,
            "Latitude": lat,
            "Longitude": lon,
            "Elevation": elevation,
            "Address": address
        }
        append_to_sheet(record)
        st.success("📌 Location logged successfully!")

# ------------------------- MAP -------------------------
df_users = fetch_latest_user_locations()
if not df_users.empty:
    df_map = df_users.rename(columns={"Latitude": "lat", "Longitude": "lon"})
    view = pdk.ViewState(
        latitude=df_map["lat"].mean(),
        longitude=df_map["lon"].mean(),
        zoom=10
    )
    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_fill_color="[255, 0, 0]",
        get_radius=60,
        pickable=True
    )
    text = pdk.Layer(
        "TextLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_text="Email",
        get_size=18,
        get_color=[0, 0, 0],
        get_alignment_baseline='"bottom"'
    )
    deck = pdk.Deck(
        layers=[scatter, text],
        initial_view_state=view,
        tooltip={"html": "<b>{Email}</b><br/>Lat: {lat}<br/>Lon: {lon}", "style": {"color": "white"}}
    )
    st.pydeck_chart(deck)
else:
    st.info("📭 No user location data available to display on map.")
