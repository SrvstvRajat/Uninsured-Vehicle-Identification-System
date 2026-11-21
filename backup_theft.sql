-- MySQL dump 10.13  Distrib 26.7.0, for macos26.6 (arm64)
--
-- Host: localhost    Database: theft_db
-- ------------------------------------------------------
-- Server version	26.7.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
SET @MYSQLDUMP_TEMP_LOG_BIN = @@SESSION.SQL_LOG_BIN;
SET @@SESSION.SQL_LOG_BIN= 0;

--
-- GTID state at the beginning of the backup 
--

SET @@GLOBAL.GTID_PURGED=/*!80000 '+'*/ 'a30e79b4-ad39-11f1-b297-da0fba79318a:1-651';

--
-- Table structure for table `theft_records`
--

DROP TABLE IF EXISTS `theft_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `theft_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `plate_no` varchar(20) NOT NULL,
  `theft_date` date DEFAULT NULL,
  `status` enum('stolen','recovered','shredded') DEFAULT 'stolen',
  `shredded_date` date DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=133 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `theft_records`
--

LOCK TABLES `theft_records` WRITE;
/*!40000 ALTER TABLE `theft_records` DISABLE KEYS */;
INSERT INTO `theft_records` VALUES (1,'DL03AC2946','2025-09-07','recovered',NULL),(2,'DL03AC7869','2024-12-24','shredded','2025-08-17'),(3,'DL09AI9539','2026-07-29','stolen',NULL),(4,'DL04AD8829','2026-07-03','stolen',NULL),(5,'DL01AA8392','2023-08-28','shredded','2023-09-25'),(6,'DL01AA1267','2026-08-02','stolen',NULL),(7,'DL09AI5823','2025-04-03','shredded','2025-06-19'),(8,'DL06AF9470','2026-02-02','shredded','2026-06-13'),(9,'DL05AE0135','2023-08-11','recovered',NULL),(10,'DL10AJ8174','2025-06-02','recovered',NULL),(11,'DL04AD3586','2026-03-11','stolen',NULL),(12,'DL07AG5107','2024-10-02','stolen',NULL),(13,'DL10AJ9693','2025-02-13','recovered',NULL),(14,'DL10AJ7647','2024-03-18','recovered',NULL),(15,'DL01AA2671','2025-08-26','stolen',NULL),(16,'DL10AJ8567','2024-03-29','recovered',NULL),(17,'DL08AH5341','2025-07-12','stolen',NULL),(18,'DL08AH0697','2024-02-01','shredded','2024-08-13'),(19,'DL04AD5509','2026-07-02','stolen',NULL),(20,'DL02AB0328','2025-03-22','shredded','2025-06-01'),(21,'DL01AA7685','2026-01-09','stolen',NULL),(22,'DL09AI9364','2026-04-05','stolen',NULL),(23,'DL01AA2260','2025-10-05','recovered',NULL),(24,'DL05AE6566','2025-12-24','shredded','2026-02-13'),(25,'DL08AH8104','2023-10-27','recovered',NULL),(26,'DL07AG7952','2024-04-07','shredded','2024-10-26'),(27,'DL06AF8878','2026-05-07','recovered',NULL),(28,'DL04AD5697','2024-10-03','recovered',NULL),(29,'DL06AF7125','2024-02-28','shredded','2024-11-21'),(30,'DL08AH8135','2026-02-27','shredded','2026-05-21'),(31,'UK01AA3178',NULL,'stolen',NULL),(32,'UT01AA3278',NULL,'stolen',NULL);
/*!40000 ALTER TABLE `theft_records` ENABLE KEYS */;
UNLOCK TABLES;
SET @@SESSION.SQL_LOG_BIN = @MYSQLDUMP_TEMP_LOG_BIN;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-20 22:49:00
