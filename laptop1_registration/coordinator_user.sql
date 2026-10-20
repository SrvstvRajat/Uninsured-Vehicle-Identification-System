CREATE USER IF NOT EXISTS 'coordinator'@'%' IDENTIFIED BY 'ChooseAStrongPassword123!';
GRANT SELECT ON vehicle_registration_db.* TO 'coordinator'@'%';
FLUSH PRIVILEGES;
