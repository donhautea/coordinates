import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

st.set_page_config(page_title="📍 Multi-User Geolocation", layout="wide")

# ---------------- GOOGLE SHEETS AUTH ----------------
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
        st.error("🛑 'Timestamp' column missing.")
        st.stop()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    return df

# ---------------- UI ----------------
st.title("📍 Multi-User Geolocation Tracker")

email = st.text_input("Enter your email address to log your location:")

get_location = st.button("📍 Detect and Log My Current Location")

location_placeholder = st.empty()

# Location JS Script
components.html("""
<script>
navigator.geolocation.getCurrentPosition(
    (position) => {
        const coords = position.coords;
        const lat = coords.latitude;
        const lon = coords.longitude;
        const input = window.parent.document.querySelector('textarea[data-testid="stTextArea"]');
        if (input) {
            input.value = lat + "," + lon;
            input.dispatchEvent(new Event("input", { bubbles: true }));
        }
    },
    (err) => alert("Location access denied: " + err.message)
);
</script>
""", height=0)

# Hidden field for location (filled by JS)
coordinates = location_placeholder.text_area("Your Coordinates (auto-filled)", key="coords", height=70)


submit = st.button("📌 Submit Location")

if submit:
    if not email:
        st.warning("⚠️ Please enter your email.")
    elif not coordinates or "," not in coordinates:
        st.warning("⚠️ Coordinates not yet detected.")
    else:
        try:
            lat, lon = map(float, coordinates.strip().split(","))
            now = datetime.now(ZoneInfo("Asia/Manila"))

            # Check if this location is the same as last log
            df_check = fetch_latest_user_locations()
            latest = df_check[df_check["Email"] == email].sort_values("Timestamp", ascending=False).head(1)
            if not latest.empty:
                last_lat = latest.iloc[0]["Latitude"]
                last_lon = latest.iloc[0]["Longitude"]
                if abs(lat - last_lat) < 1e-6 and abs(lon - last_lon) < 1e-6:
                    st.info("ℹ️ Same location already logged. Skipping entry.")
                else:
                    append_to_sheet({
                        "Email": email,
                        "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "Latitude": lat,
                        "Longitude": lon,
                        "Address": ""
                    })
                    st.success("✅ Location logged.")
            else:
                append_to_sheet({
                    "Email": email,
                    "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "Latitude": lat,
                    "Longitude": lon,
                    "Address": ""
                })
                st.success("✅ Location logged.")
        except Exception as e:
            st.error(f"❌ Error parsing coordinates: {e}")

# ---------------- MAP ----------------
if st.checkbox("🗺 Show all user locations"):
    df_map = fetch_latest_user_locations()
    if not df_map.empty:
        st.map(df_map.rename(columns={"Latitude": "lat", "Longitude": "lon"}))
    else:
        st.info("ℹ️ No location logs found.")
