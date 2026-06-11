from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request

from comparison_logic import build_comparison_report
from extractor import extract_recon_data
from training_data_manager import TrainingDataManager

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PDF = BASE_DIR / "9223_shiftreport_202604201259_POS1_3414.pdf"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize training data manager (Cosmos-backed when env vars are configured)
trainer = TrainingDataManager(
    BASE_DIR / "training_data",
    database_id="Smart Daily Reconciliation",
    container_id="training-records",
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


@app.get("/")
def index() -> str:
    return render_template("index.html", default_pdf_exists=DEFAULT_PDF.exists())


@app.get("/api/extract/default")
def extract_default():
    if not DEFAULT_PDF.exists():
        return jsonify({"error": f"Default PDF not found: {DEFAULT_PDF.name}"}), 404

    data = extract_recon_data(DEFAULT_PDF)
    return jsonify(data)


@app.post("/api/extract/upload")
def extract_upload():
    file = request.files.get("pdf")
    if file is None or file.filename is None or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a valid PDF file."}), 400

    dest = UPLOAD_DIR / Path(file.filename).name
    file.save(dest)

    data: Dict[str, Any] = extract_recon_data(dest)
    return jsonify(data)


@app.post("/api/extract/upload-multiple")
def extract_upload_multiple():
    files = request.files.getlist("pdfs")
    if not files:
        return jsonify({"error": "Please upload one or more PDF files."}), 400

    shift_buckets: Dict[str, list] = {"Morning": [], "Day": [], "Night": []}
    unknown_shifts: list = []
    errors: list = []

    for file in files:
        if file is None or file.filename is None or not file.filename.lower().endswith(".pdf"):
            errors.append({"file": file.filename if file else "unknown", "error": "Invalid PDF file."})
            continue

        dest = UPLOAD_DIR / Path(file.filename).name
        file.save(dest)

        try:
            data = extract_recon_data(dest)
            shift_label = (data.get("meta", {}).get("shift_label") or "Unknown").title()
            if shift_label in shift_buckets:
                shift_buckets[shift_label].append(data)
            else:
                unknown_shifts.append(data)
        except Exception as e:
            errors.append({"file": file.filename, "error": str(e)})

    captured = {
        "Morning": len(shift_buckets["Morning"]),
        "Day": len(shift_buckets["Day"]),
        "Night": len(shift_buckets["Night"]),
    }

    complete_capture = all(captured[shift] > 0 for shift in ("Morning", "Day", "Night"))

    return jsonify({
        "captured": captured,
        "complete_capture": complete_capture,
        "shifts": shift_buckets,
        "unknown_shifts": unknown_shifts,
        "errors": errors,
    })


@app.post("/api/compare/upload-bundle")
def compare_upload_bundle():
    pdf_files = request.files.getlist("pdfs")
    workbook_file = request.files.get("workbook")

    if len(pdf_files) != 3:
        return jsonify({"error": "Please upload exactly three PDF shift reports."}), 400

    if workbook_file is None or workbook_file.filename is None:
        return jsonify({"error": "Please upload the Excel reconciliation workbook."}), 400

    workbook_name = workbook_file.filename.lower()
    if not workbook_name.endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        return jsonify({"error": "Please upload a valid Excel workbook (.xlsx or .xlsm)."}), 400

    saved_pdf_paths: list[Path] = []
    for file in pdf_files:
        if file is None or file.filename is None or not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "All uploaded shift reports must be PDF files."}), 400
        dest = UPLOAD_DIR / Path(file.filename).name
        file.save(dest)
        saved_pdf_paths.append(dest)

    workbook_dest = UPLOAD_DIR / Path(workbook_file.filename).name
    workbook_file.save(workbook_dest)

    try:
        comparison = build_comparison_report(saved_pdf_paths, workbook_dest)
    except Exception as e:
        return jsonify({"error": f"Failed to compare uploaded bundle: {str(e)}"}), 500

    shift_buckets: Dict[str, list] = {"Morning": [], "Day": [], "Night": []}
    unknown_shifts: list = []
    for pdf_path in saved_pdf_paths:
        data = extract_recon_data(pdf_path)
        shift_label = (data.get("meta", {}).get("shift_label") or "Unknown").title()
        if shift_label in shift_buckets:
            shift_buckets[shift_label].append(data)
        else:
            unknown_shifts.append(data)

    captured = {
        "Morning": len(shift_buckets["Morning"]),
        "Day": len(shift_buckets["Day"]),
        "Night": len(shift_buckets["Night"]),
    }

    complete_capture = all(captured[shift] > 0 for shift in ("Morning", "Day", "Night"))

    return jsonify({
        "captured": captured,
        "complete_capture": complete_capture,
        "shifts": shift_buckets,
        "unknown_shifts": unknown_shifts,
        "errors": [],
        "comparison": comparison,
    })


@app.post("/api/training/save")
def save_training_record():
    """Save extracted data with user-provided value payouts to training data."""
    payload = request.get_json()
    
    if not payload:
        return jsonify({"error": "No data provided"}), 400
    
    extracted_data = payload.get("extracted_data")
    value_payouts = payload.get("value_payouts", {})
    notes = payload.get("notes", "")
    
    if not extracted_data:
        return jsonify({"error": "extracted_data is required"}), 400
    
    try:
        record = trainer.add_training_record(extracted_data, value_payouts, notes)
        return jsonify({
            "success": True,
            "message": "Training record saved successfully",
            "record_id": record["timestamp"],
        }), 201
    except Exception as e:
        return jsonify({"error": f"Failed to save training record: {str(e)}"}), 500


@app.get("/api/training/records")
def get_training_records():
    """Retrieve all training records."""
    try:
        records = trainer.get_all_records()
        return jsonify({
            "total_records": len(records),
            "records": records,
        })
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve records: {str(e)}"}), 500


@app.get("/api/training/summary")
def get_training_summary():
    """Get summary statistics of training data."""
    try:
        summary = trainer.get_records_summary()
        stats = trainer.get_payout_statistics()
        
        return jsonify({
            "summary": summary,
            "payout_statistics": stats,
        })
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve summary: {str(e)}"}), 500


@app.post("/api/training/export")
def export_training_data():
    """Export training data to a file."""
    try:
        export_path = trainer.export_training_data(BASE_DIR / "training_export.json")
        return jsonify({
            "success": True,
            "message": "Training data exported successfully",
            "file_path": str(export_path),
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to export training data: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
