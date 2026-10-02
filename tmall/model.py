"""Datamodell för en version av mallen.

En version är en mapp med:
    meta.json        metadata om versionen
    nodes.jsonl      rubriker (identitet + egenskaper), en rad per rubrik
    blocks.jsonl     stycken/tabeller, en rad per block
    trees/<namn>.jsonl   träd = kanter (nod -> förälder, ordning); flera träd kan finnas

Nod och block har beständiga ID:n (N0001, B00001) som delas av alla versioner
som är matchade mot varandra. Det är ID:n som gör jämförelser möjliga.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict


def ws(s: str) -> str:
    """Normalisera blanktecken så att jämförelser inte påverkas av mellanrum."""
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VersionError(Exception):
    """Fel som beror på indata (okänd version eller träd), inte på ett programfel."""


def available_versions():
    d = os.path.join(REPO_ROOT, "versions")
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, "meta.json")))


def resolve_version_path(path: str) -> str:
    """Tar emot 'versions/13.0', '13.0' eller en annan mapp och ger mappen med meta.json."""
    p = path.strip().strip('"\'').rstrip("/\\")
    for cand in (p, os.path.join(REPO_ROOT, p), os.path.join(REPO_ROOT, "versions", p)):
        if os.path.isfile(os.path.join(cand, "meta.json")):
            return cand
    raise VersionError("Hittar ingen version '%s'. Tillgängliga versioner: %s. "
                       "Skriv till exempel 13.0 eller versions/13.0."
                       % (path, ", ".join(available_versions()) or "(inga)"))


class Version:
    """En inläst version."""

    def __init__(self, path: str):
        path = resolve_version_path(path)
        self.path = path
        self.meta = read_json(os.path.join(path, "meta.json"))
        self.label = self.meta.get("version", os.path.basename(path.rstrip("/\\")))
        self.nodes = {r["id"]: r for r in read_jsonl(os.path.join(path, "nodes.jsonl"))}
        self.blocks = {r["id"]: r for r in read_jsonl(os.path.join(path, "blocks.jsonl"))}
        self.trees: dict[str, dict] = {}
        tdir = os.path.join(path, "trees")
        if os.path.isdir(tdir):
            for fn in sorted(os.listdir(tdir)):
                if fn.endswith(".jsonl"):
                    rows = read_jsonl(os.path.join(tdir, fn))
                    self.trees[fn[:-6]] = {r["nod"]: r for r in rows}
        self._by_node = None

    # ---- block per nod -------------------------------------------------
    def blocks_of(self, nid):
        if self._by_node is None:
            d = defaultdict(list)
            for b in self.blocks.values():
                d[b["nod"]].append(b)
            for v in d.values():
                v.sort(key=lambda b: b["lopnr"])
            self._by_node = d
        return self._by_node.get(nid, [])

    # ---- träd ------------------------------------------------------------
    def tree(self, name="dokument"):
        if name not in self.trees:
            raise VersionError("Trädet '%s' finns inte i version %s. Tillgängliga träd: %s."
                               % (name, self.label, ", ".join(sorted(self.trees))))
        return self.trees[name]

    def children(self, name="dokument"):
        d = defaultdict(list)
        for nid, e in self.tree(name).items():
            d[e["foralder"]].append(nid)
        for k in d:
            d[k].sort(key=lambda n: self.tree(name)[n]["ordning"])
        return d

    def doc_order(self, name="dokument"):
        """Noder i dokumentordning (djupet först). Noder utanför trädet läggs sist."""
        ch = self.children(name)
        out, seen = [], set()

        def walk(p):
            for c in ch.get(p, []):
                if c in seen:
                    continue
                seen.add(c)
                out.append(c)
                walk(c)

        walk(None)
        out.extend(sorted(n for n in self.nodes if n not in seen))
        return out

    def section_of(self, nid, name="dokument"):
        """Översta förfader (avsnitt) i angivet träd."""
        t = self.trees.get(name, {})
        cur, guard = nid, 0
        while cur in t and t[cur]["foralder"] is not None and guard < 100:
            cur = t[cur]["foralder"]
            guard += 1
        return cur

    def label_of(self, nid):
        n = self.nodes.get(nid)
        if not n:
            return nid
        return n.get("titel") or nid


def node_title(kod, namn, variant):
    base = (kod + ". " if kod else "") + namn
    return (base + " " + variant).strip() if variant else base
