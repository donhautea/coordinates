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

# 📌 Initialize session_state
for key in ["email", "mode", "shared_code", "sos_mode", "lat", "lon", "last_logged"]:
    if key not in st.session_state:
        st.session_state[key] = ""

# ✅ Connect to Google Sheet
@st.cache_resource
def get_worksheet():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gdrive"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    file_id = st.secrets["gdrive"]["file_id"]
    return client.open_by_key(file_id).sheet1

worksheet = get_worksheet()

# 📋 Sidebar Inputs (persistent)
st.sidebar.title("🔧 Settings")
st.session_state.email = st.sidebar.text_input("📧 Your Email", st.session_state.email)
st.session_state.mode = st.sidebar.selectbox(
    "🔐 Privacy Mode", ["Public", "Private"],
    index=["Public", "Private"].index(st.session_state.mode or "Public")
)
st.session_state.shared_code = st.sidebar.text_input("🔑 Shared Code", st.session_state.shared_code)
st.session_state.sos_mode = st.sidebar.checkbox("🚨 SOS Mode", value=st.session_state.sos_mode)
show_public = st.sidebar.checkbox("👀 Show Public Users", value=True)

# 📍 GPS Auto-detect
st.sidebar.markdown("📍 Auto-detecting coordinates...")
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
    if lat != 0.0 and lon != 0.0:
        st.session_state.lat = lat
        st.session_state.lon = lon
except:
    st.session_state.lat = 0.0
    st.session_state.lon = 0.0

# 🧭 Display coordinates in sidebar
st.sidebar.markdown(f"📌 **Latitude**: `{st.session_state.lat}`")
st.sidebar.markdown(f"📌 **Longitude**: `{st.session_state.lon}`")

# 🕒 Use Philippine time
now = datetime.now(pytz.timezone("Asia/Manila"))
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

# 🔴 SOS Mode override
if st.session_state.sos_mode:
    st.session_state.mode = "Public"
    st.session_state.shared_code = "SOS"

# 📝 Log to Google Sheet
if st.session_state.email and st.session_state.lat and st.session_state.lon:
    try:
        records = worksheet.get_all_records()
        updated = False
        for i, record in enumerate(records):
            if record.get("Email", "").strip().lower() == st.session_state.email.strip().lower():
                worksheet.update(f"A{i+2}:G{i+2}", [[
                    timestamp, st.session_state.email, st.session_state.lat,
                    st.session_state.lon, st.session_state.mode,
                    st.session_state.shared_code, "SOS" if st.session_state.sos_mode else ""
                ]])
                updated = True
                break
        if not updated:
            worksheet.append_row([
                timestamp, st.session_state.email, st.session_state.lat,
                st.session_state.lon, st.session_state.mode,
                st.session_state.shared_code, "SOS" if st.session_state.sos_mode else ""
            ])
        st.session_state.last_logged = f"✅ Logged at {timestamp}"
    except Exception as e:
        st.error(f"❌ Failed to log to Google Sheets: {e}")
        st.stop()

# ✅ Show logging confirmation
if st.session_state.last_logged:
    st.sidebar.success(st.session_state.last_logged)

# 🔁 Reload sheet data
records = worksheet.get_all_records()
if not records:
    st.warning("Google Sheet is empty.")
    st.stop()

df = pd.DataFrame(records)

# ✅ Check columns
required_cols = {"Timestamp", "Email", "Lat", "Lon", "Mode", "SharedCode", "SOS"}
if not required_cols.issubset(df.columns):
    st.error(f"Missing required columns: {required_cols - set(df.columns)}")
    st.code(f"Found columns: {list(df.columns)}")
    st.stop()

# 📊 Process data
df["Timestamp"] = pd.to_datetime(df["Timestamp"])
df["Age"] = now - df["Timestamp"]
df["Active"] = df["Age"] < timedelta(minutes=15)

# 🎨 Assign marker color
def get_color(row):
    if row["SOS"] == "SOS":
        return [255, 0, 0, 200]
    elif not row["Active"]:
        return [128, 128, 128, 100]
    elif row["Mode"] == "Public":
        return [255, 255, 0, 160]
    else:
        return [0, 255, 0, 160]

df["Color"] = df.apply(get_color, axis=1)

# 👁️ Visibility filter
def get_visible_users():
    if st.session_state.sos_mode or st.session_state.mode == "Public":
        return df[df["Mode"] == "Public"]
    else:
        in_group = (df["Mode"] == "Private") & (df["SharedCode"] == st.session_state.shared_code)
        public = df["Mode"] == "Public" if show_public else False
        return df[in_group | public]

visible_df = get_visible_users()

# 🗺️ Display map
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
