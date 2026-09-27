-- One-time local dev setup. Run as the postgres superuser:
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -f scripts/setup_local_db.sql
CREATE ROLE dealer WITH LOGIN PASSWORD 'dealer';
CREATE DATABASE dealer_ai OWNER dealer;
