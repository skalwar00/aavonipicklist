import streamlit as st
import pandas as pd
import re
import io
from datetime import datetime

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER

# --- CONFIG & CONSTANTS ---
st.set_page_config(page_title="Aavoni Pick List PRO", layout="wide", page_icon="📦")

# Professional UI Styling
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stMetric { 
        background-color: #ffffff; padding: 20px; border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-left: 5px solid #007bff;
    }
    div.stButton > button:first-child {
        background-color: #007bff; color: white; height: 3em; border-radius: 8px; font-weight: bold; width: 100%;
    }
    .dev-tag {
        background: linear-gradient(135deg, #007bff, #6610f2);
        color: white; padding: 10px; border-radius: 8px; text-align: center; font-weight: bold; margin-top: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

COLOR_KEYWORDS = {
    "ROYAL BLUE": "Teal Blue", "ROYALBLUE": "Teal Blue", "TEAL": "Teal Blue", "RB": "Teal Blue",
    "SKY BLUE": "Sky Blue", "SKY": "Sky Blue", "SB": "Sky Blue",
    "BLACK": "Black", "BLK": "Black", "WHITE": "White", "WHT": "White",
    "BEIGE": "Beige", "BG": "Beige", "BEG": "Beige", "RANI": "Rani", "PINK": "Rani", "PINNK": "Rani",
    "MAROON": "Maroon", "MRN": "Maroon", "OLIVE": "Olive", "OLV": "Olive",
    "NAVY": "Navy", "YELLOW": "Yellow", "YELLOW": "ylw", "GREY": "Grey", "GRAY": "Grey",
    "BLUE": "Blue", "GREEN": "Green", "RUST": "Rust",
    "LAVENDER": "Lavender", "MINT": "Mint", "PEACH": "Peach"
}

SIZE_ORDER = ["S","M","L","XL","XXL","2XL","3XL","4XL","5XL","6XL","7XL","8XL","9XL","10XL", "Free"]

# --- HELPERS ---

def extract_size(sku):
    sku = str(sku).upper().strip().replace("_", " ").replace("-", " ")
    match = re.search(r'(\d{1,2}XL|XXL|XL|L|M|S)$', sku)
    if not match:
        match = re.search(r'\b(\d{1,2}XL|XXL|XL|L|M|S)\b', sku)
    return match.group(1) if match else "Free"

def extract_colors(sku):
    sku_clean = str(sku).upper().replace("_", " ").replace("-", " ").strip()
    if "CBO" in sku_clean:
        match = re.search(r'\((.*?)\)', sku_clean)
        if match:
            parts = match.group(1).replace(" ", "").split("+")
            final_colors = []
            for p in parts:
                found = False
                for key in sorted(COLOR_KEYWORDS.keys(), key=len, reverse=True):
                    if key.replace(" ","") == p or key == p:
                        final_colors.append(COLOR_KEYWORDS[key]); found = True; break
                if not found: final_colors.append("Unknown")
            return list(dict.fromkeys(final_colors)) if final_colors else ["Unknown"]
    for key in sorted(COLOR_KEYWORDS.keys(), key=len, reverse=True):
        if re.search(rf'\b{key}\b', sku_clean): return [COLOR_KEYWORDS[key]]
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
            preferred = ["SELLER_SKU_CODE", "SELLER_SKU", "SKU_CODE", "SKU"]
            idx = next((norm_cols.index(p) for p in preferred if p in norm_cols), 
                      next((i for i, c in enumerate(norm_cols) if "SKU" in c), None))
            if idx is None: continue
            q_idx = next((i for i, c in enumerate(norm_cols) if any(k in c for k in ["QTY", "QUANT", "COUNT"])), None)
            subset = pd.DataFrame()
            subset['SKU'] = temp_df[orig_cols[idx]].astype(str)
            subset['RAW_QTY'] = pd.to_numeric(temp_df[orig_cols[q_idx]], errors='coerce').fillna(1) if q_idx is not None else 1
            all_dfs.append(subset)
        except: continue
    if not all_dfs: return None
    df = pd.concat(all_dfs, ignore_index=True)
    df['Category'] = df['SKU'].apply(get_category); df['Size'] = df['SKU'].apply(extract_size); df['Colors'] = df['SKU'].apply(extract_colors)
    unknown_report = df[df['Colors'].apply(lambda x: x == ["Unknown"])][['SKU', 'Category', 'Size', 'RAW_QTY']].copy()
    df = df.explode('Colors')
    final_df = df.groupby(['Category', 'Colors', 'Size'], as_index=False)['RAW_QTY'].sum()
    final_df.columns = ["Category", "Color", "Size", "Qty"]
    actual_colors = final_df["Color"].unique().tolist()
    color_order = ["Black", "White"] + sorted([c for c in actual_colors if c not in ["Black", "White", "Unknown"]]) + ["Unknown"]
    final_df["Color"] = pd.Categorical(final_df["Color"], categories=color_order, ordered=True)
    final_df["Size"] = pd.Categorical(final_df["Size"], categories=SIZE_ORDER, ordered=True)
    return final_df.sort_values(by=["Category", "Color", "Size"]).reset_index(drop=True), unknown_report

# --- PDF LAYOUT FIXED (3x5) | FONT 7 | BIG CAT COL ---
def create_pdf(dataframe):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(3*inch, 5*inch), 
                          rightMargin=0.03*inch, leftMargin=0.03*inch, topMargin=0.1*inch, bottomMargin=0.1*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom Centered Style
    cell_style = styles['Normal'].clone('CellStyle')
    cell_style.alignment = TA_CENTER
    cell_style.fontSize = 7
    
    # Title
    elements.append(Paragraph(f"<b>AAVONI PICK LIST</b>", cell_style))
    elements.append(Paragraph(f"<font size=5>{datetime.now().strftime('%d-%m %H:%M')} | Total: {int(dataframe['Qty'].sum())}</font>", cell_style))
    elements.append(Spacer(1, 0.05*inch))
    
    data = [["Cat", "Color", "Size", "Qty", "Sh"]]
    for _, row in dataframe.iterrows():
        p_color = Paragraph(row['Color'], cell_style)
        data.append([row["Category"], p_color, row["Size"], int(row["Qty"]), ""])
    
    # Total 3.0 inch width divided as:
    # Cat: 0.8" (Increased), Color: 1.05", Size: 0.5", Qty: 0.35", Sh: 0.3"
    table = Table(data, colWidths=[0.8*inch, 1.05*inch, 0.5*inch, 0.35*inch, 0.3*inch], repeatRows=0)
    
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), rl_colors.black),
        ('TEXTCOLOR',(0,0),(-1,0), rl_colors.white),
        ('GRID', (0,0), (-1,-1), 0.2, rl_colors.grey),
        ('FONTSIZE', (0,0), (-1,-1), 7), 
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 1),
        ('RIGHTPADDING', (0,0), (-1,-1), 1),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    
    elements.append(table); doc.build(elements); buffer.seek(0)
    return buffer

