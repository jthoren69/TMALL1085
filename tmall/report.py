"""Rapporter: Markdown, HTML och CSV (öppnas i Excel) ur en lista med ändringar."""
from __future__ import annotations

import csv
import html
import os

from .diff import STRUKTUR, TEXT


def _md_diff(diff):
    out = []
    for tag, t in diff:
        if tag == "eq":
            out.append(t)
        elif tag == "del":
            out.append("~~" + t.strip() + "~~ " if t.strip() else "")
        else:
            out.append("**" + t.strip() + "** " if t.strip() else "")
    return "".join(out).strip()


def _html_diff(diff):
    out = []
    for tag, t in diff:
        e = html.escape(t)
        out.append(e if tag == "eq" else ("<del>%s</del>" % e if tag == "del" else "<ins>%s</ins>" % e))
    return "".join(out)


def _by_section(ch):
    d = {}
    for c in ch:
        d.setdefault(c["sektion"], []).append(c)
    return d


def _title(summary):
    t = "TMALL 1085: %s → %s" % (summary["a"], summary["b"])
    if summary["tradA"] != summary["tradB"] or summary["a"] == summary["b"]:
        t += " (träd %s ↔ %s)" % (summary["tradA"], summary["tradB"])
    return t


def _detail_visible(c):
    return not c["via_nod"]


def write_markdown(path, ch, summary):
    L = ["# " + _title(summary), ""]
    L += ["Träd A: `%s` i version %s. Träd B: `%s` i version %s." %
          (summary["tradA"], summary["a"], summary["tradB"], summary["b"]),
          "Noder %d → %d. Block %d → %d." % (summary["noder"]["a"], summary["noder"]["b"],
                                           summary["block"]["a"], summary["block"]["b"]), ""]
    L += ["## Sammanfattning", "",
          "| Slag | Antal |", "|---|---:|",
          "| Strukturändringar (rubriker, uppbyggnad) | %d |" % summary["antal"][STRUKTUR],
          "| Textändringar (innehåll) | %d |" % summary["antal"][TEXT], ""]
    for kat, namn in ((STRUKTUR, "Struktur"), (TEXT, "Text")):
        pt = summary["per_typ"][kat]
        if pt:
            L += ["**%s per typ**" % namn, "", "| Typ | Antal |", "|---|---:|"]
            L += ["| %s | %d |" % (k, v) for k, v in sorted(pt.items(), key=lambda kv: -kv[1])] + [""]
    if summary["per_sektion"]:
        L += ["**Per avsnitt**", "", "| Avsnitt | Struktur | Text |", "|---|---:|---:|"]
        for s, v in summary["per_sektion"].items():
            L.append("| %s | %d | %d |" % (s, v[STRUKTUR], v[TEXT]))
        L.append("")
    for kat, rubrik in ((STRUKTUR, "Strukturändringar"), (TEXT, "Textändringar")):
        sel = [c for c in ch if c["kategori"] == kat]
        if not sel:
            continue
        L += ["## " + rubrik, ""]
        for sek, items in _by_section(sel).items():
            L += ["### " + sek, ""]
            hidden = sum(1 for c in items if not _detail_visible(c))
            for c in items:
                if not _detail_visible(c):
                    continue
                head = "- **%s** – %s `%s`" % (c["typ"], c["etikett"], c["id"])
                if kat == TEXT and c["typ"] == "Ändrad text":
                    L += [head, "  " + _md_diff(c["diff"])]
                else:
                    det = []
                    if c["fore"]:
                        det.append("före: " + c["fore"][:300].replace("\n", " "))
                    if c["efter"]:
                        det.append("efter: " + c["efter"][:300].replace("\n", " "))
                    L.append(head + ((" – " + "; ".join(det)) if det else ""))
            if hidden:
                L.append("- (%d stycken ingår i nya eller borttagna rubriker ovan, se CSV)" % hidden)
            L.append("")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")


_CSS = """body{font-family:Segoe UI,Arial,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}
table{border-collapse:collapse;margin:.5em 0}td,th{border:1px solid #ccc;padding:.25em .6em;text-align:left}
th{background:#f2f2f2}td.n{text-align:right}ins{background:#d4f7d4;text-decoration:none}del{background:#fbd5d5}
details{margin:.4em 0}summary{cursor:pointer;font-weight:600}.c{margin:.35em 0 .35em 1em}
.t{font-size:.8em;background:#eef;border-radius:3px;padding:0 .4em;margin-right:.4em}.id{color:#888;font-size:.8em}
.s{background:#fff3cd}.x{background:#e2f0ff}"""


