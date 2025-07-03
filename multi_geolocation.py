import streamlit as st
import pandas as pd
import requests
import gspread
from datetime import datetime
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

# --- Fetch latest per email
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

# --- Icon image per user (you can customize this mapping)
icon_map = {
    email: "https://cdn-icons-png.flaticon.com/512/149/149071.png"  # use a generic icon
    for email in df_users["Email"]
}

# --- Create icon columns
df_users["icon_url"] = df_users["Email"].map(icon_map)
df_users["icon_data"] = df_users["icon_url"].apply(lambda url: {
    "url": url,
    "width": 128,
    "height": 128,
    "anchorY": 128
})

# --- IconLayer
icon_layer = pdk.Layer(
    "IconLayer",
    data=df_users,
    get_icon="icon_data",
    get_size=4,
    size_scale=15,
    get_position=["Longitude", "Latitude"],
    pickable=True
)

text_layer = pdk.Layer(
    "TextLayer",
    data=df_users,
    get_position=["Longitude", "Latitude"],
    get_text="Email",
    get_color=[0, 0, 0],
    get_size=14,
)

# --- View zoomed to user
view_state = pdk.ViewState(
    latitude=lat,
    longitude=lon,
    zoom=12,
    pitch=0
)

# --- Show map
st.pydeck_chart(pdk.Deck(
    layers=[icon_layer, text_layer],
    initial_view_state=view_state,
    tooltip={
        "html": "<b>{Email}</b><br/>Lat: {Latitude}<br/>Lon: {Longitude}<br/>{Timestamp}",
        "style": {"color": "white"}
    }
))
