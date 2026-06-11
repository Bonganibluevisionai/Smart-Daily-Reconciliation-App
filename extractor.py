import re
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

import pdfplumber


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "").strip())


def _find_amount(pattern: str, text: str, default: float = 0.0) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return default
    return _to_float(match.group(1))


def _parse_hour(timestamp: str) -> Optional[int]:
    if not timestamp:
        return None

    formats = [
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(timestamp.strip(), fmt).hour
        except ValueError:
            continue

    match = re.search(r"\b(\d{1,2}):(\d{2})\b", timestamp)
    if not match:
        return None

    hour = int(match.group(1))
    if 0 <= hour <= 23:
        return hour
    return None


def _classify_shift(from_ts: str) -> str:
    hour = _parse_hour(from_ts)
    if hour is None:
        return "Unknown"
    if 4 <= hour < 12:
        return "Morning"
    if 12 <= hour < 18:
        return "Day"
    return "Night"


def _extract_value_payout_suppliers(text: str) -> str:
    suppliers = []
    seen = set()

    for line in text.splitlines():
        if not re.search(r"Third\s+Party\s+Paymen", line, flags=re.IGNORECASE):
            continue

        cleaned = " ".join(line.split())
        cleaned = re.sub(r".*?Third\s+Party\s+Paymen\w*", "", cleaned, flags=re.IGNORECASE).strip(" :-")
        cleaned = re.sub(r"[-+]?\d[\d,]*\.\d+\s*$", "", cleaned).strip(" :-")

        if not cleaned:
            continue

        name = re.sub(r"\s+", " ", cleaned)
        key = name.lower()
        if key in seen:
            continue

        seen.add(key)
        suppliers.append(name)

    return ", ".join(suppliers)


def _extract_card_total(text: str) -> Optional[float]:
    """
    Compute Speedpoint total from Extra payment mode > Card using:
    Forecourt + Select/Shop + Local Account + FDL Switch + Loyalty Redemption.
    """
    label_patterns = [
        r"Forecourt",
        r"Select\s*/\s*Shop",
        r"Local\s+Account",
        r"FDL\s+Switch",
        r"Loyalty\s+Redemption",
    ]

    extra_mode_match = re.search(r"Extra\s+payment\s+mode", text, flags=re.IGNORECASE)
    card_start_match = re.search(r"\bCard\b", text, flags=re.IGNORECASE)

    search_text = text
    if extra_mode_match and card_start_match and card_start_match.start() > extra_mode_match.start():
        window_start = card_start_match.start()
        window_end = min(len(text), window_start + 3000)
        search_text = text[window_start:window_end]

    total = 0.0
    found_any = False

    for label_pattern in label_patterns:
        pattern = rf"{label_pattern}\s+(-?\d+[\d,]*\.\d+)"
        match = re.search(pattern, search_text, flags=re.IGNORECASE)
        if match:
            total += _to_float(match.group(1))
            found_any = True

    return round(total, 2) if found_any else None


def _extract_safe_drop_cash_total(text: str) -> float:
    expense_cash_match = re.search(
        r"EXPENSES\s+SAFE\s+DROPS\s+CASH\s+ZAR\s+([0-9,]+\.?[0-9]*)",
        text,
        flags=re.IGNORECASE,
    )
    if expense_cash_match:
        return _to_float(expense_cash_match.group(1))

    detail_match = re.search(
        r"SAFE\s+DROPS\s+IN\s+DETAIL(?P<section>[\s\S]*?)DETAIL\s*-\s*THEORETICAL\s+CONTENTS\s+CASH\s+DRAWER",
        text,
        flags=re.IGNORECASE,
    )
    if detail_match:
        amounts = [
            _to_float(amount)
            for amount in re.findall(
                r"\d{2}[-/]\d{2}[-/]\d{4}\s+\d{2}:\d{2}\s+\d+\s+Cash\s+(?:[A-Za-z]+\s+)?([0-9,]+\.?[0-9]*)",
                detail_match.group("section"),
                flags=re.IGNORECASE,
            )
        ]
        if amounts:
            return round(sum(amounts), 2)

    return _find_amount(r"SAFE DROPS[\s\S]*?\+\s*([0-9]+\.[0-9]+)", text)


def _extract_sales_per_report_code(text: str) -> Dict[str, float]:
    section_match = re.search(
        r"SALES PER REPORT CODE\s*report code quantity turnover(?P<section>[\s\S]*?)SALES PER REPORT CODE, VAT RATE",
        text,
        flags=re.IGNORECASE,
    )
    if not section_match:
        return {}

    section = section_match.group("section")
    lines = [line.strip() for line in section.splitlines() if line.strip()]

    amounts: Dict[str, float] = {}
    row_pattern = re.compile(r"^(?P<name>.+?)\s+(?P<qty>-?\d+\.\d+)\s+(?P<amount>-?\d+\.\d+)$")

    for line in lines:
        if line.startswith("+") or "Discount/promotion" in line:
            continue
        match = row_pattern.match(line)
        if not match:
            continue
        name = match.group("name").strip()
        amounts[name] = _to_float(match.group("amount"))

    return amounts


def _extract_fuels(text: str) -> Dict[str, Dict[str, float]]:
    fuel_map = {
        "V Power 95": r"^VP 95 \(I\)\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)$",
        "Unleaded Extra 93": r"^Fuelsave 93\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)$",
        "Diesel Extra 50": r"^FuelSave D50\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)$",
        "V Power Diesel": r"^VPD\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)$",
    }

    out: Dict[str, Dict[str, float]] = {}
    for display_name, pattern in fuel_map.items():
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            out[display_name] = {
                "volume_l": _to_float(match.group(1)),
                "revenue": _to_float(match.group(2)),
            }
        else:
            out[display_name] = {"volume_l": 0.0, "revenue": 0.0}

    out["TOTAL"] = {
        "volume_l": round(sum(x["volume_l"] for x in out.values()), 2),
        "revenue": round(sum(x["revenue"] for x in out.values()), 2),
    }
    return out


def extract_recon_data(pdf_path: str | Path) -> Dict[str, Any]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")

    text = "\n".join(pages)

    station_number = re.search(r"STATION NUMBER:(\d+)", text)
    shift_number = re.search(r"SHIFT NUMBER:(\d+)", text)
    pos_terminal = re.search(r"POS\s*NUMBER:\s*(\d+)", text, flags=re.IGNORECASE)
    operator = re.search(r"OPERATOR:\s*(.+)", text)
    from_ts = re.search(r"From:\s*(.+)", text)
    to_ts = re.search(r"To:\s*(.+)", text)
    from_time = from_ts.group(1).strip() if from_ts else ""
    shift_label = _classify_shift(from_time)

    fuels = _extract_fuels(text)

    sales_by_code = _extract_sales_per_report_code(text)

    lubricants = 0.0
    airtime = 0.0
    dbs = 0.0
    ticket = 0.0
    fuel_names = {"FuelSave D50", "Fuelsave 93", "VP 95 (I)", "VPD"}

    for code_name, amount in sales_by_code.items():
        lower_name = code_name.lower()
        if code_name in fuel_names:
            continue
        if "lubricant" in lower_name or "engine oil" in lower_name:
            lubricants += amount
        elif "mobile top-up" in lower_name:
            airtime += amount
        elif "ticket" in lower_name or "lotto" in lower_name or "lottery" in lower_name:
            ticket += amount
        elif code_name in {"Bakery Products", "Deli By Shell", "Hot Drinks"}:
            dbs += amount

    general_merchandise = sum(
        amount
        for code_name, amount in sales_by_code.items()
        if code_name not in fuel_names
        and code_name not in {"Bakery Products", "Deli By Shell", "Hot Drinks", "Mobile Top-Up"}
        and "lubricant" not in code_name.lower()
        and "engine oil" not in code_name.lower()
        and "ticket" not in code_name.lower()
        and "lotto" not in code_name.lower()
        and "lottery" not in code_name.lower()
    )

    total_turnover = _find_amount(r"TOTAL TURNOVER OF THE POS\s+([0-9]+\.[0-9]+)", text)
    total_sales_articles = _find_amount(r"TOTAL SALES OF ARTICLES\s+([0-9]+\.[0-9]+)", text)
    discount_promo = _find_amount(r"DISCOUNT/PROMOTION\s+(-?[0-9]+\.[0-9]+)", text)
    payment_terminal_cards = _find_amount(r"PAYMENT TERMINAL CARDS[\s\S]*?\+\s*([0-9]+\.[0-9]+)", text)
    safe_drops = _extract_safe_drop_cash_total(text)
    cash_amount = _find_amount(r"Cash\s+\d+\s+([0-9]+\.[0-9]+)", text)
    extra_payment_mode = _find_amount(r"Extra payment mode\s+([0-9]+\.[0-9]+)", text)
    loyalty_redemption = _find_amount(r"Loyalty\s+Redemption\s+([0-9]+\.[0-9]+)", text)
    payment_terminal_mop = _find_amount(r"Payment terminal\s+([0-9]+\.[0-9]+)", text, payment_terminal_cards)
    total_cash_for_shift = cash_amount + extra_payment_mode + loyalty_redemption + payment_terminal_mop
    total_value_payout_1 = _find_amount(r"Third Party Paymen\s+([0-9]+\.[0-9]+)", text)
    total_value_payout_2 = 0.0
    value_payout_supplier = _extract_value_payout_suppliers(text)
    card_total = _extract_card_total(text)
    card_total_value = card_total if card_total is not None else 0.0
    # Speedpoint is Extra Payment plus Card breakdown components.
    speedpoint = extra_payment_mode + card_total_value

    speed_point_totals = speedpoint
    theoretical_cashier_total = total_cash_for_shift - speed_point_totals - total_value_payout_1
    hard_cash_should_till = theoretical_cashier_total - safe_drops

    return {
        "source_file": str(pdf_path.name),
        "meta": {
            "station_number": station_number.group(1) if station_number else "",
            "shift_number": shift_number.group(1) if shift_number else "",
            "pos_terminal": pos_terminal.group(1) if pos_terminal else "",
            "operator": operator.group(1).strip() if operator else "",
            "from": from_time,
            "to": to_ts.group(1).strip() if to_ts else "",
            "shift_label": shift_label,
        },
        "fuel_summary": fuels,
        "shop_summary": {
            "General Merchandise": round(general_merchandise, 2),
            "DBS": round(dbs, 2),
            "Lubricants": round(lubricants, 2),
            "Air Time": round(airtime, 2),
            "Ticket": round(ticket, 2),
            "TOTAL": round(general_merchandise + dbs + lubricants + airtime + ticket, 2),
            "TOTAL SALES OF ARTICLES": round(total_sales_articles, 2),
        },
        "payments": {
            "Cash": round(cash_amount, 2),
            "Payment Terminal Cards": round(payment_terminal_cards, 2),
            "Loyalty Redemption": round(loyalty_redemption, 2),
            "Safe Drops": round(safe_drops, 2),
            "Speedpoint": round(speedpoint, 2),
            "CardTotal": round(card_total_value, 2),
        },
        "totals": {
            "Total Turnover POS": round(total_turnover, 2),
            "Discount/Promotion": round(discount_promo, 2),
        },
        "cashier_recon": {
            "Total cash for the Shift": round(total_cash_for_shift, 2),
            "Total Value Payout 1": round(total_value_payout_1, 2),
            "Total Value Payout 2": round(total_value_payout_2, 2),
            "Value Payout Supplier": value_payout_supplier,
            "Speed ponit totals": round(speedpoint, 2),
            "Speed point totals": round(speedpoint, 2),
            "Card Total": round(card_total_value, 2),
            "Safe Drop Value": round(safe_drops, 2),
            "Theoritical Cashier Total": round(theoretical_cashier_total, 2),
            "Hard cash that should be on till": round(hard_cash_should_till, 2),
        },
        "payment_values": {
            "Speedpoint": f"{round(speedpoint, 2):.2f}",
            "CardTotal": f"{round(card_total_value, 2):.2f}",
        },
        "raw": {
            "sales_by_report_code": sales_by_code,
        },
    }