def write_html(path, ch, summary):
    e = html.escape
    H = ["<!doctype html><meta charset='utf-8'><title>%s</title><style>%s</style>" % (e(_title(summary)), _CSS),
         "<h1>%s</h1>" % e(_title(summary)),
         "<p>Träd A: <code>%s</code> (version %s). Träd B: <code>%s</code> (version %s).</p>" %
         (e(summary["tradA"]), e(summary["a"]), e(summary["tradB"]), e(summary["b"])),
         "<table><tr><th>Slag</th><th>Antal</th></tr><tr><td>Strukturändringar</td><td class=n>%d</td></tr>"
         "<tr><td>Textändringar</td><td class=n>%d</td></tr></table>" %
         (summary["antal"][STRUKTUR], summary["antal"][TEXT])]
    for kat, namn in ((STRUKTUR, "Struktur"), (TEXT, "Text")):
        pt = summary["per_typ"][kat]
        if pt:
            H.append("<table><tr><th>%s – typ</th><th>Antal</th></tr>%s</table>" % (namn, "".join(
                "<tr><td>%s</td><td class=n>%d</td></tr>" % (e(k), v)
                for k, v in sorted(pt.items(), key=lambda kv: -kv[1]))))
    if summary["per_sektion"]:
        H.append("<table><tr><th>Avsnitt</th><th>Struktur</th><th>Text</th></tr>%s</table>" % "".join(
            "<tr><td>%s</td><td class=n>%d</td><td class=n>%d</td></tr>" % (e(s), v[STRUKTUR], v[TEXT])
            for s, v in summary["per_sektion"].items()))
    for kat, rubrik, cls in ((STRUKTUR, "Strukturändringar", "s"), (TEXT, "Textändringar", "x")):
        sel = [c for c in ch if c["kategori"] == kat]
        if not sel:
            continue
        H.append("<h2>%s</h2>" % rubrik)
        for sek, items in _by_section(sel).items():
            H.append("<details><summary>%s (%d)</summary>" % (e(sek), len(items)))
            hidden = 0
            for c in items:
                if not _detail_visible(c):
                    hidden += 1
                    continue
                body = ""
                if c["typ"] == "Ändrad text" and c["diff"]:
                    body = "<div>%s</div>" % _html_diff(c["diff"])
                else:
                    if c["fore"]:
                        body += "<div>före: <del>%s</del></div>" % e(c["fore"][:600])
                    if c["efter"]:
                        body += "<div>efter: <ins>%s</ins></div>" % e(c["efter"][:600])
                H.append("<div class=c><span class='t %s'>%s</span><b>%s</b> <span class=id>%s</span>%s</div>" %
                         (cls, e(c["typ"]), e(c["etikett"]), e(c["id"]), body))
            if hidden:
                H.append("<div class=c><i>%d stycken ingår i nya eller borttagna rubriker (se CSV).</i></div>" % hidden)
            H.append("</details>")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(H))


def write_csv(path, ch):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:   # BOM så Excel läser å, ä, ö rätt
        w = csv.writer(f, delimiter=";")
        w.writerow(["slag", "typ", "id", "avsnitt", "rubrik", "före", "efter", "ingår_i_ny_eller_borttagen_rubrik"])
        for c in ch:
            w.writerow([c["kategori"], c["typ"], c["id"], c["sektion"], c["etikett"],
                        c["fore"], c["efter"], "ja" if c["via_nod"] else ""])


def write_all(outdir, ch, summary):
    os.makedirs(outdir, exist_ok=True)
    write_markdown(os.path.join(outdir, "rapport.md"), ch, summary)
    write_html(os.path.join(outdir, "rapport.html"), ch, summary)
    write_csv(os.path.join(outdir, "andringar.csv"), ch)


def write_markdown3(path, rows, base, a, b):
    L = ["# Trevägsjämförelse: bas %s, A = %s, B = %s" % (base, a, b), "",
         "| Status | Rubriker | Block |", "|---|---:|---:|"]
    for st in ("KONFLIKT", "samma ändring", "bara i A", "bara i B"):
        L.append("| %s | %d | %d |" % (st, sum(1 for r in rows if r["status"] == st and r["slag"] == "rubrik"),
                                      sum(1 for r in rows if r["status"] == st and r["slag"] == "block")))
    L.append("")
    for st in ("KONFLIKT", "samma ändring", "bara i A", "bara i B"):
        sel = [r for r in rows if r["status"] == st]
        if not sel:
            continue
        L += ["## " + st, ""]
        for r in sel:
            L.append("- %s `%s` – %s" % (r["slag"], r["id"], r["etikett"]))
            if st == "KONFLIKT":
                L += ["  - bas: " + r["bas"][:200], "  - A: " + r["a"][:200], "  - B: " + r["b"][:200]]
        L.append("")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
