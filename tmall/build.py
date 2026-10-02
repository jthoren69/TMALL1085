"""Tilldelar beständiga ID:n och skriver en versionsmapp.

Utan baslinje får alla noder och block nya ID:n (så skapas baslinjen).
Med baslinje matchas varje nod och block mot den tidigare versionen så att samma
rubrik/stycke behåller sitt ID. Det är den matchningen som gör att en ändring kan
visas som *ändrad* i stället för som *borttagen + ny*.

Matchningen är heuristisk. Allt som inte är ett exakt träffat skrivs till
`granska.jsonl` i versionsmappen så att en människa kan kontrollera det.
"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from difflib import SequenceMatcher

from . import __version__
from .model import Version, node_title, read_json, write_json, write_jsonl, ws

FUZZY_NODE = 0.80       # likhet för rubriker som bytt namn under samma förälder
FUZZY_BLOCK = 0.60      # likhet för stycken inom samma rubrik
FUZZY_MOVED = 0.85      # likhet för stycken som flyttats till annan rubrik
MAX_CROSS_PAIRS = 3_000_000


def text_hash(text: str) -> str:
    return hashlib.sha1(ws(text).encode("utf-8")).hexdigest()[:12]


def _ratio(a: str, b: str) -> float:
    if a == b:
        return 1.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < 0.4 or sm.quick_ratio() < 0.4:
        return 0.0
    return sm.ratio()


class IdMinter:
    def __init__(self, path):
        self.path = path
        self.state = read_json(path) if os.path.exists(path) else {"nod": 0, "block": 0}

    def node(self):
        self.state["nod"] += 1
        return "N%04d" % self.state["nod"]

    def block(self):
        self.state["block"] += 1
        return "B%05d" % self.state["block"]

    def save(self):
        write_json(self.path, self.state)


# ---------------------------------------------------------------------------
# Noder
# ---------------------------------------------------------------------------

def match_nodes(new_nodes, new_parent, base: Version):
    """Returnerar (map tmp-id -> basens id, hur)."""
    base_order = base.doc_order("dokument")
    base_parent = {n: e["foralder"] for n, e in base.tree("dokument").items()}
    mapped, how, used = {}, {}, set()

    def free(ids):
        return [i for i in ids if i not in used]

    # pass 1: exakt (kod, variant, namn). Vid dubbletter avgör föräldern.
    exact = defaultdict(list)
    for i in base_order:
        n = base.nodes[i]
        exact[(n["kod"], n["variant"], n["namn"])].append(i)
    for n in new_nodes:
        cands = free(exact.get((n["kod"], n["variant"], n["namn"]), []))
        if not cands:
            continue
        pick = cands[0]
        if len(cands) > 1:
            pp = mapped.get(new_parent.get(n["id"]))
            for c in cands:
                if base_parent.get(c) == pp:
                    pick = c
                    break
        mapped[n["id"]], how[n["id"]] = pick, "exakt"
        used.add(pick)

    def second_pass(keyf, label, need):
        idx = defaultdict(list)
        for i in base_order:
            if i not in used:
                idx[keyf(base.nodes[i])].append(i)
        for n in new_nodes:
            if n["id"] in mapped or not need(n):
                continue
            cands = free(idx.get(keyf(n), []))
            if not cands:
                continue
            pp = mapped.get(new_parent.get(n["id"]))
            pick = next((c for c in cands if base_parent.get(c) == pp), cands[0])
            mapped[n["id"]], how[n["id"]] = pick, label
            used.add(pick)

    # pass 2: samma kod och variant men ny rubriktext
    second_pass(lambda n: (n["kod"], n["variant"]), "rubriktext ändrad", lambda n: bool(n["kod"]))
    # pass 3: samma namn och variant men ny kod
    second_pass(lambda n: (n["namn"], n["variant"]), "kod ändrad", lambda n: len(n["namn"]) >= 4)

    # pass 4: likhet inom samma förälder
    by_parent = defaultdict(list)
    for i in base_order:
        if i not in used:
            by_parent[base_parent.get(i)].append(i)
    for n in new_nodes:
        if n["id"] in mapped:
            continue
        pp = mapped.get(new_parent.get(n["id"]))
        label = node_title(n["kod"], n["namn"], n["variant"])
        best, best_r = None, FUZZY_NODE
        for c in free(by_parent.get(pp, [])):
            bn = base.nodes[c]
            r = _ratio(label, node_title(bn["kod"], bn["namn"], bn["variant"]))
            if r > best_r:
                best, best_r = c, r
        if best:
            mapped[n["id"]], how[n["id"]] = best, "likhet %.2f" % best_r
            used.add(best)
    return mapped, how


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

def _align_node_blocks(base_list, new_list, pairs, used_base, how):
    a = [text_hash(b["text"]) for b in base_list]
    b = [text_hash(x["text"]) for x in new_list]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    anchored = []
    for m in sm.get_matching_blocks():
        for k in range(m.size):
            pairs[new_list[m.b + k]["id"]] = base_list[m.a + k]["id"]
            used_base.add(base_list[m.a + k]["id"])
            how[new_list[m.b + k]["id"]] = "exakt"
        anchored.append((m.a, m.b, m.size))
    # luckor mellan ankare: para ihop liknande stycken i ordning
    prev_a = prev_b = 0
    for (ma, mb, size) in anchored:
        gap_a = list(range(prev_a, ma))
        gap_b = list(range(prev_b, mb))
        last = -1
        for j in gap_b:
            nb = new_list[j]
            best, best_r = None, FUZZY_BLOCK
            for i in gap_a:
                if i <= last or base_list[i]["id"] in used_base:
                    continue
                r = _ratio(ws(base_list[i]["text"]), ws(nb["text"]))
                if r > best_r:
                    best, best_r = i, r
            if best is not None:
                pairs[nb["id"]] = base_list[best]["id"]
                used_base.add(base_list[best]["id"])
                how[nb["id"]] = "likhet %.2f" % best_r
                last = best
        prev_a, prev_b = ma + size, mb + size


def match_blocks(new_blocks_by_node, node_map, base: Version):
    pairs, how, used_base = {}, {}, set()
    left_new = []
    for tmp_node, new_list in new_blocks_by_node.items():
        bn = node_map.get(tmp_node)
        base_list = base.blocks_of(bn) if bn else []
        _align_node_blocks(base_list, new_list, pairs, used_base, how)
        left_new.extend(x for x in new_list if x["id"] not in pairs)

    left_base = [b for b in base.blocks.values() if b["id"] not in used_base]

    # flyttade stycken: exakt text i annan rubrik
    by_hash = defaultdict(list)
    for b in sorted(left_base, key=lambda x: x["id"]):
        by_hash[text_hash(b["text"])].append(b["id"])
    rest = []
    for x in left_new:
        lst = [i for i in by_hash.get(text_hash(x["text"]), []) if i not in used_base]
        if lst:
            pairs[x["id"]] = lst[0]
            used_base.add(lst[0])
            how[x["id"]] = "flyttad"
        else:
            rest.append(x)
    left_base = [b for b in left_base if b["id"] not in used_base]

    # flyttade och ändrade: likhet över rubrikgränser (hoppas över om för stort)
    if len(rest) * len(left_base) <= MAX_CROSS_PAIRS:
        for x in rest:
            best, best_r = None, FUZZY_MOVED
            tx = ws(x["text"])
            if len(tx) < 40:
                continue
            for b in left_base:
                if b["id"] in used_base:
                    continue
                r = _ratio(ws(b["text"]), tx)
                if r > best_r:
                    best, best_r = b, r
            if best:
                pairs[x["id"]] = best["id"]
                used_base.add(best["id"])
                how[x["id"]] = "flyttad+ändrad %.2f" % best_r
    return pairs, how


# ---------------------------------------------------------------------------
# Bygg och skriv
# ---------------------------------------------------------------------------

def build_version(raw, out_dir, meta, ids_path, base: Version | None = None):
    minter = IdMinter(ids_path)
    new_parent = {e["nod"]: e["foralder"] for e in raw.trees["dokument"]}

    node_map, node_how = ({}, {})
    if base is not None:
        node_map, node_how = match_nodes(raw.nodes, new_parent, base)
    final_node = {}
    for n in raw.nodes:                       # dokumentordning => stabil tilldelning
        final_node[n["id"]] = node_map.get(n["id"]) or minter.node()

    blocks_by_node = defaultdict(list)
    for b in raw.blocks:
        blocks_by_node[b["nod"]].append(b)
    block_map, block_how = ({}, {})
    if base is not None:
        block_map, block_how = match_blocks(blocks_by_node, node_map, base)
    final_block = {}
    for b in raw.blocks:
        final_block[b["id"]] = block_map.get(b["id"]) or minter.block()

    os.makedirs(os.path.join(out_dir, "trees"), exist_ok=True)

    nodes_out = []
    for n in raw.nodes:
        r = {k: v for k, v in n.items()}
        r["id"] = final_node[n["id"]]
        nodes_out.append(r)
    blocks_out = []
    for b in raw.blocks:
        r = dict(b)
        r["id"] = final_block[b["id"]]
        r["nod"] = final_node[b["nod"]]
        r["hash"] = text_hash(b["text"])
        blocks_out.append(r)

    write_jsonl(os.path.join(out_dir, "nodes.jsonl"), sorted(nodes_out, key=lambda r: r["id"]))
    write_jsonl(os.path.join(out_dir, "blocks.jsonl"), sorted(blocks_out, key=lambda r: r["id"]))
    for name, edges in raw.trees.items():
        rows = [{"nod": final_node[e["nod"]],
                 "foralder": final_node[e["foralder"]] if e["foralder"] else None,
                 "ordning": e["ordning"]} for e in edges]
        write_jsonl(os.path.join(out_dir, "trees", name + ".jsonl"), sorted(rows, key=lambda r: r["nod"]))

    # granskningslista: allt som inte är exakt träff eller ny utan baslinje
    review = []
    if base is not None:
        for n in raw.nodes:
            h = node_how.get(n["id"], "ny")
            if h != "exakt":
                review.append({"typ": "nod", "id": final_node[n["id"]], "hur": h,
                               "titel": n["titel"][:100]})
        for b in raw.blocks:
            h = block_how.get(b["id"], "ny")
            if h != "exakt":
                review.append({"typ": "block", "id": final_block[b["id"]], "hur": h,
                               "text": ws(b["text"])[:100]})
    if base is not None:
        write_jsonl(os.path.join(out_dir, "granska.jsonl"), review)

    def count(d, label):
        c = defaultdict(int)
        for v in d.values():
            c[v.split(" ")[0] if v.startswith("likhet") else v] += 1
        return dict(c)

    matchning = None
    if base is not None:
        nn = count(node_how, "nod")
        nn["ny"] = len(raw.nodes) - len(node_how)
        bb = count(block_how, "block")
        bb["ny"] = len(raw.blocks) - len(block_how)
        matchning = {"noder": nn, "block": bb,
                     "borttagna_noder": len(set(base.nodes) - set(node_map.values())),
                     "borttagna_block": len(set(base.blocks) - set(block_map.values()))}

    types = defaultdict(int)
    for b in raw.blocks:
        types[b["typ"]] += 1
    meta = dict(meta)
    meta.update({
        "extraherad_med": "tmall " + __version__,
        "tradar": sorted(raw.trees),
        "antal": {"noder": len(raw.nodes), "block": len(raw.blocks), "blocktyper": dict(types)},
        "kodtrad": raw.stats.get("kodtrad"),
        "matchning": matchning,
    })
    write_json(os.path.join(out_dir, "meta.json"), meta)
    minter.save()
    return meta
