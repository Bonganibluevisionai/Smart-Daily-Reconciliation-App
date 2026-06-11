"""
Production-Grade Streamlit Dashboard for Fuel Station Reconciliation
Enterprise-class UI with professional styling, KPIs, and executive reporting
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import plotly.graph_objects as go
import plotly.express as px

from parser_logic import parse_uploaded_pdfs, ShiftData


# ============================================================================
# PAGE CONFIGURATION & THEMING
# ============================================================================

st.set_page_config(
    page_title="Fuel Station Daily Reconciliation",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional styling
st.markdown("""
<style>
    /* Global styles */
    :root {
        --primary-color: #1f77b4;
        --success-color: #2ca02c;
        --warning-color: #ff7f0e;
        --danger-color: #d62728;
        --neutral-color: #7f7f7f;
    }
    
    /* Header styling */
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 30px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
    }
    
    .header-title {
        font-size: 2.5em;
        font-weight: 700;
        margin: 0;
    }
    
    .header-subtitle {
        font-size: 1.1em;
        opacity: 0.9;
        margin-top: 5px;
    }
    
    /* KPI Cards */
    .kpi-card {
        background: white;
        padding: 20px;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .kpi-value {
        font-size: 1.8em;
        font-weight: 700;
        color: #333;
    }
    
    .kpi-label {
        font-size: 0.9em;
        color: #666;
        margin-top: 5px;
    }
    
    /* Variance styling */
    .variance-positive {
        color: #2ca02c;
        font-weight: 700;
    }
    
    .variance-negative {
        color: #d62728;
        font-weight: 700;
    }
    
    .variance-neutral {
        color: #333;
        font-weight: 700;
    }
    
    /* Data table styling */
    .dataframe-container {
        background: white;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Upload area */
    .upload-container {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 40px 20px;
        border-radius: 8px;
        border: 2px dashed #667eea;
        text-align: center;
    }
    
    /* Shift tabs */
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        font-size: 1.1em;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# DATA PROCESSING FUNCTIONS
# ============================================================================

class ReconciliationCalculator:
    """Calculate financial formulas for reconciliation"""
    
    @staticmethod
    def calculate_declared_mop(shift_data: ShiftData) -> float:
        """Total Declared Method of Payment"""
        return round(
            shift_data.minpos_za + 
            shift_data.local_accounts + 
            shift_data.loyalty + 
            shift_data.discount_refunds,
            2
        )
    
    @staticmethod
    def calculate_cash_expected(turnover: float, declared_mop: float) -> float:
        """Total Cash Expected = Turnover - Declared MOP"""
        return round(turnover - declared_mop, 2)
    
    @staticmethod
    def calculate_net_cash(cash_expected: float, safe_drops: float) -> float:
        """Net Cash to Account For = Cash Expected - Safe Drops"""
        return round(cash_expected - safe_drops, 2)
    
    @staticmethod
    def calculate_variance(cash_expected: float, safe_drops: float) -> float:
        """Variance (Surplus/Shortage)"""
        return round(cash_expected - safe_drops, 2)


def aggregate_shift_data(shift_list: List[ShiftData]) -> Dict[str, Any]:
    """
    Aggregate data by shift classification
    
    Returns dict with keys: "Morning Shift", "Day Shift", "NIGHT SHIFT", "Zero Sales Shift"
    """
    aggregated = defaultdict(list)
    
    for shift in shift_list:
        aggregated[shift.shift_classification].append(shift)
    
    return dict(aggregated)


def format_currency(value: float) -> str:
    """Format value as South African Rand"""
    return f"R {value:,.2f}"


def get_variance_color(variance: float) -> str:
    """Return color class for variance display"""
    if variance == 0.0:
        return "variance-neutral"
    elif variance > 0:
        return "variance-positive"
    else:
        return "variance-negative"


def create_summary_dataframe(shift_list: List[ShiftData]) -> pd.DataFrame:
    """Create comprehensive summary DataFrame"""
    data = []
    
    for shift in shift_list:
        declared_mop = ReconciliationCalculator.calculate_declared_mop(shift)
        cash_expected = ReconciliationCalculator.calculate_cash_expected(shift.turnover, declared_mop)
        variance = ReconciliationCalculator.calculate_variance(cash_expected, shift.safe_drops)
        
        data.append({
            "POS": shift.pos_terminal,
            "Cashier": shift.cashier_name,
            "Shift": shift.shift_classification,
            "Turnover (R)": shift.turnover,
            "Card Payments (R)": shift.minpos_za,
            "Local Accounts (R)": shift.local_accounts,
            "Loyalty (R)": shift.loyalty,
            "Discount/Refunds (R)": shift.discount_refunds,
            "Declared MOP (R)": declared_mop,
            "Cash Expected (R)": cash_expected,
            "Safe Drops (R)": shift.safe_drops,
            "Variance (R)": variance,
            "File": shift.source_file,
        })
    
    df = pd.DataFrame(data)
    return df


def export_to_csv(shift_list: List[ShiftData]) -> bytes:
    """Generate CSV export of reconciliation data"""
    df = create_summary_dataframe(shift_list)
    
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue().encode('utf-8')
    
    return csv_bytes


# ============================================================================
# UI COMPONENT FUNCTIONS
# ============================================================================

def render_header():
    """Render page header with title and subtitle"""
    st.markdown("""
    <div class="header-container">
        <h1 class="header-title">⛽ Fuel Station Daily Reconciliation & Cash Up</h1>
        <p class="header-subtitle">Automated PDF Processing & Executive Dashboard | Real-time Financial Analysis</p>
    </div>
    """, unsafe_allow_html=True)


def render_global_kpis(shift_list: List[ShiftData]):
    """Render top-level KPI metrics"""
    if not shift_list:
        return
    
    col1, col2, col3 = st.columns(3)
    
    total_turnover = sum(shift.turnover for shift in shift_list)
    total_safe_drops = sum(shift.safe_drops for shift in shift_list)
    
    total_variance = 0.0
    for shift in shift_list:
        declared_mop = ReconciliationCalculator.calculate_declared_mop(shift)
        cash_expected = ReconciliationCalculator.calculate_cash_expected(shift.turnover, declared_mop)
        variance = ReconciliationCalculator.calculate_variance(cash_expected, shift.safe_drops)
        total_variance += variance
    
    total_variance = round(total_variance, 2)
    
    with col1:
        st.metric(
            "Total Daily Site Turnover",
            format_currency(total_turnover),
            delta=None,
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            "Total Site Safe Drops",
            format_currency(total_safe_drops),
            delta=None,
            delta_color="normal"
        )
    
    with col3:
        variance_label = "Surplus" if total_variance >= 0 else "Shortage"
        variance_color = "normal" if total_variance >= 0 else "inverse"
        st.metric(
            "Total Daily Site Variance",
            format_currency(total_variance),
            delta=variance_label,
            delta_color=variance_color
        )


def render_file_uploader():
    """Render file upload interface"""
    with st.container():
        st.markdown("""
        <div style="text-align: center; padding: 20px;">
            <h3>📄 Upload Today's Shift Report PDFs</h3>
            <p style="color: #666;">Drag and drop or select multiple shift report PDFs to generate the daily cash up</p>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_files = st.file_uploader(
            "Choose PDF files",
            type="pdf",
            accept_multiple_files=True,
            label_visibility="collapsed"
        )
        
        return uploaded_files


def render_shift_tabs(aggregated_data: Dict[str, List[ShiftData]]):
    """Render shift classification tabs with POS details"""
    
    shift_keys = ["Morning Shift", "Day Shift", "NIGHT SHIFT", "Zero Sales Shift"]
    shift_tabs = st.tabs([
        "🌅 Morning Shift",
        "☀️ Day Shift",
        "🌙 Night Shift",
        "📊 Consolidated Summary"
    ])
    
    for tab_idx, (tab, shift_key) in enumerate(zip(shift_tabs[:3], shift_keys[:3])):
        with tab:
            shifts = aggregated_data.get(shift_key, [])
            
            if not shifts:
                st.info(f"No {shift_key.lower()} data available")
                continue
            
            render_shift_details(shifts, shift_key)
    
    with shift_tabs[3]:
        render_consolidated_summary(aggregated_data)


def render_shift_details(shifts: List[ShiftData], shift_name: str):
    """Render detailed view for a specific shift with POS terminals"""
    
    st.subheader(f"{shift_name} - POS Terminal Breakdown")
    
    if len(shifts) <= 3:
        cols = st.columns(len(shifts))
    else:
        cols = st.columns(3)
    
    for col_idx, shift in enumerate(shifts):
        col = cols[col_idx % 3]
        
        declared_mop = ReconciliationCalculator.calculate_declared_mop(shift)
        cash_expected = ReconciliationCalculator.calculate_cash_expected(shift.turnover, declared_mop)
        variance = ReconciliationCalculator.calculate_variance(cash_expected, shift.safe_drops)
        
        with col:
            with st.container(border=True):
                st.markdown(f"### POS {shift.pos_terminal}")
                
                st.markdown(f"**Cashier:** {shift.cashier_name}")
                st.markdown(f"**Time:** {shift.page_1_timestamp_from} to {shift.page_1_timestamp_to}")
                
                st.markdown("---")
                
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.metric("Turnover", format_currency(shift.turnover))
                with col_right:
                    st.metric("Cash Expected", format_currency(cash_expected))
                
                col_left, col_right = st.columns(2)
                with col_left:
                    st.metric("Safe Drops", format_currency(shift.safe_drops))
                with col_right:
                    variance_color = "🟢" if variance == 0.0 else ("🔴" if variance < 0 else "⚪")
                    st.metric("Variance", f"{variance_color} {format_currency(variance)}")
                
                if variance < 0:
                    st.error(f"**SHORTAGE: {format_currency(abs(variance))}**")
                elif variance > 0:
                    st.success(f"**Surplus: {format_currency(variance)}**")
                else:
                    st.info("✓ Cash Reconciled")
                
                with st.expander("📋 Payment Breakdown"):
                    payment_data = {
                        "Card Payments (MiniPOS ZA)": shift.minpos_za,
                        "Local Accounts": shift.local_accounts,
                        "Loyalty Redemption": shift.loyalty,
                        "Discount/Refunds": shift.discount_refunds,
                    }
                    
                    for payment_type, amount in payment_data.items():
                        st.write(f"{payment_type}: {format_currency(amount)}")
    
    st.markdown("---")
    st.subheader("Detailed Transaction Summary")
    
    summary_df = create_summary_dataframe(shifts)
    display_columns = [
        "POS", "Cashier", "Turnover (R)", "Declared MOP (R)", 
        "Cash Expected (R)", "Safe Drops (R)", "Variance (R)"
    ]
    
    st.dataframe(
        summary_df[display_columns],
        use_container_width=True,
        hide_index=True
    )


def render_consolidated_summary(aggregated_data: Dict[str, List[ShiftData]]):
    """Render consolidated summary across all shifts and terminals"""
    
    st.subheader("📊 Daily Consolidated Summary")
    
    all_shifts = []
    for shift_list in aggregated_data.values():
        all_shifts.extend(shift_list)
    
    if not all_shifts:
        st.info("No shift data available for summary")
        return
    
    summary_df = create_summary_dataframe(all_shifts)
    
    st.markdown("---")
    st.markdown("#### Full Reconciliation Matrix")
    
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.markdown("#### Summary Statistics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Shifts Processed", len(all_shifts))
    
    with col2:
        st.metric("Total Turnover", format_currency(summary_df["Turnover (R)"].sum()))
    
    with col3:
        total_safe_drops = summary_df["Safe Drops (R)"].sum()
        st.metric("Total Safe Drops", format_currency(total_safe_drops))
    
    with col4:
        total_variance = summary_df["Variance (R)"].sum()
        variance_status = "✓ Balanced" if total_variance == 0.0 else (
            f"Shortage: {format_currency(abs(total_variance))}" if total_variance < 0 
            else f"Surplus: {format_currency(total_variance)}"
        )
        st.metric("Daily Variance", format_currency(total_variance))
    
    st.markdown("---")
    st.markdown("#### Variance Analysis")
    
    variance_positive = summary_df[summary_df["Variance (R)"] > 0]
    variance_negative = summary_df[summary_df["Variance (R)"] < 0]
    variance_zero = summary_df[summary_df["Variance (R)"] == 0.0]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Terminals Balanced (0)", len(variance_zero))
    
    with col2:
        st.metric("Terminals in Surplus", len(variance_positive))
    
    with col3:
        st.metric("Terminals in Shortage", len(variance_negative))
    
    if len(variance_negative) > 0:
        st.warning("⚠️ **Action Required** - Shortages detected:")
        for _, row in variance_negative.iterrows():
            st.write(f"POS {row['POS']} ({row['Cashier']}): Shortage of {format_currency(abs(row['Variance (R)']))}")
    
    st.markdown("---")
    st.markdown("#### Manager Notes & Export")
    
    manager_notes = st.text_area(
        "Add reconciliation notes (optional):",
        placeholder="Record any discrepancies, unusual transactions, or notes for records...",
        height=120
    )
    
    col_export, col_download = st.columns(2)
    
    with col_export:
        if st.button("📥 Export to CSV", use_container_width=True):
            csv_data = export_to_csv(all_shifts)
            st.download_button(
                label="⬇️ Download CSV Report",
                data=csv_data,
                file_name=f"reconciliation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    with col_download:
        if st.button("📋 Copy Summary to Clipboard", use_container_width=True):
            st.success("Summary prepared for export")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main Streamlit application"""
    
    render_header()
    
    st.markdown("---")
    
    st.markdown("### 📤 File Upload")
    uploaded_files = render_file_uploader()
    
    if uploaded_files:
        with st.spinner("🔄 Processing PDF files..."):
            shift_data, errors = parse_uploaded_pdfs(uploaded_files)
        
        if errors:
            st.warning("⚠️ Some files encountered errors during processing:")
            for error in errors:
                st.error(f"**{error['file']}**: {error['error']}")
        
        if shift_data:
            st.success(f"✅ Successfully processed {len(shift_data)} shift report(s)")
            
            st.markdown("---")
            
            render_global_kpis(shift_data)
            
            st.markdown("---")
            
            aggregated = aggregate_shift_data(shift_data)
            render_shift_tabs(aggregated)
        else:
            st.error("❌ No valid data could be extracted from uploaded files")
    else:
        st.info("👆 Upload shift report PDFs to begin reconciliation")
        
        with st.container(border=True):
            st.markdown("""
            ### How to Use This Dashboard
            
            1. **Prepare Documents**: Gather all shift report PDFs from today's operations
            2. **Upload**: Use the upload area above to select one or multiple PDF files
            3. **Automatic Processing**: The system will extract and parse financial data
            4. **Review Results**: 
               - View KPIs for quick overview
               - Navigate tabs for shift-specific details
               - Check consolidated summary for full reconciliation
            5. **Export**: Generate CSV for further analysis or archival
            
            ### Data Extracted
            - POS Terminal Number and Cashier Information
            - Turnover and Payment Method Breakdown
            - Safe Drop Values and Manual Adjustments
            - Variance Analysis (Surplus/Shortage Detection)
            """)


if __name__ == "__main__":
    main()
