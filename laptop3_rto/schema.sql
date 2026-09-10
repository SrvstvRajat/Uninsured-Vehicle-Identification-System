CREATE DATABASE IF NOT EXISTS rto_db;
USE rto_db;

CREATE TABLE IF NOT EXISTS rto_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    car_id VARCHAR(20) NOT NULL,
    registration_date DATE,
    renewal_date DATE,
    rto_office VARCHAR(60)
);
