import streamlit as st
import ee
import geemap.foliumap as geemap
from streamlit_folium import folium_static

# --- PREMIUM PAGE STYLING ---
st.set_page_config(layout="wide", page_title="NASA SRTM elevation Explorer")

# Inject custom CSS for a premium "Folium Example" look
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
    
    .stEcho {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    
    .main {
        background-color: #f8fafc;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛰️ NASA SRTM Global elevation")
st.write("A clean demonstration of using Google Earth Engine with Streamlit & Folium.")

# --- THE CODE BLOCK (AS SEEN IN THE USER'S SCREENSHOT) ---
with st.echo():
    import streamlit as st
    import ee
    import geemap.foliumap as geemap
    from streamlit_folium import folium_static

    import json
    import tempfile
    import os

    # --- AUTHENTICATION LOGIC ---
    try:
        if 'EE_SERVICE_ACCOUNT' in st.secrets:
            # For Streamlit Cloud: Use Service Account from Secrets
            # We'll save it to a temporary file as some GEE functions prefer a file path
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
                f.write(st.secrets['EE_SERVICE_ACCOUNT'])
                temp_path = f.name
            
            try:
                credentials = ee.ServiceAccountCredentials('', temp_path)
                ee.Initialize(credentials, project='ee-innovativegeographer')
            finally:
                # Cleanup: remove the temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            # For Local Development: Falls back to local 'earthengine authenticate' credentials
            # This will fail on Streamlit Cloud if secrets are not set, which is intended
            ee.Initialize(project='ee-innovativegeographer')
    except Exception as e:
        st.error("🔑 **Earth Engine Authentication Failed**")
        st.info("To fix this on Streamlit Cloud, ensure you have added your service account JSON to `.streamlit/secrets.toml` or the Streamlit Dashboard Secrets box.")
        st.code("""EE_SERVICE_ACCOUNT = '''\n{\n  "type": "service_account",\n  ...\n}'''""", language="toml")
        st.write(f"**Error Details:** {e}")
        st.stop()

    # 2. Define location (Cuttack, Odisha)
    lat, lon = 20.4625, 85.8828
    
    # 3. Load the SRTM Elevation dataset
    srtm = ee.Image('USGS/SRTMGL1_003')

    # 4. Set visualization parameters (Premium Palette)
    vis_params = {
        'min': 0,
        'max': 100,
        'palette': ['#006633', '#E5FFCC', '#662A00', '#D8D8D8', '#F5F5F5']
    }

    # 5. Create a Map centered on the location
    m = geemap.Map(center=[lat, lon], zoom=12)

    # 6. Add SRTM Layer
    m.addLayer(srtm, vis_params, 'SRTM Elevation')
    
    # 7. Add a Hillshade layer for the "WOW" texture factor
    hillshade = ee.Terrain.hillshade(srtm)
    m.addLayer(hillshade, {'opacity': 0.3}, 'Hillshade (3D Texture)')

    # 8. Add a marker for the city center
    m.add_marker([lat, lon], tooltip="Cuttack City Center")

    # 9. Add Layer Control for easy toggling
    m.addLayerControl()

    # 10. Call to render Folium map in Streamlit
    folium_static(m, width=1200, height=600)

st.success("✅ Map rendered successfully using Earth Engine tiles.")
