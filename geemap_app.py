import streamlit as st
import ee
import json
import os
import folium
import tempfile
import urllib.request
from streamlit_folium import st_folium
from fpdf import FPDF
from datetime import datetime

st.set_page_config(layout="wide", page_title="Cuttack DEM Explorer")
st.title("🌍 Earth Engine SRTM DEM Explorer — Cuttack")

# ── Earth Engine Authentication ──────────────────────────────────────
@st.cache_resource
def init_ee():
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
        st.info("To fix this on Streamlit Cloud, ensure you have added your service account JSON to the Streamlit Dashboard Secrets box using `json_data` and `service_account` keys.")
        st.code("""json_data = '''\n{\n  "type": "service_account",\n  ...\n}'''\n\nservice_account = '...'""", language="toml")
        st.write(f"**Error Details:** {e}")
        st.stop()

with st.spinner("Initializing Earth Engine..."):
    init_ee()

# ── Sidebar Controls ─────────────────────────────────────────────────
st.sidebar.title("📋 Report Settings")
report_name = st.sidebar.text_input("Report Title", "Cuttack Elevation Report")
user_name = st.sidebar.text_input("Your Name", "User")
buffer_km = st.sidebar.slider("Buffer Radius (km)", 1, 20, 5)

# ── Earth Engine Processing ──────────────────────────────────────────
CUTTACK_LAT, CUTTACK_LON = 20.4625, 85.8828
point = ee.Geometry.Point(CUTTACK_LON, CUTTACK_LAT)
roi = point.buffer(buffer_km * 1000)

dem = ee.Image('USGS/SRTMGL1_003')

# Compute statistics
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
col1, col2, col3, col4 = st.columns(4)
col1.metric("📊 Mean Elevation", "%.2f m" % avg_elev)
col2.metric("⬇️ Min Elevation", "%.2f m" % min_elev)
col3.metric("⬆️ Max Elevation", "%.2f m" % max_elev)
col4.metric("📐 Std Dev", "%.2f m" % std_elev)

# ── Build the Map using Folium + EE tiles ────────────────────────────
vis_params = {
    'min': 0,
    'max': 100,
    'palette': ['006633', 'E5FFCC', '662A00', 'D8D8D8', 'F5F5F5']
}

# Get EE tile URL for the DEM layer
dem_map_id = dem.getMapId(vis_params)

# Create Folium map centered on Cuttack
m = folium.Map(location=[CUTTACK_LAT, CUTTACK_LON], zoom_start=12)

# Add DEM tile layer
folium.TileLayer(
    tiles=dem_map_id['tile_fetcher'].url_format,
    attr='Google Earth Engine - SRTM DEM',
    name='SRTM DEM',
    overlay=True,
    control=True
).add_to(m)

# Add study area boundary
roi_coords = roi.getInfo()['coordinates'][0]
boundary_coords = [[c[1], c[0]] for c in roi_coords]
folium.Polygon(
    locations=boundary_coords,
    color='red',
    weight=3,
    fill=False,
    popup='Study Area: %skm buffer' % buffer_km
).add_to(m)

# Add center marker
folium.Marker(
    location=[CUTTACK_LAT, CUTTACK_LON],
    popup='Cuttack City Center',
    icon=folium.Icon(color='red', icon='info-sign')
).add_to(m)

# Add layer control
folium.LayerControl().add_to(m)

st.write("**Study Area:** %s km buffer around Cuttack (20.46N, 85.88E)" % buffer_km)
st_folium(m, width=None, height=550, use_container_width=True)


# ── Helper: Download EE Thumbnail for PDF ────────────────────────────
def get_dem_thumbnail(dem_image, region, vis):
    """Get a static thumbnail PNG from Earth Engine."""
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


# ── Interpretation Generator ─────────────────────────────────────────
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
            "susceptible to flooding, waterlogging, or tidal influence. These "
            "zones require careful consideration for urban planning and "
            "infrastructure development." % min_e
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


