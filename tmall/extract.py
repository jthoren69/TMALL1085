"""Läser ett .docx/.dotm och bygger en strukturerad modell (utan beständiga ID:n).

Det som extraheras är det mallen faktiskt använder för att uttrycka struktur:

  rubriker      formatmallarna Rubrik1-5 och Numreradrubrik1-2 -> noder
  kodning       "DB12cb. Bärlager/ Typ// Plats" -> kod, namn, variant
  okodad rubrik fetstilt kort stycke som börjar med Omfattning/Funktion/
                Teknisk lösning/Kontroll -> blocktyp 'okodad_rubrik' och kategori
  texttyper     fast, valbar (//...//), rad (helt gulmarkerat), blandad
  tabeller      ett block per tabell

Allt som är genererat (innehållsförteckning, sidnummer, bokmärken) lämnas utanför,
eftersom det ändras vid varje öppning och bara skapar brus i jämförelser.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET

from .model import ws

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def q(tag: str) -> str:
    return "{%s}%s" % (W, tag)


HEADING_LEVEL = {
    "Rubrik1": 1, "Rubrik2": 2, "Rubrik3": 3, "Rubrik4": 4, "Rubrik5": 5,
    "Numreradrubrik1": 1, "Numreradrubrik2": 2,
}
CATEGORIES = ("Omfattning", "Funktion", "Teknisk lösning", "Kontroll")

# Kod: versaler, därefter (valfritt) siffror och små bokstäver, t.ex. D, DB12cb, FE63, XD3.
# Små bokstäver tillåts bara efter en siffra, så att ord som "Hus" inte tolkas som kod.
# Enstaka koder har punkt före siffrorna (FD.62).
CODE_RE = re.compile(r"^([A-ZÅÄÖ]{1,4}(?:\d+[a-z]{0,3}\d*)?(?:\.\d+[a-z]{0,3})?)\.?\s+(\S.*)$")
SLASH_RE = re.compile(r"\s*//?(?=\s)")


class Raw:
    """Resultat av extraktion, med provisoriska ID:n (t1.., b1..)."""

    def __init__(self):
        self.nodes: list[dict] = []
        self.blocks: list[dict] = []
        self.trees: dict[str, list[dict]] = {}
        self.notes: list[str] = []
        self.stats: dict = {}


# ---------------------------------------------------------------------------
# Låg nivå: text och formatering ur XML
# ---------------------------------------------------------------------------

def _run_text(r) -> str:
    parts = []
    for c in r:
        if c.tag == q("t"):
            parts.append(c.text or "")
        elif c.tag == q("tab"):
            parts.append(" ")
        elif c.tag in (q("br"), q("cr")):
            parts.append(" ")
    return "".join(parts)


def _is_on(rpr, tag) -> bool:
    el = rpr.find(q(tag)) if rpr is not None else None
    if el is None:
        return False
    return el.get(q("val"), "1").lower() not in ("0", "false", "none")


def _paragraph(p):
    """(text, runs) där runs = [(text, markerad, fetstil)] för runs med innehåll."""
    runs = []
    for r in p.iter(q("r")):
        t = _run_text(r)
        rpr = r.find(q("rPr"))
        hl = rpr.find(q("highlight")) if rpr is not None else None
        highlighted = hl is not None and hl.get(q("val"), "yellow") != "none"
        runs.append((t, highlighted, _is_on(rpr, "b")))
    text = ws("".join(t for t, _, _ in runs))
    runs = [x for x in runs if x[0].strip()]
    return text, runs


def _style(p) -> str:
    ps = p.find(q("pPr") + "/" + q("pStyle"))
    return ps.get(q("val"), "") if ps is not None else ""


def _table_text(tbl) -> str:
    rows = []
    for tr in tbl.findall(q("tr")):
        cells = []
        for tc in tr.findall(q("tc")):
            cells.append(ws(" ".join(ws("".join(t.text or "" for t in p.iter(q("t"))))
                                     for p in tc.iter(q("p")))))
        rows.append(" | ".join(cells))
    return "\n".join(r for r in rows if r.strip(" |"))


def classify(text, runs):
    """Returnerar (typ, kategori_om_okodad_rubrik)."""
    if runs and all(h for _, h, _ in runs):
        return "rad", ""
    if text.startswith("//"):
        return "valbar", ""
    if runs and all(b for _, _, b in runs) and len(text) <= 80:
        main = text.split("/")[0].strip()
        if main in CATEGORIES:
            return "okodad_rubrik", main
    if any(h for _, h, _ in runs):
        return "blandad", ""
    return "fast", ""


def split_heading(text: str):
    """'DB12cb. Bärlager/ Typ// Plats' -> ('DB12cb', 'Bärlager', '/ Typ // Plats')."""
    m = CODE_RE.match(text)
    kod, rest = (m.group(1), m.group(2)) if m else ("", text)
    s = SLASH_RE.search(rest)
    if s:
        namn, variant = rest[: s.start()].strip(), ws(rest[s.start():])
    else:
        namn, variant = rest.strip(), ""
    return kod, ws(namn), variant


# ---------------------------------------------------------------------------
# Huvudfunktion
# ---------------------------------------------------------------------------

def extract(path: str) -> Raw:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(q("body"))

    raw = Raw()
    nid = [0]
    bid = [0]

    def new_node(**kw):
        nid[0] += 1
        n = {"id": "t%d" % nid[0]}
        n.update(kw)
        raw.nodes.append(n)
        return n

    def new_block(node, typ, kategori, stil, text, seq):
        bid[0] += 1
        raw.blocks.append({"id": "b%d" % bid[0], "nod": node["id"], "lopnr": seq,
                           "typ": typ, "kategori": kategori, "stil": stil, "text": text})

    doc_edges: list[dict] = []
    order_in_parent: dict = {}
    stack: list[tuple] = []          # (nivå, nod-id)

    def attach(node, level):
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        order_in_parent[parent] = order_in_parent.get(parent, -1) + 1
        doc_edges.append({"nod": node["id"], "foralder": parent, "ordning": order_in_parent[parent]})
        stack.append((level, node["id"]))

    front = new_node(kod="", namn="Dokumentstart", variant="", titel="Dokumentstart",
                     niva=0, stil="", art="front")
    attach(front, 0)
    stack.clear()                    # front är syskon till första avsnittet, inte förälder
    cur = front
    seq = 0
    category = ""
    in_krav = False                  # kodtolkning av rubriker börjar vid första avsnittet efter "1. Allmänt"
    seen_allmant = False
    n1 = n2 = 0
    toc_skipped = 0

    for el in body:
        if el.tag == q("sdt"):
            toc_skipped += 1         # innehållsförteckning m.m. är genererat
            continue
        if el.tag == q("p"):
            text, runs = _paragraph(el)
            style = _style(el)
            if style in HEADING_LEVEL and text:
                level = HEADING_LEVEL[style]
                if style == "Rubrik1" and seen_allmant:
                    in_krav = True
                if style == "Numreradrubrik1":
                    seen_allmant = True
                    n1 += 1
                    n2 = 0
                    kod, namn, variant, art = str(n1), text, "", "numrerad"
                elif style == "Numreradrubrik2":
                    n2 += 1
                    kod, namn, variant, art = "%d.%d" % (n1, n2), text, "", "numrerad"
                elif in_krav:
                    kod, namn, variant = split_heading(text)
                    art = "avsnitt" if level == 1 else ("kodad" if kod else "rubrik")
                else:
                    kod, namn, variant = "", text, ""
                    art = "avsnitt" if level == 1 else "rubrik"
                    s = SLASH_RE.search(text)
                    if s:
                        namn, variant = text[: s.start()].strip(), ws(text[s.start():])
                cur = new_node(kod=kod, namn=namn, variant=variant, titel=text,
                               niva=level, stil=style, art=art)
                attach(cur, level)
                seq = 0
                category = ""
                continue
            if not text:
                continue
            typ, cat = classify(text, runs)
            if typ == "okodad_rubrik":
                category = cat
            seq += 1
            new_block(cur, typ, category, style or "Normal", text, seq)
        elif el.tag == q("tbl"):
            text = _table_text(el)
            if text:
                seq += 1
                new_block(cur, "tabell", category, "Tabell", text, seq)

    raw.trees["dokument"] = doc_edges
    raw.trees["kod"] = build_kod_tree(raw.nodes, doc_edges, raw)
    raw.stats["innehallsforteckning_hoppad"] = toc_skipped
    return raw


# ---------------------------------------------------------------------------
# Alternativt träd: hierarki enligt kodens prefix (F -> FE -> FE6 -> FE63)
# ---------------------------------------------------------------------------

def build_kod_tree(nodes, doc_edges, raw: Raw):
    """Bygger trädet 'kod'. Förälder för en kodad rubrik är i första hand noden med
    längsta kodprefix, annars avsnittet. Varianter (/ Typ, // Plats) hänger under
    grundrubriken med samma kod. Okodade rubriker behåller sin plats i dokumentet.

    Detta är en härledning, inte en sanning: hierarkin finns inte i dokumentet utan
    följer av hur koderna är konstruerade. Statistik lagras i meta så den kan granskas.
    """
    doc_parent = {e["nod"]: e["foralder"] for e in doc_edges}
    pure, anyn = {}, {}
    for n in nodes:
        if n["art"] in ("kodad", "avsnitt") and n["kod"]:
            anyn.setdefault(n["kod"], n["id"])
            if not n["variant"]:
                pure.setdefault(n["kod"], n["id"])

    def top(nid_):
        cur = nid_
        while doc_parent.get(cur) is not None:
            cur = doc_parent[cur]
        return cur

    parent_of, how = {}, {"prefix": 0, "variant": 0, "avsnitt": 0, "dokument": 0}
    for n in nodes:
        nid_ = n["id"]
        if n["art"] == "kodad" and n["kod"]:
            p = None
            if n["variant"] and pure.get(n["kod"]) not in (None, nid_):
                p, h = pure[n["kod"]], "variant"
            if p is None:
                for L in range(len(n["kod"]) - 1, 0, -1):
                    c = anyn.get(n["kod"][:L])
                    if c and c != nid_:
                        p, h = c, "prefix"
                        break
            if p is None:
                t = top(nid_)
                p, h = (t if t != nid_ else None), "avsnitt"
            parent_of[nid_] = p
            how[h] += 1
        else:
            parent_of[nid_] = doc_parent.get(nid_)
            how["dokument"] += 1

    edges, counter = [], {}
    for n in nodes:                  # dokumentordning => stabil ordning bland syskon
        p = parent_of[n["id"]]
        counter[p] = counter.get(p, -1) + 1
        edges.append({"nod": n["id"], "foralder": p, "ordning": counter[p]})
    raw.stats["kodtrad"] = how
    return edges
