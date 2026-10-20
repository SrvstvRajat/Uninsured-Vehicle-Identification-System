CREATE USER IF NOT EXISTS 'coordinator'@'%' IDENTIFIED BY 'ChooseAStrongPassword123!';
GRANT SELECT, INSERT,UPDATE, DELETE ON theft_db.* TO 'coordinator'@'%';
FLUSH PRIVILEGES;