-- =====================================================================
-- Phase 3 — M5 — theft_db
-- Step 2 of 2: FK constraints on the hub table. Run AFTER the loader has
-- filled theft_records.station_id / fir_id (otherwise errno 1452).
--
-- Run:  python3 phase3/setup_theft.py fk          (safe to re-run)
-- =====================================================================
ALTER TABLE theft_records
  ADD CONSTRAINT fk_theft_station FOREIGN KEY (station_id) REFERENCES police_stations(station_id);
ALTER TABLE theft_records
  ADD CONSTRAINT fk_theft_fir FOREIGN KEY (fir_id) REFERENCES firs(fir_id);
