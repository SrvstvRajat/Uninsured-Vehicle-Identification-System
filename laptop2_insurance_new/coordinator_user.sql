CREATE USER 'api_user'@'localhost' IDENTIFIED BY 'Ins-Api-7kQ2xM9vL4';
GRANT SELECT, INSERT, UPDATE, DELETE ON insurance_db.insurance_policies TO 'api_user'@'localhost';
FLUSH PRIVILEGES;