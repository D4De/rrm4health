package it.polimi.bsnwebapp.Controller.web;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

import it.polimi.bsnwebapp.DTO.response.CampagnaResponse;
import it.polimi.bsnwebapp.DTO.response.TipoCampagnaResponse;
import it.polimi.bsnwebapp.Model.Entities.Utente;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;
import it.polimi.bsnwebapp.Service.ApplicazioneDescrittoreService;
import it.polimi.bsnwebapp.Service.CampagnaService;
import it.polimi.bsnwebapp.Service.DatabaseConfigService;
import it.polimi.bsnwebapp.Service.PersonaService;
import it.polimi.bsnwebapp.Service.ScriptCatalogService;
import it.polimi.bsnwebapp.Service.SensoreService;
import it.polimi.bsnwebapp.Service.TipoCampagnaService;
import lombok.RequiredArgsConstructor;

/**
 * Controller MVC per la home e le pagine campagne.
 * Carica campagne, persone, sensori e tipi campagna per comporre la UI e i frammenti HTMX.
 * Gestisce anche i frammenti parziali per refresh dinamici della lista campagne.
 */

@Controller
@RequiredArgsConstructor
public class HomePageController {

        @GetMapping("/api/v1/sensori/disponibili")
        @org.springframework.web.bind.annotation.ResponseBody
        public java.util.List<it.polimi.bsnwebapp.DTO.response.SensoreResponse> getSensoriDisponibili() {
            return sensoreService.listaSensoriDisponibili();
        }
    @org.springframework.beans.factory.annotation.Autowired
    private it.polimi.bsnwebapp.Service.RrmConnectionService rrmConnectionService;
    @org.springframework.beans.factory.annotation.Autowired
    private it.polimi.bsnwebapp.Service.SettingApplicationService settingApplicationService;

    private final CampagnaRepository campagnaRepository;
    private final CampagnaService campagnaService;
    private final PersonaService personaService;
    private final TipoCampagnaService tipoCampagnaService;
    private final SensoreService sensoreService;
    private final ScriptCatalogService scriptCatalogService;
    private final ApplicazioneDescrittoreService applicazioneDescrittoreService;
    private final DatabaseConfigService databaseConfigService;
    private static final int CAMPAGNE_PAGE_SIZE = 10;

    @GetMapping("/")
    public String home(Model model, Authentication authentication, @AuthenticationPrincipal Utente utente) {

        List<CampagnaResponse> campagneHome = campagnaRepository
            .findHomeCampaigns(List.of(StatoCampagna.AVVIO_IN_CORSO, StatoCampagna.IN_CORSO))
                .stream()
                .map(campagnaService::convertToResponse)
                .collect(Collectors.toList());
        model.addAttribute("campagneHome", campagneHome);

        model.addAttribute("persone", personaService.getAllPersone());
        List<TipoCampagnaResponse> tipiCampagna = tipoCampagnaService.getAllTipiCampagna();
        model.addAttribute("tipiCampagna", tipiCampagna);
        model.addAttribute("sensori", sensoreService.listaSensoriDisponibili());
        // list of Python scripts kept for backward compatibility but not used in UI anymore
        model.addAttribute("scriptsAvailable", scriptCatalogService.listScripts());
        // application identifiers obtained from descriptors
        model.addAttribute("appsAvailable", applicazioneDescrittoreService.listaDescrittori()
            .stream()
            .map(d -> d.getAppId())
            .collect(Collectors.toList()));
        model.addAttribute("databaseConfigs", databaseConfigService.listAll());

        boolean isDev = authentication.getAuthorities().stream()
                .anyMatch(a -> "USER_DEV".equals(a.getAuthority()));
        model.addAttribute("isDev", isDev);

        // Connessione automatica all'RRM se configurata
        boolean rrmAutoConnected = rrmConnectionService.tryAutoConnect();
        if (rrmAutoConnected) {
            rrmConnectionService.refreshRuntimeStatusFromRrm();
        }
        model.addAttribute("rrmAutoConnected", rrmAutoConnected);

        return "index";
    }

