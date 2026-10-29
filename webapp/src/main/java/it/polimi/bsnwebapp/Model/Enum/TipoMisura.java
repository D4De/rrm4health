package it.polimi.bsnwebapp.Model.Enum;

/**
 * Tipologie di misura supportate dai sensori.
 * Ogni misura espone una label leggibile e l'unita di misura standard.
 */
public enum TipoMisura {
    ACCELEROMETRO("Accelerometro", "m/s^2"),
    GIROSCOPIO("Giroscopio", "deg/s"),
    MAGNETOMETRO("Magnetometro", "uT");

    private final String label;
    private final String unita;

    TipoMisura(String label, String unita) {
        this.label = label;
        this.unita = unita;
    }

    public String getLabel() {
        return label;
    }

    public String getUnita() {
        return unita;
    }

    public String getLabelConUnita() {
        return label + " (" + unita + ")";
    }
}
