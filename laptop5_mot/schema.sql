CREATE DATABASE IF NOT EXISTS mot_db;
USE mot_db;

CREATE TABLE IF NOT EXISTS mot_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_plate VARCHAR(20) NOT NULL,
    report_date DATE,
    flag_reason VARCHAR(200),
    reported_by VARCHAR(60)
);
