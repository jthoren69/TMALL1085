"""Test av hela kedjan: extrahera -> matcha mot baslinjen -> jämför.

Testet gör små, kända ändringar i en kopia av version 13.0 (text, rubriknamn, kod, flytt,
ny rubrik) och kontrollerar att jämförelsen hittar exakt dem och inget annat.

Kör:  python -m unittest discover -s tests -v
"""
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

from tmall.build import build_version
from tmall.diff import compare, compare3
from tmall.extract import HEADING_LEVEL, extract, q
from tmall.model import Version

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source", "TMALL1085_v13.0_2026-03-16.dotm")
BASE = os.path.join(ROOT, "versions", "13.0")


def ptext(p):
    return "".join(t.text or "" for t in p.iter(q("t")))


def set_text(p, new):
    ts = list(p.iter(q("t")))
    ts[0].text = new
    for t in ts[1:]:
        t.text = ""


def style(p):
    ps = p.find(q("pPr") + "/" + q("pStyle"))
    return ps.get(q("val")) if ps is not None else ""


def make_variant(dst, edit):
    with zipfile.ZipFile(SRC) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        body = root.find(q("body"))
        edit(body)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
            for item in z.infolist():
                data = z.read(item.filename)
                if item.filename == "word/document.xml":
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                out.writestr(item, data)


def find_p(body, text):
    for el in body:
        if el.tag == q("p") and ptext(el).strip() == text:
            return el
    raise AssertionError("hittar inte stycke: " + text)


def new_p(sty, text):
    p = ET.Element(q("p"))
    ppr = ET.SubElement(p, q("pPr"))
    ET.SubElement(ppr, q("pStyle")).set(q("val"), sty)
    r = ET.SubElement(p, q("r"))
    ET.SubElement(r, q("t")).text = text
    return p


def edit_a(body):
    # TEXT: ändrad, borttagen
    set_text(find_p(body, "Trafikmiljön ska ha en förlåtande utformning."),
             "Trafikmiljön ska ha en tydlig och förlåtande utformning.")
    body.remove(find_p(body, "Oskyddade trafikanters behov ska beaktas."))
    # STRUKTUR: rubriktext, kod
    set_text(find_p(body, "B3. Husverksamhet"), "B3. Husverksamhet och service")
    set_text(find_p(body, "FC51b Signalpunktstavla"), "FC51c Signalpunktstavla")
    # STRUKTUR + TEXT: ny rubrik med ett stycke före avsnitt C
    c = find_p(body, "C. BEFINTLIG MARK, MILJÖ OCH KONSTRUKTION")
    idx = list(body).index(c)
    body.insert(idx, new_p("Rubrik2", "B4. Ny verksamhet"))
    body.insert(idx + 1, new_p("Brdtext", "Ny kravtext för test."))
    # STRUKTUR: flytta rubrik med innehåll till annan förälder
    els = list(body)
    start = els.index(find_p(body, "DB11cc. Cykelbana"))
    end = start + 1
    while end < len(els) and not (els[end].tag == q("p") and style(els[end]) in HEADING_LEVEL):
        end += 1
    moved = els[start:end]
    for e in moved:
        body.remove(e)
    els = list(body)
    geo = els.index(find_p(body, "C1. Befintlig mark och miljö/ Geoteknik"))
    tgt = geo + 1
    while not (els[tgt].tag == q("p") and HEADING_LEVEL.get(style(els[tgt]), 9) <= 2):
        tgt += 1
    for k, e in enumerate(moved):
        body.insert(tgt + k, e)


