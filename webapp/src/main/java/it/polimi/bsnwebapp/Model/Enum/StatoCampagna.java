package it.polimi.bsnwebapp.Model.Enum;

/**
 * Enum che descrive gli stati del ciclo di vita di una campagna.
 * Valori disponibili: AVVIO_IN_CORSO, IN_CORSO, AVVIO_FALLITO, TERMINATA.
 * Usato in: monitoraggio, dashboard e watchdog.
 */

public enum StatoCampagna {
    AVVIO_IN_CORSO,
    IN_CORSO,
    AVVIO_FALLITO,
    TERMINATA
}
