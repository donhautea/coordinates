import streamlit as st
import pandas as pd
import math
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from zoneinfo import ZoneInfo
from geopy.geocoders import Nominatim
import pydeck as pdk
from streamlit_geolocation import streamlit_geolocation

# ------------------------- CONFIG -------------------------
st.set_page_config(page_title="Geolocation Map with Origin & Destination", layout="wide")

ORIGIN_LAT = 14.64171
ORIGIN_LON = 121.05078
geolocator = Nominatim(user_agent="geo_app")

# ------------------------- HELPERS -------------------------

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def initial_bearing(lat1, lon1, lat2, lon2):
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    θ = math.degrees(math.atan2(x, y))
    return (θ + 360) % 360

def get_elevation(lat, lon):
    try:
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()["results"][0]["elevation"]
    except:
        pass
    return None

def reverse_geocode(lat, lon):
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return location.address if location else None
    except:
        return None

def append_to_gdrive(summary_dict):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = {
            "type": "service_account",
            "project_id": "geolocator-bearing",
            "private_key_id": "a9ab69929f8413446303f31d78e2116615fe1fed",
            "private_key": st.secrets["gdrive"]["private_key"].replace('\\n', '\n'),
            "client_email": st.secrets["gdrive"]["client_email"],
            "client_id": st.secrets["gdrive"]["client_id"],
            "token_uri": st.secrets["gdrive"]["token_uri"]
        }
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gc = gspread.authorize(credentials)

        file = gc.open_by_key(st.secrets["gdrive"]["file_id"])
        sheet = file.sheet1
        headers = sheet.row_values(1)
        row = [summary_dict.get(col, "") for col in headers]

        if any(row):
            sheet.append_row(row, value_input_option="USER_ENTERED")
            st.success("✅ Summary successfully logged to Server.")
        else:
            st.error("❌ No valid data to append. Check header alignment with summary record.")

    except Exception as e:
        st.error(f"❌ Error saving to Google Sheets: {e}")

# ------------------------- MAIN APP -------------------------
st.title("📍 Origin & Destination Geolocation")

st.write("""
This app fixes the **origin** at (14.64171, 121.05078) in Metro Manila (marked “O”)  
and plots your **destination** (your phone’s current GPS) as “D.”  
It computes:
- Distance (km)  
- Bearings  
- Elevation  
- Reverse-Geocoded Address  
Then saves the result to Server.
""")

location_data = streamlit_geolocation()
results = {
    "origin": {"lat": ORIGIN_LAT, "lon": ORIGIN_LON, "elevation": None, "address": None},
    "destination": {"lat": ORIGIN_LAT, "lon": ORIGIN_LON, "elevation": None, "address": None},
    "distance_km": 0.0,
    "bearing_od": 0.0,
    "bearing_do": 0.0,
}

dest_lat = location_data.get("latitude") if isinstance(location_data, dict) else None
dest_lon = location_data.get("longitude") if isinstance(location_data, dict) else None

if dest_lat and dest_lon:
    results["destination"]["lat"] = dest_lat
    results["destination"]["lon"] = dest_lon
    st.success(f"📍 Destination found: {dest_lat:.6f}, {dest_lon:.6f}")
else:
    st.info("⚠️ Unable to retrieve GPS location. Using origin as fallback.")

# Compute values
o_lat, o_lon = results["origin"]["lat"], results["origin"]["lon"]
d_lat, d_lon = results["destination"]["lat"], results["destination"]["lon"]

results["distance_km"] = haversine_distance(o_lat, o_lon, d_lat, d_lon)
results["bearing_od"] = initial_bearing(o_lat, o_lon, d_lat, d_lon)
results["bearing_do"] = initial_bearing(d_lat, d_lon, o_lat, o_lon)
results["origin"]["elevation"] = get_elevation(o_lat, o_lon)
results["destination"]["elevation"] = get_elevation(d_lat, d_lon)
results["origin"]["address"] = reverse_geocode(o_lat, o_lon)
results["destination"]["address"] = reverse_geocode(d_lat, d_lon)

