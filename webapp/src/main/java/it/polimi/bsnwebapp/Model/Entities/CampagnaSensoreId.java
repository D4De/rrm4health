package it.polimi.bsnwebapp.Model.Entities;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.*;

import java.io.Serializable;
import java.util.Objects;

/**
 * Chiave primaria composta per {@link CampagnaSensore}.
 * Incapsula gli id di campagna e sensore e viene usata come {@code @EmbeddedId}.
 * Necessaria per garantire identita coerente e caching corretto in JPA/Hibernate.
 */

@Embeddable
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@EqualsAndHashCode //per le chiavi composte
public class CampagnaSensoreId implements Serializable {

    @Column(name = "id_campagna")
    private Long campagnaId;

    @Column(name = "id_sensore")
    private Long sensoreId;

}
