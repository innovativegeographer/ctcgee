import streamlit as st
import ee
import json
import tempfile
import os
import folium
import folium.plugins as plugins
import urllib.request
from streamlit_folium import st_folium
from fpdf import FPDF
from datetime import datetime
import math

# --- PREMIUM PAGE STYLING ---
st.set_page_config(layout="wide", page_title="NASA SRTM Elevation Explorer")

# --- AUTHENTICATION LOGIC ---
try:
    json_key = None
    if 'json_data' in st.secrets:
        json_key = 'json_data'
    elif 'EE_SERVICE_ACCOUNT' in st.secrets:
        json_key = 'EE_SERVICE_ACCOUNT'

    if json_key:
        service_account_json = st.secrets[json_key]
        key_path = os.path.join(tempfile.gettempdir(), 'ee_service_account.json')
        with open(key_path, 'w') as f:
            f.write(service_account_json)
        sa_email = st.secrets.get(
            'service_account',
            json.load(open(key_path))['client_email']
        )
        credentials = ee.ServiceAccountCredentials(sa_email, key_file=key_path)
        ee.Initialize(credentials, project='ee-innovativegeographer')
    else:
        ee.Initialize(project='ee-innovativegeographer')
except Exception as e:
    st.error("🔑 **Earth Engine Authentication Failed**")
    st.info("Ensure your service account JSON is in the Streamlit Dashboard Secrets box under `json_data` and `service_account` keys.")
    st.write(f"**Error Details:** {e}")
    st.stop()

