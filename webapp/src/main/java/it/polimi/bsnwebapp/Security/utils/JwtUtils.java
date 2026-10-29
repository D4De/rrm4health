package it.polimi.bsnwebapp.Security.utils;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.io.Decoders;
import io.jsonwebtoken.security.Keys;
import lombok.NonNull;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;
import io.jsonwebtoken.Claims;

import java.security.Key;
import java.util.Date;
import java.util.HashMap;
import java.util.function.Function;

/**
 * Utility per la gestione dei token JWT.
 * Genera token firmati con la chiave configurata, estrae claim, verifica scadenza e validita per un utente.
 * Usata da AuthService in fase di login e dal filtro JWT per la validazione delle richieste.
 */

@Service
public class JwtUtils {

    @Value("${security.secret-key}")
    private String secretKey;

    /**
     * Estrae l'username dal token JWT.
     * @param token Il token JWT.
     * @return L'username estratto dal token.
     */
    public String extractUsername(String token) {
        return extractClaim(token, Claims::getSubject);
    }

    /**
     * Estrae un determinato claim dal token JWT utilizzando il resolver fornito.
     * @param token Il token JWT.
     * @param claimsResolver Funzione per risolvere il claim.
     * @param <T> Tipo del claim.
     * @return Il claim estratto.
     */
    public <T> T extractClaim(String token, Function<Claims, T> claimsResolver) {
        return claimsResolver.apply(extractAllClaims(token));
    }

    /**
     * Estrae tutti i claim dal token JWT.
     * @param token Il token JWT.
     * @return I claim estratti dal token.
     */
    private Claims extractAllClaims(String token) {
        return Jwts.parserBuilder().setSigningKey(getSigningKey()).build().parseClaimsJws(token).getBody();
    }

    /**
     * Restituisce la chiave di firma utilizzata per firmare il token JWT.
     * @return La chiave di firma.
     */
    private @NonNull Key getSigningKey() {
        byte[] keyBytes = Decoders.BASE64.decode(secretKey);
        return Keys.hmacShaKeyFor(keyBytes);
    }

    /**
     * Genera un token JWT per l'utente specificato.
     * @param userDetails I dettagli dell'utente.
     * @return Il token JWT generato.
     */
    public String generateToken(UserDetails userDetails) {
        return generateToken(new HashMap<>(), userDetails);
    }

    /**
     * Genera un token JWT con claim aggiuntivi per l'utente specificato.
     * @param extraClaims I claim aggiuntivi.
     * @param userDetails I dettagli dell'utente.
     * @return Il token JWT generato.
     */
    public String generateToken(HashMap<String, Object> extraClaims, UserDetails userDetails) {
        return Jwts.builder()
                .setClaims(extraClaims)
                .setSubject(userDetails.getUsername())
                .setIssuedAt(new Date(System.currentTimeMillis()))
                .setExpiration(new Date(System.currentTimeMillis() + 1000 * 60 * 60 * 10)) // 10 hours
                .signWith(getSigningKey())
                .compact();
    }

    /**
     * Controlla se il token JWT è scaduto.
     * @param token Il token JWT.
     * @return True se il token è scaduto, altrimenti False.
     */
    public boolean isTokenExpired(String token) {
        return extractExpiration(token).before(new Date());
    }

    /**
     * Estrae la data di scadenza dal token JWT.
     * @param token Il token JWT.
     * @return La data di scadenza del token.
     */
    private Date extractExpiration(String token) {
        return extractClaim(token, Claims::getExpiration);
    }

    /**
     * Controlla se il token JWT è valido per l'utente specificato.
     * @param token Il token JWT.
     * @param userDetails I dettagli dell'utente.
     * @return True se il token è valido, altrimenti False.
     */
    public boolean isTokenValid(String token, @NonNull UserDetails userDetails) {
        final String username = extractUsername(token);
        return (username.equals(userDetails.getUsername()) && !isTokenExpired(token));
    }
}
