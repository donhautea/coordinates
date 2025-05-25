pip install streamlit folium streamlit-folium

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MousePosition
from folium.features import DivIcon
import math

# --- Page config ---------------------------------------------------
st.set_page_config(page_title="Coordinate Picker & Bearing & Distance", layout="wide")

# --- Session state defaults ---------------------------------------
for key in ("origin", "destination", "origin_input", "destination_input"):
    if key not in st.session_state:
        st.session_state[key] = ""

# Callback functions for buttons
def update_map():
    st.session_state.origin = st.session_state.origin_input
    st.session_state.destination = st.session_state.destination_input

def reset_map():
    for key in ("origin", "destination", "origin_input", "destination_input"):
        st.session_state[key] = ""

# --- Sidebar UI ----------------------------------------------------
st.sidebar.header("Select Coordinates, Bearings & Distance")
# Manual entry fields
st.sidebar.text_input(
    "Origin (lat, lon)",
    key="origin_input",
    label_visibility="visible",
)
st.sidebar.text_input(
    "Destination (lat, lon)",
    key="destination_input",
    label_visibility="visible",
)
# Buttons to apply or reset using callbacks
st.sidebar.button("Update Map", on_click=update_map)
st.sidebar.button("Reset Map", on_click=reset_map)

# Mode selector for map clicks
coord_mode = st.sidebar.radio(
    "Click map to set →",
    ("Origin", "Destination"),
)

# --- Bearing & Distance calculation ------------------------------------------
def calculate_bearing(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - \
        math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

# Haversine formula for distance in km
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Display bearings & distance if both coords set
if st.session_state.origin and st.session_state.destination:
    try:
        lat1, lon1 = map(float, st.session_state.origin.split(","))
        lat2, lon2 = map(float, st.session_state.destination.split(","))
        b1 = calculate_bearing(lat1, lon1, lat2, lon2)
        b2 = calculate_bearing(lat2, lon2, lat1, lon1)
        dist_km = calculate_distance(lat1, lon1, lat2, lon2)
        st.sidebar.markdown("**Bearings & Distance**:")
        st.sidebar.write(f"Origin → Destination: {b1:.2f}°")
        st.sidebar.write(f"Destination → Origin: {b2:.2f}°")
        st.sidebar.write(f"Distance: {dist_km:.2f} km")
    except ValueError:
        st.sidebar.error("Invalid coordinate format. Use 'lat, lon'.")

# --- Build Folium map ---------------------------------------------
# Determine map center
try:
    lat0, lon0 = map(float, st.session_state.origin.split(","))
except ValueError:
    lat0, lon0 = 0, 0

m = folium.Map(location=[lat0, lon0], zoom_start=4)
# Live mouse coordinates
MousePosition(
    position="topright",
    separator=" | ",
    empty_string="NaN",
    prefix="Mouse:",
    num_digits=6,
).add_to(m)

# Draw line and markers if coords available
if st.session_state.origin and st.session_state.destination:
    try:
        lat1, lon1 = map(float, st.session_state.origin.split(","))
        lat2, lon2 = map(float, st.session_state.destination.split(","))
        # Line
        folium.PolyLine(locations=[[lat1, lon1], [lat2, lon2]], weight=3).add_to(m)
        # Bearings
        b1 = calculate_bearing(lat1, lon1, lat2, lon2)
        b2 = calculate_bearing(lat2, lon2, lat1, lon1)
        # Origin marker
        folium.Marker(
            [lat1, lon1],
            icon=DivIcon(html=f'<div style="font-weight:bold;color:red;">O: {b1:.2f}°</div>')
        ).add_to(m)
        # Destination marker
        folium.Marker(
            [lat2, lon2],
            icon=DivIcon(html=f'<div style="font-weight:bold;color:red;">D: {b2:.2f}°</div>')
        ).add_to(m)
    except ValueError:
        pass

# Render map and capture interactions
map_data = st_folium(m, width=900, height=600)

# --- Handle click event -------------------------------------------
clicked = map_data.get("last_clicked")
if clicked:
    coord_str = f"{clicked['lat']:.6f}, {clicked['lng']:.6f}"
    if coord_mode == "Origin":
        st.session_state.origin_input = coord_str
        st.session_state.origin = coord_str
    else:
        st.session_state.destination_input = coord_str
        st.session_state.destination = coord_str
