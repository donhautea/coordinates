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
import math

# ------------------------- CONFIG -------------------------
st.set_page_config(page_title="Multi-User Geolocation Map", layout="wide")
PH_TIMEZONE = ZoneInfo("Asia/Manila")
geolocator = Nominatim(user_agent="geo_app")
FILE_ID = st.secrets["gdrive"]["file_id"]

# ------------------------- HELPERS -------------------------
def default_origin():
    return 14.64171, 121.05078

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

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# ------------------------- GOOGLE SHEET -------------------------
@st.cache_resource
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict({
        "type": st.secrets["gdrive"]["type"],
        "project_id": st.secrets["gdrive"]["project_id"],
        "private_key_id": st.secrets["gdrive"]["private_key_id"],
        "private_key": st.secrets["gdrive"]["private_key"].replace('\\n', '\n'),
        "client_email": st.secrets["gdrive"]["client_email"],
        "client_id": st.secrets["gdrive"]["client_id"],
        "auth_uri": st.secrets["gdrive"]["auth_uri"],
        "token_uri": st.secrets["gdrive"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["gdrive"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["gdrive"]["client_x509_cert_url"]
    }, scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(FILE_ID)
    try:
        return sh.worksheet("multi_geolocator_log")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="multi_geolocator_log", rows="1000", cols="8")
        headers = ["Timestamp", "Email", "Latitude", "Longitude", "Elevation", "Mode", "SharedCode", "SOS"]
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
    now = datetime.now(PH_TIMEZONE)
    df["Age"] = now - df["Timestamp"]
    df["Active"] = df["Age"] < timedelta(minutes=15)
    df["lat"] = df["Latitude"]
    df["lon"] = df["Longitude"]
    df.sort_values("Timestamp", ascending=True, inplace=True)
    df = df.drop_duplicates(subset="Email", keep="last")
    return df

# ------------------------- UI + MAP -------------------------
st.title("📍 Multi-User Geolocation Tracker with SOS and Privacy Settings")

with st.sidebar:
    st.header("🔒 Settings")
    email = st.text_input("Enter your email:")
    mode = st.radio("Privacy Mode", ["Public", "Private"])
    shared_code = st.text_input("Shared Code", value="group1" if mode == "Private" else "")
    show_public = st.checkbox("Also show public users", value=True)
    sos = st.checkbox("🚨 Emergency Mode (SOS)")
    if st.button("📍 Refresh My Location"):
        st.session_state["streamlit_geolocation"] = None

origin_lat, origin_lon = default_origin()

# Reserved space to avoid layout shifting
message_area = st.empty()

# Detect GPS
data = streamlit_geolocation()

if data and email:
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is not None and lon is not None:
        now = datetime.now(PH_TIMEZONE)
        elev = get_elevation(lat, lon)
        distance_km = round(haversine(origin_lat, origin_lon, lat, lon), 2)
        record = {
            "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "Email": email,
            "Latitude": lat,
            "Longitude": lon,
            "Elevation": elev,
            "Mode": "SOS" if sos else mode,
            "SharedCode": shared_code if mode == "Private" else "",
            "SOS": "YES" if sos else ""
        }
        append_to_sheet(record)
        with st.sidebar:
            st.markdown(f"🧭 **Your Coordinates:** `{lat}, {lon}`")
            st.markdown(f"📏 **Distance to Origin:** `{distance_km} km`")
        message_area.success("📌 Location logged successfully.")
    else:
        message_area.warning("⚠️ GPS not available.")
else:
    message_area.info("Please allow GPS access and enter your email.")

# Display map
df_map = fetch_latest_locations()
if not df_map.empty:
    if mode == "Private":
        df_map = df_map[((df_map["Mode"] == "Public") & show_public) | (df_map["SharedCode"] == shared_code)]
    elif mode == "Public":
        df_map = df_map[df_map["Mode"] == "Public"]

    df_map["Distance_km"] = df_map.apply(lambda row: round(haversine(origin_lat, origin_lon, row.lat, row.lon), 2), axis=1)

    df_map["Color"] = df_map.apply(
        lambda row: [255, 0, 0] if row["SOS"] == "YES"
        else [255, 255, 0] if row["Mode"] == "Public"
        else [100, 100, 100] if not row["Active"]
        else [0, 255, 0], axis=1
    )

    df_lines = pd.DataFrame([
        {"start_lat": origin_lat, "start_lon": origin_lon, "end_lat": row.lat, "end_lon": row.lon}
        for _, row in df_map.iterrows()
    ])
    view = pdk.ViewState(latitude=origin_lat, longitude=origin_lon, zoom=12)

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_fill_color="Color",
        get_radius=40,
        pickable=True
    )
    text = pdk.Layer(
        "TextLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_text="Email",
        get_size=12,
        get_color=[255, 255, 0],
        get_alignment_baseline='"bottom"'
    )
    line = pdk.Layer(
        "LineLayer",
        data=df_lines,
        get_source_position=["start_lon", "start_lat"],
        get_target_position=["end_lon", "end_lat"],
        get_color=[0, 128, 255],
        get_width=2
    )

    deck = pdk.Deck(
        layers=[scatter, text, line],
        initial_view_state=view,
        tooltip={"html": "<b>{Email}</b><br/>Lat: {lat}<br/>Lon: {lon}<br/>Distance: {Distance_km} km<br/>Mode: {Mode}<br/>SOS: {SOS}"}
    )
    st.pydeck_chart(deck, use_container_width=True, height=600)
else:
    st.info("No user data available yet.")
