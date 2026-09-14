CREATE USER IF NOT EXISTS 'coordinator'@'%' IDENTIFIED BY 'ChooseAStrongPassword123!';
GRANT INSERT ON mot_db.* TO 'coordinator'@'%';
FLUSH PRIVILEGES;
