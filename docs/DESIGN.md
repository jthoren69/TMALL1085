# Design

## Utgångspunkt

Word-filen uttrycker sin struktur med formatering och skrivna konventioner:

| Begrepp | Hur det står i Word |
|---|---|
| Avsnitt, rubriker | formatmallarna Rubrik 1–4 |
| Kodad rubrik | text: `DB12cb. Bärlager/ Typ// Plats` |
| Variant | `/` markerar typ, `//` markerar plats, skrivna i rubriktexten |
| Okodad rubrik (Omfattning, Funktion, Teknisk lösning, Kontroll) | **fetstil i brödtext**, inte rubrikmall |
| Fast kravtext | oformaterad, vänsterställd |
| Valbar kravtext | text som börjar och slutar med `//` |
| Rådstext | gul markering + kursiv |

Eftersom inget av detta är data går det inte att jämföra versioner på annat sätt än genom att
tolka dokumentet. `tmall/extract.py` gör den tolkningen en gång och lagrar resultatet.

## Modell

```
Nod      id, kod, namn, variant, titel, niva, stil, art
Block    id, nod, lopnr, typ, kategori, stil, text, hash
Träd     nod -> förälder, ordning        (flera träd per version)
```

* **Nod** = rubrik. `art` är `front`, `numrerad`, `avsnitt`, `kodad` eller `rubrik` (okodad).
* **Block** = ett stycke eller en tabell. `typ` är `fast`, `valbar`, `rad`, `blandad`,
  `okodad_rubrik` eller `tabell`. `kategori` är den okodade rubrik som stycket står under.
* **Träd** är separata från noderna. En nod kan finnas i flera träd med olika förälder.
* Innehållsförteckning, sidnummer och bokmärken lagras inte. De genereras vid varje öppning.

### Varför ID:n

Jämförelse på position eller rubriktext går sönder så fort något flyttas eller får nytt namn.
Med beständiga ID:n kan samma stycke följas genom alla utgåvor, även om det byter rubrik,
kod eller plats. ID:n delas ut en gång (`ids.json` håller räknarna) och återanvänds aldrig.

## Matchning mellan versioner (`tmall/build.py`)

**Rubriker**, i ordning (första träff gäller):

1. exakt lika kod, variant och namn (vid dubbletter avgör föräldern)
2. lika kod och variant, ny rubriktext → *rubriktext ändrad*
3. lika namn och variant, ny kod → *kod ändrad*
4. liknande titel (≥ 0,80) under samma förälder → *likhet*
5. annars **ny** rubrik

**Stycken:**

1. inom matchad rubrik: exakt text (SequenceMatcher på hash)
2. mellan exakta ankare: liknande text (≥ 0,60) i ordning
3. exakt text i annan rubrik → *flyttad*
4. likhet ≥ 0,85 i annan rubrik → *flyttad+ändrad*
5. annars **nytt** eller **borttaget**

Allt utom exakta träffar hamnar i `granska.jsonl`.

## Hur ändringar klassas (`tmall/diff.py`)

**Struktur:** Ny/Borttagen rubrik · Kod ändrad · Rubriktext ändrad · Variant ändrad ·
Rubriknivå ändrad · Formatmall ändrad · Rubrik flyttad · Rubrik omordnad · Ingår (inte) i
trädet · Ny/Borttagen/Ändrad okodad rubrik · Stycke flyttat · Stycke omordnat ·
Kravkategori ändrad · Texttyp ändrad.

**Text:** Ändrad text (med ordvis diff) · Ny text · Borttagen text.

Stycken i helt nya eller borttagna rubriker räknas men listas inte en och en i
rapporten (de står i CSV:n).

## Alternativa träd

Ett träd är en fil `versions/<V>/trees/<namn>.jsonl` med rader `{"nod","foralder","ordning"}`.
Innehållet (noder och block) delas av alla träd. Det ger:

* **Olika hierarkier över samma innehåll**, till exempel Word-nivåerna mot kodhierarkin.
* **Urval:** ett projektanpassat träd som bara innehåller de rubriker projektet valt. Det är
  så TB-mallen används i praktiken ("rensa kodade rubriker som inte är tillämpliga").
* **Jämförelse mellan träd** i samma version: `jamfor V V --trad-a dokument --trad-b kod`.
* **Jämförelse över tid** av samma träd: `jamfor A B`.

Så lägger du till ett träd för en version: skriv en fil enligt formatet ovan med alla noder
som ska ingå. `python -m tmall kontrollera V` kontrollerar att föräldrar finns och att
inga cykler uppstår.

### Begränsningar

* Ett **block hör till en nod**. Träd kan välja nod och ordna noder men kan inte flytta ett
  enskilt stycke mellan rubriker. Det gör bara en ny version (stycke flyttat).
* **`kod`-trädet är härlett** ur kodens prefix och kan inte vara bättre än koderna. Statistik
  över hur föräldrar valts ligger i `meta.json` (`kodtrad`).
* Träd för äldre generationer, till exempel dokumentet *Disposition*, måste importeras och
  matchas för att ge ID:n. Det finns ingen import för det ännu.

## Parallella versioner

Versioner är fristående mappar. De delar ID:n så länge de matchats mot samma bas. `tre BAS A B`
jämför `A` och `B` mot basen och klassar varje berört objekt som *bara i A*, *bara i B*,
*samma ändring* eller *KONFLIKT* (båda har ändrat, olika resultat).

## Kända begränsningar

* Matchningen är heuristisk. En rubrik som både byter kod och namn och flyttas matchas troligen
  inte, och blir då borttagen + ny.
* Dubbletter (till exempel tre rubriker "Digital projekthantering") matchas i dokumentordning.
* En rubrik som tas bort och senare återinförs får ett nytt ID. Det finns ingen "väckning" ur
  äldre versioner än basen.
* Direktformatering som inte styr typ (teckenstorlek, färger utöver gulmarkering) jämförs inte.
* Bilder, ritobjekt och fotnoter ingår inte.
* Korsreferenser och tabellnummer är skrivna för hand eller SEQ-fält. De jämförs som text.
