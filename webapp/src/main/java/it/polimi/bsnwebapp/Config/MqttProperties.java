package it.polimi.bsnwebapp.Config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Mappa le proprieta di configurazione MQTT (prefisso app.mqtt).
 * Contiene broker, topic, clientId, credenziali e QoS, oltre al flag enabled.
 * Viene iniettata in MqttSseService per connettersi al broker e sottoscrivere i topic.
 */

@Getter
@Setter
@Component

//@ConfigurationProperties mappa un blocco di configurazione (es. app.mqtt.*) dentro una classe Java.
//       - prende le property con un prefisso (app.mqtt)
//       - riempie i campi della classe con quei valori
//       - se una property manca, usa il default del campo
@ConfigurationProperties(prefix = "app.mqtt")
public class MqttProperties {
    private boolean enabled = true;
    private String broker = "tcp://131.175.120.117:1883"; //valori di default se non presenti in application.properties
    private String topic = "aaac/campaign/#";
    private String clientId = "bsn-webapp-sse";
    private String username;
    private String password;
    private int qos = 0;
}
