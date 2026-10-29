package it.polimi.bsnwebapp.Controller.web;

import it.polimi.bsnwebapp.DTO.request.RegisterRequest;
import it.polimi.bsnwebapp.Service.AuthService;
import it.polimi.bsnwebapp.exception.ConflictException;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

/**
 * Controller MVC per le pagine di autenticazione.
 * Espone le view di login e registrazione e gestisce il submit del form di registrazione.
 * Usa AuthService per creare nuovi utenti e mostra eventuali errori di validazione.
 */

@Controller
@RequiredArgsConstructor
public class AuthPageController {

    private final AuthService authService;

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/register")
    public String register(Model model) {
        model.addAttribute("registerRequest", new RegisterRequest());
        return "register";
    }

    @PostMapping("/register")
    public String doRegister(@Valid @ModelAttribute("registerRequest") RegisterRequest request,
                             BindingResult bindingResult,
                             Model model) {

        if (bindingResult.hasErrors()) return "register";

        try {
            authService.registrazioneUtente(request);
        } catch (ConflictException e) {
            model.addAttribute("errorMessage", "Username già registrato");
            return "register";
        }

        return "redirect:/login?registered=true";
    }
}
