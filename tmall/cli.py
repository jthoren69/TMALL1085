"""Kommandorad:  python -m tmall <kommando> ...

  importera  DOKUMENT --version 13.1 [--bas versions/13.0]   läs in en Word-fil
  jamfor     A B [--trad-a dokument] [--trad-b kod]          rapport (md, html, csv)
  tre        BAS A B                                         parallella versioner
  info       VERSION                                         översikt över en version
  kontrollera VERSION                                        kontrollera att data hänger ihop
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

from .build import build_version
from .diff import compare, compare3
from .extract import extract
from .model import Version, VersionError
from .report import write_all, write_markdown3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_import(a):
    base = Version(a.bas) if a.bas else None
    out = a.ut or os.path.join(ROOT, "versions", a.version)
    if os.path.exists(os.path.join(out, "meta.json")) and not a.skriv_over:
        sys.exit("Mappen %s finns redan. Använd --skriv-over för att ersätta den." % out)
    raw = extract(a.dokument)
    meta = {"version": a.version, "datum": a.datum or "", "mall": "TMALL 1085",
            "titel": "Mall för Teknisk beskrivning TB för TE",
            "kalla": os.path.relpath(a.dokument, ROOT) if a.dokument.startswith(ROOT) else os.path.basename(a.dokument),
            "kalla_sha256": _sha256(a.dokument),
            "baserad_pa": base.label if base else None,
            "kommentar": a.kommentar or ""}
    os.makedirs(out, exist_ok=True)
    m = build_version(raw, out, meta, os.path.join(ROOT, "ids.json"), base)
    print("Version %s skriven till %s" % (a.version, out))
    print("  noder %(noder)d, block %(block)d" % m["antal"])
    if m["matchning"]:
        print("  matchning noder:", m["matchning"]["noder"], "borttagna:", m["matchning"]["borttagna_noder"])
        print("  matchning block:", m["matchning"]["block"], "borttagna:", m["matchning"]["borttagna_block"])
        print("  Granska gärna %s" % os.path.join(out, "granska.jsonl"))


def cmd_compare(a):
    A, B = Version(a.a), Version(a.b)
    ta, tb = a.trad_a, a.trad_b or a.trad_a
    ch, summary = compare(A, B, ta, tb)
    name = "%s_vs_%s" % (A.label, B.label)
    if ta != tb:
        name += "_%s-%s" % (ta, tb)
    out = a.ut or os.path.join(ROOT, "reports", name)
    write_all(out, ch, summary)
    print("Struktur: %d ändringar. Text: %d ändringar." % (summary["antal"]["struktur"], summary["antal"]["text"]))
    print("Rapporter i", out)


def cmd_three(a):
    BASE, A, B = Version(a.bas), Version(a.a), Version(a.b)
    rows = compare3(BASE, A, B)
    out = a.ut or os.path.join(ROOT, "reports", "tre_%s_%s_%s" % (BASE.label, A.label, B.label))
    os.makedirs(out, exist_ok=True)
    write_markdown3(os.path.join(out, "rapport.md"), rows, BASE.label, A.label, B.label)
    print("Konflikter:", sum(1 for r in rows if r["status"] == "KONFLIKT"), "– rapport i", out)


def cmd_info(a):
    V = Version(a.version)
    print("Version", V.label, "–", V.meta.get("titel", ""))
    print("Noder:", len(V.nodes), " Block:", len(V.blocks), " Träd:", ", ".join(sorted(V.trees)))
    print("Blocktyper:", V.meta.get("antal", {}).get("blocktyper"))
    print("Kodträd (hur föräldrar valts):", V.meta.get("kodtrad"))


def cmd_validate(a):
    V = Version(a.version)
    errs = []
    for b in V.blocks.values():
        if b["nod"] not in V.nodes:
            errs.append("block %s pekar på okänd nod %s" % (b["id"], b["nod"]))
    for name, t in V.trees.items():
        for nid, e in t.items():
            if nid not in V.nodes:
                errs.append("träd %s: okänd nod %s" % (name, nid))
            if e["foralder"] is not None and e["foralder"] not in t:
                errs.append("träd %s: förälder %s saknas för %s" % (name, e["foralder"], nid))
        for nid in t:                                  # cykelkontroll
            seen, cur = set(), nid
            while cur is not None and cur in t:
                if cur in seen:
                    errs.append("träd %s: cykel vid %s" % (name, nid))
                    break
                seen.add(cur)
                cur = t[cur]["foralder"]
        missing = set(V.nodes) - set(t)
        if missing:
            errs.append("träd %s saknar %d noder" % (name, len(missing)))
    print("OK" if not errs else "\n".join(errs[:50]))
    sys.exit(1 if errs else 0)


def main(argv=None):
    p = argparse.ArgumentParser(prog="tmall", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    i = sp.add_parser("importera", help="läs in en Word-fil som en version")
    i.add_argument("dokument")
    i.add_argument("--version", required=True)
    i.add_argument("--datum")
    i.add_argument("--bas", help="mapp för versionen som ID:n ska hämtas från")
    i.add_argument("--ut")
    i.add_argument("--kommentar")
    i.add_argument("--skriv-over", action="store_true")
    i.set_defaults(f=cmd_import)

    j = sp.add_parser("jamfor", help="jämför två versioner")
    j.add_argument("a")
    j.add_argument("b")
    j.add_argument("--trad-a", default="dokument")
    j.add_argument("--trad-b")
    j.add_argument("--ut")
    j.set_defaults(f=cmd_compare)

    t = sp.add_parser("tre", help="gemensam bas + två parallella versioner")
    t.add_argument("bas")
    t.add_argument("a")
    t.add_argument("b")
    t.add_argument("--ut")
    t.set_defaults(f=cmd_three)

    n = sp.add_parser("info")
    n.add_argument("version")
    n.set_defaults(f=cmd_info)

    k = sp.add_parser("kontrollera")
    k.add_argument("version")
    k.set_defaults(f=cmd_validate)

    a = p.parse_args(argv)
    try:
        a.f(a)
    except VersionError as e:
        sys.exit("Fel: %s" % e)
