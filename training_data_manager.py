from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List
from uuid import uuid4

try:
    from azure.cosmos import CosmosClient, PartitionKey
except Exception:  # pragma: no cover - handled via fallback mode
    CosmosClient = None
    PartitionKey = None


class TrainingDataManager:
    """Training records store with Cosmos DB support and local JSON fallback."""

    def __init__(
        self,
        data_dir: Path,
        database_id: str = "Smart Daily Reconciliation",
        container_id: str = "training-records",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.records_file = self.data_dir / "records.json"
        self.database_id = os.getenv("AZURE_COSMOS_DATABASE", database_id).strip() or database_id
        self.container_id = os.getenv("AZURE_COSMOS_CONTAINER", container_id).strip() or container_id
        self.endpoint = os.getenv("AZURE_COSMOS_ENDPOINT", "").strip()
        self.key = os.getenv("AZURE_COSMOS_KEY", "").strip()

        self._use_cosmos = bool(self.endpoint and self.key and CosmosClient)
        self._container = None

        if self._use_cosmos:
            client = CosmosClient(self.endpoint, credential=self.key)
            database = client.create_database_if_not_exists(id=self.database_id)
            self._container = database.create_container_if_not_exists(
                id=self.container_id,
                partition_key=PartitionKey(path="/shiftLabel"),
            )
            return

        if not self.records_file.exists():
            self.records_file.write_text("[]", encoding="utf-8")

    def _extract_shift_label(self, extracted_data: Dict[str, Any]) -> str:
        meta = extracted_data.get("meta", {}) if isinstance(extracted_data, dict) else {}
        shift_label = str(meta.get("shift_label") or "Unknown").strip()
        return shift_label.title() if shift_label else "Unknown"

    def _build_record(
        self,
        extracted_data: Dict[str, Any],
        value_payouts: Dict[str, Any] | None = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        shift_label = self._extract_shift_label(extracted_data)

        return {
            "id": f"{timestamp}_{uuid4().hex[:8]}",
            "timestamp": timestamp,
            "shiftLabel": shift_label,
            "extracted_data": extracted_data,
            "value_payouts": value_payouts or {},
            "notes": notes,
            "source_file": extracted_data.get("source_file", "") if isinstance(extracted_data, dict) else "",
        }

    def _read_all_cosmos_records(self) -> List[Dict[str, Any]]:
        if not self._container:
            return []

        records = list(
            self._container.query_items(
                query="SELECT * FROM c",
                enable_cross_partition_query=True,
            )
        )
        records.sort(key=lambda item: item.get("timestamp", ""))
        return records

    def _load_records(self) -> List[Dict[str, Any]]:
        raw = self.records_file.read_text(encoding="utf-8")
        if not raw.strip():
            return []
        return json.loads(raw)

    def _save_records(self, records: List[Dict[str, Any]]) -> None:
        self.records_file.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def add_training_record(
        self,
        extracted_data: Dict[str, Any],
        value_payouts: Dict[str, Any] | None = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        record = self._build_record(extracted_data, value_payouts, notes)

        if self._container:
            self._container.upsert_item(record)
            return record

        records = self._load_records()
        record.pop("id", None)
        record.pop("shiftLabel", None)
        record.pop("source_file", None)
        records.append(record)
        self._save_records(records)
        return record

    def get_all_records(self) -> List[Dict[str, Any]]:
        if self._container:
            return self._read_all_cosmos_records()
        return self._load_records()

    def get_records_summary(self) -> Dict[str, Any]:
        records = self.get_all_records()
        return {
            "total_records": len(records),
            "latest_record_timestamp": records[-1]["timestamp"] if records else None,
        }

    def get_payout_statistics(self) -> Dict[str, Any]:
        records = self.get_all_records()
        values_by_key: Dict[str, List[float]] = defaultdict(list)

        for record in records:
            payouts = record.get("value_payouts", {})
            if not isinstance(payouts, dict):
                continue

            for key, value in payouts.items():
                try:
                    values_by_key[str(key)].append(float(value))
                except (TypeError, ValueError):
                    continue

        stats: Dict[str, Any] = {}
        for key, values in values_by_key.items():
            stats[key] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": mean(values),
            }

        return stats

    def export_training_data(self, export_path: Path) -> Path:
        export_path = Path(export_path)
        records = self.get_all_records()
        export_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        return export_path
