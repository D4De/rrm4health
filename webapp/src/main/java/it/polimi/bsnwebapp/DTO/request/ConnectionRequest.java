package it.polimi.bsnwebapp.DTO.request;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * DTO di richiesta per la connessione a RRM Global.
 * Contiene indirizzo IP e porta per la comunicazione ZeroMQ.
 */
@Getter
@Setter
@AllArgsConstructor
@NoArgsConstructor
public class ConnectionRequest {
    
    @NotBlank(message = "L'indirizzo IP non può essere vuoto")
    private String ip;
    
    @Min(value = 1024, message = "La porta deve essere >= 1024")
    @Max(value = 65535, message = "La porta deve essere <= 65535")
    private Integer port;
}
