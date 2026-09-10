CREATE USER IF NOT EXISTS 'coordinator'@'%' IDENTIFIED BY 'ChooseAStrongPassword123!';
GRANT SELECT, INSERT, UPDATE ON insurance_db.* TO 'coordinator'@'%';
FLUSH PRIVILEGES;