# ── PDF Report Generator ─────────────────────────────────────────────
class ReportPDF(FPDF):
    """Custom PDF class with automatic headers and footers."""
    def header(self):
        if self.page_no() == 1:
            return  # Page 1 has custom header
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
    """Helper to print a green section heading."""
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(0, 102, 51)
    pdf.cell(0, 10, txt="%s. %s" % (num, title), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(0, 102, 51)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)


def create_pdf(title, creator, avg, min_e, max_e, std, buf_km, map_img_path):
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ════════════════════════════════════════════════════════════════
    # PAGE 1: COVER — Title, Metadata, Map
    # ════════════════════════════════════════════════════════════════
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

    # ════════════════════════════════════════════════════════════════
    # PAGE 2: Map Metadata, Data Source, Methodology
    # ════════════════════════════════════════════════════════════════
    pdf.add_page()

    # Section 1: Location Details
    section_heading(pdf, 1, "LOCATION DETAILS")
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 7, txt="City: Cuttack, Odisha, India", ln=True)
    pdf.cell(0, 7, txt="Center Coordinates: 20.4625 N, 85.8828 E", ln=True)
    pdf.cell(0, 7, txt="Study Area Buffer: %s km radius" % buf_km, ln=True)
    pdf.cell(0, 7, txt="Approximate Area: %.1f sq km" % (3.14159 * buf_km * buf_km), ln=True)
    pdf.cell(0, 7, txt="Region: Mahanadi River Delta, Eastern India", ln=True)
    pdf.ln(4)

    # Section 2: Map Metadata
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

    # Section 3: Methodology
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
        "from the Google Earth Engine data catalog. This dataset provides "
        "near-global elevation data at approximately 30-meter resolution.",
        "",
        "Step 3: Statistical Analysis",
        "Zonal statistics were computed using ee.Image.reduceRegion() with "
        "combined reducers (mean, min, max, stdDev) over the ROI at native "
        "30m resolution. The maxPixels parameter was set to 1e9 to ensure "
        "complete coverage.",
        "",
        "Step 4: Visualization",
        "The DEM was visualized using a five-color palette (green to white) "
        "with min=0m and max=100m, optimized for the low-elevation coastal "
        "terrain of the Cuttack region. The map was rendered using Folium "
        "with Earth Engine tile layers.",
        "",
        "Step 5: Report Generation",
        "Statistics, map thumbnail, and interpretation were compiled into "
        "this PDF report using the FPDF library integrated with the "
        "Streamlit web application.",
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

    # ════════════════════════════════════════════════════════════════
    # PAGE 3: Statistics & Interpretation
    # ════════════════════════════════════════════════════════════════
    pdf.add_page()

    # Section 4: Elevation Statistics
    section_heading(pdf, 4, "ELEVATION STATISTICS")

    # Stats table
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

    # Section 5: Interpretation
    section_heading(pdf, 5, "INTERPRETATION & ANALYSIS")
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

    # ── Disclaimer ───────────────────────────────────────────────────
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

    # Return as bytes
    pdf_str = pdf.output(dest='S')
    return pdf_str.encode('latin-1')



# ── Sidebar download ─────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("📄 Generate Report")
if st.sidebar.button("Generate PDF Report", type="primary"):
    with st.sidebar:
        with st.spinner("Downloading map thumbnail..."):
            map_img = get_dem_thumbnail(dem, roi, vis_params)
        with st.spinner("Generating PDF report..."):
            pdf_bytes = create_pdf(
                report_name, user_name,
                avg_elev, min_elev, max_elev, std_elev, buffer_km,
                map_img
            )
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name="%s.pdf" % report_name.replace(' ', '_'),
                mime="application/pdf"
            )
            st.success("PDF generated successfully!")
        # Clean up temp file
        if map_img and os.path.exists(map_img):
            os.unlink(map_img)
