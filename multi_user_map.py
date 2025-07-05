import streamlit as st
import pandas as pd
import pydeck as pdk
import gspread
from google.oauth2 import service_account
from datetime import datetime, timedelta
import pytz

st.set_page_config(page_title="Multi-User Map Tracker", layout="wide")

# 🔁 Auto-refresh every 60 seconds
st.markdown("""
    <meta http-equiv="refresh" content="60">
    <script>
        setTimeout(function(){
            window.location.reload(1);
        }, 60000);
    </script>
""", unsafe_allow_html=True)

# ✅ Connect to Google Sheet
@st.cache_resource
def get_worksheet():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gdrive"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    file_id = st.secrets["gdrive"]["file_id"]
    sheet = client.open_by_key(file_id).sheet1
    return sheet

worksheet = get_worksheet()

# 📋 Sidebar Inputs
st.sidebar.title("🔧 Settings")
email = st.sidebar.text_input("📧 Your Email")
mode = st.sidebar.selectbox("🔐 Privacy Mode", ["Public", "Private"])
shared_code = st.sidebar.text_input("🔑 Shared Code (Private group)")
show_public = st.sidebar.checkbox("👀 Show Public Users", value=True)
sos_mode = st.sidebar.checkbox("🚨 Seek Emergency Assistance (SOS Mode)", value=False)

# 📍 Auto GPS via JS
st.sidebar.markdown("📍 Auto-detecting location...")
gps_html = """
<script>
navigator.geolocation.getCurrentPosition(
    (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const coords = `${lat},${lon}`;
        window.parent.postMessage({type: 'streamlit:setComponentValue', value: coords}, '*');
    },
    (err) => {
        window.parent.postMessage({type: 'streamlit:setComponentValue', value: '0,0'}, '*');
    }
);
</script>
"""
coords = st.components.v1.html(gps_html, height=0)
coords = st.session_state.get("_streamlit_component_value", "0,0")

try:
    lat, lon = map(float, coords.split(","))
except:
    lat, lon = 0.0, 0.0

# ⏰ Use Philippine Time
now = datetime.now(pytz.timezone("Asia/Manila"))
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

# 🔴 If SOS, override mode
if sos_mode:
    mode = "Public"
    shared_code = "SOS"

# 📝 Write to Google Sheet
if email and lat != 0.0 and lon != 0.0:
    worksheet.append_row([timestamp, email, lat, lon, mode, shared_code, "SOS" if sos_mode else ""])

# 📊 Read and validate Google Sheet
records = worksheet.get_all_records()

if not records:
    st.warning("Google Sheet is empty. Submit your location first.")
    st.stop()

df = pd.DataFrame(records)

required_cols = {"Timestamp", "Email", "Lat", "Lon", "Mode", "SharedCode", "SOS"}
if not required_cols.issubset(df.columns):
    st.error(f"Missing required columns in Sheet: {required_cols - set(df.columns)}")
    st.code(f"Found columns: {list(df.columns)}")
    st.stop()

# 📅 Convert types
df["Timestamp"] = pd.to_datetime(df["Timestamp"])
df["Age"] = now - df["Timestamp"]
df["Active"] = df["Age"] < timedelta(minutes=15)

# 🎨 Assign marker color
def get_color(row):
    if row["SOS"] == "SOS":
        return [255, 0, 0, 200]      # Red - SOS
    elif not row["Active"]:
        return [128, 128, 128, 100]  # Gray - Inactive
    elif row["Mode"] == "Public":
        return [255, 255, 0, 160]    # Yellow - Public
    else:
        return [0, 255, 0, 160]      # Green - Private

df["Color"] = df.apply(get_color, axis=1)

# 🔍 Visibility filtering
def get_visible_users():
    if sos_mode or mode == "Public":
        return df[df["Mode"] == "Public"]
    else:
        in_group = (df["Mode"] == "Private") & (df["SharedCode"] == shared_code)
        public = df["Mode"] == "Public" if show_public else False
        return df[in_group | public]

visible_df = get_visible_users()

# 🗺 Display map
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
    st.warning("No users to display based on your filters.")
