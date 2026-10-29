package it.polimi.bsnwebapp.Model.Entities;

import it.polimi.bsnwebapp.Model.Enum.RuoloUtente;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;

/**
 * Entity JPA che rappresenta un utente applicativo.
 * Implementa {@link UserDetails} per integrare Spring Security con ruoli e credenziali.
 * Mappa la tabella {@code utente} e fornisce le authority a partire dal ruolo associato.
 */

@Entity
@Table(name = "utente")
@Getter
@Setter
@NoArgsConstructor //crea un costruttore senza parametri, richiesto da JPA per creare le istanze delle entità
public class Utente implements UserDetails {

  @Id                   //Dico che questa è la Chiave Primaria
  @GeneratedValue(strategy = GenerationType.IDENTITY)   //Dico che è AUTO_INCREMENT
  @Column(name = "id_utente", updatable = false, nullable = false)
    private Long id;  //Long è una classe wrapper di long e può essere null, a differenza del tipo primitivo long

    @Column (name = "username", nullable = false, unique = true, length = 50)
    private String username;

    @Column(name = "password", nullable = false, length = 255)
    private String password;

    @Enumerated(EnumType.STRING)
    @Column (name = "ruolo", nullable = false)
    private RuoloUtente ruolo;

    public Utente(String username, String password, RuoloUtente ruolo){
        this.username = username;
        this.password = password;
        this.ruolo = ruolo;
    }

    @Override
    public boolean isAccountNonExpired() {
        return UserDetails.super.isAccountNonExpired();
    }

    @Override
    public boolean isAccountNonLocked() {
        return UserDetails.super.isAccountNonLocked();
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return UserDetails.super.isCredentialsNonExpired();
    }

    @Override
    public boolean isEnabled() {
        return UserDetails.super.isEnabled();
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        // Ritorna una lista contenente il ruolo dell'utente come SimpleGrantedAuthority
        return List.of(new SimpleGrantedAuthority(ruolo.name()));
    }

    @Override
    public String toString(){
        return "Utente{id=" + id + ", username=" + username + ", ruolo=" + ruolo + "}";
    }

}
