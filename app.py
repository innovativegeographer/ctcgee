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
import plotly.graph_objects as go
import plotly.express as px
import numpy as np

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
    html, body, [data-testid="stSidebar"] { font-family: 'Inter', sans-serif; }
    h1 {
        font-weight: 800;
        background: linear-gradient(135deg, #006633, #00994d);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -1px;
    }
    .main { background-color: #f8fafc; }
    [data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 700; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #0a1628 0%, #132742 100%); }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 14px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .draw-info-box {
        background: linear-gradient(135deg, #f0fdf4, #dcfce7);
        border: 1px solid #86efac; border-radius: 12px; padding: 20px; margin: 10px 0;
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
st.sidebar.info("Draw on the map to analyze any custom area.")
point_buffer_m = st.sidebar.slider("Point buffer (m)", 100, 5000, 500)

# ── Earth Engine Processing ──────────────────────────────────────────
CUTTACK_LAT, CUTTACK_LON = 20.4625, 85.8828
ee_point = ee.Geometry.Point(CUTTACK_LON, CUTTACK_LAT)
roi = ee_point.buffer(buffer_km * 1000)
dem = ee.Image('USGS/SRTMGL1_003')


# ══════════════════════════════════════════════════════════════════════
# ANALYSIS FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)
def compute_stats(_geometry_info):
    """Compute elevation stats for a geometry."""
    geom = ee.Geometry(json.loads(_geometry_info))
    s = dem.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geom, scale=30, maxPixels=1e9
    ).getInfo()
    return {
        'mean': round(s.get('elevation_mean', 0), 2),
        'min': round(s.get('elevation_min', 0), 2),
        'max': round(s.get('elevation_max', 0), 2),
        'std': round(s.get('elevation_stdDev', 0), 2),
    }


@st.cache_data(ttl=600)
def compute_histogram(_geometry_info, num_bins=50):
    """Compute elevation histogram using EE fixed histogram reducer."""
    geom = ee.Geometry(json.loads(_geometry_info))
    # Get min/max first
    mm = dem.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=geom, scale=30, maxPixels=1e9
    ).getInfo()
    lo = mm.get('elevation_min', 0)
    hi = mm.get('elevation_max', 100)
    if hi <= lo:
        hi = lo + 1

    hist = dem.reduceRegion(
        reducer=ee.Reducer.fixedHistogram(lo, hi, num_bins),
        geometry=geom, scale=30, maxPixels=1e9
    ).getInfo()

    buckets = hist.get('elevation', [])
    bin_edges = [b[0] for b in buckets]
    counts = [b[1] for b in buckets]
    return bin_edges, counts, lo, hi


@st.cache_data(ttl=600)
def compute_slope_stats(_geometry_info):
    """Compute slope statistics."""
    geom = ee.Geometry(json.loads(_geometry_info))
    slope = ee.Terrain.slope(dem)
    s = slope.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
        geometry=geom, scale=30, maxPixels=1e9
    ).getInfo()
    return {
        'mean': round(s.get('slope_mean', 0), 2),
        'min': round(s.get('slope_min', 0), 2),
        'max': round(s.get('slope_max', 0), 2),
        'std': round(s.get('slope_stdDev', 0), 2),
    }


@st.cache_data(ttl=600)
def compute_slope_histogram(_geometry_info, num_bins=36):
    """Compute slope histogram."""
    geom = ee.Geometry(json.loads(_geometry_info))
    slope = ee.Terrain.slope(dem)

    hist = slope.reduceRegion(
        reducer=ee.Reducer.fixedHistogram(0, 90, num_bins),
        geometry=geom, scale=30, maxPixels=1e9
    ).getInfo()

    buckets = hist.get('slope', [])
    bin_edges = [b[0] for b in buckets]
    counts = [b[1] for b in buckets]
    return bin_edges, counts


@st.cache_data(ttl=600)
def compute_aspect_histogram(_geometry_info):
    """Compute aspect histogram (8 cardinal directions)."""
    geom = ee.Geometry(json.loads(_geometry_info))
    aspect = ee.Terrain.aspect(dem)

    hist = aspect.reduceRegion(
        reducer=ee.Reducer.fixedHistogram(0, 360, 8),
        geometry=geom, scale=30, maxPixels=1e9
    ).getInfo()

    buckets = hist.get('aspect', [])
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    counts = [b[1] for b in buckets]
    return directions, counts


@st.cache_data(ttl=600)
def compute_terrain_classes(_geometry_info):
    """Classify elevation into terrain zones and compute pixel percentages."""
    geom = ee.Geometry(json.loads(_geometry_info))
    s = compute_stats(_geometry_info)
    lo, hi = s['min'], s['max']

    # Create 5 elevation zones
    rng = hi - lo
    if rng == 0:
        return ['Flat'], [100.0], [(lo, hi)]

    thresholds = [
        lo,
        lo + rng * 0.2,
        lo + rng * 0.4,
        lo + rng * 0.6,
        lo + rng * 0.8,
        hi + 0.1
    ]
    labels = ['Very Low', 'Low', 'Moderate', 'High', 'Very High']
    ranges = []
    percentages = []

    total = 0
    zone_counts = []
    for i in range(5):
        zone = dem.gte(thresholds[i]).And(dem.lt(thresholds[i+1]))
        cnt = zone.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom, scale=30, maxPixels=1e9
        ).getInfo().get('elevation', 0)
        zone_counts.append(cnt)
        total += cnt
        ranges.append((round(thresholds[i], 1), round(thresholds[i+1], 1)))

    if total > 0:
        percentages = [round(c / total * 100, 1) for c in zone_counts]
    else:
        percentages = [20.0] * 5

    return labels, percentages, ranges


