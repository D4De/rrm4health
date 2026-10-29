= 6. Sicurezza
#v(0.6em)

#let title_color = rgb("#0075af")

La *BSN WebApp* adotta misure di sicurezza standard per proteggere applicazione e dati, con particolare attenzione a *autenticazione* e *segregazione dei permessi*, dato che esistono ruoli distinti.

== 6.1 Autenticazione con Spring Security e JWT

L’implementazione segue un’architettura *stateless* basata su JWT: il server non mantiene una sessione applicativa “persistente” tra una richiesta e la successiva. Ogni richiesta HTTP viene autenticata (o rifiutata) esclusivamente in base al token presentato dal client.

Il meccanismo si basa su due concetti fondamentali:

#set list(indent: 1.5em)

#list(
  [una *catena di filtri* (*SecurityFilterChain*) che intercetta ogni richiesta HTTP in ingresso e applica controlli di sicurezza prima di raggiungere i controller;],
  [un *SecurityContext* (accessibile tramite `SecurityContextHolder`) che contiene l’utente autenticato per la *singola richiesta* corrente, oppure `null`/anonimo se non autenticato.]
)

A livello di configurazione, la classe di *SecurityConfig* definisce principalmente:

#list(
  [la `SecurityFilterChain`, cioè l’ordine e la composizione dei filtri applicati alle richieste;],
  [l’oggetto `HttpSecurity`, tramite cui si impostano regole di accesso, CSRF/CORS, gestione delle sessioni (in stateless), ecc.]
)

#list(
  [*Login*: il client invia le credenziali. Se valide, il server genera un JWT tramite `JwtUtils`e lo restituisce al client.],
  [*Richieste successive*: il client include il token nell’header `Authorization: Bearer <token>`.],
  [Il filtro `JwtAuthFilter` intercetta la richiesta, valida il token (firma e scadenza) ed estrae le informazioni principali (es. username e ruoli).],
  [Se il token è valido, viene creata un’istanza di `Authentication` e inserita nel *SecurityContext*; da quel momento Spring può applicare le regole di autorizzazione su quella richiesta.]
)

#text(fill:title_color, weight: "bold")[L’oggetto Authentication in Spring Security]

Spring Security lavora con un oggetto `Authentication`, che rappresenta l’identità (e i permessi) associati alla richiesta corrente. In particolare:

#list(
  [*principal*: rappresenta l’utente autenticato; è un oggetto che implementa `UserDetails`, cioè l’interfaccia con cui Spring “vede” un utente;],
  [*authorities*: insieme di ruoli e/o permessi (`USER_DEV`, `USER_MED`) usati per l’autorizzazione;],
  [*authenticated*: booleano che vale `true` quando l’autenticazione è stata completata con successo.]
)

In pratica, il `JwtAuthFilter` costruisce/riempie questo oggetto a partire dai dati presenti nel JWT e lo associa al `SecurityContext` della richiesta.

#text(fill:title_color, weight: "bold")[Contenuto e verifica del JWT]

Il JWT è un token firmato che include:

#list(
  [lo *username* (o identificativo utente);],
  [i *ruoli/authorities* necessari per autorizzare le operazioni;]
)

In fase di verifica, il server controlla l’integrità del token (firma) e la validità temporale (scadenza). Se uno dei controlli fallisce, la richiesta viene trattata come non autenticata e può essere bloccata dalle regole di autorizzazione.

== 6.2 Autorizzazione basata sui ruoli

L’applicazione distingue almeno due ruoli: `USER_MED` e `USER_DEV`. Il backend applica restrizioni su rotte e funzionalità:

#list(
  [
    Le rotte “dev” (tipicamente prefissate da `/api/v1/dev/**` e/o pagine admin) sono accessibili solo a `USER_DEV`. Un utente medico che tenti l’accesso riceverà un errore di *accesso negato*.
  ],
  [
    Le rotte “med” sono destinate a `USER_MED`. `USER_DEV` rimane comunque in grado di poter svolgere il 100% delle funzionalità.
  ],
)

== 6.3 Protezione delle password

Le password non vengono memorizzate in chiaro: sono salvate come *hash*. Si fa uso di *BCrypt* in Spring Security:

#list(
  [in registrazione: la password viene codificata prima del salvataggio;],
  [in login: la verifica avviene confrontando l’hash (BCrypt gestisce anche il *salt* in modo sicuro).]
)


