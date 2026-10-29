USE `bsn_db`;

INSERT INTO `persona` (`id_persona`, `cognome`, `data_nascita`, `nome`, `note`) VALUES
(1, 'Gianchino', '1997-05-02', 'Francesco', ''),
(2, 'Rossi', '2026-03-13', 'Mario', ''),
(3, 'Miele', '2026-03-13', 'Antonio', ''),
(4, 'Bolchini', '2026-03-11', 'Cristiana', '')
ON DUPLICATE KEY UPDATE
  `cognome` = VALUES(`cognome`),
  `data_nascita` = VALUES(`data_nascita`),
  `nome` = VALUES(`nome`),
  `note` = VALUES(`note`);

INSERT INTO `sensore` (`id_sensore`, `codice`, `nome`, `protocollo`, `tipo`, `eliminato`) VALUES
(12, 'IMUXEXA', 'IMUXEXA', 'BLE', 'nano 33 BLE SENSE REV 2', b'0'),
(13, 'IMU3C95', 'IMU3C95', 'BLE', 'nano 33 BLE SENSE REV 2', b'0'),
(15, 'IMU5E0C', 'IMU5E0C', 'BLE', 'nano 33 BLE SENSE REV 2', b'0'),
(16, 'B0:B2:1C:4A:00:38', 'IMU7811', 'WIFI', 'nano 33 IoT', b'0'),
(17, 'IMU373B', 'IMU373B', 'BLE', 'nano 33 BLE', b'0'),
(18, 'IMU5B35', 'IMU5B35', 'BLE', 'nano 33 BLE SENSE', b'0'),
(19, 'IMUX7X7', 'IMUX7X7', 'BLE', 'nano 33 BLE', b'0'),
(20, 'IMUFB9D', 'IMUFB9D', 'BLE', 'BIO', b'0'),
(21, 'IMUEDF1', 'IMUEDF1', 'BLE', 'BIO', b'0'),
(22, 'IMU3F4B', 'IMU3F4B', 'BLE', 'BIO', b'1'),
(23, 'IMU36C9', 'IMU36C9', 'BLE', 'BIO', b'1'),
(24, 'IMU1747', 'IMU1747', 'BLE', 'BIO', b'0')
ON DUPLICATE KEY UPDATE
  `nome` = VALUES(`nome`),
  `protocollo` = VALUES(`protocollo`),
  `tipo` = VALUES(`tipo`),
  `eliminato` = VALUES(`eliminato`);

INSERT IGNORE INTO `sensore_misura` (`id_sensore`, `misura`) VALUES
(12, 'ACCELEROMETRO'), (12, 'GIROSCOPIO'), (12, 'MAGNETOMETRO'),
(13, 'ACCELEROMETRO'), (13, 'GIROSCOPIO'), (13, 'MAGNETOMETRO'),
(15, 'ACCELEROMETRO'), (15, 'GIROSCOPIO'), (15, 'MAGNETOMETRO'),
(16, 'ACCELEROMETRO'), (16, 'GIROSCOPIO'),
(17, 'ACCELEROMETRO'), (17, 'GIROSCOPIO'), (17, 'MAGNETOMETRO'),
(18, 'ACCELEROMETRO'), (18, 'GIROSCOPIO'), (18, 'MAGNETOMETRO'),
(19, 'ACCELEROMETRO'), (19, 'GIROSCOPIO'), (19, 'MAGNETOMETRO'),
(20, 'ACCELEROMETRO'), (20, 'GIROSCOPIO'), (20, 'MAGNETOMETRO'),
(21, 'ACCELEROMETRO'), (21, 'GIROSCOPIO'), (21, 'MAGNETOMETRO'),
(22, 'ACCELEROMETRO'), (22, 'GIROSCOPIO'), (22, 'MAGNETOMETRO'),
(23, 'ACCELEROMETRO'), (23, 'GIROSCOPIO'), (23, 'MAGNETOMETRO'),
(24, 'ACCELEROMETRO'), (24, 'GIROSCOPIO'), (24, 'MAGNETOMETRO');

INSERT IGNORE INTO `sensore_protocollo` (`id_sensore`, `protocollo`) VALUES
(12, 'BLE'), (13, 'BLE'), (15, 'BLE'), (16, 'WIFI'), (17, 'BLE'),
(18, 'BLE'), (19, 'BLE'), (20, 'BLE'), (21, 'BLE'), (22, 'BLE'),
(23, 'BLE'), (24, 'BLE');
