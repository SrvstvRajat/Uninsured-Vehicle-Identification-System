CREATE DATABASE IF NOT EXISTS vehicle_registration_db;
USE vehicle_registration_db;

CREATE TABLE IF NOT EXISTS vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reg_plate VARCHAR(20) NOT NULL,
    make VARCHAR(50),
    model VARCHAR(50),
    color VARCHAR(30),
    owner_name VARCHAR(100),
    engine_no VARCHAR(30),
    chassis_no VARCHAR(30),
    UNIQUE KEY uq_plate (reg_plate)
);
