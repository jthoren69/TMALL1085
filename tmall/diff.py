"""Jämför två versioner (eller två träd i samma version).

Ändringarna delas i två slag som aldrig blandas:

  STRUKTUR  rubriker och uppbyggnad: ny/borttagen rubrik, ändrad kod eller rubriktext,
            ändrad variant (/ Typ, // Plats), ändrad rubriknivå, flyttad rubrik,
            omordnad, ändrad okodad rubrik (Funktion, Kontroll ...), stycke flyttat
            till annan rubrik, ändrad kravkategori eller texttyp (fast/valbar/råd).
  TEXT      innehållet i ett stycke eller en tabell: ändrad, ny eller borttagen text.

Jämförelsen sker på beständiga ID:n, inte på position eller rubriktext.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .model import Version, node_title, ws

STRUKTUR = "struktur"
TEXT = "text"


def word_diff(a: str, b: str):
    """Ordvis diff som lista av (tag, text), tag i {'eq','del','ins'}."""
    tok = lambda s: re.findall(r"\s+|\w+|[^\w\s]", s)
    ta, tb = tok(a), tok(b)
    sm = SequenceMatcher(None, ta, tb, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(("eq", "".join(ta[i1:i2])))
        else:
            if i2 > i1:
                out.append(("del", "".join(ta[i1:i2])))
            if j2 > j1:
                out.append(("ins", "".join(tb[j1:j2])))
    return out


def _words(s):
    return len(re.findall(r"\w+", s))


class Change(dict):
    """kategori, typ, id, sektion, etikett, fore, efter, diff (valfritt), via_nod."""


def _label(v: Version, nid):
    n = v.nodes.get(nid)
    if not n:
        return "(rot)" if nid is None else str(nid)
    return n.get("titel") or node_title(n["kod"], n["namn"], n["variant"])


def _block_label(v: Version, b):
    return _label(v, b["nod"])


def _lcs_outliers(seq_a, seq_b):
    """Element i seq_b som inte ligger i samma relativa ordning som i seq_a."""
    sm = SequenceMatcher(None, seq_a, seq_b, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            out.extend(seq_b[j1:j2])
    return out


def compare(A: Version, B: Version, tree_a="dokument", tree_b="dokument"):
    """Returnerar (lista med Change, sammanfattning)."""
    ch: list[Change] = []
    ta, tb = A.tree(tree_a), B.tree(tree_b)
    order = {n: i for i, n in enumerate(B.doc_order(tree_b))}
    for n, i in ((n, i) for i, n in enumerate(A.doc_order(tree_a))):
        order.setdefault(n, 10 ** 6 + i)

    def sektion(nid):
        if nid in B.nodes and nid in tb:
            s = B.section_of(nid, tree_b)
            return _label(B, s)
        if nid in A.nodes and nid in ta:
            return _label(A, A.section_of(nid, tree_a))
        return "(okänd)"

    def add(kat, typ, nid, etikett, fore="", efter="", diff=None, via_nod=False, block=None):
        ch.append(Change(kategori=kat, typ=typ, id=nid, sektion=sektion(block["nod"] if block else nid),
                         etikett=etikett, fore=fore, efter=efter, diff=diff, via_nod=via_nod,
                         ordning=order.get(block["nod"] if block else nid, 10 ** 9)))

    ids_a, ids_b = set(A.nodes), set(B.nodes)

    # ---- noder: ny/borttagen ---------------------------------------------
    for nid in sorted(ids_b - ids_a, key=lambda x: order.get(x, 0)):
        nb = len(B.blocks_of(nid))
        add(STRUKTUR, "Ny rubrik", nid, _label(B, nid),
            efter="under " + _label(B, tb[nid]["foralder"]) + (" (%d stycken)" % nb if nb else "")
            if nid in tb else "")
    for nid in sorted(ids_a - ids_b, key=lambda x: order.get(x, 0)):
        nb = len(A.blocks_of(nid))
        add(STRUKTUR, "Borttagen rubrik", nid, _label(A, nid),
            fore="fanns under " + _label(A, ta[nid]["foralder"]) + (" (%d stycken)" % nb if nb else "")
            if nid in ta else "")

    # ---- noder: egenskaper ------------------------------------------------
    common = ids_a & ids_b
    attrs = (("kod", "Kod ändrad"), ("namn", "Rubriktext ändrad"), ("variant", "Variant ändrad"),
             ("niva", "Rubriknivå ändrad"), ("stil", "Formatmall ändrad (rubrik)"))
    for nid in sorted(common, key=lambda x: order.get(x, 0)):
        a, b = A.nodes[nid], B.nodes[nid]
        for key, typ in attrs:
            if ws(str(a.get(key, ""))) != ws(str(b.get(key, ""))):
                add(STRUKTUR, typ, nid, _label(B, nid), fore=str(a.get(key, "")), efter=str(b.get(key, "")))

    # ---- träd: ingår, flyttad, omordnad -----------------------------------
    for nid in sorted(common, key=lambda x: order.get(x, 0)):
        ea, eb = ta.get(nid), tb.get(nid)
        if ea is None and eb is not None:
            add(STRUKTUR, "Ingår i trädet", nid, _label(B, nid), efter="under " + _label(B, eb["foralder"]))
        elif ea is not None and eb is None:
            add(STRUKTUR, "Ingår inte i trädet", nid, _label(A, nid), fore="låg under " + _label(A, ea["foralder"]))
        elif ea is not None and eb is not None and ea["foralder"] != eb["foralder"]:
            add(STRUKTUR, "Rubrik flyttad", nid, _label(B, nid),
                fore=_label(A, ea["foralder"]), efter=_label(B, eb["foralder"]))

    def siblings(tree, ver, parent, keep):
        ids = [n for n, e in tree.items() if e["foralder"] == parent and n in keep]
        return sorted(ids, key=lambda n: tree[n]["ordning"])

    same_parent = {n for n in common if n in ta and n in tb and ta[n]["foralder"] == tb[n]["foralder"]}
    parents = {ta[n]["foralder"] for n in same_parent}
    for p in parents:
        sa, sb = siblings(ta, A, p, same_parent), siblings(tb, B, p, same_parent)
        if sa != sb:
            for nid in _lcs_outliers(sa, sb):
                add(STRUKTUR, "Rubrik omordnad", nid, _label(B, nid), efter="under " + _label(B, p))

    # ---- block ------------------------------------------------------------
    ba, bb = A.blocks, B.blocks
    for bid in sorted(set(bb) - set(ba), key=lambda x: order.get(bb[x]["nod"], 0)):
        b = bb[bid]
        via = b["nod"] not in A.nodes
        if b["typ"] == "okodad_rubrik":
            add(STRUKTUR, "Ny okodad rubrik", bid, _block_label(B, b), efter=b["text"], via_nod=via, block=b)
        else:
            add(TEXT, "Ny text", bid, _block_label(B, b), efter=b["text"], via_nod=via, block=b)
    for bid in sorted(set(ba) - set(bb), key=lambda x: order.get(ba[x]["nod"], 0)):
        b = ba[bid]
        via = b["nod"] not in B.nodes
        if b["typ"] == "okodad_rubrik":
            add(STRUKTUR, "Borttagen okodad rubrik", bid, _block_label(A, b), fore=b["text"], via_nod=via, block=b)
        else:
            add(TEXT, "Borttagen text", bid, _block_label(A, b), fore=b["text"], via_nod=via, block=b)

    for bid in sorted(set(ba) & set(bb), key=lambda x: order.get(bb[x]["nod"], 0)):
        a, b = ba[bid], bb[bid]
        lab = _block_label(B, b)
        if a["nod"] != b["nod"]:
            add(STRUKTUR, "Stycke flyttat till annan rubrik", bid, lab,
                fore=_block_label(A, a), efter=_block_label(B, b), block=b)
        if a.get("kategori", "") != b.get("kategori", ""):
            add(STRUKTUR, "Kravkategori ändrad", bid, lab, fore=a.get("kategori", "") or "(ingen)",
                efter=b.get("kategori", "") or "(ingen)", block=b)
        if a["typ"] != b["typ"]:
            add(STRUKTUR, "Texttyp ändrad", bid, lab, fore=a["typ"], efter=b["typ"], block=b)
        if a.get("stil") != b.get("stil"):
            add(STRUKTUR, "Formatmall ändrad (stycke)", bid, lab, fore=a.get("stil", ""), efter=b.get("stil", ""), block=b)
        if ws(a["text"]) != ws(b["text"]):
            if "okodad_rubrik" in (a["typ"], b["typ"]):
                add(STRUKTUR, "Okodad rubrik ändrad", bid, lab, fore=a["text"], efter=b["text"], block=b)
            else:
                add(TEXT, "Ändrad text", bid, lab, fore=a["text"], efter=b["text"],
                    diff=word_diff(ws(a["text"]), ws(b["text"])), block=b)

    # ordning av stycken inom samma rubrik
    per_node = {}
    for bid in set(ba) & set(bb):
        if ba[bid]["nod"] == bb[bid]["nod"]:
            per_node.setdefault(bb[bid]["nod"], []).append(bid)
    for nid, ids in per_node.items():
        sa = [x for x in sorted(ids, key=lambda i: ba[i]["lopnr"])]
        sb = [x for x in sorted(ids, key=lambda i: bb[i]["lopnr"])]
        if sa != sb:
            for bid in _lcs_outliers(sa, sb):
                add(STRUKTUR, "Stycke omordnat", bid, _label(B, nid),
                    efter=ws(bb[bid]["text"])[:100], block=bb[bid])

    ch.sort(key=lambda c: (c["ordning"], c["kategori"], c["typ"], c["id"]))
    return ch, summarize(A, B, tree_a, tree_b, ch)


def summarize(A, B, tree_a, tree_b, ch):
    by_typ = {STRUKTUR: {}, TEXT: {}}
    by_sec = {}
    for c in ch:
        by_typ[c["kategori"]][c["typ"]] = by_typ[c["kategori"]].get(c["typ"], 0) + 1
        s = by_sec.setdefault(c["sektion"], {STRUKTUR: 0, TEXT: 0})
        s[c["kategori"]] += 1
    return {
        "a": A.label, "b": B.label, "tradA": tree_a, "tradB": tree_b,
        "antal": {STRUKTUR: sum(by_typ[STRUKTUR].values()), TEXT: sum(by_typ[TEXT].values())},
        "per_typ": by_typ, "per_sektion": by_sec,
        "noder": {"a": len(A.nodes), "b": len(B.nodes)},
        "block": {"a": len(A.blocks), "b": len(B.blocks)},
    }


# ---------------------------------------------------------------------------
# Tre-vägs: gemensam förfader + två parallella versioner
# ---------------------------------------------------------------------------

def compare3(BASE: Version, A: Version, B: Version):
    """Visar vad som ändrats i A respektive B relativt BASE och var de krockar.

    Block som ändrats på båda sidor är 'samma ändring' om slutresultatet är identiskt,
    annars 'konflikt'. Noder jämförs på kod, namn, variant och förälder.
    """
    rows = []
    for bid in sorted(set(BASE.blocks) | set(A.blocks) | set(B.blocks)):
        base = BASE.blocks.get(bid)
        a, b = A.blocks.get(bid), B.blocks.get(bid)
        key = lambda x: None if x is None else (ws(x["text"]), x["nod"], x["typ"], x.get("kategori", ""))
        kb, ka, kbb = key(base), key(a), key(b)
        ch_a, ch_b = ka != kb, kbb != kb
        if not (ch_a or ch_b):
            continue
        if ch_a and ch_b:
            status = "samma ändring" if ka == kbb else "KONFLIKT"
        else:
            status = "bara i A" if ch_a else "bara i B"
        ref = (b or a or base)
        rows.append({"slag": "block", "id": bid, "status": status,
                     "etikett": _label(B if bid in B.blocks else A if bid in A.blocks else BASE, ref["nod"]),
                     "bas": base["text"] if base else "", "a": a["text"] if a else "", "b": b["text"] if b else ""})
    for nid in sorted(set(BASE.nodes) | set(A.nodes) | set(B.nodes)):
        base, a, b = BASE.nodes.get(nid), A.nodes.get(nid), B.nodes.get(nid)

        def key(v, x):
            if x is None:
                return None
            e = v.trees.get("dokument", {}).get(nid)
            return (x["kod"], x["namn"], x["variant"], x["niva"], e["foralder"] if e else None)

        kb, ka, kbb = key(BASE, base), key(A, a), key(B, b)
        ch_a, ch_b = ka != kb, kbb != kb
        if not (ch_a or ch_b):
            continue
        if ch_a and ch_b:
            status = "samma ändring" if ka == kbb else "KONFLIKT"
        else:
            status = "bara i A" if ch_a else "bara i B"
        v = B if b else A if a else BASE
        rows.append({"slag": "rubrik", "id": nid, "status": status, "etikett": _label(v, nid),
                     "bas": str(kb), "a": str(ka), "b": str(kbb)})
    return rows
