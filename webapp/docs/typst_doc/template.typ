// template.typ
#let bg-color = rgb("#e9d6bd") // Crema chiaro
#let text-color = rgb("#000000") // Quasi nero
#let accent-color = rgb("#c33d36") // Rosso mattone per i link

#let project(title: "", authors: (), date: none, body) = {
  // 1. Impostazioni Pagina
  set document(author: authors.map(author => author.name), title: title)
  set page(
    paper: "a4",
    fill: bg-color, // Questo colora tutto lo sfondo
    margin: (x: 2cm, y: 2cm),
    numbering: none,
  )
  set text(font: "Roboto", fill: text-color, lang: "it", size: 12pt)

  // Impostazioni per i link
  show link: it => text(fill: accent-color, it)

  // Impostazioni per i titoli (es. Abstract)
  show heading.where(level: 1): it => {
     pagebreak(weak: true)
     set text(size: 1.3em)
     it
  }
  
  // 2. Frontespizio (Cover Page)
  align(center + horizon)[
    #v(3cm)
    #image("assets/sensor-icon.svg", width: 7cm)
    #text(3em, weight: "bold")[#title]
    #v(1.2em, weak: true)
    #text(1.1em)[Report]
    #v(2em)

    // Griglia per gli autori (Layout a due colonne)
  #grid(
    columns: (1fr, 1fr), // Due colonne uguali
    gutter: 2em, // Spazio tra le colonne
    ..authors.map(author => align(center)[
      // Nome in Maiuscoletto o Grassetto
      #text(weight: "bold", size: 1.1em, author.name) \
      
      // Email in font monospazio
      #v(0.2em)
      #text(font: "Roboto Mono", size: 0.9em, author.email) \
      
      // Link GitHub colorato
      #v(0.2em)
      #link(author.link)[#author.link.replace("https://", "")]
    ])
  )
    #v(17em)
    #date
  ]
  pagebreak()

  // 3. Indice
  show outline.entry.where(level: 1): it => {
    set text(weight: "bold")
    it
  }
  outline(indent: auto)
  pagebreak()

  // 4. Il contenuto vero e proprio
  set page(numbering: "1")
  counter(page).update(1)
  body
}
