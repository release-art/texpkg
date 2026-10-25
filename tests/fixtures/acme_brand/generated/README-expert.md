# expert: acme-brand-tex 1.2.0

Cards under the brand's lock-up.

Compile the template with LuaLaTeX from this directory:

    latexmk -lualatex expert-template.tex

## Files

- `NOTICE.txt`
- `README-expert.md`
- `README-vocab.md`
- `acme-brand-provenance.sty`
- `acme-brand.sty`
- `expert-template.tex`
- `lmroman10-regular.otf`
- `lockup.pdf`
- `vocab-template.tex`

## The template is written with

- `\setlength{\abFactGap}{3mm}`

Variants of the kind (the Python module writes them; the template is the kind's own): `compact`, `wide`.

## Commands

- `\begin{abDeck} ... \end{abDeck}`: Cards under the brand's lock-up.
- `\abMark`: The brand's lock-up.
- `\begin{abCard} ... \end{abCard}`: A card: a title and up to three facts.
- `\abTitle{text}`: The subject's name.
- `\abFact[accent]{text}`: One short sentence under the title.
