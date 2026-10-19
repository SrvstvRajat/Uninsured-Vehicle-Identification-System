CREATE USER IF NOT EXISTS 'coordinator'@'%' IDENTIFIED BY 'ChooseAStrongPassword123!';
GRANT SELECT ON rto_db.* TO 'coordinator'@'%';
FLUSH PRIVILEGES;
