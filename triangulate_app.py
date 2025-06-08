import streamlit as st
import pandas as pd
import math
import requests
from geopy.geocoders import Nominatim
import pydeck as pdk
import time

st.set_page_config(page_title="Bearing Line Convergence", layout="wide")
geolocator = Nominatim(user_agent="geo_app")

# --- Helper Functions ---
def rotate_bearing(lat, lon, bearing_deg, distance_km=1000):
    R = 6371.0
    bearing_rad = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    lat2 = math.asin(math.sin(lat1) * math.cos(distance_km / R) +
                     math.cos(lat1) * math.sin(distance_km / R) * math.cos(bearing_rad))
    lon2 = lon1 + math.atan2(math.sin(bearing_rad) * math.sin(distance_km / R) * math.cos(lat1),
                             math.cos(distance_km / R) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)

def line_intersection(p1, b1, p2, b2):
    # Compute intersection of two geodesics
    φ1, λ1 = map(math.radians, p1)
    φ2, λ2 = map(math.radians, p2)
    θ13 = math.radians(b1)
    θ23 = math.radians(b2)

    Δφ = φ2 - φ1
    Δλ = λ2 - λ1

    Δ12 = 2 * math.asin(math.sqrt(math.sin(Δφ / 2) ** 2 +
                                  math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2))
    if Δ12 == 0:
        return None

    θa = math.acos((math.sin(φ2) - math.sin(φ1) * math.cos(Δ12)) /
                   (math.sin(Δ12) * math.cos(φ1)))
    θb = math.acos((math.sin(φ1) - math.sin(φ2) * math.cos(Δ12)) /
                   (math.sin(Δ12) * math.cos(φ2)))

    if math.sin(λ2 - λ1) > 0:
        θ12, θ21 = θa, 2 * math.pi - θb
    else:
        θ12, θ21 = 2 * math.pi - θa, θb

    α1 = (θ13 - θ12 + math.pi) % (2 * math.pi) - math.pi
    α2 = (θ21 - θ23 + math.pi) % (2 * math.pi) - math.pi

    if math.sin(α1) == 0 and math.sin(α2) == 0:
        return None
    if math.sin(α1) * math.sin(α2) < 0:
        return None

    α3 = math.acos(-math.cos(α1) * math.cos(α2) +
                   math.sin(α1) * math.sin(α2) * math.cos(Δ12))
    Δ13 = math.atan2(math.sin(Δ12) * math.sin(α1) * math.sin(α2),
                     math.cos(α2) + math.cos(α1) * math.cos(α3))

    φ3 = math.asin(math.sin(φ1) * math.cos(Δ13) +
                   math.cos(φ1) * math.sin(Δ13) * math.cos(θ13))
    λ3 = λ1 + math.atan2(math.sin(θ13) * math.sin(Δ13) * math.cos(φ1),
                         math.cos(Δ13) - math.sin(φ1) * math.sin(φ3))
    return math.degrees(φ3), math.degrees(λ3)

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

# --- Coordinates ---
coords = {
    "A": {"lat": 14.64171, "lon": 121.05078},
    "B": {"lat": 14.595534, "lon": 121.136655},
    "C": {"lat": 14.365178, "lon": 120.891176},
}

st.title("📍 Bearing Convergence from Points A, B, C")

# User-defined bearings
st.sidebar.header("🧭 Bearings (0° = North)")
bearings = {
    k: st.sidebar.slider(f"Bearing from Point {k}", 0, 359, 0)
    for k in coords
}

# Calculate projected points for each line
projections = {
    k: rotate_bearing(coords[k]["lat"], coords[k]["lon"], bearings[k], 1000)
    for k in coords
}

# Button to triangulate
show_center = st.sidebar.button("🔍 Triangulate Location")

# Intersections between bearing lines
inter1 = line_intersection((coords["A"]["lat"], coords["A"]["lon"]), bearings["A"],
                           (coords["B"]["lat"], coords["B"]["lon"]), bearings["B"])
inter2 = line_intersection((coords["B"]["lat"], coords["B"]["lon"]), bearings["B"],
                           (coords["C"]["lat"], coords["C"]["lon"]), bearings["C"])
inter3 = line_intersection((coords["C"]["lat"], coords["C"]["lon"]), bearings["C"],
                           (coords["A"]["lat"], coords["A"]["lon"]), bearings["A"])

if show_center and inter1 and inter2 and inter3:
    lat_center = (inter1[0] + inter2[0] + inter3[0]) / 3
    lon_center = (inter1[1] + inter2[1] + inter3[1]) / 3
    elevation = get_elevation(lat_center, lon_center)
    address = reverse_geocode(lat_center, lon_center)
else:
    lat_center = lon_center = elevation = address = None

# Map layers
df_points = pd.DataFrame([
    {"name": f"Point {k}", "latitude": coords[k]["lat"], "longitude": coords[k]["lon"], "color": [255, 0, 0]}
    for k in coords
])

df_lines = pd.DataFrame([
    {"start_lat": coords[k]["lat"], "start_lon": coords[k]["lon"],
     "end_lat": projections[k][0], "end_lon": projections[k][1]}
    for k in coords
])

df_center = pd.DataFrame([{
    "name": "Intersection Center",
    "latitude": lat_center,
    "longitude": lon_center,
    "color": [0, 255, 0]
}]) if lat_center else pd.DataFrame()

# Map rendering
deck = pdk.Deck(
    layers=[
        pdk.Layer("ScatterplotLayer", data=df_points, get_position=["longitude", "latitude"],
                  get_fill_color="color", get_radius=8, radiusUnits="pixels"),
        pdk.Layer("LineLayer", data=df_lines, get_source_position=["start_lon", "start_lat"],
                  get_target_position=["end_lon", "end_lat"], get_color=[0, 128, 255], get_width=3),
        pdk.Layer("ScatterplotLayer", data=df_center, get_position=["longitude", "latitude"],
                  get_fill_color="color", get_radius=12 + 4 * int(time.time()) % 2, radiusUnits="pixels")
    ],
    initial_view_state=pdk.ViewState(latitude=14.5, longitude=121.0, zoom=9),
    tooltip={"html": "<b>{name}</b><br/>Lat: {latitude}<br/>Lon: {longitude}"}
)

st.pydeck_chart(deck)

# Sidebar output
if show_center and lat_center:
    st.sidebar.header("📍 Intersection Location")
    st.sidebar.write(f"**Coordinates:** {lat_center:.6f}, {lon_center:.6f}")
    st.sidebar.write(f"**Elevation:** {elevation:.1f} m" if elevation else "-")
    st.sidebar.write(f"**Address:** {address if address else 'N/A'}")
