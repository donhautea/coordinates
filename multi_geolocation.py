import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

# ---------------- CONFIG ----------------
st.set_page_config(page_title="📍 Multi-User Geolocation", layout="wide")

# ---------------- GOOGLE SHEETS ACCESS ----------------
@st.cache_resource
def get_worksheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = st.secrets["gdrive"]
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(creds)
    try:
        return gc.open_by_key(creds_dict["file_id"]).worksheet("multi_geolocator_log")
    except gspread.WorksheetNotFound:
        st.warning("⚠️ 'multi_geolocator_log' not found. Using first worksheet.")
        return gc.open_by_key(creds_dict["file_id"]).sheet1

def append_to_sheet(entry: dict):
    sheet = get_worksheet()
    headers = sheet.row_values(1)
    if not headers:
        headers = list(entry.keys())
        sheet.insert_row(headers, index=1)
    row = [entry.get(h, "") for h in headers]
    sheet.append_row(row, value_input_option="USER_ENTERED")

@st.cache_data(ttl=60)
def fetch_latest_user_locations():
    sheet = get_worksheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if "Timestamp" not in df.columns:
        st.error("🛑 'Timestamp' column missing in Google Sheet.")
        st.stop()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    return df

# ---------------- UI ----------------
st.title("📍 Multi-User Geolocation Tracker")

email = st.text_input("Enter your email")

# Geolocation JavaScript → fetch and return to Streamlit
geoloc = st.button("📍 Detect My Location")
if geoloc:
    components.html("""
        <script>
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const coords = pos.coords;
                const streamlitEvent = new CustomEvent("streamlit:location", {
                    detail: { lat: coords.latitude, lon: coords.longitude }
                });
                window.dispatchEvent(streamlitEvent);
            },
            (err) => alert("Failed to get location: " + err.message)
        );
        </script>
    """, height=0)

# Placeholders for coordinates
lat_holder = st.empty()
lon_holder = st.empty()
lat = lat_holder.number_input("Latitude", key="lat_input", format="%.6f")
lon = lon_holder.number_input("Longitude", key="lon_input", format="%.6f")

# JS → Python: capture location from browser
components.html("""
<script>
window.addEventListener("streamlit:location", function(e) {
    const coords = e.detail;
    const inputLat = window.parent.document.querySelector('[data-testid="stNumberInput"] input[name="lat_input"]');
    const inputLon = window.parent.document.querySelector('[data-testid="stNumberInput"] input[name="lon_input"]');
    if (inputLat && inputLon) {
        inputLat.value = coords.lat;
        inputLat.dispatchEvent(new Event('input', { bubbles: true }));
        inputLon.value = coords.lon;
        inputLon.dispatchEvent(new Event('input', { bubbles: true }));
    }
});
</script>
""", height=0)

submit = st.button("Log My Location")
if submit:
    if email and lat and lon:
        timestamp = datetime.now(ZoneInfo("Asia/Manila"))
        record = {
            "Email": email,
            "Timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "Latitude": lat,
            "Longitude": lon,
            "Address": ""
        }
        append_to_sheet(record)
        st.success("✅ Location logged.")
    else:
        st.warning("⚠️ Fill in all fields or click 📍 Detect Location first.")

# ---------------- MAP ----------------
if st.checkbox("🗺 Show All Logged Locations"):
    df = fetch_latest_user_locations()
    if not df.empty:
        st.map(df.rename(columns={"Latitude": "lat", "Longitude": "lon"}))
    else:
        st.info("ℹ️ No data logged yet.")