# --- MAIN UI ---
st.title("📦 Aavoni Pick List PRO")
with st.sidebar:
    st.header("⚙️ Settings")
    uploaded_files = st.file_uploader("Upload CSV Files", type=["csv"], accept_multiple_files=True)
    st.markdown("---")
    st.markdown('<div class="dev-tag">👨‍💻 Developed by Sunil</div>', unsafe_allow_html=True)

if uploaded_files:
    res = process_data(uploaded_files)
    if res:
        final_df, unknown_report = res
        with st.sidebar:
            with st.expander("🔍 Unknown SKU Check", expanded=not unknown_report.empty):
                if not unknown_report.empty:
                    st.warning("SKUs to check:"); st.dataframe(unknown_report.rename(columns={'RAW_QTY': 'Qty'}), hide_index=True)
                else: st.success("All colors matched! ✅")
        
        display_df = final_df[final_df["Category"].isin(st.sidebar.multiselect("Category Filter", sorted(final_df["Category"].unique()), default=final_df["Category"].unique()))]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("📦 Total Items", int(display_df["Qty"].sum()))
        m2.metric("🌈 Variants", len(display_df)); m3.metric("📂 Files", len(uploaded_files))
        
        st.dataframe(display_df.style.apply(lambda r: ['background-color: #fff2f2; color: #cc0000; font-weight: bold' if r.Qty >= 5 else '' for _ in r], axis=1), use_container_width=True, hide_index=True)
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as writer: display_df.to_excel(writer, index=False)
            st.download_button("📥 Excel", data=excel_buf.getvalue(), file_name="PickList.xlsx", use_container_width=True)
        with c2:
            pdf_file = create_pdf(display_df)
            st.download_button("📄 Download PDF", data=pdf_file, file_name="PickList_3x5.pdf", use_container_width=True)
else:
    st.info("👋 Shuru karne ke liye sidebar se CSV files upload karein.")