@st.cache_data(ttl=600)
def compute_hypsometric(_geometry_info, num_bins=50):
    """Compute hypsometric (cumulative) curve."""
    bin_edges, counts, lo, hi = compute_histogram(_geometry_info, num_bins)
    total = sum(counts)
    if total == 0:
        return [], []

    cumulative = []
    running = 0
    for c in counts:
        running += c
        cumulative.append(round((1 - running / total) * 100, 2))

    return bin_edges, cumulative


# ══════════════════════════════════════════════════════════════════════
# CHART GENERATORS
# ══════════════════════════════════════════════════════════════════════

def create_histogram_chart(bin_edges, counts, title="Elevation Distribution"):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=bin_edges, y=counts,
        marker_color='#006633',
        marker_line_color='#004d26',
        marker_line_width=0.5,
        opacity=0.85,
        hovertemplate='Elevation: %{x:.1f}m<br>Pixel Count: %{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, family='Inter')),
        xaxis_title='Elevation (m)',
        yaxis_title='Pixel Count',
        template='plotly_white',
        height=380,
        margin=dict(l=60, r=30, t=50, b=50),
        font=dict(family='Inter')
    )
    return fig


def create_slope_chart(bin_edges, counts):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=bin_edges, y=counts,
        marker_color='#8b5cf6',
        marker_line_color='#6d28d9',
        marker_line_width=0.5,
        opacity=0.85,
        hovertemplate='Slope: %{x:.1f}°<br>Pixel Count: %{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text='Slope Distribution', font=dict(size=16, family='Inter')),
        xaxis_title='Slope (degrees)',
        yaxis_title='Pixel Count',
        template='plotly_white',
        height=380,
        margin=dict(l=60, r=30, t=50, b=50),
        font=dict(family='Inter')
    )
    return fig


def create_aspect_chart(directions, counts):
    # Repeat first value to close the loop
    dirs = directions + [directions[0]]
    vals = counts + [counts[0]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals,
        theta=dirs,
        fill='toself',
        fillcolor='rgba(59, 130, 246, 0.3)',
        line=dict(color='#3b82f6', width=2),
        marker=dict(size=6, color='#3b82f6'),
        hovertemplate='%{theta}: %{r:,.0f} pixels<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text='Aspect (Terrain Orientation)', font=dict(size=16, family='Inter')),
        polar=dict(
            radialaxis=dict(visible=True, showticklabels=True),
            angularaxis=dict(direction='clockwise', rotation=90)
        ),
        template='plotly_white',
        height=400,
        margin=dict(l=60, r=60, t=50, b=50),
        font=dict(family='Inter'),
        showlegend=False
    )
    return fig


