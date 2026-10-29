USE `bsn_db`;

DELETE FROM `database_config`;
ALTER TABLE `database_config` AUTO_INCREMENT = 1;
INSERT INTO `database_config` (`id_database`, `db_name`, `host`, `nome`) VALUES
(1, 'bsn_timeseries', 'localhost:8086', 'Influx locale');

DELETE FROM `setting` WHERE `id` IN (1, 2) OR `key_name` IN ('rrm.ip', 'rrm.port');
ALTER TABLE `setting` AUTO_INCREMENT = 1;
INSERT INTO `setting` (`id`, `key_name`, `value`) VALUES
(1, 'rrm.ip', '127.0.0.1'),
(2, 'rrm.port', '41798');
