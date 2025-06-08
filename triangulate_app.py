import streamlit as st
import pandas as pd
import math
import requests
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium
import folium

# --- Page Config ---
st.set_page_config(page_title="4G1AQX Triangulation System", layout="wide")
geolocator = Nominatim(user_agent="geo_app")

# --- Helper Functions ---
def rotate_bearing(lat, lon, bearing_deg, distance_km=1000):
    R = 6371.0
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1)*math.cos(distance_km/R) + math.cos(lat1)*math.sin(distance_km/R)*math.cos(br))
    lon2 = lon1 + math.atan2(math.sin(br)*math.sin(distance_km/R)*math.cos(lat1), math.cos(distance_km/R)-math.sin(lat1)*math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)

def line_intersection(p1, b1, p2, b2):
    φ1, λ1 = map(math.radians, p1)
    φ2, λ2 = map(math.radians, p2)
    θ13, θ23 = math.radians(b1), math.radians(b2)
    Δφ, Δλ = φ2 - φ1, λ2 - λ1
    Δ12 = 2 * math.asin(math.sqrt(math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2))
    if Δ12 == 0: return None
    θa = math.acos((math.sin(φ2) - math.sin(φ1)*math.cos(Δ12)) / (math.sin(Δ12)*math.cos(φ1)))
    θb = math.acos((math.sin(φ1) - math.sin(φ2)*math.cos(Δ12)) / (math.sin(Δ12)*math.cos(φ2)))
    θ12, θ21 = (θa, 2*math.pi-θb) if math.sin(λ2-λ1) > 0 else (2*math.pi-θa, θb)
    α1 = (θ13 - θ12 + math.pi) % (2*math.pi) - math.pi
    α2 = (θ21 - θ23 + math.pi) % (2*math.pi) - math.pi
    if math.sin(α1) == 0 and math.sin(α2) == 0: return None
    if math.sin(α1)*math.sin(α2) < 0: return None
    α3 = math.acos(-math.cos(α1)*math.cos(α2) + math.sin(α1)*math.sin(α2)*math.cos(Δ12))
    Δ13 = math.atan2(math.sin(Δ12)*math.sin(α1)*math.sin(α2), math.cos(α2) + math.cos(α1)*math.cos(α3))
    φ3 = math.asin(math.sin(φ1)*math.cos(Δ13) + math.cos(φ1)*math.sin(Δ13)*math.cos(θ13))
    λ3 = λ1 + math.atan2(math.sin(θ13)*math.sin(Δ13)*math.cos(φ1), math.cos(Δ13) - math.sin(φ1)*math.sin(φ3))
    return math.degrees(φ3), math.degrees(λ3)

def reverse_geocode(lat, lon):
    try:
        loc = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return loc.address if loc else None
    except:
        return None

# --- Base Points ---
coords = {
    "A": {"lat": 14.64171, "lon": 121.05078},
    "B": {"lat": 14.595534, "lon": 121.136655},
    "C": {"lat": 14.365178, "lon": 120.891176},
}

# --- UI Controls ---
st.title("📍 4G1AQX Triangulation System")
st.sidebar.header("Required Azimuth and Controls")
# Bearing sliders
bearings = {k: st.sidebar.slider(f"Azimuth for {k} (0°=North)", 0, 359, 0) for k in coords}
# Buttons
if 'calculated' not in st.session_state:
    st.session_state.calculated = False
    st.session_state.selected = []
if st.sidebar.button("🔍 Calculate"):
    st.session_state.calculated = True
if st.sidebar.button("🔄 Reset"):
    st.session_state.calculated = False
    st.session_state.selected = []

# Precompute intersections
i_pts = {}
pairs = [("AB","A","B"), ("BC","B","C"), ("CA","C","A")]
for tag, p, q in pairs:
    pt = line_intersection(
        (coords[p]["lat"], coords[p]["lon"]), bearings[p],
        (coords[q]["lat"], coords[q]["lon"]), bearings[q]
    )
    if pt:
        i_pts[tag] = pt

# Build map
m = folium.Map(location=[14.5, 121.0], zoom_start=9, width='100%', height=600)
# Plot base points
for lbl, v in coords.items():
    folium.CircleMarker(
        [v['lat'], v['lon']],
        radius=6,
        color='red',
        fill=True,
        fill_color='red',
        popup=f"Point {lbl}"
    ).add_to(m)
# Plot bearing lines clipped
def _endpoint(k):
    ends = [i_pts[t] for t in i_pts if k in t]
    return min(ends, key=lambda x: (x[0]-coords[k]['lat'])**2 + (x[1]-coords[k]['lon'])**2) if ends else rotate_bearing(
        coords[k]["lat"], coords[k]["lon"], bearings[k]
    )
for k in coords:
    endpt = _endpoint(k)
    folium.PolyLine(
        [(coords[k]['lat'], coords[k]['lon']), endpt],
        color='blue',
        weight=2
    ).add_to(m)
# Plot intersections
for tag, (lat, lon) in i_pts.items():
    folium.Marker(
        [lat, lon],
        popup=tag,
        icon=folium.Icon(color='orange')
    ).add_to(m)

# Show intersection center if calculated
if st.session_state.calculated and i_pts:
    sel = st.sidebar.multiselect(
        "Select intersections for centroid:",
        list(i_pts.keys()),
        default=list(i_pts.keys())
    )
    st.session_state.selected = sel
    if sel:
        int_center = (
            sum(i_pts[k][0] for k in sel) / len(sel),
            sum(i_pts[k][1] for k in sel) / len(sel)
        )
        int_address = reverse_geocode(int_center[0], int_center[1])
        # shade polygon and draw center
        poly = [i_pts[k] for k in sel]
        folium.Polygon(
            poly,
            color='green',
            fill=True,
            fill_opacity=0.2
        ).add_to(m)
        folium.PolyLine(
            poly + [poly[0]],
            color='green',
            weight=3
        ).add_to(m)
        folium.CircleMarker(
            int_center,
            radius=8,
            color='green',
            fill=True,
            fill_color='green',
            popup=f"Intersection Center\n{int_address if int_address else ''}"
        ).add_to(m)
        # Sidebar details
        st.sidebar.header("📍 Intersection Center")
        st.sidebar.markdown(
            f"🟢 **Coordinates:** {int_center[0]:.6f}, {int_center[1]:.6f}"
        )
        st.sidebar.markdown(
            f"🟢 **Address:** {int_address if int_address else 'N/A'}"
        )

# Display map
st_folium(m, width='100%', height=600)
