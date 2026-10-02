# Iakttagelser i version 13.0

Framkom när baslinjen byggdes. De påverkar hur väl versioner kan matchas och är värda att rätta i källan.

* **Hierarkin i koderna finns inte i Word.** Koden uttrycker `F → FE → FE6 → FE63`, men i Word ligger
  nästan alla rubriker på nivå 2 eller 3. Rubriknivå och kodens djup stämmer inte överens.
  571 av 781 rubriker får olika förälder i trädet `kod` jämfört med `dokument`.
* **Okodade rubriker är fetstil, inte rubrikmall** (Omfattning, Funktion, Teknisk lösning, Kontroll;
  1 115 st). De syns därför inte i innehållsförteckningen eller navigeringen.
* **Texttyp styrs av formatering och tecken:** råd = gul markering, valbar = `//…//`. 15 stycken är delvis
  markerade och därför osäkra (typ `blandad`).
* **Kod utan punkt** (11 rubriker): `DB12cb Bärlager`, `FB1 Banöverbyggnad`, `FB11d Rälsskarv`,
  `FC51b Signalpunktstavla`, `FC51e`, `FC54d`, `FC54e`, `FD.62 …`.
* **Möjlig felstavning:** `XB. Projekteringsbeskr ivning/ Geoteknik`.
* **Identiska rubriker flera gånger:** `Digital projekthantering` (3), `FB74. Trumma/ Trumma under bana // XX` (2).
* **Återanvänd text utan gemensam källa:** 186 längre stycken förekommer ordagrant flera gånger
  (422 förekomster). Ändras en av dem blir det en separat ändring på varje plats.
* **Sidhuvudet bär versionen** ("13.0"). Ändringshistorik finns i separata dokument (PM Uppdateringar,
  Brev om uppdatering) och inte i mallen.