def create_terrain_pie(labels, percentages, ranges):
    colors = ['#006633', '#4CAF50', '#E5FFCC', '#D8D8D8', '#8B4513']
    custom_labels = [
        '%s<br>%.1f–%.1f m' % (l, r[0], r[1])
        for l, r in zip(labels, ranges)
    ]
    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=custom_labels,
        values=percentages,
        marker_colors=colors,
        hole=0.4,
        textinfo='percent+label',
        textfont_size=11,
        hovertemplate='%{label}<br>%{percent}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text='Terrain Classification', font=dict(size=16, family='Inter')),
        template='plotly_white',
        height=400,
        margin=dict(l=30, r=30, t=50, b=30),
        font=dict(family='Inter'),
        showlegend=True,
        legend=dict(font=dict(size=10))
    )
    return fig


def create_hypsometric_chart(elevations, cumulative_pct):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cumulative_pct, y=elevations,
        mode='lines',
        fill='tozerox',
        fillcolor='rgba(0, 102, 51, 0.15)',
        line=dict(color='#006633', width=2.5),
        hovertemplate='Area above: %{x:.1f}%<br>Elevation: %{y:.1f}m<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text='Hypsometric Curve', font=dict(size=16, family='Inter')),
        xaxis_title='Cumulative Area Above (%)',
        yaxis_title='Elevation (m)',
        template='plotly_white',
        height=380,
        margin=dict(l=60, r=30, t=50, b=50),
        font=dict(family='Inter')
    )
    return fig


def display_full_analysis(geom_info, area_label):
    """Render all analysis charts and tables for a given geometry."""

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Elevation Histogram",
        "⛰️ Slope Analysis",
        "🧭 Aspect Analysis",
        "🗺️ Terrain Classification",
        "📈 Hypsometric Curve"
    ])

    with tab1:
        with st.spinner("Computing elevation histogram..."):
            bin_edges, counts, lo, hi = compute_histogram(geom_info)
            if len(bin_edges) > 0:
                fig = create_histogram_chart(bin_edges, counts,
                    title="Elevation Distribution — %s" % area_label)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "Distribution of elevation values across %d bins from %.1f m to %.1f m. "
                    "Total pixels analyzed: %s" % (
                        len(bin_edges), lo, hi, '{:,.0f}'.format(sum(counts))
                    )
                )
            else:
                st.warning("Not enough data for histogram.")

    with tab2:
        with st.spinner("Computing slope analysis..."):
            slope_stats = compute_slope_stats(geom_info)
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("📐 Mean Slope", "%.2f°" % slope_stats['mean'])
            sc2.metric("⬇️ Min Slope", "%.2f°" % slope_stats['min'])
            sc3.metric("⬆️ Max Slope", "%.2f°" % slope_stats['max'])
            sc4.metric("📊 Std Dev", "%.2f°" % slope_stats['std'])

            slope_bins, slope_counts = compute_slope_histogram(geom_info)
            if len(slope_bins) > 0:
                fig = create_slope_chart(slope_bins, slope_counts)
                st.plotly_chart(fig, use_container_width=True)

                # Slope classification
                flat_pct = sum(c for b, c in zip(slope_bins, slope_counts) if b < 5)
                gentle_pct = sum(c for b, c in zip(slope_bins, slope_counts) if 5 <= b < 15)
                moderate_pct = sum(c for b, c in zip(slope_bins, slope_counts) if 15 <= b < 30)
                steep_pct = sum(c for b, c in zip(slope_bins, slope_counts) if b >= 30)
                total_s = flat_pct + gentle_pct + moderate_pct + steep_pct
                if total_s > 0:
                    st.markdown("**Slope Classification:**")
                    scol1, scol2, scol3, scol4 = st.columns(4)
                    scol1.metric("Flat (<5°)", "%.1f%%" % (flat_pct / total_s * 100))
                    scol2.metric("Gentle (5-15°)", "%.1f%%" % (gentle_pct / total_s * 100))
                    scol3.metric("Moderate (15-30°)", "%.1f%%" % (moderate_pct / total_s * 100))
                    scol4.metric("Steep (>30°)", "%.1f%%" % (steep_pct / total_s * 100))

    with tab3:
        with st.spinner("Computing aspect analysis..."):
            directions, aspect_counts = compute_aspect_histogram(geom_info)
            if len(aspect_counts) > 0 and sum(aspect_counts) > 0:
                fig = create_aspect_chart(directions, aspect_counts)
                st.plotly_chart(fig, use_container_width=True)

                # Find dominant aspect
                max_idx = aspect_counts.index(max(aspect_counts))
                total_a = sum(aspect_counts)
                st.info(
                    "**Dominant Aspect:** %s (%s-facing slopes) — %.1f%% of the area. "
                    "This indicates the terrain predominantly faces %s." % (
                        directions[max_idx],
                        directions[max_idx],
                        aspect_counts[max_idx] / total_a * 100,
                        directions[max_idx]
                    )
                )

                # Aspect table
                aspect_data = []
                for d, c in zip(directions, aspect_counts):
                    aspect_data.append({
                        'Direction': d,
                        'Pixel Count': int(c),
                        'Percentage': '%.1f%%' % (c / total_a * 100) if total_a > 0 else '0%',
                    })
                st.dataframe(aspect_data, use_container_width=True, hide_index=True)
            else:
                st.warning("Not enough data for aspect analysis.")

    with tab4:
        with st.spinner("Computing terrain classification..."):
            labels, percentages, ranges = compute_terrain_classes(geom_info)
            if len(labels) > 1:
                fig = create_terrain_pie(labels, percentages, ranges)
                st.plotly_chart(fig, use_container_width=True)

                # Classification table
                class_data = []
                for l, p, r in zip(labels, percentages, ranges):
                    class_data.append({
                        'Class': l,
                        'Range': '%.1f – %.1f m' % (r[0], r[1]),
                        'Percentage': '%.1f%%' % p,
                    })
                st.dataframe(class_data, use_container_width=True, hide_index=True)
            else:
                st.info("Area is uniformly flat — no classification needed.")

    with tab5:
        with st.spinner("Computing hypsometric curve..."):
            elevations, cum_pct = compute_hypsometric(geom_info)
            if len(elevations) > 0:
                fig = create_hypsometric_chart(elevations, cum_pct)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "The hypsometric curve shows the proportion of total area above each "
                    "elevation. A concave curve indicates a mature/eroded landscape, while "
                    "a convex curve suggests a youthful/uplifting landscape."
                )
            else:
                st.warning("Not enough data for hypsometric curve.")


