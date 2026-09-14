CREATE USER IF NOT EXISTS 'coordinator'@'%' IDENTIFIED BY 'ChooseAStrongPassword123!';
GRANT SELECT ON insurance_db.* TO 'coordinator'@'%';
FLUSH PRIVILEGES;
