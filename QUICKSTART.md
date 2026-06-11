# 🚀 Quick Start Guide - Fuel Station Reconciliation System

## ⏱️ 5-Minute Setup

### Step 1: Install Dependencies (2 minutes)

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install streamlit==1.36.0 pypdf==4.1.0 pandas==2.2.0 plotly==5.18.0
```

### Step 2: Launch Dashboard (30 seconds)

```bash
streamlit run app_reconciliation.py
```

Your browser will open to `http://localhost:8501`

### Step 3: Upload PDFs (1 minute)

1. Click "Upload PDF files" button
2. Select one or multiple shift report PDFs
3. System processes automatically

### Step 4: Review Results (1.5 minutes)

- **See Global KPIs** at the top
- **Navigate tabs** for each shift
- **View POS terminals** as cards
- **Export CSV** from Consolidated Summary

---

## 📂 File Usage

### For PDF Processing Only

```python
from parser_logic import PDFShiftReportParser

parser = PDFShiftReportParser()
shift_data = parser.parse_shift_report("path/to/pdf.pdf")

print(shift_data.pos_terminal)      # "1"
print(shift_data.turnover)          # 152923.70
print(shift_data.cashier_name)      # "Dlomoze"
```

### Multiple Files

```python
shift_list, errors = parser.parse_multiple_reports([
    "report1.pdf",
    "report2.pdf",
    "report3.pdf"
])

for shift in shift_list:
    print(f"POS {shift.pos_terminal}: R{shift.turnover:,.2f}")

for error in errors:
    print(f"Error in {error['file']}: {error['error']}")
```

### For Calculations

```python
from app_reconciliation import ReconciliationCalculator

declared_mop = ReconciliationCalculator.calculate_declared_mop(shift_data)
cash_expected = ReconciliationCalculator.calculate_cash_expected(
    shift_data.turnover, declared_mop
)
variance = ReconciliationCalculator.calculate_variance(
    cash_expected, shift_data.safe_drops
)

print(f"Variance: R{variance:,.2f}")
```

---

## 🎯 Common Tasks

### Task: Extract Data Programmatically

```python
from parser_logic import parse_uploaded_pdfs
import json

# In a real scenario, use uploaded_files from Streamlit
uploaded_files = [...]  # List of uploaded files

shift_list, errors = parse_uploaded_pdfs(uploaded_files)

# Convert to JSON
data_json = json.dumps(
    [shift.to_dict() for shift in shift_list],
    indent=2,
    default=str
)
print(data_json)
```

### Task: Generate Custom Report

```python
from app_reconciliation import create_summary_dataframe

summary_df = create_summary_dataframe(shift_list)

# Filter by POS
pos1_data = summary_df[summary_df['POS'] == '1']

# Calculate aggregates
total_turnover = summary_df['Turnover (R)'].sum()
avg_variance = summary_df['Variance (R)'].mean()

print(f"Total Turnover: R{total_turnover:,.2f}")
print(f"Average Variance: R{avg_variance:,.2f}")
```

### Task: Batch Process Directory

```python
from pathlib import Path
from parser_logic import PDFShiftReportParser

parser = PDFShiftReportParser()
pdf_dir = Path("./uploads")

all_shifts = []
for pdf_file in pdf_dir.glob("*.pdf"):
    try:
        shift = parser.parse_shift_report(pdf_file)
        all_shifts.append(shift)
    except Exception as e:
        print(f"Error processing {pdf_file}: {e}")

print(f"Processed {len(all_shifts)} shift reports")
```

---

## 🎨 UI Navigation Map