# ------------------------- MAP (D → O) -------------------------
df_markers = pd.DataFrame([
    {"name": "Origin (O)", "latitude": o_lat, "longitude": o_lon, "marker": "O"},
    {"name": "Destination (D)", "latitude": d_lat, "longitude": d_lon, "marker": "D"},
])

df_line = pd.DataFrame([{
    "start_lat": d_lat, "start_lon": d_lon,
    "end_lat": o_lat, "end_lon": o_lon
}])

scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df_markers,
    get_position=["longitude", "latitude"],
    get_fill_color=[255, 0, 0, 200],
    get_radius=6,
    pickable=True
)

text_layer = pdk.Layer(
    "TextLayer",
    data=df_markers,
    get_position=["longitude", "latitude"],
    get_text="marker",
    get_color=[255, 0, 0],
    get_size=32
)

line_layer = pdk.Layer(
    "LineLayer",
    data=df_line,
    get_source_position=["start_lon", "start_lat"],
    get_target_position=["end_lon", "end_lat"],
    get_color=[0, 128, 255],
    get_width=4
)

mid_lat = (o_lat + d_lat) / 2
mid_lon = (o_lon + d_lon) / 2

view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=5)

deck = pdk.Deck(
    layers=[line_layer, scatter_layer, text_layer],
    initial_view_state=view_state,
    tooltip={
        "html": "<b>{name}</b><br/>Lat: {latitude}<br/>Lon: {longitude}",
        "style": {"color": "white"}
    }
)

st.pydeck_chart(deck)

# ------------------------- SIDEBAR SUMMARY -------------------------
st.sidebar.header("📋 Summary")
st.sidebar.subheader("Origin (O)")
st.sidebar.write(f"- **Coordinates:** {o_lat:.6f}, {o_lon:.6f}")
st.sidebar.write(f"- **Elevation:** {results['origin']['elevation'] or 'N/A'} m")
st.sidebar.write(f"- **Address:** {results['origin']['address'] or 'N/A'}")

st.sidebar.subheader("Destination (D)")
st.sidebar.write(f"- **Coordinates:** {d_lat:.6f}, {d_lon:.6f}")
st.sidebar.write(f"- **Elevation:** {results['destination']['elevation'] or 'N/A'} m")
st.sidebar.write(f"- **Address:** {results['destination']['address'] or 'N/A'}")

st.sidebar.subheader("Route Info")
st.sidebar.write(f"- **Distance:** {results['distance_km']:.3f} km")
st.sidebar.write(f"- **Bearing O → D:** {results['bearing_od']:.1f}°")
st.sidebar.write(f"- **Bearing D → O:** {results['bearing_do']:.1f}°")

# ------------------------- GOOGLE SHEET LOG -------------------------
# ------------------------- GOOGLE SHEET LOG -------------------------
# Use Philippine timezone
ph_time = datetime.now(ZoneInfo("Asia/Manila"))

summary_record = {
    "Date": ph_time.strftime("%Y-%m-%d"),
    "Time": ph_time.strftime("%H:%M:%S"),
    "Origin_Lat": o_lat,
    "Origin_Lon": o_lon,
    "Origin_Elevation": results['origin']['elevation'],
    "Origin_Address": results['origin']['address'],
    "Destination_Lat": d_lat,
    "Destination_Lon": d_lon,
    "Destination_Elevation": results['destination']['elevation'],
    "Destination_Address": results['destination']['address'],
    "Distance_km": round(results["distance_km"], 3),
    "Bearing_O_to_D": round(results["bearing_od"], 2),
    "Bearing_D_to_O": round(results["bearing_do"], 2),
}

# Only write if D ≠ O
if round(o_lat, 6) == round(d_lat, 6) and round(o_lon, 6) == round(d_lon, 6):
    st.info("🛑 Log skipped: Origin and Destination coordinates are identical.")
else:
    append_to_gdrive(summary_record)
