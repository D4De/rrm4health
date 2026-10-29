package it.polimi.bsnwebapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Entry point di Spring Boot per la BSN WebApp.
 * Avvia il contesto applicativo, abilita scheduling e async per i task che gestiscono campagne e script.
 * La classe non contiene logica di business: delega tutto ai bean configurati nel container.
 */

@SpringBootApplication
@EnableScheduling //serve per script python insieme a EnableAsync
@EnableAsync //permette di avere thread separati per ogni sensore
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

}
