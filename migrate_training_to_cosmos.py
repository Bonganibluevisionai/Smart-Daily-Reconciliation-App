from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from azure.cosmos import CosmosClient, PartitionKey

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RECORDS_FILE = BASE_DIR / "training_data" / "records.json"

DATABASE_ID = os.getenv("AZURE_COSMOS_DATABASE", "Smart Daily Reconciliation")
CONTAINER_ID = os.getenv("AZURE_COSMOS_CONTAINER", "training-records")


def _extract_shift_label(extracted_data: Dict[str, Any]) -> str:
    meta = extracted_data.get("meta", {}) if isinstance(extracted_data, dict) else {}
    shift = str(meta.get("shift_label") or "Unknown").strip()
    return shift.title() if shift else "Unknown"


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    extracted_data = record.get("extracted_data") if isinstance(record.get("extracted_data"), dict) else {}
    timestamp = str(record.get("timestamp") or "").strip() or "unknown-timestamp"

    return {
        "id": str(record.get("id") or f"{timestamp}_{uuid4().hex[:8]}"),
        "timestamp": timestamp,
        "shiftLabel": str(record.get("shiftLabel") or _extract_shift_label(extracted_data)),
        "extracted_data": extracted_data,
        "value_payouts": record.get("value_payouts") if isinstance(record.get("value_payouts"), dict) else {},
        "notes": str(record.get("notes") or ""),
        "source_file": str(record.get("source_file") or extracted_data.get("source_file") or ""),
    }


def _load_local_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    data = json.loads(raw)
    return data if isinstance(data, list) else []


def main() -> None:
    endpoint = os.getenv("AZURE_COSMOS_ENDPOINT", "").strip()
    key = os.getenv("AZURE_COSMOS_KEY", "").strip()

    if not endpoint or not key:
        raise RuntimeError("Missing AZURE_COSMOS_ENDPOINT or AZURE_COSMOS_KEY environment variables.")

    records = _load_local_records(DEFAULT_RECORDS_FILE)
    if not records:
        print("No local records found to migrate.")
        return

    client = CosmosClient(endpoint, credential=key)
    database = client.create_database_if_not_exists(id=DATABASE_ID)
    container = database.create_container_if_not_exists(
        id=CONTAINER_ID,
        partition_key=PartitionKey(path="/shiftLabel"),
    )

    inserted = 0
    for raw_record in records:
        if not isinstance(raw_record, dict):
            continue
        record = _normalize_record(raw_record)
        container.upsert_item(record)
        inserted += 1

    print(f"Migrated {inserted} record(s) to Cosmos DB.")
    print(f"Database: {DATABASE_ID}")
    print(f"Container: {CONTAINER_ID}")


if __name__ == "__main__":
    main()
