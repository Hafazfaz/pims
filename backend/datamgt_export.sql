-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: localhost    Database: datamgt_db
-- ------------------------------------------------------
-- Server version	8.0.44

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

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `admin_user_id` int NOT NULL,
  `action` varchar(255) NOT NULL,
  `target_type` varchar(255) NOT NULL,
  `target_id` int NOT NULL,
  `old_value` text,
  `new_value` text,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `ip_address` varchar(45) DEFAULT NULL,
  `device_info` text,
  PRIMARY KEY (`id`),
  KEY `admin_user_id` (`admin_user_id`),
  CONSTRAINT `audit_logs_ibfk_1` FOREIGN KEY (`admin_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_logs`
--

LOCK TABLES `audit_logs` WRITE;
/*!40000 ALTER TABLE `audit_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `audit_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `departments`
--

DROP TABLE IF EXISTS `departments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `departments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `code` varchar(50) NOT NULL,
  `head_id` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `code` (`code`),
  KEY `head_id` (`head_id`),
  CONSTRAINT `departments_ibfk_1` FOREIGN KEY (`head_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `departments`
--

LOCK TABLES `departments` WRITE;
/*!40000 ALTER TABLE `departments` DISABLE KEYS */;
INSERT INTO `departments` VALUES (1,'Test Dept','TD',NULL,'2025-11-22 19:05:37','2025-11-22 19:05:37'),(2,'HR','HR',NULL,'2025-11-24 04:25:55','2025-11-24 04:25:55');
/*!40000 ALTER TABLE `departments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `document_workflow`
--

DROP TABLE IF EXISTS `document_workflow`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `document_workflow` (
  `id` int NOT NULL AUTO_INCREMENT,
  `document_id` int NOT NULL,
  `from_user_id` int NOT NULL,
  `to_user_id` int DEFAULT NULL,
  `action` varchar(50) NOT NULL,
  `comment` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `from_user_id` (`from_user_id`),
  KEY `to_user_id` (`to_user_id`),
  KEY `idx_doc_workflow` (`document_id`),
  CONSTRAINT `document_workflow_ibfk_1` FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`) ON DELETE CASCADE,
  CONSTRAINT `document_workflow_ibfk_2` FOREIGN KEY (`from_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `document_workflow_ibfk_3` FOREIGN KEY (`to_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `document_workflow`
--

LOCK TABLES `document_workflow` WRITE;
/*!40000 ALTER TABLE `document_workflow` DISABLE KEYS */;
/*!40000 ALTER TABLE `document_workflow` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `documents`
--

DROP TABLE IF EXISTS `documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `documents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `title` varchar(255) NOT NULL,
  `content` text,
  `file_path` varchar(255) DEFAULT NULL,
  `type` enum('minute','memo','letter','other') DEFAULT 'other',
  `created_by` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `created_by` (`created_by`),
  KEY `idx_file_documents` (`file_id`),
  CONSTRAINT `documents_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE,
  CONSTRAINT `documents_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `documents`
--

LOCK TABLES `documents` WRITE;
/*!40000 ALTER TABLE `documents` DISABLE KEYS */;
/*!40000 ALTER TABLE `documents` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_access_logs`
--

DROP TABLE IF EXISTS `file_access_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `file_access_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `user_id` int NOT NULL,
  `access_type` varchar(255) NOT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `file_id` (`file_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `file_access_logs_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE,
  CONSTRAINT `file_access_logs_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_access_logs`
--

LOCK TABLES `file_access_logs` WRITE;
/*!40000 ALTER TABLE `file_access_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `file_access_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_activation_requests`
--

DROP TABLE IF EXISTS `file_activation_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `file_activation_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `requestor_id` int NOT NULL,
  `request_reason` text NOT NULL,
  `status` enum('pending','approved','rejected') DEFAULT 'pending',
  `processed_by` int DEFAULT NULL,
  `processed_at` timestamp NULL DEFAULT NULL,
  `rejection_reason` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `file_id` (`file_id`),
  KEY `requestor_id` (`requestor_id`),
  KEY `processed_by` (`processed_by`),
  KEY `idx_activation_status` (`status`),
  CONSTRAINT `file_activation_requests_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE,
  CONSTRAINT `file_activation_requests_ibfk_2` FOREIGN KEY (`requestor_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `file_activation_requests_ibfk_3` FOREIGN KEY (`processed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_activation_requests`
--

LOCK TABLES `file_activation_requests` WRITE;
/*!40000 ALTER TABLE `file_activation_requests` DISABLE KEYS */;
/*!40000 ALTER TABLE `file_activation_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_history`
--

DROP TABLE IF EXISTS `file_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `file_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `user_id` int NOT NULL,
  `action` varchar(255) NOT NULL,
  `details` text,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `file_id` (`file_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `file_history_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE,
  CONSTRAINT `file_history_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_history`
--

LOCK TABLES `file_history` WRITE;
/*!40000 ALTER TABLE `file_history` DISABLE KEYS */;
INSERT INTO `file_history` VALUES (19,22,12,'approved','ok','2025-11-24 11:29:05'),(20,22,12,'approved','ok','2025-11-24 11:29:53');
/*!40000 ALTER TABLE `file_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_number_counters`
--

DROP TABLE IF EXISTS `file_number_counters`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `file_number_counters` (
  `id` int NOT NULL AUTO_INCREMENT,
  `year` int NOT NULL,
  `category` enum('Personal','Policy') NOT NULL,
  `employment_type` enum('Permanent','Locum','Contract','NYSC') DEFAULT NULL,
  `department_code` varchar(50) DEFAULT NULL,
  `last_serial` int DEFAULT '0',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_counter` (`year`,`category`,`employment_type`,`department_code`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_number_counters`
--

LOCK TABLES `file_number_counters` WRITE;
/*!40000 ALTER TABLE `file_number_counters` DISABLE KEYS */;
INSERT INTO `file_number_counters` VALUES (1,2025,'Personal','Permanent',NULL,14,'2025-11-23 20:24:15'),(2,2025,'Personal','Contract',NULL,1,'2025-11-23 11:13:56');
/*!40000 ALTER TABLE `file_number_counters` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_tags`
--

DROP TABLE IF EXISTS `file_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `file_tags` (
  `id` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `tag` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `file_id` (`file_id`),
  CONSTRAINT `file_tags_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_tags`
--

LOCK TABLES `file_tags` WRITE;
/*!40000 ALTER TABLE `file_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `file_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `files`
--

DROP TABLE IF EXISTS `files`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `files` (
  `id` int NOT NULL AUTO_INCREMENT,
  `file_number` varchar(255) NOT NULL,
  `filename` varchar(255) NOT NULL,
  `filepath` varchar(255) NOT NULL,
  `file_category` enum('Personal','Policy') NOT NULL,
  `employment_type` enum('Permanent','Locum','Contract','NYSC') DEFAULT NULL,
  `second_level_auth` tinyint(1) DEFAULT '0',
  `department_id` int DEFAULT NULL,
  `uploader_id` int NOT NULL,
  `owner_id` int DEFAULT NULL,
  `current_location_user_id` int DEFAULT NULL,
  `status` enum('active','archived') DEFAULT 'active',
  `file_state` enum('Inactive','Active','Archived') DEFAULT 'Inactive',
  `progress` enum('In Action','Closed') DEFAULT 'Closed',
  `sensitivity` enum('Normal','Confidential','Restricted') DEFAULT 'Normal',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `expires_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `file_number` (`file_number`),
  KEY `department_id` (`department_id`),
  KEY `uploader_id` (`uploader_id`),
  KEY `idx_file_state` (`file_state`),
  KEY `idx_current_location` (`current_location_user_id`),
  KEY `idx_owner` (`owner_id`),
  CONSTRAINT `files_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE SET NULL,
  CONSTRAINT `files_ibfk_2` FOREIGN KEY (`uploader_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_files_current_location` FOREIGN KEY (`current_location_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_files_owner` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `files`
--

LOCK TABLES `files` WRITE;
/*!40000 ALTER TABLE `files` DISABLE KEYS */;
INSERT INTO `files` VALUES (1,'TD-1','Test Doc','C:\\datamgt\\backend\\uploads\\test_doc.txt','Personal',NULL,0,1,2,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-22 19:05:41','2025-11-22 19:05:41',NULL),(2,'FMCAB/2025/PS/001','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:12:07','2025-11-23 11:12:07',NULL),(3,'FMCAB/2025/PS/002','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:12:16','2025-11-23 11:12:16',NULL),(4,'FMCAB/2025/PS/003','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:12:17','2025-11-23 11:12:17',NULL),(5,'FMCAB/2025/PS/004','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:12:17','2025-11-23 11:12:17',NULL),(6,'FMCAB/2025/PS/005','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:12:17','2025-11-23 11:12:17',NULL),(7,'FMCAB/2025/PS/006','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:12:18','2025-11-23 11:12:18',NULL),(8,'FMCAB/2025/CS/001','USMAN EMPLOYMENT FILE','','Personal','Contract',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:13:56','2025-11-23 11:13:56',NULL),(9,'FMCAB/2025/PS/007','TEST FILE 1763896651','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:17:33','2025-11-23 11:17:33',NULL),(10,'FMCAB/2025/PS/008','TEST FILE 1763896824','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:20:26','2025-11-23 11:20:26',NULL),(11,'FMCAB/2025/PS/009','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',1,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:23:08','2025-11-23 11:23:08',NULL),(12,'FMCAB/2025/PS/010','ABDULLAH EMPLOYMENT FILE','','Personal','Permanent',1,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 11:23:11','2025-11-23 11:23:11',NULL),(13,'FMCAB/2025/PS/011','DOC TEST FILE 1763927709','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 19:55:11','2025-11-23 19:55:11',NULL),(14,'FMCAB/2025/PS/012','DOC TEST FILE 1763927827','','Personal','Permanent',0,NULL,13,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-23 19:57:09','2025-11-23 19:57:09',NULL),(15,'FMCAB/2025/PS/013','DOC TEST FILE 1763927936','','Personal','Permanent',0,NULL,13,9,NULL,'active','Inactive','Closed','Normal','2025-11-23 19:58:58','2025-11-23 19:58:58',NULL),(16,'FMCAB/2025/PS/014','ROUTING TEST FILE','','Personal','Permanent',0,NULL,15,14,NULL,'active','Inactive','Closed','Normal','2025-11-23 20:24:15','2025-11-23 20:24:15',NULL),(17,'HR-1','Document Management System Workflows.pdf','backend\\uploads\\Document_Management_System_Workflows.pdf','Personal',NULL,0,2,11,NULL,NULL,'active','Inactive','Closed','Normal','2025-11-24 04:25:55','2025-11-24 04:25:55',NULL),(22,'HR-2','DMS Executive Dashboards.pdf','backend\\uploads\\DMS_Executive_Dashboards.pdf','Personal',NULL,0,2,11,NULL,NULL,'active','Active','Closed','Normal','2025-11-24 04:46:58','2025-11-24 11:57:19',NULL);
/*!40000 ALTER TABLE `files` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `permissions`
--

DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `permissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `permissions`
--

LOCK TABLES `permissions` WRITE;
/*!40000 ALTER TABLE `permissions` DISABLE KEYS */;
INSERT INTO `permissions` VALUES (1,'create_role','Allows creation of new roles'),(2,'read_role','Allows viewing of roles'),(3,'update_role','Allows updating of existing roles'),(4,'delete_role','Allows deletion of roles'),(5,'read_permission','Allows viewing of permissions'),(6,'create_user','Allows creation of new users'),(7,'read_user','Allows viewing of user details'),(8,'update_user','Allows updating of user details'),(9,'delete_user','Allows deletion of users'),(10,'assign_role','Allows assigning roles to users'),(11,'create_document','Allows creation of new documents'),(12,'read_document','Allows viewing of documents'),(13,'update_document','Allows updating of documents'),(14,'delete_document','Allows deletion of documents'),(15,'approve_document','Allows approving documents'),(16,'read_audit_log','Allows viewing of audit logs'),(17,'manage_departments','Allows managing departments'),(18,'manage_workflows','Allows managing workflows'),(19,'access_control','Allows managing access control settings'),(20,'generate_reports','Allows generating reports'),(21,'create_department','Allows creation of new departments'),(22,'read_department','Allows viewing of departments'),(23,'update_department','Allows updating of existing departments'),(24,'delete_department','Allows deletion of departments'),(25,'reassign_department_head','Allows reassigning department heads'),(26,'read_staff_simple','Allows viewing a simplified list of staff'),(27,'create_file','Allows creation of new files'),(28,'read_file','Allows viewing of files'),(29,'update_file','Allows updating of existing files'),(30,'delete_file','Allows deletion of files'),(31,'view_workflows','Allows viewing workflows'),(32,'approve_workflows','Allows approving workflows'),(33,'create_workflow_template','Allows creation of new workflow templates'),(34,'view_workflow_templates','Allows viewing workflow templates'),(35,'edit_workflow_templates','Allows editing workflow templates'),(36,'delete_workflow_templates','Allows deletion of workflow templates'),(37,'view_reports','Allows viewing reports'),(38,'manage_file_activation','Approve/reject file activation requests'),(39,'deactivate_file','Deactivate active files'),(40,'archive_file','Archive files permanently'),(41,'read_all_files','Read access to all files in the system');
/*!40000 ALTER TABLE `permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_permissions` (
  `role_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`role_id`,`permission_id`),
  KEY `permission_id` (`permission_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_permissions`
--

LOCK TABLES `role_permissions` WRITE;
/*!40000 ALTER TABLE `role_permissions` DISABLE KEYS */;
INSERT INTO `role_permissions` VALUES (2,1),(2,2),(2,3),(2,4),(2,5),(2,6),(2,7),(3,7),(2,8),(2,9),(2,10),(1,11),(2,11),(1,12),(2,12),(3,12),(1,13),(2,13),(3,13),(2,14),(2,15),(3,15),(2,16),(3,16),(2,17),(2,18),(2,19),(2,20),(3,20),(2,21),(2,22),(3,22),(2,23),(2,24),(2,25),(2,26),(3,26),(2,27),(7,27),(2,28),(3,28),(2,29),(2,30),(2,31),(2,32),(2,33),(2,34),(2,35),(2,36),(2,37),(3,37),(7,38),(7,39),(7,40),(7,41);
/*!40000 ALTER TABLE `role_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES (1,'Staff',NULL),(2,'Admin',NULL),(3,'HOD',NULL),(7,'Registry','Registry personnel responsible for file custodianship and activation');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_roles` (
  `user_id` int NOT NULL,
  `role_id` int NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_roles`
--

LOCK TABLES `user_roles` WRITE;
/*!40000 ALTER TABLE `user_roles` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `department_id` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `role_id` int NOT NULL DEFAULT '1',
  `is_active` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  KEY `fk_role` (`role_id`),
  CONSTRAINT `fk_role` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (2,'admin','scrypt:32768:8:1$EQtWD1K3ed8IlnhW$7bc6e7d473d3ed445bf814f4eb1f9ee62dc726c7a801e4bc7fc746404074e58346d78432253b7b09bcf3babdea7d55808350ac71bc7ae77306aa3ea5badaca77','admin@example.com',NULL,'2025-11-03 19:34:36','2025-11-21 05:12:03',2,1),(5,'Hafazfaz','scrypt:32768:8:1$2WF4MbFO4Xkb93Hc$5f5db4b5bb98b4eee10826dec7aa52cc58e9f64fbf1d86fbdd7fc545973f334bde780f281e1692105e2246de489d0f4c6ccb1a279226ebc608550d6674b1b5b0','Hafazfaz@gmail.com',NULL,'2025-11-04 14:02:45','2025-11-04 14:02:45',2,1),(7,'Kamsid','scrypt:32768:8:1$EhFWdnaqT9WrISYk$46041fb0916511c4deede7f9095e725483295ddde2eca1d456a40d50297a0f34ad52726f4bc266fbf31079adf7b30228c6146c5a9a6bec9cac89a367d1d2adbc','kamsid@gmail.com',NULL,'2025-11-04 22:03:05','2025-11-04 22:03:05',2,1),(9,'testuser','scrypt:32768:8:1$f71skj5iEkPDWaXq$a7f5666a62d175496ef6151b90882cfcf9b2740715da79dfdcef1e980063a77f453455f79049e8e8d958dab67a4e7a6a7df4893bcfd5c058b0d23170214abee3','testuser@gmail.com',NULL,'2025-11-06 09:16:18','2025-11-23 11:20:04',1,1),(11,'testuser2','scrypt:32768:8:1$BEnbruvnnnh9HML6$2002cc27dcf8716560e87297297cea466d7b27a7543ce7de7b5fcffbdd6266971550215b5ac9b83b52879935d86e0ec487ea92ce4586ce4bbb341ea62874821f','testuser@co.za',NULL,'2025-11-23 05:17:30','2025-11-23 05:17:30',1,1),(12,'hod','scrypt:32768:8:1$Pn9bdCXwzj7JDSlr$50166678d3a615fae092db501b5061b2f0f2968b8a9990a59899b657944a8fa09a80ade4a90c61af40ea7fcadda6fa6d5e65ff1993a92481bb1b04603d704af7','hod@co.za',NULL,'2025-11-23 05:40:46','2025-11-23 05:40:46',3,1),(13,'registry_officer','scrypt:32768:8:1$Vj8kKhCJGtrasZc6$3986a090205e6e4708492210c165813d5e6cb7149aaae2849dd2470cb03585fa7bfed2093eb4d808df62375e4dd8a31d748cdc8b68944f54eea5ff7ff6dd088f','registry@fmcabuja.gov.ng',NULL,'2025-11-23 10:26:17','2025-11-23 10:26:17',7,1),(14,'staff_user','scrypt:32768:8:1$G9mxjklZRsC0Pbt8$5d91fc7d443c6932acaf5dfff9649b948470e128af26f6f049fb47dc1ef058a985f176fd2b2a3e4dd86228bfd1eef57f2ada46c932b3cfbcc952f23225cf33c5','staff@test.com',1,'2025-11-23 20:23:11','2025-11-23 20:23:11',1,1),(15,'registry_user','scrypt:32768:8:1$gZQq5KIcuiyo4RcD$e7c95044167515b88bc9e57e9ab57a73f681dda065e15d4571c034d302f82720c0cbe307e75c00afc1a410991c2b91858d94af75dd04eabfe5165ec19d7b64cf','registry@test.com',NULL,'2025-11-23 20:23:12','2025-11-23 20:23:12',7,1),(16,'hod_user','scrypt:32768:8:1$jpk8tKgizXWQrq86$06b754f786c119f3176f5a71b7c29007215ca6d56a19b4e71391feed67ce7165e67ced6bd479e9ddca9c52f47a74262bb494805da29ef3420ee2fc0c652f01a8','hod@test.com',1,'2025-11-23 20:23:12','2025-11-23 20:23:12',3,1);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `workflow_steps`
--

DROP TABLE IF EXISTS `workflow_steps`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `workflow_steps` (
  `id` int NOT NULL AUTO_INCREMENT,
  `template_id` int NOT NULL,
  `step_order` int NOT NULL,
  `role_id` int NOT NULL,
  `action_type` enum('approval','review') DEFAULT 'approval',
  PRIMARY KEY (`id`),
  KEY `template_id` (`template_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `workflow_steps_ibfk_1` FOREIGN KEY (`template_id`) REFERENCES `workflow_templates` (`id`) ON DELETE CASCADE,
  CONSTRAINT `workflow_steps_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `workflow_steps`
--

LOCK TABLES `workflow_steps` WRITE;
/*!40000 ALTER TABLE `workflow_steps` DISABLE KEYS */;
INSERT INTO `workflow_steps` VALUES (1,2,1,2,'approval'),(2,2,2,1,'approval');
/*!40000 ALTER TABLE `workflow_steps` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `workflow_templates`
--

DROP TABLE IF EXISTS `workflow_templates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `workflow_templates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` text,
  `department_id` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `department_id` (`department_id`),
  CONSTRAINT `workflow_templates_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `workflow_templates`
--

LOCK TABLES `workflow_templates` WRITE;
/*!40000 ALTER TABLE `workflow_templates` DISABLE KEYS */;
INSERT INTO `workflow_templates` VALUES (2,'Test Workflow','A test workflow',1,'2025-11-22 19:05:39');
/*!40000 ALTER TABLE `workflow_templates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `workflows`
--

DROP TABLE IF EXISTS `workflows`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `workflows` (
  `id` int NOT NULL AUTO_INCREMENT,
  `file_id` int NOT NULL,
  `sender_id` int NOT NULL,
  `receiver_id` int NOT NULL,
  `status` enum('pending','approved','rejected') DEFAULT 'pending',
  `comment` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `file_id` (`file_id`),
  KEY `sender_id` (`sender_id`),
  KEY `receiver_id` (`receiver_id`),
  CONSTRAINT `workflows_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE CASCADE,
  CONSTRAINT `workflows_ibfk_2` FOREIGN KEY (`sender_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `workflows_ibfk_3` FOREIGN KEY (`receiver_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `workflows`
--

LOCK TABLES `workflows` WRITE;
/*!40000 ALTER TABLE `workflows` DISABLE KEYS */;
INSERT INTO `workflows` VALUES (1,17,11,16,'pending',NULL,'2025-11-24 04:25:55','2025-11-24 04:25:55'),(2,22,11,12,'approved','ok','2025-11-24 04:46:58','2025-11-24 11:29:53');
/*!40000 ALTER TABLE `workflows` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-11-24 13:34:42
