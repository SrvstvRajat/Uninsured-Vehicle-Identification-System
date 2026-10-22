CREATE USER IF NOT EXISTS 'coordinator'@'%' IDENTIFIED BY 'ChooseAStrongPassword123!';
GRANT SELECT, INSERT,UPDATE, DELETE ON theft_db.* TO 'coordinator'@'%';
GRANT DELETE ON theft_db.theft_records TO 'coordinator'@'localhost';
FLUSH PRIVILEGES;