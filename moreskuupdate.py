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

COLOR_KEYWORDS = {
    "BLACK": "Black", "BLK": "Black",
    "WHITE": "White", "WHT": "White",
    "BEIGE": "Beige", "BG": "Beige", "BEG": "Beige",
    "RANI": "Rani", "PINK": "Rani",
    "MAROON": "Maroon", "MRN": "Maroon",
    "OLIVE": "Olive", "OLV": "Olive",
    "NAVY": "Navy", "YELLOW": "Yellow",
    "GREY": "Grey", "GRAY": "Grey",
    "BLUE": "Blue", "GREEN": "Green", "RUST": "Rust"
}

SIZE_ORDER = ["S","M","L","XL","XXL","2XL","3XL","4XL","5XL","6XL","7XL","8XL","9XL","10XL", "Free"]

# --- IMPROVED HELPERS ---

def extract_size(sku):
    sku = str(sku).upper().strip()
    # Matches 2XL through 10XL first, then standard sizes
    match = re.search(r'\b(\d{1,2}XL|XXL|XL|L|M|S)\b', sku)
    return match.group(1) if match else "Free"

def extract_colors(sku):
    sku = str(sku).upper()
    if "CBO" in sku:
        match = re.search(r'\((.*?)\)', sku)
        if match:
            parts = match.group(1).replace(" ", "").split("+")
            final_colors = []
            for p in parts:
                if p in ["RB", "TEAL"]: final_colors.append("Teal Blue")
                elif p in COLOR_KEYWORDS: final_colors.append(COLOR_KEYWORDS[p])
            return list(dict.fromkeys(final_colors)) if final_colors else ["Unknown"]
    
    if any(x in sku for x in ["TEAL", "RB"]): return ["Teal Blue"]
    if any(x in sku for x in ["SB", "SKY"]): return ["Sky Blue"]

    for key, value in COLOR_KEYWORDS.items():
        if re.search(rf'\b{key}\b', sku):
            return [value]
    return ["Unknown"]

def get_category(sku):
    sku = str(sku).upper()
    if sku.startswith("HF"): return "HF"
    if sku.startswith("PL"): return "PLAZZO"
    return "TROUSER"

def create_pdf(dataframe):
    buffer = io.BytesIO()
    # 3x5 Thermal Label Size
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=(3*inch, 5*inch),
        rightMargin=0.05*inch, leftMargin=0.05*inch,
        topMargin=0.1*inch, bottomMargin=0.1*inch
    )

    elements = []
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontSize = 9
    
    ts = datetime.now().strftime("%d-%m %H:%M")
    elements.append(Paragraph(f"<b>AAVONI PICK LIST</b>", header_style))
    elements.append(Paragraph(f"<font size=7>{ts} | Total Items: {dataframe['Qty'].sum()}</font>", header_style))
    elements.append(Spacer(1, 0.1*inch))

    data = [["Cat", "Color", "Size", "Qty"]]
    for _, row in dataframe.iterrows():
        data.append([row["Category"], row["Color"], row["Size"], row["Qty"]])

    # Adjusted widths to maximize the 3-inch width
    table = Table(data, colWidths=[0.45*inch, 1.35*inch, 0.6*inch, 0.4*inch], repeatRows=1)

    style_list = [
        ('BACKGROUND', (0,0), (-1,0), rl_colors.black),
        ('TEXTCOLOR',(0,0),(-1,0), rl_colors.white),
        ('GRID', (0,0), (-1,-1), 0.1, rl_colors.grey),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
    ]

    for i in range(1, len(data)):
        if i % 2 == 0:
            style_list.append(('BACKGROUND', (0, i), (-1, i), rl_colors.whitesmoke))
        if int(data[i][3]) > 3:
            style_list.append(('TEXTCOLOR', (0, i), (-1, i), rl_colors.red))
            style_list.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))

    table.setStyle(TableStyle(style_list))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- MAIN APP ---

st.title("📦 Aavoni Pick List PRO")

with st.sidebar:
    st.header("Settings")
    uploaded_files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)
    st.divider()
    st.info("Files are merged automatically. Quantity column is auto-detected.")

if uploaded_files:
    # 1. Load and Clean Data
    all_dfs = []
    for file in uploaded_files:
        temp_df = pd.read_csv(file)
        temp_df.columns = [c.upper().strip() for c in temp_df.columns]
        if "SKU" not in temp_df.columns:
            st.error(f"❌ '{file.name}' missing SKU column.")
            continue
        all_dfs.append(temp_df)

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
        qty_col = next((c for c in df.columns if "QTY" in c or "QUANT" in c), None)
        if qty_col:
            df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(1)
        else:
            df['QTY'] = 1
            qty_col = 'QTY'

        # 2. Process using Vectorized approach
        df['Category'] = df['SKU'].apply(get_category)
        df['Size'] = df['SKU'].apply(extract_size)
        df['Colors'] = df['SKU'].apply(extract_colors)
        
        # Expand colors (handles CBO/combos)
        df = df.explode('Colors')
        
        # 3. Aggregate
        final_df = df.groupby(['Category', 'Colors', 'Size'], as_index=False)[qty_col].sum()
        final_df.columns = ["Category", "Color", "Size", "Qty"]
        
        # 4. Filter and Sort
        final_df["Size"] = pd.Categorical(final_df["Size"], categories=SIZE_ORDER, ordered=True)
        final_df = final_df.sort_values(by=["Category", "Color", "Size"]).dropna(subset=['Size'])

        # Sidebar Filters
        available_cats = final_df["Category"].unique().tolist()
        selected_cats = st.sidebar.multiselect("Filter by Category", available_cats, default=available_cats)
        
        display_df = final_df[final_df["Category"].isin(selected_cats)]

        # --- DASHBOARD ---
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Items", int(display_df["Qty"].sum()))
        m2.metric("Variants", len(display_df))
        m3.metric("Categories", len(display_df["Category"].unique()))

        # --- TABLE VIEW ---
        def style_logic(row):
            styles = [''] * len(row)
            if row.Qty > 3:
                styles = ['background-color: #fff2f2; color: #cc0000; font-weight: bold'] * len(row)
            return styles

        st.subheader("📋 Picking Table")
        st.dataframe(
            display_df.style.apply(style_logic, axis=1),
            use_container_width=True,
            hide_index=True
        )

        # --- EXPORTS ---
        st.divider()
        c1, c2 = st.columns(2)
        
        with c1:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                display_df.to_excel(writer, sheet_name="PickList", index=False)
            st.download_button("📥 Download Excel", data=excel_buffer.getvalue(),
                             file_name=f"PickList_{datetime.now().strftime('%Y%m%d')}.xlsx",
                             use_container_width=True)

        with c2:
            pdf_file = create_pdf(display_df)
            st.download_button("📄 Download Thermal PDF (3x5)", data=pdf_file,
                             file_name=f"PickList_{datetime.now().strftime('%H%M')}.pdf",
                             use_container_width=True)
else:
    st.info("Please upload your order CSV files to begin.")