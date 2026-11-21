-- =====================================================================
-- Phase 3 — M5 (Laptop 4, Theft & Shredding) — theft_db
-- Step 1 of 2: new tables + FK columns (constraints on theft_records come in
-- step 2, schema_theft_fk.sql, AFTER the data has been loaded).
--
-- Run:  python3 phase3/setup_theft.py schema      (safe to re-run)
--
-- Phase 2 keeps working: no existing table or column is removed or renamed.
-- =====================================================================

-- FOREIGN KEY constraints are ignored by MyISAM; the hub table must be InnoDB.
ALTER TABLE theft_records ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Parent tables
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS police_stations (
  station_id   INT AUTO_INCREMENT PRIMARY KEY,
  station_code VARCHAR(10) NOT NULL UNIQUE,      -- e.g. DEL03 (used in FIR numbers)
  station_name VARCHAR(100) NOT NULL,
  city         VARCHAR(60),
  phone        VARCHAR(15)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS firs (
  fir_id            INT AUTO_INCREMENT PRIMARY KEY,
  fir_no            VARCHAR(30) NOT NULL UNIQUE,   -- FIR/DEL03/2025/0142
  station_id        INT NOT NULL,
  filed_on          DATE NOT NULL,
  complainant_name  VARCHAR(100),
  complainant_phone VARCHAR(15),
  INDEX idx_fir_phone (complainant_phone),
  INDEX idx_fir_name (complainant_name),
  CONSTRAINT fk_fir_station FOREIGN KEY (station_id) REFERENCES police_stations(station_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- FK columns on the existing hub table (nullable; filled by the loader)
-- ---------------------------------------------------------------------
ALTER TABLE theft_records ADD COLUMN station_id INT NULL;
ALTER TABLE theft_records ADD COLUMN fir_id     INT NULL;
ALTER TABLE theft_records ADD INDEX idx_theft_station (station_id);
ALTER TABLE theft_records ADD INDEX idx_theft_fir (fir_id);

-- ---------------------------------------------------------------------
-- Child (event) tables. theft_id must have EXACTLY the type of
-- theft_records.id (setup_theft.py adapts it if needed).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recoveries (
  recovery_id       INT AUTO_INCREMENT PRIMARY KEY,
  theft_id          INT NOT NULL,
  recovery_date     DATE NOT NULL,
  location          VARCHAR(100),
  vehicle_condition VARCHAR(50),                   -- intact | damaged | parts missing ...
  CONSTRAINT fk_rec_theft FOREIGN KEY (theft_id) REFERENCES theft_records(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS shredding_certificates (
  cert_id        INT AUTO_INCREMENT PRIMARY KEY,
  theft_id       INT NOT NULL,
  scrap_yard     VARCHAR(100),
  shred_date     DATE NOT NULL,
  certificate_no VARCHAR(30) UNIQUE,               -- SHR202500012
  CONSTRAINT fk_shred_theft FOREIGN KEY (theft_id) REFERENCES theft_records(id)
) ENGINE=InnoDB;
