package it.polimi.bsnwebapp.Config;

import it.polimi.bsnwebapp.Repository.UtenteRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * Configurazione applicativa di base per l'autenticazione.
 * Espone i bean usati da Spring Security: UserDetailsService su UtenteRepository, PasswordEncoder BCrypt,
 * AuthenticationProvider DAO e AuthenticationManager.
 * Questa configurazione e' condivisa sia dalle API REST sia dalle pagine web protette.
 */

@Configuration
@RequiredArgsConstructor
public class ApplicationConfig {
    private final UtenteRepository UtenteRepository;

    /**
     * Bean per il servizio di gestione dei dettagli dell'utente.
     * Dato un username, viene preso l'utente dal database.
     * @return Un'istanza di UserDetailsService che carica i dettagli dell'utente.
     */
    @Bean
    public UserDetailsService userDetailsService() {
        return username -> UtenteRepository.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException("Utente non trovato"));
    }

    /**
     * Bean che specifica quale metodo utilizzare per codificare la password.
     * @return Un'istanza dell'encoder.
     */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    /**
     * Bean per la configurazione del provider di autenticazione.
     * Include il servizio di gestione dei dettagli dell'utente e il codificatore di password.
     * @return Un'istanza di AuthenticationProvider configurata.
     */
    @Bean
    public AuthenticationProvider authenticationProvider() {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        // Specifica il service da utilizzare per prendere i dati dell'utente dal db.
        provider.setUserDetailsService(userDetailsService());
        // Specifica il metodo per codificare la password.
        provider.setPasswordEncoder(passwordEncoder());
        return provider;
    }

    /**
     * Bean che specifica come gestire l'autenticazione.
     * @param authenticationConfiguration Configurazione dell'AuthenticationManager.
     * @return Un'istanza dell'AuthenticationManager.
     * @throws Exception Eccezione generale che può essere lanciata durante la configurazione.
     */
    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration authenticationConfiguration) throws Exception {
        return authenticationConfiguration.getAuthenticationManager();
    }
}