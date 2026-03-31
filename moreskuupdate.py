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
    "BLUE": "Blue", "GREEN": "Green", "RUST": "Rust",
    "LAVENDER": "Lavender", "MINT": "Mint", "PEACH": "Peach"
}

SIZE_ORDER = ["S","M","L","XL","XXL","2XL","3XL","4XL","5XL","6XL","7XL","8XL","9XL","10XL", "Free"]

# --- HELPERS ---

def extract_size(sku):
    sku = str(sku).upper().strip()
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

@st.cache_data
def process_data(uploaded_files):
    all_dfs = []
    for file in uploaded_files:
        try:
            temp_df = pd.read_csv(file)
            
            # Normalize column names
            temp_df.columns = [c.upper().strip().replace(" ", "_") for c in temp_df.columns]
            
            # FIX: Remove duplicate column names if any
            temp_df = temp_df.loc[:, ~temp_df.columns.duplicated()]
            
            # Flexible SKU & Qty Detection
            sku_col = next((c for c in temp_df.columns if "SKU" in c), None)
            qty_col = next((c for c in temp_df.columns if any(k in c for k in ["QTY", "QUANT", "COUNT"])), None)
            
            if not sku_col:
                st.error(f"❌ '{file.name}' missing SKU column.")
                continue
                
            # Keep only necessary data to prevent memory/index issues
            subset = pd.DataFrame()
            subset['SKU'] = temp_df[sku_col].astype(str)
            subset['RAW_QTY'] = pd.to_numeric(temp_df[qty_col], errors='coerce').fillna(1) if qty_col else 1
            
            all_dfs.append(subset)
        except Exception as e:
            st.error(f"Error reading {file.name}: {e}")

    if not all_dfs:
        return None

    # Safe Concat
    df = pd.concat(all_dfs, ignore_index=True)
    
    df['Category'] = df['SKU'].apply(get_category)
    df['Size'] = df['SKU'].apply(extract_size)
    df['Colors'] = df['SKU'].apply(extract_colors)
    df = df.explode('Colors')
    
    # Aggregation
    final_df = df.groupby(['Category', 'Colors', 'Size'], as_index=False)['RAW_QTY'].sum()
    final_df.columns = ["Category", "Color", "Size", "Qty"]
    
    # Sorting Logic (Black/White Priority)
    actual_colors = final_df["Color"].unique().tolist()
    other_colors = sorted([c for c in actual_colors if c not in ["Black", "White", "Unknown"]])
    color_order = ["Black", "White"] + other_colors + ["Unknown"]
    
    actual_sizes = final_df["Size"].unique().tolist()
    size_order = [s for s in SIZE_ORDER if s in actual_sizes] + [s for s in actual_sizes if s not in SIZE_ORDER]

    final_df["Color"] = pd.Categorical(final_df["Color"], categories=color_order, ordered=True)
    final_df["Size"] = pd.Categorical(final_df["Size"], categories=size_order, ordered=True)
    
    return final_df.sort_values(by=["Category", "Color", "Size"]).reset_index(drop=True)

def create_pdf(dataframe):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=(3.5*inch, 6*inch),
        rightMargin=0.05*inch, leftMargin=0.05*inch,
        topMargin=0.1*inch, bottomMargin=0.1*inch
    )

    elements = []
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontSize = 9
    
    ts = datetime.now().strftime("%d-%m %H:%M")
    elements.append(Paragraph(f"<b>AAVONI PICK LIST</b>", header_style))
    elements.append(Paragraph(f"<font size=7>{ts} | Total: {int(dataframe['Qty'].sum())}</font>", header_style))
    elements.append(Spacer(1, 0.1*inch))

    data = [["Cat", "Color", "Size", "Qty"]]
    for _, row in dataframe.iterrows():
        data.append([row["Category"], row["Color"], row["Size"], int(row["Qty"])])

    table = Table(data, colWidths=[0.5*inch, 1.4*inch, 0.7*inch, 0.45*inch], repeatRows=1)
    style_list = [
        ('BACKGROUND', (0,0), (-1,0), rl_colors.black),
        ('TEXTCOLOR',(0,0),(-1,0), rl_colors.white),
        ('GRID', (0,0), (-1,-1), 0.1, rl_colors.grey),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]

    for i in range(1, len(data)):
        if i % 2 == 0:
            style_list.append(('BACKGROUND', (0, i), (-1, i), rl_colors.whitesmoke))
        if int(data[i][3]) >= 5:
            style_list.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
            style_list.append(('TEXTCOLOR', (0, i), (0, i), rl_colors.red))

    table.setStyle(TableStyle(style_list))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- MAIN APP ---

st.title("📦 Aavoni Pick List PRO")

with st.sidebar:
    st.header("Upload Center")
    uploaded_files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)
    st.divider()
    st.caption("v2.5 - Stable Build")

if uploaded_files:
    final_df = process_data(uploaded_files)

    if final_df is not None:
        # Sidebar Unknown Check
        with st.sidebar:
            unknown_data = final_df[final_df["Color"] == "Unknown"]
            with st.expander("🔍 Unknown SKU Check", expanded=not unknown_data.empty):
                if not unknown_data.empty:
                    st.warning(f"Found {len(unknown_data)} unknown variants")
                    st.dataframe(unknown_data[["Category", "Size", "Qty"]], hide_index=True)
                else:
                    st.success("All colors matched! ✅")

        # Sidebar Filters
        available_cats = sorted(final_df["Category"].unique().tolist())
        selected_cats = st.sidebar.multiselect("Filter Category", available_cats, default=available_cats)
        display_df = final_df[final_df["Category"].isin(selected_cats)]

        # Dashboard
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Items", int(display_df["Qty"].sum()))
        m2.metric("Variants", len(display_df))
        m3.metric("Files", len(uploaded_files))

        # Table
        st.subheader("📋 Picking Table")
        st.dataframe(
            display_df.style.apply(lambda r: ['background-color: #fff2f2; color: #cc0000; font-weight: bold' if r.Qty >= 5 else '' for _ in r], axis=1),
            use_container_width=True,
            hide_index=True
        )

        # Exports
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                display_df.to_excel(writer, index=False)
            st.download_button("📥 Excel", data=excel_buffer.getvalue(), 
                               file_name=f"PickList_{datetime.now().strftime('%Y%m%d')}.xlsx",
                               use_container_width=True)
        with c2:
            pdf_file = create_pdf(display_df)
            st.download_button("📄 PDF (3x5)", data=pdf_file,
                               file_name=f"PickList_{datetime.now().strftime('%H%M')}.pdf",
                               use_container_width=True)
else:
    st.info("Upload CSV files. Works with 'SKU', 'Seller SKU Code', and 'Seller SKU'.")
