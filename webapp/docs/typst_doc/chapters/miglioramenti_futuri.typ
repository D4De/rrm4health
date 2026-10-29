= 7. Miglioramenti futuri possibili
#v(0.6em)

Nonostante nel progetto siano state utilizzate tecnologie inizialmente nuove per noi, e quindi non completamente conosciute all’avvio dello sviluppo, rimangono, come in ogni progetto software, diverse possibilità di miglioramento.
Alcune delle principali idee e direzioni evolutive sono riportate di seguito.


== 7.1 Upgrade a InfluxDB 2.x

#pad(left: 1.5em)[
  InfluxDB 1.8, sebbene stabile, è una versione legacy. Un miglioramento sarebbe passare a *InfluxDB 2 (o superiore)*, che introduce il concetto di bucket, API unificate e richiede token per la sicurezza. L’app andrebbe aggiornata per usare il nuovo client e gestire l’autenticazione, migliorando la sicurezza del dato.
]



== 7.2 Modernizzazione UI front-end

#pad(left: 1.5em)[
Sebbene l’attuale scelta di *CSS + HTMX + JS* sia efficiente, in futuro si potrebbe valutare di passare ad un front-end interamente single-page application *(React/Vue/Angular...)* per offrire esperienze utente ancora più ricche, soprattutto se si vogliono grafici interattivi avanzati, multitouch, ecc. Ciò richiederebbe di trasformare le attuali pagine in API REST complete e separare front-end e back-end. In alternativa l’utilizzo di Web Components o librerie come Stimulus potrebbe migliorare l’organizzazione del codice JS mantenendolo discreto.
]

== 7.3 Esperienza utente e interfaccia

#pad(left: 1.5em)[
#underline[Potenziamenti possibili includono:]

+ *Funzionalità di annotazione*: permettere al medico di inserire note o event marker durante una campagna (es. “paziente ha riferito sintomo X ora”) che vengono registrate e visualizzate sul grafico.
+ *Multi-utenza avanzata*: se in futuro più medici useranno il sistema, introdurre il concetto di team o assegnazione paziente-medico così che ciascun utente veda solo i propri pazienti. Attualmente, tutti gli USER_MED possono vedere tutte le persone.
]