    @GetMapping("/framework")
    public String frameworkPage(Model model) {
        String rrmIp = settingApplicationService.getValue("rrm.ip");
        String rrmPort = settingApplicationService.getValue("rrm.port");
        model.addAttribute("rrmIp", rrmIp);
        model.addAttribute("rrmPort", rrmPort);
        return "framework";
    }

    @GetMapping("/campagne/tutte")
    public String tutteLeCampagne(Model model, @AuthenticationPrincipal Utente utente) {
        CampagnaPage page = buildCampagnaPage(utente.getId(), "TUTTI", null, null, null, 1);
        model.addAttribute("campagne", page.campagne());
        model.addAttribute("currentPage", page.currentPage());
        model.addAttribute("totalPages", page.totalPages());
        return "campagne-tutte";
    }

    /**
     * Pagina dettagli campagna con grafici storici letti da InfluxDB.
     *
     * @param id ID campagna
     * @param model modello MVC
     * @return template dettagli campagna
     */
    @GetMapping("/campagne/{id}")
    public String dettaglioCampagna(@PathVariable Long id, Model model) {
        CampagnaResponse campagna = campagnaService.getCampagnaById(id);
        model.addAttribute("campagna", campagna);
        model.addAttribute("isBreathAnalysis", campagna.getTipiCampagna() != null
                && campagna.getTipiCampagna().stream()
                .anyMatch(tipo -> "BreathAnalysis".equalsIgnoreCase(tipo.getCodice())));
        model.addAttribute("databaseConfigs", databaseConfigService.listAll());
        return "campagna-dettaglio";
    }

    @GetMapping("/fragments/campagne/home")
    public String campagneHomeFragment(Model model) {
        List<CampagnaResponse> campagneHome = campagnaRepository
            .findHomeCampaigns(List.of(StatoCampagna.AVVIO_IN_CORSO, StatoCampagna.IN_CORSO))
                .stream()
                .map(campagnaService::convertToResponse)
                .collect(Collectors.toList());
        model.addAttribute("campagneHome", campagneHome);
        return "fragments/campagne :: righeHome";
    }

    @GetMapping("/fragments/campagne/all")
    public String campagneAllFragment(@RequestParam(defaultValue = "TUTTI") String stato,
                                      @RequestParam(required = false) String persona,
                                      @RequestParam(required = false) String campagna,
                                      @RequestParam(required = false) String dataInizio,
                                      @RequestParam(defaultValue = "1") Integer page,
                                      Model model,
                                      @AuthenticationPrincipal Utente utente) {
        CampagnaPage pageData = buildCampagnaPage(utente.getId(), stato, persona, campagna, dataInizio, page);
        model.addAttribute("campagne", pageData.campagne());
        model.addAttribute("currentPage", pageData.currentPage());
        model.addAttribute("totalPages", pageData.totalPages());
        return "fragments/campagne :: tabellaTutte";
    }

    private CampagnaPage buildCampagnaPage(Long utenteId,
                                           String stato,
                                           String persona,
                                           String campagna,
                                           String dataInizio,
                                           int page) {
        List<CampagnaResponse> campagne = campagnaService.getCampagneByUtente(utenteId);
        campagne = applyFilters(campagne, stato, persona, campagna, dataInizio);
        campagne = sortByLatest(campagne);
        return paginateCampagne(campagne, page, CAMPAGNE_PAGE_SIZE);
    }

