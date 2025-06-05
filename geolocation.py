# gps_streamlit_app.py

import streamlit as st
import pandas as pd
import math
import requests
from geopy.geocoders import Nominatim
import pydeck as pdk
from streamlit_geolocation import streamlit_geolocation

# --- Configuration ---
st.set_page_config(
    page_title="Geolocation Map with Origin & Destination",
    layout="wide"
)

# Fixed origin coordinates (Manila, PH by default)
ORIGIN_LAT = 14.64171
ORIGIN_LON = 121.05078

# Initialize geocoder (for reverse geocoding)
geolocator = Nominatim(user_agent="geo_app")


# ------------------------- Helper Functions -------------------------

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great‐circle distance between two points 
    using the Haversine formula (in kilometers).
    """
    R = 6371.0  # Earth radius in km
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)

    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def initial_bearing(lat1, lon1, lat2, lon2):
    """
    Calculate the initial bearing (forward azimuth) from (lat1, lon1) to (lat2, lon2).
    The result is in degrees from North (0° ≤ θ < 360°).
    """
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)

    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    θ = math.degrees(math.atan2(x, y))
    return (θ + 360) % 360


def get_elevation(lat, lon):
    """
    Query Open‐Elevation API to get elevation (in meters) for the given lat/lon.
    Falls back to None on error.
    """
    try:
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data["results"][0]["elevation"]
    except Exception:
        pass
    return None


def reverse_geocode(lat, lon):
    """
    Use Nominatim to reverse‐geocode (lat, lon) into a human‐readable address.
    Returns None on failure.
    """
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return location.address if location else None
    except Exception:
        return None


# ------------------------- Streamlit UI -------------------------

st.title("📍 Origin & Destination Geolocation")
st.write(
    """
    This app fixes the **origin** at (14.64171, 121.05078) in Metro Manila (marked “O”) 
    and plots your **destination** (your phone’s current GPS) as “D.”  
    It draws a line between them and computes:
      - Distance (km)  
      - Bearing from Origin → Destination (°)  
      - Bearing from Destination → Origin (°)  
      - Elevation (m)  
      - Address (reverse‐geocoded)

    All details are summarized in the **sidebar**.
    """
)

# Request user location
location_data = streamlit_geolocation()

# Prepare a structure to hold results
results = {
    "origin": {
        "lat": ORIGIN_LAT,
        "lon": ORIGIN_LON,
        "elevation": None,
        "address": None,
    },
    "destination": {
        "lat": None,
        "lon": None,
        "elevation": None,
        "address": None,
    },
    "distance_km": None,
    "bearing_od": None,     # Origin → Destination
    "bearing_do": None,     # Destination → Origin
}

# 1) Compute everything if user grants location
if isinstance(location_data, dict) and "latitude" in location_data:
    dest_lat = location_data["latitude"]
    dest_lon = location_data["longitude"]
    results["destination"]["lat"] = dest_lat
    results["destination"]["lon"] = dest_lon

    # Distance
    dist = haversine_distance(ORIGIN_LAT, ORIGIN_LON, dest_lat, dest_lon)
    results["distance_km"] = dist

    # Bearing Origin → Destination
    brg_od = initial_bearing(ORIGIN_LAT, ORIGIN_LON, dest_lat, dest_lon)
    results["bearing_od"] = brg_od

    # Bearing Destination → Origin
    brg_do = initial_bearing(dest_lat, dest_lon, ORIGIN_LAT, ORIGIN_LON)
    results["bearing_do"] = brg_do

    # Elevations
    results["origin"]["elevation"] = get_elevation(ORIGIN_LAT, ORIGIN_LON)
    results["destination"]["elevation"] = get_elevation(dest_lat, dest_lon)

    # Reverse geocoding
    results["origin"]["address"] = reverse_geocode(ORIGIN_LAT, ORIGIN_LON)
    results["destination"]["address"] = reverse_geocode(dest_lat, dest_lon)

    st.success(f"Destination found: {dest_lat:.6f}, {dest_lon:.6f}")
else:
    st.info("Waiting for you to click the button and grant location permission.")

# 2) Build Map (only if destination is known)
if results["destination"]["lat"] is not None:

    # DataFrame for two markers: origin (O) and destination (D)
    df_markers = pd.DataFrame([
        {
            "name": "Origin (O)",
            "latitude": results["origin"]["lat"],
            "longitude": results["origin"]["lon"],
            "marker": "O"
        },
        {
            "name": "Destination (D)",
            "latitude": results["destination"]["lat"],
            "longitude": results["destination"]["lon"],
            "marker": "D"
        }
    ])

    # DataFrame for the line connecting O → D
    df_line = pd.DataFrame([{
        "start_lat": results["origin"]["lat"],
        "start_lon": results["origin"]["lon"],
        "end_lat": results["destination"]["lat"],
        "end_lon": results["destination"]["lon"]
    }])

    # Pydeck layers
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_markers,
        get_position=["longitude", "latitude"],
        get_fill_color=[255, 0, 0, 200],
        get_radius=100,
        pickable=True,
        auto_highlight=True,
    )

    text_layer = pdk.Layer(
        "TextLayer",
        data=df_markers,
        pickable=False,
        get_position=["longitude", "latitude"],
        get_text="marker",
        get_color=[0, 0, 0, 255],
        get_size=32,
        get_alignment_baseline="'bottom'"
    )

    line_layer = pdk.Layer(
        "LineLayer",
        data=df_line,
        get_source_position=["start_lon", "start_lat"],
        get_target_position=["end_lon", "end_lat"],
        get_color=[0, 128, 255, 200],
        get_width=4,
    )

    # Center the map on the midpoint
    mid_lat = (results["origin"]["lat"] + results["destination"]["lat"]) / 2
    mid_lon = (results["origin"]["lon"] + results["destination"]["lon"]) / 2

    view_state = pdk.ViewState(
        latitude=mid_lat,
        longitude=mid_lon,
        zoom=5,
        pitch=0,
    )

    deck = pdk.Deck(
        layers=[line_layer, scatter_layer, text_layer],
        initial_view_state=view_state,
        tooltip={
            "html": "<b>{name}</b><br/>Lat: {latitude}<br/>Lon: {longitude}",
            "style": {"color": "white"},
        },
    )

    st.pydeck_chart(deck)


# 3) Sidebar Summary
st.sidebar.header("📋 Summary")

# Origin summary
st.sidebar.subheader("Origin (O)")
st.sidebar.write(f"- **Coordinates:** {results['origin']['lat']:.6f}, {results['origin']['lon']:.6f}")
if results["origin"]["elevation"] is not None:
    st.sidebar.write(f"- **Elevation:** {results['origin']['elevation']:.1f} m")
else:
    st.sidebar.write("- **Elevation:** N/A")
if results["origin"]["address"]:
    st.sidebar.write(f"- **Address:** {results['origin']['address']}")
else:
    st.sidebar.write("- **Address:** N/A")

# Destination summary (only if available)
if results["destination"]["lat"] is not None:
    st.sidebar.subheader("Destination (D)")
    st.sidebar.write(
        f"- **Coordinates:** {results['destination']['lat']:.6f}, {results['destination']['lon']:.6f}"
    )
    if results["destination"]["elevation"] is not None:
        st.sidebar.write(f"- **Elevation:** {results['destination']['elevation']:.1f} m")
    else:
        st.sidebar.write("- **Elevation:** N/A")
    if results["destination"]["address"]:
        st.sidebar.write(f"- **Address:** {results['destination']['address']}")
    else:
        st.sidebar.write("- **Address:** N/A")

    # Distance & Bearings
    st.sidebar.subheader("Route Info")
    st.sidebar.write(f"- **Distance:** {results['distance_km']:.3f} km")
    st.sidebar.write(f"- **Bearing O → D:** {results['bearing_od']:.1f}°")
    st.sidebar.write(f"- **Bearing D → O:** {results['bearing_do']:.1f}°")
else:
    st.sidebar.info("No destination data yet. Please grant location permission.")

