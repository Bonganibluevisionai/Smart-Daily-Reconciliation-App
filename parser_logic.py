"""
Production-Grade PDF Parser for Fuel Station POS Shift Reports
Extracts financial and operational data with robust error handling and data validation
"""

import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    import pypdf
except ImportError:
    pypdf = None


@dataclass
class ShiftData:
    """Data class for structured shift information"""
    pos_terminal: str
    cashier_name: str
    shift_classification: str
    turnover: float
    minpos_za: float
    local_accounts: float
    loyalty: float
    discount_refunds: float
    safe_drops: float
    page_1_timestamp_from: str
    page_1_timestamp_to: str
    source_file: str
    extracted_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class PDFShiftReportParser:
    """
    Enterprise-grade parser for POS shift report PDFs
    Handles text extraction, regex pattern matching, and data validation
    """

    def __init__(self):
        self.patterns = {
            "pos_number": r"POS\s+NUMBER:\s*(\d+)",
            "operator": r"OPERATOR:\s*([A-Za-z0-9\-\s]+?)(?:\n|$)",
            "total_of_shift_zero": r"TOTAL\s+OF\s+THE\s+SHIFT\s+=\s+ZERO",
            "total_turnover": r"TOTAL\s+TURNOVER\s+(?:OF\s+THE\s+)?POS\s+([0-9,]+\.?[0-9]*)",
            "minpos_za": r"MiniPOS\s+ZA\s+([0-9,]+\.?[0-9]*)",
            "local_account": r"(?:Local\s+Account|Corporate|LOCAL\s+ACCOUNT)[:\s]+([0-9,]+\.?[0-9]*)",
            "loyalty": r"(?:LOYALTY\s+REDEMPTION|LOYALTY|V\+)[:\s]+([0-9,]+\.?[0-9]*)",
            "discount_promotion": r"DISCOUNT\s*/?PROMOTION[:\s]+(-?[0-9,]+\.?[0-9]*)",
            "safe_drops_cash": r"EXPENSES\s+SAFE\s+DROPS\s+CASH\s+ZAR\s+([0-9,]+\.?[0-9]*)",
            "safe_drops": r"SAFE\s+DROPS[:\s]+([0-9,]+\.?[0-9]*)",
            "safe_drops_total": r"SAFE\s+DROPS[\s\S]*?\+\s*([0-9,]+\.?[0-9]*)",
            "from_timestamp": r"From:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM))?)",
            "to_timestamp": r"To:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM))?)",
        }

    def extract_text_from_pdf(self, pdf_path: str | Path) -> str:
        """
        Extract text from PDF file
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text from all pages
            
        Raises:
            FileNotFoundError: If PDF file doesn't exist
            ImportError: If pypdf is not installed
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        if pypdf is None:
            raise ImportError("pypdf library is required. Install with: pip install pypdf")
        
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            text = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += f"\n--- PAGE {page_num + 1} ---\n{page_text}"
            return text
        except Exception as e:
            raise RuntimeError(f"Error reading PDF {pdf_path.name}: {str(e)}")

    def _clean_currency_value(self, value: str) -> float:
        """
        Convert currency string to float
        Handles formats like "152,923.70", "152923.70", etc.
        
        Args:
            value: Currency string
            
        Returns:
            Float value, defaults to 0.0 if parsing fails
        """
        if not value or not isinstance(value, str):
            return 0.0
        
        try:
            cleaned = value.strip().replace(",", "").replace(" ", "")
            return float(cleaned) if cleaned else 0.0
        except (ValueError, AttributeError):
            return 0.0

    def _extract_value(self, pattern: str, text: str, group: int = 1) -> float:
        """
        Extract a single numeric value using regex pattern
        Returns 0.0 if not found or parsing fails
        
        Args:
            pattern: Regex pattern
            text: Text to search
            group: Regex group to extract
            
        Returns:
            Extracted float value
        """
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                value_str = match.group(group)
                return self._clean_currency_value(value_str)
        except (IndexError, AttributeError):
            pass
        return 0.0

    def _extract_safe_drops(self, text: str) -> float:
        """Extract cash-only safe drops without mixing in value payouts."""
        safe_drops = self._extract_value(self.patterns["safe_drops_cash"], text)
        if safe_drops != 0.0:
            return safe_drops

        detail_match = re.search(
            r"SAFE\s+DROPS\s+IN\s+DETAIL(?P<section>[\s\S]*?)DETAIL\s*-\s*THEORETICAL\s+CONTENTS\s+CASH\s+DRAWER",
            text,
            re.IGNORECASE,
        )
        if detail_match:
            amounts = [
                self._clean_currency_value(amount)
                for amount in re.findall(
                    r"\d{2}[/-]\d{2}[/-]\d{4}\s+\d{2}:\d{2}\s+\d+\s+Cash\s+(?:[A-Za-z]+\s+)?([0-9,]+\.?[0-9]*)",
                    detail_match.group("section"),
                    re.IGNORECASE,
                )
            ]
            if amounts:
                return round(sum(amounts), 2)

        safe_drops = self._extract_value(self.patterns["safe_drops_total"], text)
        if safe_drops == 0.0:
            safe_drops = self._extract_value(self.patterns["safe_drops"], text)
        return safe_drops

    def _classify_shift(self, from_time: str, to_time: str, text: str) -> str:
        """
        Classify shift based on timestamps and content
        
        Args:
            from_time: Start timestamp string
            to_time: End timestamp string
            text: Full PDF text
            
        Returns:
            Shift classification: "Morning Shift", "Day Shift", or "NIGHT SHIFT"
        """
        if re.search(self.patterns["total_of_shift_zero"], text):
            return "Zero Sales Shift"
        
        if not from_time:
            return "Unknown Shift"
        
        try:
            hour_match = re.search(r"(\d{1,2}):\d{2}", from_time)
            if hour_match:
                hour = int(hour_match.group(1))
                
                if 4 <= hour < 12:
                    return "Morning Shift"
                elif 12 <= hour < 18:
                    return "Day Shift"
                else:
                    return "NIGHT SHIFT"
        except (ValueError, AttributeError):
            pass
        
        return "Unclassified Shift"

    def _extract_pos_terminal(self, text: str) -> str:
        """Extract POS terminal number"""
        value = re.search(self.patterns["pos_number"], text, re.IGNORECASE)
        return value.group(1) if value else "0"

    def _extract_cashier_name(self, text: str) -> str:
        """Extract cashier name from OPERATOR field"""
        match = re.search(self.patterns["operator"], text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            name = re.sub(r"\d+", "", name).strip()
            return name if name else "Unknown"
        return "Unknown"

    def _extract_timestamps(self, text: str) -> tuple[str, str]:
        """Extract From and To timestamps"""
        from_match = re.search(self.patterns["from_timestamp"], text, re.IGNORECASE)
        to_match = re.search(self.patterns["to_timestamp"], text, re.IGNORECASE)
        
        from_time = from_match.group(1) if from_match else ""
        to_time = to_match.group(1) if to_match else ""
        
        return from_time, to_time

    def parse_shift_report(self, pdf_path: str | Path) -> ShiftData:
        """
        Parse complete shift report PDF and extract structured data
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            ShiftData object with all extracted information
            
        Raises:
            FileNotFoundError: If PDF doesn't exist
            RuntimeError: If PDF reading fails
        """
        pdf_path = Path(pdf_path)
        
        text = self.extract_text_from_pdf(pdf_path)
        
        from_time, to_time = self._extract_timestamps(text)
        
        pos_terminal = self._extract_pos_terminal(text)
        cashier_name = self._extract_cashier_name(text)
        shift_classification = self._classify_shift(from_time, to_time, text)
        
        turnover = self._extract_value(self.patterns["total_turnover"], text)
        minpos_za = self._extract_value(self.patterns["minpos_za"], text)
        local_accounts = self._extract_value(self.patterns["local_account"], text)
        loyalty = self._extract_value(self.patterns["loyalty"], text)
        discount_refunds = self._extract_value(self.patterns["discount_promotion"], text)
        
        safe_drops = self._extract_safe_drops(text)
        
        return ShiftData(
            pos_terminal=pos_terminal,
            cashier_name=cashier_name,
            shift_classification=shift_classification,
            turnover=round(turnover, 2),
            minpos_za=round(minpos_za, 2),
            local_accounts=round(local_accounts, 2),
            loyalty=round(loyalty, 2),
            discount_refunds=round(discount_refunds, 2),
            safe_drops=round(safe_drops, 2),
            page_1_timestamp_from=from_time,
            page_1_timestamp_to=to_time,
            source_file=pdf_path.name,
            extracted_at=datetime.now().isoformat()
        )

    def parse_multiple_reports(self, pdf_paths: List[str | Path]) -> List[ShiftData]:
        """
        Parse multiple PDF files
        
        Args:
            pdf_paths: List of PDF file paths
            
        Returns:
            List of ShiftData objects
        """
        results = []
        errors = []
        
        for pdf_path in pdf_paths:
            try:
                shift_data = self.parse_shift_report(pdf_path)
                results.append(shift_data)
            except Exception as e:
                errors.append({
                    "file": Path(pdf_path).name,
                    "error": str(e)
                })
        
        return results, errors


def parse_uploaded_pdfs(uploaded_files: List) -> tuple[List[ShiftData], List[Dict[str, str]]]:
    """
    Parse uploaded PDF files (for Streamlit integration)
    
    Args:
        uploaded_files: List of Streamlit UploadedFile objects
        
    Returns:
        Tuple of (list of ShiftData, list of errors)
    """
    parser = PDFShiftReportParser()
    results = []
    errors = []
    
    for uploaded_file in uploaded_files:
        try:
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.getbuffer())
                tmp_path = tmp_file.name
            
            try:
                shift_data = parser.parse_shift_report(tmp_path)
                results.append(shift_data)
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            errors.append({
                "file": uploaded_file.name,
                "error": str(e)
            })
    
    return results, errors
