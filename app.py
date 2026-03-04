import streamlit as st
import ee
import json
import tempfile
import os
import folium
from streamlit_folium import folium_static

# --- PREMIUM PAGE STYLING ---
st.set_page_config(layout="wide", page_title="NASA SRTM Elevation Explorer")

# --- AUTHENTICATION LOGIC ---
try:
    # Determine which secret key holds the JSON
    json_key = None
    if 'json_data' in st.secrets:
        json_key = 'json_data'
    elif 'EE_SERVICE_ACCOUNT' in st.secrets:
        json_key = 'EE_SERVICE_ACCOUNT'

    if json_key:
        # For Streamlit Cloud: write JSON secret to a temp file
        # (avoids json.loads escape-character issues with TOML strings)
        service_account_json = st.secrets[json_key]
        key_path = os.path.join(tempfile.gettempdir(), 'ee_service_account.json')
        with open(key_path, 'w') as f:
            f.write(service_account_json)

        # Read email from the secret or from the JSON file
        sa_email = st.secrets.get(
            'service_account',
            json.load(open(key_path))['client_email']
        )

        credentials = ee.ServiceAccountCredentials(sa_email, key_file=key_path)
        ee.Initialize(credentials, project='ee-innovativegeographer')
    else:
        # For Local Development
        ee.Initialize(project='ee-innovativegeographer')
except Exception as e:
    st.error("🔑 **Earth Engine Authentication Failed**")
    st.info("To fix this on Streamlit Cloud, ensure you have added your service account JSON to `.streamlit/secrets.toml` or the Streamlit Dashboard Secrets box under `json_data` and `service_account` keys.")
    st.code("""json_data = '''\n{\n  "type": "service_account",\n  ...\n}'''\n\nservice_account = '...'""", language="toml")
    st.write(f"**Error Details:** {e}")
    st.stop()

# Inject custom CSS for a premium look
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');

    html, body, [data-testid="stSidebar"] {
        font-family: 'Inter', sans-serif;
    }

    h1 {
        font-weight: 800;
        color: #1e293b;
        letter-spacing: -1px;
        margin-bottom: 0.5rem;
    }

    .main {
        background-color: #f8fafc;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛰️ NASA SRTM Global Elevation")
st.write("A clean demonstration of using Google Earth Engine with Streamlit & Folium.")

# --- MAP SECTION ---
with st.echo():
    # 1. Define location (Cuttack, Odisha)
    lat, lon = 20.4625, 85.8828

    # 2. Load the SRTM Elevation dataset
    srtm = ee.Image('USGS/SRTMGL1_003')

    # 3. Set visualization parameters
    vis_params = {
        'min': 0,
        'max': 100,
        'palette': ['#006633', '#E5FFCC', '#662A00', '#D8D8D8', '#F5F5F5']
    }

    # 4. Get EE tile URL for the DEM layer
    dem_map_id = srtm.getMapId(vis_params)

    # 5. Get EE tile URL for Hillshade layer
    hillshade = ee.Terrain.hillshade(srtm)
    hillshade_map_id = hillshade.getMapId({'min': 0, 'max': 255})

    # 6. Create a Folium Map centered on the location
    m = folium.Map(location=[lat, lon], zoom_start=12)

    # 7. Add SRTM DEM tile layer
    folium.TileLayer(
        tiles=dem_map_id['tile_fetcher'].url_format,
        attr='Google Earth Engine - SRTM DEM',
        name='SRTM Elevation',
        overlay=True,
        control=True
    ).add_to(m)

    # 8. Add Hillshade tile layer for 3D texture
    folium.TileLayer(
        tiles=hillshade_map_id['tile_fetcher'].url_format,
        attr='Google Earth Engine - Hillshade',
        name='Hillshade (3D Texture)',
        overlay=True,
        control=True,
        opacity=0.3
    ).add_to(m)

    # 9. Add a marker for the city center
    folium.Marker(
        location=[lat, lon],
        popup='Cuttack City Center',
        tooltip='Cuttack City Center',
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)

    # 10. Add Layer Control for easy toggling
    folium.LayerControl().add_to(m)

    # 11. Render the Folium map in Streamlit
    folium_static(m, width=1200, height=600)

st.success("✅ Map rendered successfully using Earth Engine tiles.")