    private List<CampagnaResponse> applyFilters(List<CampagnaResponse> campagne,
                                                String stato,
                                                String persona,
                                                String campagna,
                                                String dataInizio) {
        List<CampagnaResponse> filtered = campagne;
        if (stato != null && !"TUTTI".equalsIgnoreCase(stato)) {
            String requested = stato.trim().toUpperCase();
            if ("IN_CORSO".equals(requested)) {
            filtered = filtered.stream()
                .filter(c -> c.getStato() == StatoCampagna.IN_CORSO
                    || c.getStato() == StatoCampagna.AVVIO_IN_CORSO)
                .collect(Collectors.toList());
            } else if ("TERMINATA".equals(requested)) {
            filtered = filtered.stream()
                .filter(c -> c.getStato() == StatoCampagna.TERMINATA
                    || c.getStato() == StatoCampagna.AVVIO_FALLITO)
                .collect(Collectors.toList());
            } else {
            filtered = filtered.stream()
                .filter(c -> c.getStato() != null && requested.equalsIgnoreCase(c.getStato().name()))
                .collect(Collectors.toList());
            }
        }
        if (persona != null && !persona.isBlank()) {
            String personaFilter = persona.trim().toLowerCase();
            filtered = filtered.stream()
                    .filter(c -> {
                        String nome = c.getNomePersona() == null ? "" : c.getNomePersona().toLowerCase();
                        String cognome = c.getCognomePersona() == null ? "" : c.getCognomePersona().toLowerCase();
                        String full = (nome + " " + cognome).trim();
                        return nome.contains(personaFilter)
                                || cognome.contains(personaFilter)
                                || full.contains(personaFilter);
                    })
                    .collect(Collectors.toList());
        }
        if (campagna != null && !campagna.isBlank()) {
            String campagnaFilter = campagna.trim().toLowerCase();
            filtered = filtered.stream()
                    .filter(c -> c.getNome() != null && c.getNome().toLowerCase().contains(campagnaFilter))
                    .collect(Collectors.toList());
        }
        if (dataInizio != null && !dataInizio.isBlank()) {
            try {
                java.time.LocalDate date = java.time.LocalDate.parse(dataInizio);
                filtered = filtered.stream()
                        .filter(c -> c.getDataInizio() != null && date.equals(c.getDataInizio().toLocalDate()))
                        .collect(Collectors.toList());
            } catch (java.time.format.DateTimeParseException ignored) {
                // ignorato: formato data non valido
            }
        }
        return filtered;
    }

    private List<CampagnaResponse> sortByLatest(List<CampagnaResponse> campagne) {
        return campagne.stream()
                .sorted((a, b) -> {
                    java.time.LocalDateTime aDate = a.getDataFine() != null ? a.getDataFine() : a.getDataInizio();
                    java.time.LocalDateTime bDate = b.getDataFine() != null ? b.getDataFine() : b.getDataInizio();
                    if (aDate == null && bDate == null) {
                        return compareIdsDesc(a, b);
                    }
                    if (aDate == null) {
                        return 1;
                    }
                    if (bDate == null) {
                        return -1;
                    }
                    int cmp = bDate.compareTo(aDate);
                    if (cmp != 0) {
                        return cmp;
                    }
                    return compareIdsDesc(a, b);
                })
                .collect(Collectors.toList());
    }

    private int compareIdsDesc(CampagnaResponse a, CampagnaResponse b) {
        Long aId = a.getId();
        Long bId = b.getId();
        if (aId == null && bId == null) {
            return 0;
        }
        if (aId == null) {
            return 1;
        }
        if (bId == null) {
            return -1;
        }
        return bId.compareTo(aId);
    }

    private CampagnaPage paginateCampagne(List<CampagnaResponse> campagne, int page, int pageSize) {
        int totalItems = campagne.size();
        int totalPages = Math.max(1, (int) Math.ceil(totalItems / (double) pageSize));
        int safePage = Math.min(Math.max(page, 1), totalPages);
        int fromIndex = Math.min((safePage - 1) * pageSize, totalItems);
        int toIndex = Math.min(fromIndex + pageSize, totalItems);
        List<CampagnaResponse> slice = campagne.subList(fromIndex, toIndex);
        return new CampagnaPage(slice, safePage, totalPages);
    }

    private record CampagnaPage(List<CampagnaResponse> campagne, int currentPage, int totalPages) {
    }

    @GetMapping("/fragments/persone/select")
    public String personeSelectFragment(Model model) {
        model.addAttribute("persone", personaService.getAllPersone());
        return "fragments/persone :: selectPazienti";
    }
}
