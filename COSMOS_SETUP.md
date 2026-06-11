# Cosmos DB Setup (Flask App)

This project now supports Azure Cosmos DB (NoSQL) for training records.

## Required Azure Resource Names

- Database id: Smart Daily Reconciliation
- Container id: training-records
- Partition key: /shiftLabel

## 1) Install Dependencies

```bash
pip install -r requirements.txt
```

## 2) Set Environment Variables

PowerShell:

```powershell
$env:AZURE_COSMOS_ENDPOINT = "https://<your-account>.documents.azure.com:443/"
$env:AZURE_COSMOS_KEY = "<your-primary-key>"
$env:AZURE_COSMOS_DATABASE = "Smart Daily Reconciliation"
$env:AZURE_COSMOS_CONTAINER = "training-records"
```

## 3) Run the Flask App

```bash
python app.py
```

When Cosmos variables are present, training records are saved to Cosmos.
If variables are missing, the app falls back to local JSON storage.

## 4) One-Time Migration from Local JSON to Cosmos

This script migrates records from training_data/records.json:

```bash
python migrate_training_to_cosmos.py
```

## Notes

- Documents written to Cosmos include:
  - id
  - timestamp
  - shiftLabel
  - extracted_data
  - value_payouts
  - notes
  - source_file
- Ensure /shiftLabel is present on every document (the migration script and app do this automatically).