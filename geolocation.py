import streamlit as st
import pandas as pd
import math
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
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
    except Exception as e:
        st.warning(f"Elevation API error: {e}")
    return None

def reverse_geocode(lat, lon):
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return location.address if location else None
    except Exception as e:
        st.warning(f"Reverse geocoding error: {e}")
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
        st.write("📋 Google Sheet headers:", headers)

        row = [summary_dict.get(col, "") for col in headers]
        st.write("📝 Row to append:", row)

        if all(cell == "" for cell in row):
            st.error("❌ All values in the row are empty. Check if headers match the dictionary keys.")
        else:
            sheet.append_row(row, value_input_option="USER_ENTERED")
            st.success("✅ Successfully appended to Google Sheet.")

    except gspread.exceptions.APIError as api_err:
        st.error(f"❌ Google Sheets API error: {api_err}")
    except KeyError as key_err:
        st.error(f"❌ Missing key in summary_record: {key_err}")
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")

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
Then saves the result to Google Sheets.
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

# Compute results
o_lat, o_lon = results["origin"]["lat"], results["origin"]["lon"]
d_lat, d_lon = results["destination"]["lat"], results["destination"]["lon"]

results["distance_km"] = haversine_distance(o_lat, o_lon, d_lat, d_lon)
results["bearing_od"] = initial_bearing(o_lat, o_lon, d_lat, d_lon)
results["bearing_do"] = initial_bearing(d_lat, d_lon, o_lat, o_lon)
results["origin"]["elevation"] = get_elevation(o_lat, o_lon)
results["destination"]["elevation"] = get_elevation(d_lat, d_lon)
results["origin"]["address"] =
