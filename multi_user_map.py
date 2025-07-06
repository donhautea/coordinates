import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import requests
import gspread
import random
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from geopy.geocoders import Nominatim
import pydeck as pdk
from streamlit_geolocation import streamlit_geolocation
import math

# ------------------------- CONFIG -------------------------
st.set_page_config(page_title="Multi-User Geolocation Map", layout="wide")
st_autorefresh(interval=60 * 1000, key="auto_refresh")  # Refresh every 60 seconds

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
    return df

# ------------------------- UI -------------------------
st.title("\ud83d\udccd Multi-User Geolocation Tracker with SOS and Path Viewer")

if "email" not in st.session_state:
    st.session_state["email"] = ""

with st.sidebar:
    st.header("\ud83d\udd12 Settings")
    email = st.text_input("Enter your email:", value=st.session_state["email"])
    st.session_state["email"] = email
    mode = st.radio("Privacy Mode", ["Public", "Private"])
    shared_code = st.text_input("Shared Code", value="group1" if mode == "Private" else "")
    show_public = st.checkbox("Also show public users", value=True)
    sos = st.checkbox("\ud83d\udea8 Emergency Mode (SOS)")
    if st.button("\ud83d\udccd Refresh My Location"):
        st.session_state["streamlit_geolocation"] = None

    origin_user = None
    df_all = fetch_latest_locations()
    df_active_users = df_all[df_all["Active"]]

    if mode == "Private" and shared_code and not df_active_users.empty:
        private_users = df_active_users[
            (df_active_users["Mode"].isin(["Private", "SOS"])) &
            (df_active_users["SharedCode"] == shared_code)
        ]
        origin_options = private_users["Email"].unique().tolist()
        if origin_options:
            origin_user = st.selectbox("Select Origin User", options=origin_options)
        else:
            st.info("No active users found with the same Shared Code.")

    show_path = st.checkbox("\ud83d\uddfa Show path for user (today only)")
    path_user = None
    if show_path:
        all_users = df_all["Email"].unique().tolist()
        path_user = st.selectbox("Select user for path", options=all_users)

if mode == "Private" and origin_user:
    user_row = df_active_users[df_active_users["Email"] == origin_user].iloc[0]
    origin_lat, origin_lon = user_row["lat"], user_row["lon"]
else:
    origin_lat, origin_lon = default_origin()

message_area = st.empty()
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
            "Mode": "Public" if sos else mode,
            "SharedCode": shared_code if mode == "Private" else "",
            "SOS": "YES" if sos else ""
        }
        append_to_sheet(record)
        with st.sidebar:
            st.markdown(f"\ud83e\uddf1 **Your Coordinates:** `{lat}, {lon}`")
            st.markdown(f"\ud83d\udccd **Distance to Origin:** `{distance_km} km`")
        message_area.success("\ud83d\udccc Location logged successfully.")
    else:
        message_area.warning("\u26a0\ufe0f GPS not available.")
else:
    message_area.info("Please allow GPS access and enter your email.")

view = pdk.ViewState(latitude=origin_lat, longitude=origin_lon, zoom=12)

if show_path and path_user:
    today = datetime.now(PH_TIMEZONE).date()
    df_user_path = df_all[
        (df_all["Email"] == path_user) & (df_all["Timestamp"].dt.date == today)
    ].sort_values("Timestamp")

    if not df_user_path.empty:
        df_user_path["Color"] = df_user_path.apply(
            lambda row: [255, 0, 0, 255 if random.choice([True, False]) else 50] if row["SOS"] == "YES"
            else [0, 200, 255, 200], axis=1
        )

        scatter = pdk.Layer(
            "ScatterplotLayer",
            data=df_user_path,
            get_position="[lon, lat]",
            get_fill_color="Color",
            radius_scale=5,
            radius_min_pixels=4,
            radius_max_pixels=20,
            pickable=True
        )
        text = pdk.Layer(
            "TextLayer",
            data=df_user_path,
            get_position="[lon, lat]",
            get_text="Timestamp",
            get_size=10,
            get_color=[255, 255, 255],
            get_alignment_baseline='"bottom"'
        )

        deck = pdk.Deck(
            layers=[scatter, text],
            initial_view_state=view,
            tooltip={"html": "<b>{Email}</b><br/>Lat: {lat}<br/>Lon: {lon}<br/>Time: {Timestamp}"}
        )
        st.pydeck_chart(deck, use_container_width=True, height=600)
    else:
        st.warning("No location records found for today.")
else:
    df_map = df_all.copy()

    if mode == "Private":
        df_map = df_map[((df_map["Mode"] == "Public") & show_public) | (df_map["SharedCode"] == shared_code)]
    elif mode == "Public":
        df_map = df_map[df_map["Mode"] == "Public"]

    df_map["Distance_km"] = df_map.apply(lambda row: round(haversine(origin_lat, origin_lon, row.lat, row.lon), 2), axis=1)

    df_map["Color"] = df_map.apply(
        lambda row: [255, 0, 0, 255 if random.choice([True, False]) else 50] if row["SOS"] == "YES"
        else [100, 100, 100, 100] if not row["Active"]
        else [255, 255, 0, 200] if row["Mode"] == "Public"
        else [0, 255, 0, 200], axis=1
    )
    df_map["LineColor"] = df_map.apply(
        lambda row: [100, 100, 100] if not row["Active"] else [0, 128, 255], axis=1
    )

    df_lines = pd.DataFrame([
        {
            "start_lat": origin_lat,
            "start_lon": origin_lon,
            "end_lat": row.lat,
            "end_lon": row.lon,
            "color": row.LineColor
        }
        for _, row in df_map.iterrows()
    ])

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position="[lon, lat]",
        get_fill_color="Color",
        radius_scale=5,
        radius_min_pixels=4,
        radius_max_pixels=20,
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
        get_color="color",
        get_width=2
    )

    deck = pdk.Deck(
        layers=[scatter, text, line],
        initial_view_state=view,
        tooltip={"html": "<b>{Email}</b><br/>Lat: {lat}<br/>Lon: {lon}<br/>Distance: {Distance_km} km<br/>Mode: {Mode}<br/>SOS: {SOS}"}
    )
    st.pydeck_chart(deck, use_container_width=True, height=600)
