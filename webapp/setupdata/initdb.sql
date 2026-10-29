CREATE DATABASE IF NOT EXISTS `bsn_db` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `bsn_db`;

CREATE TABLE IF NOT EXISTS `applicazione_descrittore` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `app_id` varchar(255) NOT NULL,
  `last_updated` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `parametri` longtext DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_applicazione_descrittore_app_id` (`app_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `utente` (
  `id_utente` bigint NOT NULL AUTO_INCREMENT,
  `password` varchar(255) NOT NULL,
  `ruolo` enum('USER_DEV','USER_MED') NOT NULL,
  `username` varchar(50) NOT NULL,
  PRIMARY KEY (`id_utente`),
  UNIQUE KEY `uk_utente_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `persona` (
  `id_persona` bigint NOT NULL AUTO_INCREMENT,
  `cognome` varchar(100) NOT NULL,
  `data_nascita` date DEFAULT NULL,
  `nome` varchar(100) NOT NULL,
  `note` text DEFAULT NULL,
  PRIMARY KEY (`id_persona`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `tipo_campagna` (
  `id_tipo` bigint NOT NULL AUTO_INCREMENT,
  `codice` varchar(30) NOT NULL,
  `descrizione` varchar(100) NOT NULL,
  `script_filename` varchar(255) NOT NULL,
  PRIMARY KEY (`id_tipo`),
  UNIQUE KEY `uk_tipo_campagna_codice` (`codice`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `sensore` (
  `id_sensore` bigint NOT NULL AUTO_INCREMENT,
  `codice` varchar(50) NOT NULL,
  `nome` varchar(100) NOT NULL,
  `protocollo` enum('ANT','BLE','WIFI') NOT NULL,
  `tipo` varchar(50) NOT NULL,
  `eliminato` bit(1) NOT NULL DEFAULT b'0',
  PRIMARY KEY (`id_sensore`),
  UNIQUE KEY `uk_sensore_codice` (`codice`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `database_config` (
  `id_database` bigint NOT NULL AUTO_INCREMENT,
  `db_name` varchar(100) NOT NULL,
  `host` varchar(255) NOT NULL,
  `nome` varchar(100) NOT NULL,
  PRIMARY KEY (`id_database`),
  UNIQUE KEY `uk_database_config_nome` (`nome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `setting` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `key_name` varchar(100) NOT NULL,
  `value` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_setting_key_name` (`key_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `campagna` (
  `id_campagna` bigint NOT NULL AUTO_INCREMENT,
  `connettivita` enum('ANT','BLE','WIFI') DEFAULT NULL,
  `data_fine` datetime(6) DEFAULT NULL,
  `data_inizio` datetime(6) NOT NULL,
  `db_host` varchar(255) DEFAULT NULL,
  `db_name` varchar(255) DEFAULT NULL,
  `durata` int DEFAULT NULL,
  `frequenza` int DEFAULT NULL,
  `nome` varchar(150) NOT NULL,
  `note` text DEFAULT NULL,
  `script_filename` varchar(255) DEFAULT NULL,
  `stato` enum('AVVIO_FALLITO','AVVIO_IN_CORSO','IN_CORSO','TERMINATA') NOT NULL,
  `id_persona` bigint NOT NULL,
  `id_utente_creatore` bigint NOT NULL,
  PRIMARY KEY (`id_campagna`),
  KEY `idx_campagna_persona` (`id_persona`),
  KEY `idx_campagna_utente_creatore` (`id_utente_creatore`),
  CONSTRAINT `fk_campagna_persona` FOREIGN KEY (`id_persona`) REFERENCES `persona` (`id_persona`),
  CONSTRAINT `fk_campagna_utente` FOREIGN KEY (`id_utente_creatore`) REFERENCES `utente` (`id_utente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `campagna_tipo` (
  `id_campagna` bigint NOT NULL,
  `id_tipo` bigint NOT NULL,
  PRIMARY KEY (`id_campagna`, `id_tipo`),
  KEY `idx_campagna_tipo_tipo` (`id_tipo`),
  CONSTRAINT `fk_campagna_tipo_campagna` FOREIGN KEY (`id_campagna`) REFERENCES `campagna` (`id_campagna`) ON DELETE CASCADE,
  CONSTRAINT `fk_campagna_tipo_tipo` FOREIGN KEY (`id_tipo`) REFERENCES `tipo_campagna` (`id_tipo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `campagna_sensore` (
  `attivo` bit(1) NOT NULL,
  `protocollo` enum('ANT','BLE','WIFI') NOT NULL,
  `id_campagna` bigint NOT NULL,
  `id_sensore` bigint NOT NULL,
  `location` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id_campagna`, `id_sensore`),
  KEY `idx_campagna_sensore_sensore` (`id_sensore`),
  CONSTRAINT `fk_campagna_sensore_campagna` FOREIGN KEY (`id_campagna`) REFERENCES `campagna` (`id_campagna`) ON DELETE CASCADE,
  CONSTRAINT `fk_campagna_sensore_sensore` FOREIGN KEY (`id_sensore`) REFERENCES `sensore` (`id_sensore`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE `campagna_sensore`
  ADD COLUMN IF NOT EXISTS `location` varchar(255) DEFAULT NULL;

CREATE TABLE IF NOT EXISTS `sensore_misura` (
  `id_sensore` bigint NOT NULL,
  `misura` enum('ACCELEROMETRO','GIROSCOPIO','MAGNETOMETRO') NOT NULL,
  PRIMARY KEY (`id_sensore`, `misura`),
  CONSTRAINT `fk_sensore_misura_sensore` FOREIGN KEY (`id_sensore`) REFERENCES `sensore` (`id_sensore`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `sensore_protocollo` (
  `id_sensore` bigint NOT NULL,
  `protocollo` enum('ANT','BLE','WIFI') NOT NULL,
  PRIMARY KEY (`id_sensore`, `protocollo`),
  CONSTRAINT `fk_sensore_protocollo_sensore` FOREIGN KEY (`id_sensore`) REFERENCES `sensore` (`id_sensore`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
