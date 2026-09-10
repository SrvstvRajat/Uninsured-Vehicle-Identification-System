CREATE DATABASE IF NOT EXISTS insurance_db;
USE insurance_db;

CREATE TABLE IF NOT EXISTS insurance_policies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_number VARCHAR(20) NOT NULL,
    insurer_name VARCHAR(100),
    policy_no VARCHAR(30),
    policy_start_date DATE,
    policy_end_date DATE,
    premium_amount DECIMAL(10,2)
);
