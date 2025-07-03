import streamlit as st
import pandas as pd
import requests
import gspread
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from oauth2client.service_account import ServiceAccountCredentials
from geopy.geocoders import Nominatim
from streamlit_geolocation import streamlit_geolocation
import pydeck as pdk

# --- Config
st.set_page_config(page_title="📍 Live User Geomap", layout="wide")
PH_TIMEZONE = ZoneInfo("Asia/Manila")
geolocator = Nominatim(user_agent="geo_app")

# --- Email input
email = st.text_input("Enter your email (used as ID):")
if not email:
    st.warning("Please enter your email to proceed.")
    st.stop()

# --- Get location
location_data = streamlit_geolocation()
if not location_data or not location_data.get("latitude"):
    st.info("Waiting for GPS trigger...")
    st.stop()

lat, lon = location_data["latitude"], location_data["longitude"]

# --- Elevation and Address
def get_elevation(lat, lon):
    try:
        r = requests.get(f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}")
        return r.json()['results'][0]['elevation']
    except:
        return None

def reverse_geocode(lat, lon):
    try:
        loc = geolocator.reverse((lat, lon), timeout=10)
        return loc.address
    except:
        return None

elevation = get_elevation(lat, lon)
address = reverse_geocode(lat, lon)
now = datetime.now(PH_TIMEZONE)
timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

# --- Append to Google Sheet
def append_to_sheet(row_dict):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = {
        "type": "service_account",
        "project_id": "dummy-id",
        "private_key_id": "dummy",
        "private_key": st.secrets["gdrive"]["private_key"].replace("\\n", "\n"),
        "client_email": st.secrets["gdrive"]["client_email"],
        "client_id": st.secrets["gdrive"]["client_id"],
        "token_uri": st.secrets["gdrive"]["token_uri"]
    }
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(credentials)
    sheet = gc.open_by_key(st.secrets["gdrive"]["file_id"]).sheet1
    headers = sheet.row_values(1)
    row = [row_dict.get(h, "") for h in headers]
    sheet.append_row(row, value_input_option="USER_ENTERED")

summary = {
    "Email": email,
    "Date": now.strftime("%Y-%m-%d"),
    "Time": now.strftime("%H:%M:%S"),
    "Latitude": lat,
    "Longitude": lon,
    "Elevation": elevation,
    "Address": address,
    "Timestamp": timestamp_str,
}
append_to_sheet(summary)
st.success("✅ Your location has been logged!")

# --- Fetch latest user locations
@st.cache_data(ttl=60)
def fetch_latest_user_locations():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = {
        "type": "service_account",
        "project_id": "dummy-id",
        "private_key_id": "dummy",
        "private_key": st.secrets["gdrive"]["private_key"].replace("\\n", "\n"),
        "client_email": st.secrets["gdrive"]["client_email"],
        "client_id": st.secrets["gdrive"]["client_id"],
        "token_uri": st.secrets["gdrive"]["token_uri"]
    }
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(credentials)
    df = pd.DataFrame(gc.open_by_key(st.secrets["gdrive"]["file_id"]).sheet1.get_all_records())

    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.dropna(subset=["Timestamp"])
    df = df.sort_values("Timestamp").groupby("Email", as_index=False).tail(1)

    return df

df_users = fetch_latest_user_locations()

# --- Determine if recent (≤ 5 minutes old)
now_dt = datetime.now(PH_TIMEZONE)
threshold = now_dt - timedelta(minutes=5)
df_users["is_recent"] = df_users["Timestamp"] >= threshold
df_users["color"] = df_users["is_recent"].map(lambda recent: [255, 0, 0] if recent else [128, 128, 128])

# --- Map layers
scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df_users,
    get_position=["Longitude", "Latitude"],
    get_fill_color="color",
    get_radius=60,
    pickable=True
)

text_layer = pdk.Layer(
    "TextLayer",
    data=df_users,
    get_position=["Longitude", "Latitude"],
    get_text="Email",
    get_color=[0, 0, 0],
    get_size=16,
)

view_state = pdk.ViewState(
    latitude=lat,
    longitude=lon,
    zoom=12
)

# --- Display Map
st.pydeck_chart(pdk.Deck(
    layers=[scatter_layer, text_layer],
    initial_view_state=view_state,
    tooltip={
        "html": "<b>{Email}</b><br/>Lat: {Latitude}<br/>Lon: {Longitude}<br/>{Timestamp}",
        "style": {"color": "white"}
    }
))
