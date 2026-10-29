package it.polimi.bsnwebapp.Model.Entities;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Entity JPA che rappresenta una configurazione database selezionabile dall'admin.
 * Contiene nome descrittivo, indirizzo host e nome del database.
 * Viene usata per precompilare i parametri di salvataggio nelle campagne.
 */
@Entity
@Table(name = "database_config")
@Getter
@Setter
@NoArgsConstructor
public class DatabaseConfig {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id_database", updatable = false, nullable = false)
    private Long id;

    @Column(name = "nome", nullable = false, unique = true, length = 100)
    private String nome;

    @Column(name = "host", nullable = false, length = 255)
    private String host;

    @Column(name = "db_name", nullable = false, length = 100)
    private String dbName;

    public DatabaseConfig(String nome, String host, String dbName) {
        this.nome = nome;
        this.host = host;
        this.dbName = dbName;
    }
}
