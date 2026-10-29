package it.polimi.bsnwebapp.Security.filter;

import it.polimi.bsnwebapp.Security.utils.JwtUtils;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Filtro JWT eseguito una sola volta per richiesta.
 * Legge l'header Authorization, valida il token tramite JwtUtils, carica l'utente e popola il SecurityContext.
 * Se il token e' assente o invalido, lascia proseguire la richiesta senza autenticazione.
 */

@Component
@RequiredArgsConstructor
public class JwtAuthFilter extends OncePerRequestFilter {

    private final JwtUtils jwtUtils;
    private final UserDetailsService userDetailsService;

    /**
     * Metodo che viene eseguito per ogni richiesta per verificare il token JWT.
     * @param request La richiesta HTTP.
     * @param response La risposta HTTP.
     * @param filterChain La catena di filtri.
     * @throws ServletException Se si verifica un errore generico su una servlet.
     * @throws IOException Se si verifica un problema di input/output.
     */
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        final String authHeader = request.getHeader("Authorization");
        final String username;
        final String jwt;

        // Se l'header Authorization non contiene un token JWT valido, continua con la catena di filtri.
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            filterChain.doFilter(request, response);
            return;
        }

        // Estrae il token JWT dall'header Authorization.
        jwt = authHeader.substring("Bearer ".length());
        username = jwtUtils.extractUsername(jwt);

        // Se il token è presente e l'utente non è ancora autenticato, verifica il token.
        if (username != null && SecurityContextHolder.getContext().getAuthentication() == null) {
            UserDetails userDetails = this.userDetailsService.loadUserByUsername(username);

            // Se il token è valido, crea un oggetto di autenticazione e lo imposta nel contesto di sicurezza.
            if (jwtUtils.isTokenValid(jwt, userDetails)) {
                UsernamePasswordAuthenticationToken authToken = new UsernamePasswordAuthenticationToken(
                        userDetails, null, userDetails.getAuthorities());
                authToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
                SecurityContextHolder.getContext().setAuthentication(authToken);
            }
        }

        // Continua con la catena di filtri.
        filterChain.doFilter(request, response);
    }
}
