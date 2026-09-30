source scripts/start_postgres.sh
python3 -m activity_reporter ingest
python3 -m activity_reporter report