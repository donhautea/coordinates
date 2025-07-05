import streamlit as st
import pandas as pd
import pydeck as pdk
import gspread
from google.oauth2 import service_account
from datetime import datetime, timedelta
import pytz

# Streamlit Page Config
st.set_page_config(page_title="Multi-User Map Tracker", layout="wide")

# Connect to Google Sheet
@st.cache_resource
def get_worksheet():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    sheet = client.open("multi_geolocation_log").sheet1
    return sheet

worksheet = get_worksheet()

# Sidebar – User Inputs
st.sidebar.title("🔧 Settings")
email = st.sidebar.text_input("📧 Your Email")
lat = st.sidebar.number_input("🧭 Latitude", format="%.6f")
lon = st.sidebar.number_input("🧭 Longitude", format="%.6f")
mode = st.sidebar.selectbox("🔐 Privacy Mode", ["Public", "Private"])
shared_code = st.sidebar.text_input("🔑 Shared Code (Private groups)")
show_public = st.sidebar.checkbox("👀 Show Public Users", value=True)
sos_mode = st.sidebar.checkbox("🚨 Seek Emergency Assistance (SOS Mode)", value=False)

# Use Philippine local time
now = datetime.now(pytz.timezone("Asia/Manila"))
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

# If SOS, override privacy and shared code
if sos_mode:
    mode = "Public"
    shared_code = "SOS"

# Append user data to Google Sheet
if email and lat and lon:
    worksheet.append_row([timestamp, email, lat, lon, mode, shared_code, "SOS" if sos_mode else ""])

# Force refresh every minute
st_autorefresh = st.experimental_rerun
st.experimental_rerun_interval = 60000

# Load data
df = pd.DataFrame(worksheet.get_all_records())
df["Timestamp"] = pd.to_datetime(df["Timestamp"])
df["Age"] = now - df["Timestamp"]
df["Active"] = df["Age"] < timedelta(minutes=15)

# Assign colors
def get_color(row):
    if row["SOS"] == "SOS":
        return [255, 0, 0, 200]     # RED - SOS
    elif not row["Active"]:
        return [128, 128, 128, 100]  # GRAY - Inactive
    elif row["Mode"] == "Public":
        return [255, 255, 0, 160]   # YELLOW - Active Public
    else:
        return [0, 255, 0, 160]     # GREEN - Active Private

df["Color"] = df.apply(get_color, axis=1)

# Determine visible users
def get_visible_users():
    if sos_mode or mode == "Public":
        return df[df["Mode"] == "Public"]
    else:
        in_group = (df["Mode"] == "Private") & (df["SharedCode"] == shared_code)
        public = (df["Mode"] == "Public") if show_public else False
        return df[in_group | public]

visible_df = get_visible_users()

# Show map
if not visible_df.empty:
    st.subheader("📍 Real-Time User Locations")

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=visible_df,
        get_position='[Lon, Lat]',
        get_color='Color',
        get_radius=100,
        pickable=True
    )

    view_state = pdk.ViewState(
        latitude=visible_df["Lat"].mean(),
        longitude=visible_df["Lon"].mean(),
        zoom=5,
        pitch=0
    )

    st.pydeck_chart(pdk.Deck(
        map_style="mapbox://styles/mapbox/light-v9",
        initial_view_state=view_state,
        layers=[layer],
        tooltip={"text": "📧 {Email}\n🕒 {Timestamp}\n🔐 {Mode} {SOS}"}
    ))

else:
    st.warning("No users to display based on your visibility settings.")

