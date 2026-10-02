# TMALL1085

Verktyg och data för att **jämföra versioner** av *TMALL 1085 – Mall för Teknisk beskrivning (TB för TE)*.

Repot används bara som jämförelsebas. Word-filerna är källan; här finns en strukturerad
kopia av varje version där varje rubrik och varje stycke har ett **beständigt ID**. Det är
ID:na som gör att en ändring kan visas som *ändrad* i stället för *borttagen + ny*.

| | |
|---|---|
| Baslinje | `versions/13.0`, byggd ur `source/TMALL1085_v13.0_2026-03-16.dotm` |
| Innehåll | 781 rubriker, 6 358 block (stycken och tabeller), 2 träd |
| Beroenden | Python 3.9+ och ingenting mer (endast standardbiblioteket) |

## Kom igång

```
python -m tmall info versions/13.0
python -m tmall importera source/NY_FIL.dotm --version 14.0 --datum 2026-10-01 --bas versions/13.0
python -m tmall jamfor versions/13.0 versions/14.0
```

Rapporten hamnar i `reports/13.0_vs_14.0/` (mappen ligger i `.gitignore`):

| Fil | Används till |
|---|---|
| `rapport.html` | läsa i webbläsaren, med färgad ordvis diff, grupperad per avsnitt |
| `rapport.md` | samma innehåll som text |
| `andringar.csv` | öppna i Excel (semikolon, UTF-8) för filtrering och sortering |

Ingen Python lokalt? Använd GitHub Actions, se längre ned.

## Kommandon

| Kommando | Gör |
|---|---|
| `importera DOKUMENT --version V [--bas MAPP]` | läser in en Word-fil som version V. Med `--bas` hämtas ID:n från den versionen. Utan `--bas` skapas nya ID:n. |
| `jamfor A B` | rapport för A mot B. Byter du plats på A och B får du bakåtjämförelsen. |
| `jamfor A A --trad-a dokument --trad-b kod` | jämför **två träd** i samma version |
| `tre BAS A B` | två parallella versioner mot sin gemensamma bas. Visar vad som ändrats på ena sidan, på båda och var de krockar. |
| `info V` / `kontrollera V` | översikt och integritetskontroll |

## Två slags ändringar, aldrig blandade

| Struktur | Text |
|---|---|
| ny eller borttagen rubrik | ändrad text i ett stycke eller en tabell |
| ändrad kod, rubriktext, variant (`/ Typ`, `// Plats`) eller rubriknivå | nytt stycke |
| rubrik flyttad eller omordnad | borttaget stycke |
| ändrad okodad rubrik (Funktion, Kontroll …) | |
| stycke flyttat till annan rubrik | |
| ändrad kravkategori eller texttyp (fast, valbar, råd) | |

## Alternativa träd

Strukturen är **inte** inbakad i texten. Rubriker (noder) och stycken (block) är egna
objekt med ID, och ett **träd** är bara en lista över "nod → förälder, ordning". Flera träd kan
därför finnas för samma innehåll. Baslinjen har två:

* `dokument`: hierarkin som Word-mallen har (Rubrik 1–4).
* `kod`: hierarkin som koderna uttrycker (F → FE → FE6 → FE63). Den är härledd ur kodens
  prefix och finns inte i Word-filen. I version 13.0 ger de två träden olika förälder för 571
  av 781 rubriker.

Se `docs/DESIGN.md` för hur man lägger till fler träd (till exempel Disposition-dokumentet
eller en projektanpassad struktur) och vilka begränsningar som gäller.

## Parallella versioner och egna varianter

* **Framåt/bakåt:** `jamfor` med A och B i valfri ordning.
* **Parallellt:** importera båda mot samma bas (`--bas versions/13.0`) så delar de ID:n.
  `jamfor` visar skillnaden dem emellan, `tre` visar ändringarna mot basen och konflikter.
* **Egna varianter:** importera den anpassade Word-filen som egen version, till exempel
  `--version 13.0-projektX --bas versions/13.0`.

Viktigt: **använd alltid den version som filen härstammar från som `--bas`.** Då följer ID:na med.

## Granska matchningen

Matchningen mellan versioner är heuristisk. Allt som inte är en exakt träff skrivs till
`versions/<V>/granska.jsonl` (ändrad rubrik, likhetsmatchade stycken, nya rubriker). Titta igenom
filen efter varje import innan du litar på rapporten.

## GitHub Actions

* **Jämför versioner** (`.github/workflows/jamfor.yml`): Actions → Run workflow → ange två mappar,
  till exempel `versions/13.0` och `versions/14.0`. Rapporten laddas ner som artefakt.
* **Importera version** (`.github/workflows/importera.yml`): ladda upp Word-filen i `source/`,
  kör arbetsflödet och ange version och bas. Resultatet checkas in i `versions/`.
* **Tester** (`.github/workflows/test.yml`): körs vid varje push.

## Tester

```
python -m unittest discover -s tests -v
```

Testerna bygger ändrade kopior av version 13.0 (ändrad text, nytt rubriknamn, ny kod, flyttad
rubrik, ny rubrik) och kontrollerar att jämförelsen hittar exakt dessa ändringar.

## Struktur

```
source/            Word-filerna (källan)
versions/<V>/      meta.json, nodes.jsonl, blocks.jsonl, trees/*.jsonl, granska.jsonl
ids.json           räknare för nästa lediga nod- och block-ID (får aldrig återanvändas)
tmall/             extract, build (matchning), diff, report, cli
docs/              DESIGN.md, IAKTTAGELSER_13.0.md
```

## Sekretess

Mallen kommer från Trafikverkets arbetsrum. Ha repot **privat** och kontrollera att det är
tillåtet att lagra filerna hos GitHub innan du laddar upp.
