import streamlit as st
import pandas as pd
import re
import io
from datetime import datetime

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import inch

# --- CONFIG & CONSTANTS ---
st.set_page_config(page_title="Aavoni Pick List PRO", layout="wide", page_icon="📦")

# Custom CSS for Professional Look
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stMetric { 
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-left: 5px solid #007bff;
    }
    div.stButton > button:first-child {
        background-color: #007bff;
        color: white;
        height: 3em;
        border-radius: 8px;
        border: none;
        font-weight: bold;
        transition: 0.3s;
    }
    div.stButton > button:first-child:hover {
        background-color: #0056b3;
        border: none;
    }
    .dev-tag {
        background: linear-gradient(135deg, #007bff, #6610f2);
        color: white;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        font-weight: bold;
        margin-top: 20px;
    }
    </style>
    """, unsafe_allow_html=True) # FIXED TYPO HERE

COLOR_KEYWORDS = {
    "BLACK": "Black", "BLK": "Black", "WHITE": "White", "WHT": "White",
    "BEIGE": "Beige", "BG": "Beige", "BEG": "Beige", "RANI": "Rani", 
    "PINK": "Rani", "MAROON": "Maroon", "MRN": "Maroon", "OLIVE": "Olive", 
    "OLV": "Olive", "NAVY": "Navy", "YELLOW": "Yellow", "GREY": "Grey", 
    "GRAY": "Grey", "BLUE": "Blue", "GREEN": "Green", "RUST": "Rust",
    "LAVENDER": "Lavender", "MINT": "Mint", "PEACH": "Peach"
}

SIZE_ORDER = ["S","M","L","XL","XXL","2XL","3XL","4XL","5XL","6XL","7XL","8XL","9XL","10XL", "Free"]

# --- HELPERS ---

def extract_size(sku):
    sku = str(sku).upper().strip().replace("_", " ")
    match = re.search(r'(\d{1,2}XL|XXL|XL|L|M|S)$', sku)
    if not match:
        match = re.search(r'\b(\d{1,2}XL|XXL|XL|L|M|S)\b', sku)
    return match.group(1) if match else "Free"

def extract_colors(sku):
    sku_clean = str(sku).upper().replace("_", " ")
    if "CBO" in sku_clean:
        match = re.search(r'\((.*?)\)', sku_clean)
        if match:
            parts = match.group(1).replace(" ", "").split("+")
            final_colors = []
            for p in parts:
                if p in ["RB", "TEAL"]: final_colors.append("Teal Blue")
                elif p in COLOR_KEYWORDS: final_colors.append(COLOR_KEYWORDS[p])
            return list(dict.fromkeys(final_colors)) if final_colors else ["Unknown"]
    if any(x in sku_clean for x in ["TEAL", "RB"]): return ["Teal Blue"]
    if any(x in sku_clean for x in ["SB", "SKY"]): return ["Sky Blue"]
    for key, value in COLOR_KEYWORDS.items():
        if re.search(rf'\b{key}\b', sku_clean): return [value]
    return ["Unknown"]

def get_category(sku):
    sku = str(sku).upper()
    if sku.startswith("HF"): return "HF"
    if sku.startswith("PL"): return "PLAZZO"
    return "TROUSER"

@st.cache_data
def process_data(uploaded_files):
    all_dfs = []
    for file in uploaded_files:
        try:
            temp_df = pd.read_csv(file)
            orig_cols = temp_df.columns.tolist()
            norm_cols = [c.upper().strip().replace(" ", "_") for c in orig_cols]
            preferred_names = ["SELLER_SKU_CODE", "SELLER_SKU", "SKU_CODE", "SKU"]
            sku_col_idx = next((norm_cols.index(p) for p in preferred_names if p in norm_cols), 
                              next((i for i, c in enumerate(norm_cols) if "SKU" in c), None))
            if sku_col_idx is None: continue
            actual_sku_col = orig_cols[sku_col_idx]
            qty_col_idx = next((i for i, c in enumerate(norm_cols) if any(k in c for k in ["QTY", "QUANT", "COUNT"])), None)
            subset = pd.DataFrame()
            subset['SKU'] = temp_df[actual_sku_col].astype(str)
            subset['RAW_QTY'] = pd.to_numeric(temp_df[orig_cols[qty_col_idx]], errors='coerce').fillna(1) if qty_col_idx is not None else 1
            all_dfs.append(subset)
        except: continue
    if not all_dfs: return None
    df = pd.concat(all_dfs, ignore_index=True)
    df['Category'] = df['SKU'].apply(get_category)
    df['Size'] = df['SKU'].apply(extract_size)
    df['Colors'] = df['SKU'].apply(extract_colors)
    unknown_report = df[df['Colors'].apply(lambda x: x == ["Unknown"])][['SKU', 'Category', 'Size', 'RAW_QTY']].copy()
    df = df.explode('Colors')
    final_df = df.groupby(['Category', 'Colors', 'Size'], as_index=False)['RAW_QTY'].sum()
    final_df.columns = ["Category", "Color", "Size", "Qty"]
    actual_colors = final_df["Color"].unique().tolist()
    other_colors = sorted([c for c in actual_colors if c not in ["Black", "White", "Unknown"]])
    color_order = ["Black", "White"] + other_colors + ["Unknown"]
    final_df["Color"] = pd.Categorical(final_df["Color"], categories=color_order, ordered=True)
    final_df["Size"] = pd.Categorical(final_df["Size"], categories=SIZE_ORDER, ordered=True)
    return final_df.sort_values(by=["Category", "Color", "Size"]).reset_index(drop=True), unknown_report

def create_pdf(dataframe):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(3.5*inch, 6*inch), rightMargin=0.05*inch, leftMargin=0.05*inch, topMargin=0.1*inch, bottomMargin=0.1*inch)
    elements = []
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontSize = 8
    elements.append(Paragraph(f"<b>AAVONI PICK LIST</b>", header_style))
    elements.append(Paragraph(f"<font size=6>{datetime.now().strftime('%d-%m %H:%M')} | Total: {int(dataframe['Qty'].sum())}</font>", header_style))
    elements.append(Spacer(1, 0.05*inch))
    data = [["Cat", "Color", "Size", "Qty"]]
    for _, row in dataframe.iterrows():
        data.append([row["Category"], row["Color"], row["Size"], int(row["Qty"])])
    table = Table(data, colWidths=[0.4*inch, 1.5*inch, 0.7*inch, 0.4*inch], repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), rl_colors.black), ('TEXTCOLOR',(0,0),(-1,0), rl_colors.white), ('GRID', (0,0), (-1,-1), 0.1, rl_colors.grey), ('FONTSIZE', (0,0), (-1,-1), 7), ('ALIGN',(0,0),(-1,-1),'CENTER'), ('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    elements.append(table); doc.build(elements); buffer.seek(0)
    return buffer

# --- MAIN UI ---
st.title("📦 Aavoni Pick List PRO")

with st.sidebar:
    st.header("⚙️ Control Panel")
    uploaded_files = st.file_uploader("Upload Orders (CSV)", type=["csv"], accept_multiple_files=True)
    
    st.markdown("---")
    # --- DEVELOPER BRANDING ---
    st.markdown('<div class="dev-tag">👨‍💻 Developed by Sunil</div>', unsafe_allow_html=True)
    st.caption("Aavoni Inventory Solution v2.7")

if uploaded_files:
    res = process_data(uploaded_files)
    if res:
        final_df, unknown_report = res
        
        with st.sidebar:
            with st.expander("🔍 Unknown SKU Detector", expanded=not unknown_report.empty):
                if not unknown_report.empty:
                    st.warning("Pechan mein nahi aaye:")
                    st.dataframe(unknown_report.rename(columns={'RAW_QTY': 'Qty'}), hide_index=True)
                else:
                    st.success("All SKUs matched! ✅")

        cats = sorted(final_df["Category"].unique())
        selected = st.sidebar.multiselect("Filter Category", cats, default=cats)
        display_df = final_df[final_df["Category"].isin(selected)]

        # Dashboard
        c1, c2, c3 = st.columns(3)
        c1.metric("📦 Total Items", int(display_df["Qty"].sum()))
        c2.metric("🌈 Unique Variants", len(display_df))
        c3.metric("📂 Files", len(uploaded_files))

        st.subheader("📋 Packing List")
        st.dataframe(
            display_df.style.apply(lambda r: ['background-color: #fff2f2; color: #cc0000; font-weight: bold' if r.Qty >= 5 else '' for _ in r], axis=1),
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        st.subheader("🚀 Quick Export")
        col1, col2 = st.columns(2)
        with col1:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer: display_df.to_excel(writer, index=False)
            st.download_button("📥 Excel Sheet", data=excel_buffer.getvalue(), file_name=f"PickList_{datetime.now().strftime('%d%m')}.xlsx", use_container_width=True)
        with col2:
            pdf_file = create_pdf(display_df)
            st.download_button("📄 PDF (Mobile Print)", data=pdf_file, file_name=f"PickList_{datetime.now().strftime('%H%M')}.pdf", use_container_width=True)

else:
    st.info("👋 **Aavoni Dashboard** | Sidebar se CSV files upload karke shuru karein.")