# ══════════════════════════════════════════════════════════════════════
# MAIN APP: STATS, MAP, ANALYSIS
# ══════════════════════════════════════════════════════════════════════

# Compute default stats
roi_info = json.dumps(roi.getInfo())
default_stats = compute_stats(roi_info)
avg_elev = default_stats['mean']
min_elev = default_stats['min']
max_elev = default_stats['max']
std_elev = default_stats['std']
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

# ── Default Area Analysis ────────────────────────────────────────────
with st.expander("🔬 **Detailed Analysis — Default Study Area** (click to expand)", expanded=False):
    display_full_analysis(roi_info, "Default %skm Buffer" % buffer_km)

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

folium.TileLayer(
    tiles=dem_map_id['tile_fetcher'].url_format,
    attr='Google Earth Engine - SRTM DEM',
    name='SRTM Elevation', overlay=True, control=True
).add_to(m)

folium.TileLayer(
    tiles=hillshade_map_id['tile_fetcher'].url_format,
    attr='Google Earth Engine - Hillshade',
    name='Hillshade (3D Texture)', overlay=True, control=True, opacity=0.3
).add_to(m)

roi_coords = roi.getInfo()['coordinates'][0]
boundary_coords = [[c[1], c[0]] for c in roi_coords]
folium.Polygon(
    locations=boundary_coords, color='#e63946', weight=3,
    fill=False, popup='Study Area: %s km buffer' % buffer_km
).add_to(m)

folium.Marker(
    location=[CUTTACK_LAT, CUTTACK_LON],
    popup='Cuttack City Center', tooltip='Cuttack City Center',
    icon=folium.Icon(color='red', icon='info-sign')
).add_to(m)

# Drawing tools
draw = plugins.Draw(
    export=True, position='topleft',
    draw_options={
        'polyline': False,
        'polygon': {'allowIntersection': False, 'shapeOptions': {'color': '#3b82f6', 'weight': 3, 'fillOpacity': 0.2}},
        'rectangle': {'shapeOptions': {'color': '#8b5cf6', 'weight': 3, 'fillOpacity': 0.2}},
        'circle': {'shapeOptions': {'color': '#f59e0b', 'weight': 3, 'fillOpacity': 0.2}},
        'marker': True, 'circlemarker': False,
    },
    edit_options={'edit': True, 'remove': True}
)
draw.add_to(m)
folium.LayerControl().add_to(m)