def edit_b(body):
    set_text(find_p(body, "Trafikmiljön ska ha en förlåtande utformning."),
             "Trafikmiljön ska ha en förlåtande och trygg utformning.")   # krockar med A
    body.remove(find_p(body, "Oskyddade trafikanters behov ska beaktas."))  # samma som A


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "ids.json"), os.path.join(cls.tmp, "ids.json"))
        cls.base = Version(BASE)
        for name, fn in (("a", edit_a), ("b", edit_b)):
            doc = os.path.join(cls.tmp, name + ".docx")
            make_variant(doc, fn)
            out = os.path.join(cls.tmp, "v_" + name)
            os.makedirs(out)
            build_version(extract(doc), out, {"version": name.upper()},
                          os.path.join(cls.tmp, "ids.json"), cls.base)
        cls.A = Version(os.path.join(cls.tmp, "v_a"))
        cls.B = Version(os.path.join(cls.tmp, "v_b"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_baseline_is_sane(self):
        self.assertGreater(len(self.base.nodes), 700)
        self.assertGreater(len(self.base.blocks), 6000)
        self.assertEqual(set(self.base.trees), {"dokument", "kod"})
        for t in self.base.trees.values():
            self.assertEqual(set(t), set(self.base.nodes))

    def test_reextract_is_identical(self):
        out = os.path.join(self.tmp, "same")
        os.makedirs(out)
        build_version(extract(SRC), out, {"version": "same"}, os.path.join(self.tmp, "ids.json"), self.base)
        ch, s = compare(self.base, Version(out))
        self.assertEqual(ch, [])
        self.assertEqual(s["antal"], {"struktur": 0, "text": 0})

    def test_known_changes_found_and_nothing_else(self):
        ch, s = compare(self.base, self.A)
        got = Counter((c["kategori"], c["typ"]) for c in ch)
        want = Counter({
            ("text", "Ändrad text"): 1,
            ("text", "Borttagen text"): 1,
            ("text", "Ny text"): 1,
            ("struktur", "Rubriktext ändrad"): 1,
            ("struktur", "Kod ändrad"): 1,
            ("struktur", "Ny rubrik"): 1,
            ("struktur", "Rubrik flyttad"): 1,
        })
        self.assertEqual(got, want, "oväntade ändringar: %s" % [c["typ"] + " " + c["etikett"] for c in ch])
        by = {c["typ"]: c for c in ch}
        self.assertEqual(by["Rubrik flyttad"]["etikett"], "DB11cc. Cykelbana")
        self.assertIn("Geoteknik", by["Rubrik flyttad"]["efter"])
        self.assertTrue(by["Ny text"]["via_nod"])
        self.assertEqual(by["Kod ändrad"]["fore"], "FC51b")
        self.assertEqual(by["Kod ändrad"]["efter"], "FC51c")

    def test_ids_are_stable(self):
        ids_base = set(self.base.nodes)
        ids_a = set(self.A.nodes)
        self.assertEqual(len(ids_a - ids_base), 1)           # bara den nya rubriken
        self.assertEqual(len(ids_base - ids_a), 0)

    def test_backward_is_mirror(self):
        fwd, _ = compare(self.base, self.A)
        back, _ = compare(self.A, self.base)
        self.assertEqual(len(fwd), len(back))
        self.assertIn("Borttagen rubrik", {c["typ"] for c in back})

    def test_alternative_trees_in_same_version(self):
        ch, s = compare(self.base, self.base, "dokument", "kod")
        self.assertEqual(s["antal"]["text"], 0)
        self.assertGreater(s["antal"]["struktur"], 100)
        self.assertEqual({c["typ"] for c in ch} - {"Rubrik flyttad", "Rubrik omordnad"}, set())

    def test_version_name_is_resolved(self):
        from tmall.model import VersionError
        self.assertEqual(Version("13.0").label, "13.0")
        self.assertEqual(Version("versions/13.0/").label, "13.0")
        with self.assertRaises(VersionError) as cm:
            Version("99.9")
        self.assertIn("13.0", str(cm.exception))
        with self.assertRaises(VersionError):
            self.base.tree("finns-inte")

    def test_three_way(self):
        rows = {(r["slag"], r["id"]): r["status"] for r in compare3(self.base, self.A, self.B)}
        self.assertEqual(rows[("block", "B00870")], "KONFLIKT")
        self.assertEqual(rows[("block", "B00871")], "samma ändring")
        self.assertEqual(rows[("rubrik", "N0128")], "bara i A")


if __name__ == "__main__":
    unittest.main()