```
┌─────────────────────────────────────────────────┐
│         ⛽ Fuel Station Dashboard              │
│     Automated PDF & Executive Reconciliation   │
└─────────────────────────────────────────────────┘
              │
              ├─── Global KPI Metrics
              │    ├── Total Daily Turnover
              │    ├── Total Safe Drops
              │    └── Total Site Variance
              │
              ├─── File Upload Area
              │    └── Drag & Drop PDFs
              │
              └─── Shift Tabs
                   ├── 🌅 Morning Shift
                   │   ├── POS 1 Card
                   │   ├── POS 2 Card
                   │   └── POS 3 Card
                   │
                   ├── ☀️ Day Shift
                   │   ├── POS 1 Card
                   │   ├── POS 2 Card
                   │   └── POS 3 Card
                   │
                   ├── 🌙 Night Shift
                   │   ├── POS 1 Card
                   │   ├── POS 2 Card
                   │   └── POS 3 Card
                   │
                   └── 📊 Consolidated Summary
                       ├── Full Matrix Table
                       ├── Statistics
                       ├── Variance Analysis
                       ├── Manager Notes
                       └── CSV Export
```

---

## 🔧 Customization

### Change Shift Times

Edit in `parser_logic.py` `_classify_shift()` method:

```python
if 4 <= hour < 12:           # Morning: 04:00-12:00
    return "Morning Shift"
elif 12 <= hour < 18:        # Day: 12:00-18:00
    return "Day Shift"
else:                         # Night: 18:00+
    return "NIGHT SHIFT"
```

### Modify Dashboard Colors

Edit CSS in `app_reconciliation.py`:

```python
st.markdown("""
<style>
    --primary-color: #1f77b4;      # Change these
    --success-color: #2ca02c;
    --danger-color: #d62728;
</style>
""", unsafe_allow_html=True)
```

### Add New Extraction Pattern

Edit `parser_logic.py`:

```python
self.patterns = {
    "your_new_field": r"YOUR_REGEX_PATTERN",
    # ... existing patterns
}
```

Then use:
```python
your_value = self._extract_value(self.patterns["your_new_field"], text)
```

---

## 📊 Sample Dashboard Session

1. **Open app** → `streamlit run app_reconciliation.py`
2. **Upload 3 PDFs** → POS1 Morning, POS2 Day, POS3 Night
3. **See KPIs**:
   - Total Turnover: R 369,671.65
   - Safe Drops: R 15,000.00
   - Site Variance: R 2,145.32
4. **View Morning Shift**:
   - POS 1: Turnover R 152,923.70, Variance R 1,200.00
5. **View Day Shift**:
   - POS 2: Turnover R 76,325.25, Variance R 0.00 ✓
6. **View Night Shift**:
   - POS 3: Turnover R 140,422.70, Variance -R 945.32 ⚠️
7. **Export CSV** → `reconciliation_20260516_143000.csv`

---

## ⚠️ Important Notes

1. **PDF Format**: System expects standard POS shift report format with:
   - POS NUMBER: [digit]
   - OPERATOR: [name]
   - TOTAL TURNOVER POS [amount]
   - SAFE DROPS [amount]

2. **Data Quality**: Ensure PDFs are:
   - Text-based (not scanned images)
   - Properly encoded UTF-8
   - Complete (all pages included)

3. **Performance**:
   - Processing time: ~2 seconds per PDF
   - Works smoothly with 10+ files
   - Dashboard updates in <1 second

4. **Storage**:
   - Uploaded PDFs saved to `/uploads/`
   - Training data stored in `/training_data/`
   - Clean up old files periodically

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: pypdf` | Run `pip install pypdf` |
| `StreamlitAPIException` | Restart dashboard: Stop and re-run command |
| PDF not extracting data | Verify PDF format matches expected shift report |
| Dashboard won't load | Check Python version (3.8+), reinstall packages |
| Variance seems wrong | Review Safe Drops and payment methods in PDF |

---

## 📞 Next Steps

1. ✅ Test with sample PDFs
2. ✅ Verify data extraction accuracy
3. ✅ Adjust regex patterns if needed
4. ✅ Deploy to production server
5. ✅ Train users on upload workflow

---

**Ready to go!** 🚀