st.markdown("### 🗺️ Interactive Map — Draw to Analyze")
st.markdown(
    "✏️ **Use the toolbar** on the left of the map to draw shapes. "
    "Elevation analysis runs automatically for each drawn area."
)
map_data = st_folium(m, width=None, height=600, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# DRAWN FEATURE ANALYSIS
# ══════════════════════════════════════════════════════════════════════

def geojson_to_ee_geometry(feature):
    geom = feature.get('geometry', feature)
    geom_type = geom.get('type', '')
    coords = geom.get('coordinates', [])
    if geom_type == 'Point':
        return ee.Geometry.Point(coords).buffer(point_buffer_m)
    elif geom_type == 'Polygon':
        return ee.Geometry.Polygon(coords)
    elif geom_type == 'LineString':
        return ee.Geometry.LineString(coords).buffer(100)
    return None


def get_feature_label(feature, index):
    geom = feature.get('geometry', feature)
    geom_type = geom.get('type', '')
    coords = geom.get('coordinates', [])
    if geom_type == 'Point':
        return "Point %d (%.4f N, %.4f E) - %dm buffer" % (index, coords[1], coords[0], point_buffer_m)
    elif geom_type == 'Polygon':
        n = len(coords[0]) - 1 if coords else 0
        return "Polygon %d (%d vertices)" % (index, n)
    return "Shape %d (%s)" % (index, geom_type)


all_drawings = map_data.get('all_drawings', []) if map_data else []
if 'drawn_features' not in st.session_state:
    st.session_state.drawn_features = []
if 'drawn_results' not in st.session_state:
    st.session_state.drawn_results = []

if all_drawings and len(all_drawings) > 0:
    st.session_state.drawn_features = all_drawings

st.markdown("---")
st.markdown("### ✏️ Custom Site Analysis")

if len(st.session_state.drawn_features) > 0:
    st.success("**%d feature(s) drawn** — Analyzing..." % len(st.session_state.drawn_features))

    results = []
    for idx, feature in enumerate(st.session_state.drawn_features, 1):
        ee_geom = geojson_to_ee_geometry(feature)
        if ee_geom:
            try:
                geom_info = json.dumps(ee_geom.getInfo())
                feature_stats = compute_stats(geom_info)
                label = get_feature_label(feature, idx)
                results.append({
                    'label': label,
                    'stats': feature_stats,
                    'geom_info': geom_info,
                    'index': idx
                })
            except Exception as e:
                st.warning("Could not analyze feature %d: %s" % (idx, str(e)))

    st.session_state.drawn_results = results

    for item in st.session_state.drawn_results:
        s = item['stats']
        st.markdown("#### 📍 %s" % item['label'])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📊 Mean", "%.2f m" % s['mean'])
        c2.metric("⬇️ Min", "%.2f m" % s['min'])
        c3.metric("⬆️ Max", "%.2f m" % s['max'])
        c4.metric("📐 Std Dev", "%.2f m" % s['std'])

        with st.expander("🔬 **Detailed Analysis — %s**" % item['label'], expanded=False):
            display_full_analysis(item['geom_info'], item['label'])

    # Comparison table
    if len(st.session_state.drawn_results) > 1:
        st.markdown("#### 📋 Multi-Site Comparison")
        table_data = []
        for item in st.session_state.drawn_results:
            s = item['stats']
            table_data.append({
                'Site': item['label'],
                'Mean (m)': s['mean'], 'Min (m)': s['min'],
                'Max (m)': s['max'], 'Std Dev (m)': s['std'],
                'Range (m)': round(s['max'] - s['min'], 2)
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

        # Grouped bar chart
        fig = go.Figure()
        names = [d['Site'][:20] for d in table_data]
        fig.add_trace(go.Bar(name='Mean', x=names, y=[d['Mean (m)'] for d in table_data], marker_color='#006633'))
        fig.add_trace(go.Bar(name='Min', x=names, y=[d['Min (m)'] for d in table_data], marker_color='#93c5fd'))
        fig.add_trace(go.Bar(name='Max', x=names, y=[d['Max (m)'] for d in table_data], marker_color='#ef4444'))
        fig.update_layout(
            title='Multi-Site Elevation Comparison',
            barmode='group', template='plotly_white', height=400,
            font=dict(family='Inter')
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.markdown(
        '<div class="draw-info-box">'
        '<h4 style="margin:0 0 8px 0; color:#166534;">✏️ Draw on the map to analyze any area</h4>'
        '<p style="margin:0; color:#15803d;">'
        '<strong>📍 Marker</strong> — Point with %dm buffer &nbsp;|&nbsp; '
        '<strong>🔷 Polygon</strong> — Custom shape &nbsp;|&nbsp; '
        '<strong>⬜ Rectangle</strong> — Box area &nbsp;|&nbsp; '
        '<strong>⭕ Circle</strong> — Circular area'
        '</p>'
        '<p style="margin:6px 0 0; color:#15803d;">Each drawn area gets: '
        '<strong>histogram, slope, aspect, terrain classes, and hypsometric curve!</strong></p>'
        '</div>' % point_buffer_m,
        unsafe_allow_html=True
    )

# ── Manual Coordinate Input ──────────────────────────────────────────
st.markdown("---")
st.markdown("### 📍 Analyze by Coordinates")
coord_col1, coord_col2, coord_col3 = st.columns([2, 2, 1])
with coord_col1:
    manual_lat = st.number_input("Latitude", value=20.4625, format="%.4f", step=0.01)
with coord_col2:
    manual_lon = st.number_input("Longitude", value=85.8828, format="%.4f", step=0.01)
with coord_col3:
    manual_buffer = st.number_input("Buffer (m)", value=500, min_value=100, max_value=10000, step=100)

if st.button("🔍 Analyze This Location", type="primary"):
    manual_geom = ee.Geometry.Point(manual_lon, manual_lat).buffer(manual_buffer)
    manual_geom_info = json.dumps(manual_geom.getInfo())

    with st.spinner("Computing analysis for (%.4f, %.4f)..." % (manual_lat, manual_lon)):
        ms = compute_stats(manual_geom_info)
        st.markdown("#### 📍 Results for (%.4f°N, %.4f°E) — %dm buffer" % (manual_lat, manual_lon, manual_buffer))
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("📊 Mean", "%.2f m" % ms['mean'])
        mc2.metric("⬇️ Min", "%.2f m" % ms['min'])
        mc3.metric("⬆️ Max", "%.2f m" % ms['max'])
        mc4.metric("📐 Std Dev", "%.2f m" % ms['std'])

        display_full_analysis(manual_geom_info, "Manual Point (%.4f, %.4f)" % (manual_lat, manual_lon))


# ══════════════════════════════════════════════════════════════════════
# PDF REPORT GENERATION
# ══════════════════════════════════════════════════════════════════════

def get_dem_thumbnail(dem_image, region, vis):
    thumb_url = dem_image.getThumbURL({
        'min': vis['min'], 'max': vis['max'], 'palette': vis['palette'],
        'region': region, 'dimensions': 800, 'format': 'png'
    })
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    urllib.request.urlretrieve(thumb_url, tmp.name)
    return tmp.name


def get_interpretation(avg, min_e, max_e, std, e_range, buf_km):
    lines = []
    lines.append("TERRAIN CLASSIFICATION:")
    if avg < 50:
        lines.append("The study area falls within a low-lying alluvial plain with a mean elevation of %.2f m." % avg)
    elif avg < 200:
        lines.append("The study area exhibits moderate elevation (mean: %.2f m), indicating gently undulating terrain." % avg)
    else:
        lines.append("The study area shows high elevation (mean: %.2f m), indicating hilly/mountainous terrain." % avg)
    lines.append("")
    lines.append("ELEVATION VARIABILITY:")
    lines.append(
        "Elevation range: %.2f m (%.2f m to %.2f m), Std Dev: %.2f m — %s variability within %s km zone." % (
            e_range, min_e, max_e, std,
            "low" if std < 10 else ("moderate" if std < 30 else "high"),
            buf_km
        ))
    lines.append("")
    lines.append("GEOMORPHOLOGICAL CONTEXT:")
    lines.append(
        "Cuttack sits at the apex of the Mahanadi Delta. The elevation pattern is consistent with "
        "deltaic floodplain geomorphology."
    )
    lines.append("")
    lines.append("PLANNING IMPLICATIONS:")
    lines.append("1. Areas below %.2f m should be prioritized for flood mitigation." % avg)
    lines.append("2. Flat terrain (std: %.2f m) is favorable for road networks." % std)
    lines.append("3. Drainage should account for minimal elevation gradient.")
    return lines


class ReportPDF(FPDF):
    def header(self):
        if self.page_no() == 1: return
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
        self.cell(0, 10, "Google Earth Engine | ee-innovativegeographer | Page %s" % self.page_no(), align='C')


def section_heading(pdf, num, title):
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(0, 102, 51)
    pdf.cell(0, 10, txt="%s. %s" % (num, title), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(0, 102, 51)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)


def create_pdf(title, creator, avg, min_e, max_e, std, buf_km, map_img_path,
               drawn_stats_list=None, slope_data=None, aspect_data=None, terrain_data=None):
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    sec = [0]  # mutable counter

    def next_sec():
        sec[0] += 1
        return sec[0]

    # PAGE 1: COVER
    pdf.add_page()
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

    pdf.set_fill_color(240, 240, 240)
    pdf.set_draw_color(200, 200, 200)
    for label, val in [
        ("Report Title:", title), ("Prepared By:", creator),
        ("Date:", datetime.now().strftime('%B %d, %Y at %H:%M')),
        ("GEE Project:", "ee-innovativegeographer"),
        ("CRS:", "WGS 84 (EPSG:4326)")
    ]:
        pdf.set_x(15)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(85, 8, "  %s" % label, border=1, fill=True)
        pdf.set_font("Arial", size=10)
        pdf.cell(95, 8, "  %s" % val, border=1, fill=True, ln=True)
    pdf.ln(6)

    if map_img_path and os.path.exists(map_img_path):
        pdf.set_font("Arial", 'B', 13)
        pdf.set_text_color(0, 102, 51)
        pdf.cell(0, 10, txt="STUDY AREA MAP", ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.image(map_img_path, x=20, w=170)
        pdf.ln(3)
        pdf.set_font("Arial", 'I', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, txt="Figure 1: SRTM DEM — %s km buffer around Cuttack" % buf_km, ln=True, align='C')
        pdf.set_text_color(0, 0, 0)

    # PAGE 2: STATISTICS
    pdf.add_page()
    section_heading(pdf, next_sec(), "ELEVATION STATISTICS")

    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(0, 102, 51)
    pdf.set_text_color(255, 255, 255)
    cw = [15, 85, 45, 45]
    for i, h in enumerate(["#", "Statistic", "Value", "Unit"]):
        pdf.cell(cw[i], 10, h, border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=11)
    for i, (n, l, v, u) in enumerate([
        ("1", "Mean Elevation", "%.2f" % avg, "m"),
        ("2", "Minimum Elevation", "%.2f" % min_e, "m"),
        ("3", "Maximum Elevation", "%.2f" % max_e, "m"),
        ("4", "Standard Deviation", "%.2f" % std, "m"),
        ("5", "Elevation Range", "%.2f" % (max_e - min_e), "m"),
        ("6", "Study Area", "%.1f" % (3.14159 * buf_km ** 2), "sq km"),
        ("7", "Buffer Radius", "%s" % buf_km, "km"),
        ("8", "Analysis Scale", "30", "m"),
    ]):
        bg = (245, 245, 245) if i % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.cell(cw[0], 9, n, border=1, fill=True, align='C')
        pdf.cell(cw[1], 9, "  %s" % l, border=1, fill=True)
        pdf.cell(cw[2], 9, v, border=1, fill=True, align='C')
        pdf.cell(cw[3], 9, u, border=1, fill=True, align='C')
        pdf.ln()
    pdf.ln(4)

    # Slope stats in PDF
    if slope_data:
        section_heading(pdf, next_sec(), "SLOPE ANALYSIS")
        pdf.set_font("Arial", size=10)
        for k, v in [
            ("Mean Slope", "%.2f deg" % slope_data['mean']),
            ("Min Slope", "%.2f deg" % slope_data['min']),
            ("Max Slope", "%.2f deg" % slope_data['max']),
            ("Std Dev", "%.2f deg" % slope_data['std']),
        ]:
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(60, 7, "  %s" % k, border=1, fill=True)
            pdf.set_font("Arial", size=10)
            pdf.cell(50, 7, "  %s" % v, border=1, ln=True)
        pdf.ln(4)

    # Aspect data in PDF
    if aspect_data:
        section_heading(pdf, next_sec(), "ASPECT ANALYSIS")
        pdf.set_font("Arial", size=10)
        dirs, counts = aspect_data
        total_a = sum(counts)
        for d, c in zip(dirs, counts):
            pct = (c / total_a * 100) if total_a > 0 else 0
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(30, 7, "  %s" % d, border=1, fill=True)
            pdf.set_font("Arial", size=10)
            pdf.cell(40, 7, "  %s pixels" % int(c), border=1)
            pdf.cell(30, 7, "  %.1f%%" % pct, border=1, ln=True)
        pdf.ln(4)

    # Terrain classification in PDF
    if terrain_data:
        section_heading(pdf, next_sec(), "TERRAIN CLASSIFICATION")
        labels_t, pcts_t, ranges_t = terrain_data
        pdf.set_font("Arial", size=10)
        for l, p, r in zip(labels_t, pcts_t, ranges_t):
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(40, 7, "  %s" % l, border=1, fill=True)
            pdf.set_font("Arial", size=10)
            pdf.cell(50, 7, "  %.1f - %.1f m" % (r[0], r[1]), border=1)
            pdf.cell(30, 7, "  %.1f%%" % p, border=1, ln=True)
        pdf.ln(4)

    # Drawn features
    if drawn_stats_list and len(drawn_stats_list) > 0:
        section_heading(pdf, next_sec(), "CUSTOM DRAWN SITE ANALYSIS")
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 5, txt="Statistics for user-drawn features on the interactive map:")
        pdf.ln(3)
        for item in drawn_stats_list:
            s = item['stats']
            pdf.set_font("Arial", 'B', 11)
            pdf.set_text_color(0, 102, 51)
            pdf.cell(0, 8, txt=item['label'], ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(245, 245, 245)
            for mk, mv in [
                ("Mean", "%.2f m" % s['mean']), ("Min", "%.2f m" % s['min']),
                ("Max", "%.2f m" % s['max']), ("Std Dev", "%.2f m" % s['std']),
                ("Range", "%.2f m" % (s['max'] - s['min'])),
            ]:
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(60, 7, "  %s" % mk, border=1, fill=True)
                pdf.set_font("Arial", size=9)
                pdf.cell(40, 7, "  %s" % mv, border=1, ln=True)
            pdf.ln(4)

    # Interpretation
    section_heading(pdf, next_sec(), "INTERPRETATION & ANALYSIS")
    pdf.set_font("Arial", size=10)
    for line in get_interpretation(avg, min_e, max_e, std, max_e - min_e, buf_km):
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
        txt="Disclaimer: Auto-generated using Google Earth Engine and NASA SRTM data. "
            "Vertical accuracy ~16m. Validate with ground-truth data for critical applications. "
            "Generated on %s." % datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    pdf_str = pdf.output(dest='S')
    return pdf_str.encode('latin-1')


# ── Sidebar: PDF Report Download ─────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("📄 Generate Report")
st.sidebar.markdown("**Include in report:**")
inc_drawn = st.sidebar.checkbox("Custom drawn sites", value=True)
inc_slope = st.sidebar.checkbox("Slope analysis", value=True)
inc_aspect = st.sidebar.checkbox("Aspect analysis", value=True)
inc_terrain = st.sidebar.checkbox("Terrain classification", value=True)

if st.sidebar.button("Generate PDF Report", type="primary"):
    with st.sidebar:
        with st.spinner("Downloading map thumbnail..."):
            map_img = get_dem_thumbnail(dem, roi, vis_params)

        with st.spinner("Computing analysis data..."):
            slope_d = compute_slope_stats(roi_info) if inc_slope else None
            aspect_d = compute_aspect_histogram(roi_info) if inc_aspect else None
            terrain_d = compute_terrain_classes(roi_info) if inc_terrain else None
            drawn_d = st.session_state.drawn_results if inc_drawn else None

        with st.spinner("Generating PDF report..."):
            pdf_bytes = create_pdf(
                report_name, user_name,
                avg_elev, min_elev, max_elev, std_elev, buffer_km,
                map_img, drawn_d, slope_d, aspect_d, terrain_d
            )
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name="%s.pdf" % report_name.replace(' ', '_'),
                mime="application/pdf"
            )
            st.success("PDF generated!")

        if map_img and os.path.exists(map_img):
            os.unlink(map_img)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<small style='color:#64748b'>Built with Streamlit &bull; Earth Engine &bull; Folium &bull; Plotly</small>",
    unsafe_allow_html=True
)
