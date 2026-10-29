-- Add new Campagna status values to the enum.
-- Run against the bsn_db schema.

ALTER TABLE campagna
  MODIFY COLUMN stato ENUM('AVVIO_IN_CORSO','IN_CORSO','AVVIO_FALLITO','TERMINATA') NOT NULL;