# ── Custom CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

    html, body, [data-testid="stSidebar"] {
        font-family: 'Inter', sans-serif;
    }

    h1 {
        font-weight: 800;
        background: linear-gradient(135deg, #006633, #00994d);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -1px;
        margin-bottom: 0.5rem;
    }

    .main {
        background-color: #f8fafc;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.4rem;
        font-weight: 700;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0a1628 0%, #132742 100%);
    }

    [data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }

    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }

    .draw-info-box {
        background: linear-gradient(135deg, #f0fdf4, #dcfce7);
        border: 1px solid #86efac;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
    }

    .custom-site-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 18px;
        margin: 8px 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
</style>
""", unsafe_allow_html=True)

st.title("🛰️ NASA SRTM Elevation Explorer")
st.caption("Powered by Google Earth Engine  •  Cuttack, Odisha, India")

# ── Sidebar Controls ─────────────────────────────────────────────────
st.sidebar.title("📋 Report Settings")
report_name = st.sidebar.text_input("Report Title", "Cuttack Elevation Report")
user_name = st.sidebar.text_input("Your Name", "User")
buffer_km = st.sidebar.slider("Buffer Radius (km)", 1, 20, 5)

st.sidebar.markdown("---")
st.sidebar.title("✏️ Drawing Tools")
st.sidebar.info(
    "Use the **drawing tools** on the map to draw points, polygons, "
    "rectangles, or circles. Elevation statistics will be computed "
    "automatically for your drawn area."
)
point_buffer_m = st.sidebar.slider(
    "Point buffer radius (m)", 100, 5000, 500,
    help="When you draw a point, this buffer radius is used to create an analysis area around it."
)

# ── Earth Engine Processing ──────────────────────────────────────────
CUTTACK_LAT, CUTTACK_LON = 20.4625, 85.8828
point = ee.Geometry.Point(CUTTACK_LON, CUTTACK_LAT)
roi = point.buffer(buffer_km * 1000)

dem = ee.Image('USGS/SRTMGL1_003')

# Compute statistics for default ROI
with st.spinner("Computing elevation statistics from SRTM DEM..."):
    stats = dem.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=roi,
        scale=30,
        maxPixels=1e9
    ).getInfo()

avg_elev = round(stats.get('elevation_mean', 0), 2)
min_elev = round(stats.get('elevation_min', 0), 2)
max_elev = round(stats.get('elevation_max', 0), 2)
std_elev = round(stats.get('elevation_stdDev', 0), 2)
elev_range = round(max_elev - min_elev, 2)

# ── Display Metrics ──────────────────────────────────────────────────
st.markdown("### 📊 Default Study Area — Elevation Statistics")
st.caption("Based on %s km buffer around Cuttack city center" % buffer_km)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("📊 Mean", "%.2f m" % avg_elev)
col2.metric("⬇️ Min", "%.2f m" % min_elev)
col3.metric("⬆️ Max", "%.2f m" % max_elev)
col4.metric("📐 Std Dev", "%.2f m" % std_elev)
col5.metric("📏 Range", "%.2f m" % elev_range)

# ── Build the Map with Drawing Tools ─────────────────────────────────
vis_params = {
    'min': 0,
    'max': 100,
    'palette': ['006633', 'E5FFCC', '662A00', 'D8D8D8', 'F5F5F5']
}

dem_map_id = dem.getMapId(vis_params)

hillshade = ee.Terrain.hillshade(dem)
hillshade_map_id = hillshade.getMapId({'min': 0, 'max': 255})

m = folium.Map(location=[CUTTACK_LAT, CUTTACK_LON], zoom_start=12)

# DEM tile layer
folium.TileLayer(
    tiles=dem_map_id['tile_fetcher'].url_format,
    attr='Google Earth Engine - SRTM DEM',
    name='SRTM Elevation',
    overlay=True,
    control=True
).add_to(m)

# Hillshade tile layer
folium.TileLayer(
    tiles=hillshade_map_id['tile_fetcher'].url_format,
    attr='Google Earth Engine - Hillshade',
    name='Hillshade (3D Texture)',
    overlay=True,
    control=True,
    opacity=0.3
).add_to(m)

# Study area boundary
roi_coords = roi.getInfo()['coordinates'][0]
boundary_coords = [[c[1], c[0]] for c in roi_coords]
folium.Polygon(
    locations=boundary_coords,
    color='#e63946',
    weight=3,
    fill=False,
    popup='Study Area: %s km buffer' % buffer_km
).add_to(m)

# Center marker
folium.Marker(
    location=[CUTTACK_LAT, CUTTACK_LON],
    popup='Cuttack City Center',
    tooltip='Cuttack City Center',
    icon=folium.Icon(color='red', icon='info-sign')
).add_to(m)

# ── Add Drawing Tools ────────────────────────────────────────────────
draw = plugins.Draw(
    export=True,
    position='topleft',
    draw_options={
        'polyline': False,
        'polygon': {
            'allowIntersection': False,
            'shapeOptions': {
                'color': '#3b82f6',
                'weight': 3,
                'fillOpacity': 0.2
            }
        },
        'rectangle': {
            'shapeOptions': {
                'color': '#8b5cf6',
                'weight': 3,
                'fillOpacity': 0.2
            }
        },
        'circle': {
            'shapeOptions': {
                'color': '#f59e0b',
                'weight': 3,
                'fillOpacity': 0.2
            }
        },
        'marker': True,
        'circlemarker': False,
    },
    edit_options={
        'edit': True,
        'remove': True,
    }
)
draw.add_to(m)

folium.LayerControl().add_to(m)

st.markdown("### 🗺️ Interactive Map — Draw to Analyze")
st.markdown(
    "**Study Area:** %s km buffer around Cuttack (20.46°N, 85.88°E) &nbsp;|&nbsp; "
    "✏️ **Use the toolbar on the left of the map** to draw points, polygons, rectangles, or circles "
    "and get instant elevation analysis." % buffer_km
)

# Render map and capture drawn data
map_data = st_folium(m, width=None, height=600, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# DRAWN FEATURE ANALYSIS
# ══════════════════════════════════════════════════════════════════════

def compute_drawn_stats(geometry):
    """Compute elevation statistics for a drawn EE geometry."""
    drawn_stats = dem.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geometry,
        scale=30,
        maxPixels=1e9
    ).getInfo()
    return {
        'mean': round(drawn_stats.get('elevation_mean', 0), 2),
        'min': round(drawn_stats.get('elevation_min', 0), 2),
        'max': round(drawn_stats.get('elevation_max', 0), 2),
        'std': round(drawn_stats.get('elevation_stdDev', 0), 2),
    }


def geojson_to_ee_geometry(feature):
    """Convert a GeoJSON feature to an Earth Engine geometry."""
    geom = feature.get('geometry', feature)
    geom_type = geom.get('type', '')
    coords = geom.get('coordinates', [])

    if geom_type == 'Point':
        return ee.Geometry.Point(coords).buffer(point_buffer_m)
    elif geom_type == 'Polygon':
        return ee.Geometry.Polygon(coords)
    elif geom_type == 'LineString':
        return ee.Geometry.LineString(coords).buffer(100)
    else:
        return None


def get_feature_label(feature, index):
    """Generate a human-readable label for a drawn feature."""
    geom = feature.get('geometry', feature)
    geom_type = geom.get('type', '')
    coords = geom.get('coordinates', [])

    if geom_type == 'Point':
        return "📍 Point %d (%.4f°N, %.4f°E) — %dm buffer" % (
            index, coords[1], coords[0], point_buffer_m
        )
    elif geom_type == 'Polygon':
        n_vertices = len(coords[0]) - 1 if coords else 0
        return "🔷 Polygon %d (%d vertices)" % (index, n_vertices)
    else:
        return "📐 Shape %d (%s)" % (index, geom_type)


# Check if any features were drawn
all_drawings = map_data.get('all_drawings', []) if map_data else []
last_drawing = map_data.get('last_active_drawing') if map_data else None

# Store drawn features in session state
if 'drawn_features' not in st.session_state:
    st.session_state.drawn_features = []
if 'drawn_stats' not in st.session_state:
    st.session_state.drawn_stats = []

# Update drawn features from map
if all_drawings and len(all_drawings) > 0:
    st.session_state.drawn_features = all_drawings

st.markdown("---")
st.markdown("### ✏️ Custom Site Analysis")

if len(st.session_state.drawn_features) > 0:
    st.success("**%d feature(s) drawn** — Computing elevation statistics..." % len(st.session_state.drawn_features))

    # Process each drawn feature
    new_stats = []
    for idx, feature in enumerate(st.session_state.drawn_features, 1):
        ee_geom = geojson_to_ee_geometry(feature)
        if ee_geom:
            try:
                feature_stats = compute_drawn_stats(ee_geom)
                label = get_feature_label(feature, idx)
                new_stats.append({
                    'label': label,
                    'stats': feature_stats,
                    'feature': feature,
                    'index': idx
                })
            except Exception as e:
                st.warning("Could not compute stats for feature %d: %s" % (idx, str(e)))

    st.session_state.drawn_stats = new_stats

    # Display stats for each drawn feature
    for item in st.session_state.drawn_stats:
        s = item['stats']
        with st.container():
            st.markdown(
                '<div class="custom-site-card">',
                unsafe_allow_html=True
            )
            st.markdown("#### %s" % item['label'])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📊 Mean", "%.2f m" % s['mean'])
            c2.metric("⬇️ Min", "%.2f m" % s['min'])
            c3.metric("⬆️ Max", "%.2f m" % s['max'])
            c4.metric("📐 Std Dev", "%.2f m" % s['std'])
            st.markdown('</div>', unsafe_allow_html=True)

    # Comparison table
    if len(st.session_state.drawn_stats) > 1:
        st.markdown("#### 📋 Comparison Table")
        table_data = []
        for item in st.session_state.drawn_stats:
            s = item['stats']
            table_data.append({
                'Site': item['label'],
                'Mean (m)': s['mean'],
                'Min (m)': s['min'],
                'Max (m)': s['max'],
                'Std Dev (m)': s['std'],
                'Range (m)': round(s['max'] - s['min'], 2)
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

else:
    st.markdown(
        '<div class="draw-info-box">'
        '<h4 style="margin:0 0 8px 0; color:#166534;">✏️ Draw on the map to analyze any area</h4>'
        '<p style="margin:0; color:#15803d;">'
        'Use the <strong>drawing toolbar</strong> on the left side of the map to:'
        '</p>'
        '<ul style="color:#15803d; margin:8px 0;">'
        '<li><strong>📍 Marker</strong> — Click to place a point (analyzed with %dm buffer)</li>'
        '<li><strong>🔷 Polygon</strong> — Click vertices to draw a custom shape</li>'
        '<li><strong>⬜ Rectangle</strong> — Click and drag to draw a box</li>'
        '<li><strong>⭕ Circle</strong> — Click and drag to draw a circle</li>'
        '</ul>'
        '<p style="margin:0; color:#15803d;">'
        'Elevation statistics will be computed instantly for your drawn area!'
        '</p>'
        '</div>' % point_buffer_m,
        unsafe_allow_html=True
    )

# ── Manual Coordinate Input ──────────────────────────────────────────
st.markdown("---")
st.markdown("### 📍 Analyze by Coordinates")
st.caption("Enter latitude and longitude manually to analyze a specific point.")

coord_col1, coord_col2, coord_col3 = st.columns([2, 2, 1])
with coord_col1:
    manual_lat = st.number_input("Latitude", value=20.4625, format="%.4f", step=0.01)
with coord_col2:
    manual_lon = st.number_input("Longitude", value=85.8828, format="%.4f", step=0.01)
with coord_col3:
    manual_buffer = st.number_input("Buffer (m)", value=500, min_value=100, max_value=10000, step=100)

if st.button("🔍 Analyze This Location", type="primary"):
    with st.spinner("Computing elevation for (%.4f, %.4f)..." % (manual_lat, manual_lon)):
        manual_geom = ee.Geometry.Point(manual_lon, manual_lat).buffer(manual_buffer)
        manual_stats = compute_drawn_stats(manual_geom)

        st.markdown("#### 📍 Results for (%.4f°N, %.4f°E) — %dm buffer" % (manual_lat, manual_lon, manual_buffer))
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("📊 Mean", "%.2f m" % manual_stats['mean'])
        mc2.metric("⬇️ Min", "%.2f m" % manual_stats['min'])
        mc3.metric("⬆️ Max", "%.2f m" % manual_stats['max'])
        mc4.metric("📐 Std Dev", "%.2f m" % manual_stats['std'])

        # Quick interpretation
        avg_m = manual_stats['mean']
        if avg_m < 10:
            terrain = "very low-lying coastal/floodplain"
        elif avg_m < 50:
            terrain = "low-elevation alluvial plain"
        elif avg_m < 200:
            terrain = "moderately elevated terrain"
        elif avg_m < 500:
            terrain = "elevated/hilly terrain"
        else:
            terrain = "high-altitude mountainous terrain"

        st.info(
            "**Quick Interpretation:** This location has a mean elevation of **%.2f m**, "
            "classified as **%s**. Elevation ranges from **%.2f m** to **%.2f m** "
            "within the %dm analysis buffer." % (
                avg_m, terrain, manual_stats['min'], manual_stats['max'], manual_buffer
            )
        )


# ══════════════════════════════════════════════════════════════════════
# PDF REPORT GENERATION
# ══════════════════════════════════════════════════════════════════════

def get_dem_thumbnail(dem_image, region, vis):
    """Download a static thumbnail PNG from Earth Engine."""
    thumb_url = dem_image.getThumbURL({
        'min': vis['min'],
        'max': vis['max'],
        'palette': vis['palette'],
        'region': region,
        'dimensions': 800,
        'format': 'png'
    })
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    urllib.request.urlretrieve(thumb_url, tmp.name)
    return tmp.name


def get_interpretation(avg, min_e, max_e, std, e_range, buf_km):
    """Generate professional interpretation of the elevation data."""
    lines = []

    lines.append("TERRAIN CLASSIFICATION:")
    if avg < 50:
        lines.append(
            "The study area around Cuttack falls within a low-lying alluvial "
            "plain, characteristic of the Mahanadi River delta region. With a "
            "mean elevation of %.2f m above sea level, the terrain is "
            "predominantly flat." % avg
        )
    elif avg < 200:
        lines.append(
            "The study area exhibits moderate elevation with a mean of "
            "%.2f m, indicating gently undulating terrain." % avg
        )
    else:
        lines.append(
            "The study area shows high elevation with a mean of "
            "%.2f m, indicating hilly or mountainous terrain." % avg
        )

    lines.append("")
    lines.append("ELEVATION VARIABILITY:")
    lines.append(
        "The elevation range of %.2f m (from %.2f m to %.2f m) with a "
        "standard deviation of %.2f m indicates %s topographic variability "
        "within the %s km buffer zone." % (
            e_range, min_e, max_e, std,
            "low" if std < 10 else ("moderate" if std < 30 else "high"),
            buf_km
        )
    )

    if min_e < 0:
        lines.append("")
        lines.append("FLOOD RISK ASSESSMENT:")
        lines.append(
            "IMPORTANT: The minimum elevation of %.2f m (below sea level) "
            "suggests the presence of low-lying areas that are potentially "
            "susceptible to flooding, waterlogging, or tidal influence." % min_e
        )

    lines.append("")
    lines.append("GEOMORPHOLOGICAL CONTEXT:")
    lines.append(
        "Cuttack is situated at the apex of the Mahanadi Delta, between the "
        "Mahanadi and Kathajodi rivers. The observed elevation pattern is "
        "consistent with the deltaic floodplain geomorphology, where natural "
        "levees along rivers create slightly elevated ridges while inter-"
        "distributary areas remain low-lying."
    )

    lines.append("")
    lines.append("PLANNING IMPLICATIONS:")
    lines.append(
        "1. Areas below %.2f m (mean elevation) should be prioritized for "
        "flood mitigation infrastructure." % avg
    )
    lines.append(
        "2. The relatively flat terrain (std dev: %.2f m) is favorable for "
        "transportation and road network development." % std
    )
    lines.append(
        "3. Drainage planning should account for the minimal elevation "
        "gradient across the study area."
    )
    return lines


class ReportPDF(FPDF):
    """Custom PDF with professional headers and footers."""
    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(0, 102, 51)
        self.rect(0, 0, 210, 15, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", 'B', 9)
        self.set_y(3)
        self.cell(0, 10, "Elevation Analysis Report - Cuttack, Odisha", align='C')
        self.set_text_color(0, 0, 0)
        self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10,
                  "Generated via Google Earth Engine | Project: ee-innovativegeographer | Page %s" % self.page_no(),
                  align='C')


def section_heading(pdf, num, title):
    """Print a green section heading with underline."""
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(0, 102, 51)
    pdf.cell(0, 10, txt="%s. %s" % (num, title), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(0, 102, 51)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)


def create_pdf(title, creator, avg, min_e, max_e, std, buf_km, map_img_path, drawn_stats_list=None):
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ═══════════════════════════════════════════════════════════════
    # PAGE 1: COVER
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()

    # Green header bar
    pdf.set_fill_color(0, 102, 51)
    pdf.rect(0, 0, 210, 35, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 22)
    pdf.set_y(8)
    pdf.cell(0, 12, txt="ELEVATION ANALYSIS REPORT", ln=True, align='C')
    pdf.set_font("Arial", 'I', 11)
    pdf.cell(0, 8, txt="Cuttack, Odisha, India", ln=True, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

    # Report metadata table
    pdf.set_fill_color(240, 240, 240)
    pdf.set_draw_color(200, 200, 200)
    x = 15
    meta_rows = [
        ("Report Title:", title),
        ("Prepared By:", creator),
        ("Date Generated:", datetime.now().strftime('%B %d, %Y at %H:%M')),
        ("GEE Project:", "ee-innovativegeographer"),
        ("Coordinate System:", "WGS 84 (EPSG:4326)"),
    ]
    for label, val in meta_rows:
        pdf.set_x(x)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(85, 8, "  %s" % label, border=1, fill=True)
        pdf.set_font("Arial", size=10)
        pdf.cell(95, 8, "  %s" % val, border=1, fill=True, ln=True)

    pdf.ln(6)

    # Map image
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(0, 102, 51)
    pdf.cell(0, 10, txt="STUDY AREA MAP", ln=True)
    pdf.set_text_color(0, 0, 0)

    if map_img_path and os.path.exists(map_img_path):
        img_w = 170
        img_x = (210 - img_w) / 2
        pdf.image(map_img_path, x=img_x, w=img_w)
        pdf.ln(3)
        pdf.set_font("Arial", 'I', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6,
                 txt="Figure 1: SRTM DEM for %s km buffer around Cuttack (20.4625N, 85.8828E)" % buf_km,
                 ln=True, align='C')
        pdf.set_text_color(0, 0, 0)

    # Color legend
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 6,
             txt="Legend: Green = Low Elev. | Cream = Moderate | Brown = High | White = Highest",
             ln=True, align='C')

    # ═══════════════════════════════════════════════════════════════
    # PAGE 2: Map Metadata, Data Source, Methodology
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()

    section_heading(pdf, 1, "LOCATION DETAILS")
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 7, txt="City: Cuttack, Odisha, India", ln=True)
    pdf.cell(0, 7, txt="Center Coordinates: 20.4625 N, 85.8828 E", ln=True)
    pdf.cell(0, 7, txt="Study Area Buffer: %s km radius" % buf_km, ln=True)
    pdf.cell(0, 7, txt="Approximate Area: %.1f sq km" % (3.14159 * buf_km * buf_km), ln=True)
    pdf.cell(0, 7, txt="Region: Mahanadi River Delta, Eastern India", ln=True)
    pdf.ln(4)

    section_heading(pdf, 2, "MAP METADATA")
    pdf.set_font("Arial", size=11)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_draw_color(200, 200, 200)
    map_meta = [
        ("Dataset ID", "USGS/SRTMGL1_003"),
        ("Dataset Name", "NASA SRTM Global 1 arc-second"),
        ("Data Type", "Raster (Digital Elevation Model)"),
        ("Band Used", "elevation"),
        ("Spatial Resolution", "1 arc-second (~30 meters)"),
        ("Vertical Datum", "EGM96 Geoid"),
        ("Horizontal Datum", "WGS 84"),
        ("Vertical Accuracy", "< 16 m (absolute), < 10 m (relative)"),
        ("Acquisition Period", "February 11-22, 2000"),
        ("Coverage", "60N to 56S latitude"),
        ("Provider", "NASA / USGS"),
        ("Visualization Min", "0 m"),
        ("Visualization Max", "100 m"),
        ("Color Palette", "Green-Cream-Brown-Grey-White"),
    ]
    for i, (k, v) in enumerate(map_meta):
        bg = (245, 245, 245) if i % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(75, 7, "  %s" % k, border=1, fill=True)
        pdf.set_font("Arial", size=10)
        pdf.cell(105, 7, "  %s" % v, border=1, fill=True, ln=True)
    pdf.ln(4)

    section_heading(pdf, 3, "METHODOLOGY")
    pdf.set_font("Arial", size=10)
    method_steps = [
        "Step 1: Study Area Definition",
        "A circular buffer of %s km radius was created around the center point "
        "of Cuttack (20.4625N, 85.8828E) using ee.Geometry.Point().buffer(). "
        "This defines the Region of Interest (ROI) for all subsequent analysis." % buf_km,
        "",
        "Step 2: DEM Data Acquisition",
        "The NASA SRTM Global 1 arc-second DEM (USGS/SRTMGL1_003) was loaded "
        "from the Google Earth Engine data catalog.",
        "",
        "Step 3: Statistical Analysis",
        "Zonal statistics were computed using ee.Image.reduceRegion() with "
        "combined reducers (mean, min, max, stdDev) over the ROI at 30m resolution.",
        "",
        "Step 4: Interactive Drawing Analysis",
        "Users can draw custom polygons, rectangles, circles, or place points "
        "on the interactive map. Elevation statistics are computed on-the-fly "
        "for each drawn feature using the same SRTM DEM dataset.",
        "",
        "Step 5: Report Generation",
        "Statistics, map thumbnail, and interpretation were compiled into "
        "this PDF report using FPDF integrated with the Streamlit application.",
    ]
    for line in method_steps:
        if line == "":
            pdf.ln(2)
        elif line.startswith("Step"):
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(0, 7, txt=line, ln=True)
            pdf.set_font("Arial", size=10)
        else:
            pdf.multi_cell(0, 5, txt=line)

    # ═══════════════════════════════════════════════════════════════
    # PAGE 3: Statistics & Interpretation
    # ═══════════════════════════════════════════════════════════════
    pdf.add_page()

    section_heading(pdf, 4, "ELEVATION STATISTICS — DEFAULT STUDY AREA")

    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(0, 102, 51)
    pdf.set_text_color(255, 255, 255)
    col_w = [15, 85, 45, 45]
    headers = ["#", "Statistic", "Value", "Unit"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 10, h, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=11)
    rows = [
        ("1", "Mean Elevation", "%.2f" % avg, "meters"),
        ("2", "Minimum Elevation", "%.2f" % min_e, "meters"),
        ("3", "Maximum Elevation", "%.2f" % max_e, "meters"),
        ("4", "Standard Deviation", "%.2f" % std, "meters"),
        ("5", "Elevation Range", "%.2f" % (max_e - min_e), "meters"),
        ("6", "Study Area", "%.1f" % (3.14159 * buf_km * buf_km), "sq km"),
        ("7", "Buffer Radius", "%s" % buf_km, "km"),
        ("8", "Analysis Scale", "30", "meters"),
    ]
    for i, (num, label, val, unit) in enumerate(rows):
        bg = (245, 245, 245) if i % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.cell(col_w[0], 9, num, border=1, fill=True, align='C')
        pdf.cell(col_w[1], 9, "  %s" % label, border=1, fill=True)
        pdf.cell(col_w[2], 9, val, border=1, fill=True, align='C')
        pdf.cell(col_w[3], 9, unit, border=1, fill=True, align='C')
        pdf.ln()

    pdf.ln(6)

    # ── Drawn Features Stats in PDF ──────────────────────────────
    if drawn_stats_list and len(drawn_stats_list) > 0:
        section_heading(pdf, 5, "CUSTOM DRAWN SITE ANALYSIS")
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 5,
            txt="The following elevation statistics were computed for user-drawn "
                "features on the interactive map."
        )
        pdf.ln(3)

        for item in drawn_stats_list:
            s = item['stats']
            # Site heading
            pdf.set_font("Arial", 'B', 11)
            pdf.set_text_color(0, 102, 51)
            pdf.cell(0, 8, txt=item['label'], ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", size=10)

            # Mini stats table
            pdf.set_fill_color(245, 245, 245)
            pdf.set_draw_color(200, 200, 200)
            mini_rows = [
                ("Mean Elevation", "%.2f m" % s['mean']),
                ("Min Elevation", "%.2f m" % s['min']),
                ("Max Elevation", "%.2f m" % s['max']),
                ("Std Dev", "%.2f m" % s['std']),
                ("Range", "%.2f m" % (s['max'] - s['min'])),
            ]
            for mk, mv in mini_rows:
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(60, 7, "  %s" % mk, border=1, fill=True)
                pdf.set_font("Arial", size=9)
                pdf.cell(40, 7, "  %s" % mv, border=1, ln=True)
            pdf.ln(4)

        next_section = 6
    else:
        next_section = 5

    # Section: Interpretation
    section_heading(pdf, next_section, "INTERPRETATION & ANALYSIS")
    pdf.set_font("Arial", size=10)

    interp_lines = get_interpretation(avg, min_e, max_e, std, max_e - min_e, buf_km)
    for line in interp_lines:
        if line == "":
            pdf.ln(2)
        elif line.endswith(":"):
            pdf.set_font("Arial", 'B', 11)
            pdf.cell(0, 7, txt=line, ln=True)
            pdf.set_font("Arial", size=10)
        else:
            pdf.multi_cell(0, 5, txt=line)

    # Disclaimer
    pdf.ln(8)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Arial", 'I', 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 4,
        txt="Disclaimer: This report was auto-generated using Google Earth "
            "Engine and NASA SRTM data. SRTM elevation values have a vertical "
            "accuracy of approximately 16 meters (absolute). Results should be "
            "validated with ground-truth data for critical applications. "
            "Generated on %s." % datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    pdf_str = pdf.output(dest='S')
    return pdf_str.encode('latin-1')


# ── Sidebar: PDF Report Download ─────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("📄 Generate Report")
include_drawn = st.sidebar.checkbox("Include drawn sites in report", value=True)

if st.sidebar.button("Generate PDF Report", type="primary"):
    with st.sidebar:
        with st.spinner("Downloading map thumbnail from EE..."):
            map_img = get_dem_thumbnail(dem, roi, vis_params)
        with st.spinner("Generating PDF report..."):
            drawn_list = st.session_state.drawn_stats if include_drawn else None
            pdf_bytes = create_pdf(
                report_name, user_name,
                avg_elev, min_elev, max_elev, std_elev, buffer_km,
                map_img, drawn_list
            )
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name="%s.pdf" % report_name.replace(' ', '_'),
                mime="application/pdf"
            )
            st.success("PDF generated successfully!")
        if map_img and os.path.exists(map_img):
            os.unlink(map_img)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<small style='color:#64748b'>Built with Streamlit &bull; Earth Engine &bull; Folium</small>",
    unsafe_allow_html=True
)
