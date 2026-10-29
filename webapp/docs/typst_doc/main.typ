// main.typ
#import "template.typ": *

// Applichiamo il template definito prima
#show: project.with(
  title: "BSN WebApp",
  authors: (
    (
      name: "Arturo Matteo Santarlasci",
      email: "arturomatteo.santarlasci@mail.polimi.it",
      link: "https://github.com/ArturoMatteoSantarlasci"
    ),
    (
      name: "Filippo Polvani",
      email: "filippo.polvani@mail.polimi.it",
      link: "https://github.com/filippo0000"
    ),
  ),
  date: "Gennaio 2026"
)

// Includiamo i capitoli in ordine
 #include "chapters/abstract.typ"
 #include "chapters/tecnologie_utilizzate.typ"
 #include "chapters/architettura.typ"
 #include "chapters/database_relazionale.typ"
 #include "chapters/Funzionalità.typ"
 #include "chapters/Sicurezzza.typ"
 #include "chapters/miglioramenti_futuri.typ"