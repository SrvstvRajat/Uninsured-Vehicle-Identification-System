CREATE DATABASE IF NOT EXISTS theft_db;
USE theft_db;

CREATE TABLE IF NOT EXISTS theft_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plate_no VARCHAR(20) NOT NULL,
    theft_date DATE,
    status ENUM('stolen','recovered','shredded') DEFAULT 'stolen',
    shredded_date DATE NULL,
    INDEX idx_plate_no (plate_no)
);