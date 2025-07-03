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
st.set_page_config(page_title="📍 Multi-User Geolocation Map", layout="wide")
PH_TIMEZONE = ZoneInfo("Asia/Manila")
geolocator = Nominatim(user_agent="geo_app")

# --- Function: get elevation and reverse geocode
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
    sheet = gc.open_by_key(st.secrets["gdrive"]["file_id"]).worksheet("multi_geolocator_log")
    headers = sheet.row_values(1)
    row = [row_dict.get(h, "") for h in headers]
    sheet.append_row(row, value_input_option="USER_ENTERED")

# --- Get latest locations from Sheet
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
    sheet = gc.open_by_key(st.secrets["gdrive"]["file_id"]).worksheet("multi_geolocator_log")
    df = pd.DataFrame(sheet.get_all_records())
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.dropna(subset=["Timestamp"])
    df = df.sort_values("Timestamp").groupby("Email", as_index=False).tail(1)
    return df

# --- SECTION: Log current user's location
with st.expander("📍 Log My Current Location"):
    email = st.text_input("Enter your email (used as ID):")
    location_data = streamlit_geolocation()

    if email and location_data and location_data.get("latitude"):
        lat, lon = location_data["latitude"], location_data["longitude"]
        elevation = get_elevation(lat, lon)
        address = reverse_geocode(lat, lon)
        now = datetime.now(PH_TIMEZONE)
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

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
        st.success("✅ Your location has been logged.")

# --- SECTION: Display map
st.subheader("🗺️ Latest Locations from All Users")

df_users = fetch_latest_user_locations()

# --- Email selector
selected_email = st.selectbox("Select Email to focus on:", df_users["Email"].unique())
focus_row = df_users[df_users["Email"] == selected_email].iloc[0]

# --- Assign icons per user
DEFAULT_ICON_URL = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
icon_map = {
    email: DEFAULT_ICON_URL for email in df_users["Email"]
}

df_users["icon_url"] = df_users["Email"].map(icon_map)
df_users["icon_data"] = df_users["icon_url"].apply(lambda url: {
    "url": url,
    "width": 128,
    "height": 128,
    "anchorY": 128
})

# --- Map center = selected user
view_state = pdk.ViewState(
    latitude=focus_row["Latitude"],
    longitude=focus_row["Longitude"],
    zoom=14,
    pitch=0
)

# --- Icon Layer
icon_layer = pdk.Layer(
    "IconLayer",
    data=df_users,
    get_icon="icon_data",
    get_size=6,
    size_scale=20,
    get_position=["Longitude", "Latitude"],
    pickable=True
)

# --- Text Labels
text_layer = pdk.Layer(
    "TextLayer",
    data=df_users,
    get_position=["Longitude", "Latitude"],
    get_text="Email",
    get_color=[0, 0, 0],
    get_size=14,
)

# --- Google-style basemap using Mapbox
st.pydeck_chart(pdk.Deck(
    layers=[icon_layer, text_layer],
    initial_view_state=view_state,
    map_style="mapbox://styles/mapbox/streets-v11",
    mapbox_key=st.secrets["mapbox_token"],
    tooltip={
        "html": "<b>{Email}</b><br/>Lat: {Latitude}<br/>Lon: {Longitude}<br/>{Timestamp}",
        "style": {"color": "white"}
    }
))
