#!/usr/bin/env python3
"""spec_coverage.py — Spec <-> backlog coverage gate for the UnBubble level-up.

Closes the failure mode where a requirement is DOCUMENTED but no task ever owns
it, so the rebuild "finishes" without it. Seen in practice: features
written in `07-business-rules.md` and in the PRD that no BACKLOG story cited were
simply not built — and nobody noticed until users did.

`parity_check.py` guards a different, LATER hop (migrated schema vs. the code
that was actually written). This script guards the EARLIER one, before a single
line is implemented:

    inventory -> docs/PRD (requirements) -> BACKLOG (stories) -> code
                                        ^^^^ here

Checks (the first three are GATES, exit code 1):
  1. Forward coverage  — every requirement id is cited by at least one story.
  2. No orphan stories — every story cites at least one requirement id.
  3. Atomicity         — no story is left undecomposed (size `G`, or text
                         saying "quebrar"/"break later"/"decompor").
  4. Verifiability     — every requirement carries an acceptance criterion
                         (`Aceite:`/`Acceptance:`) or is written in EARS form
                         (QUANDO ... DEVE / WHEN ... SHALL). Warning by default;
                         `--strict-acceptance` promotes it to a gate. A purely
                         descriptive requirement opts out with `[descritivo]`
                         (or `[descriptive]`) on its definition line.

Coverage follows the real traceability chain, so it does not cry wolf:
  * ranges and lists expand — `BR-020…023`, `P-DOC-1...5`, `P-ORG-1/2`;
  * coverage is TRANSITIVE — a story citing `P-DOC-1` covers the `BR-010` that
    `P-DOC-1` derives from, and the report shows the chain;
  * a story that legitimately implements no product requirement (bootstrap,
    migration, cutover) opts out with `[infra]` on its bullet — a conscious
    marker, never a silent orphan.

Deterministic and dependency-free (Python 3.8+, stdlib only). Read-only.

Usage:
  python3 spec_coverage.py --spec docs/07-business-rules.md \
                           --spec levelup/PRD-v2.md \
                           --backlog levelup/BACKLOG.md \
                           [--out levelup] [--strict-acceptance] [--warn-only]

Outputs: spec-coverage.md (human) + spec-coverage.json (machine), plus a stdout
summary. Exit 0 = pass, 1 = gate failure (unless --warn-only).
"""

import argparse
import json
import os
import re
import sys

# Requirement ids: BR-001 (business rule) and P-DOC-1 / U-SEC-2 (PRD parity and
# upgrade requirements). Kept configurable because other packs may name them
# differently.
DEFAULT_ID_PATTERN = r"(?:BR-\d{2,4}|[A-Z]-[A-Z]{2,8}-\d{1,3})"

# A story bullet: "- **F-1 (P)** ..." / "- **DOM-DOC (G→quebrar)** ..." / "- **MIG-6** ..."
STORY_RE = re.compile(
    r"^\s*[-*+]\s*\*\*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\s*(?:\(([^)]*)\))?\s*\*\*"
)

ACCEPTANCE_RE = re.compile(r"\b(aceite|aceita[çc][ãa]o|acceptance|crit[ée]rio de aceite)\b", re.I)
EARS_RE = re.compile(
    r"\b(QUANDO|WHEN|SE|IF)\b.{0,500}?\b(DEVE|SHALL|MUST|ENT[ÃA]O|THEN)\b", re.I | re.S
)
DESCRIPTIVE_RE = re.compile(r"\[(descritivo|descriptive)\]", re.I)
INFRA_RE = re.compile(r"\[(infra|infraestrutura|infrastructure)\]", re.I)

# Story size/marker meaning "not decomposed yet".
NON_ATOMIC_SIZE_RE = re.compile(r"^\s*G\b|\bG\s*(?:→|->|=>)", re.I)
NON_ATOMIC_TEXT_RE = re.compile(r"\b(quebrar|decompor|break later|to split|split later)\b", re.I)


def build_regexes(id_pattern):
    ident = re.compile(r"\b" + id_pattern + r"\b")
    # "- **BR-021 — ...", "### BR-021", "**P-DOC-1** ..." -> a DEFINITION line
    definition = re.compile(
        r"^\s*(?:[-*+]\s*)?(?:#{1,6}\s*)?(?:\*\*|__)?\s*(" + id_pattern + r")\b"
    )
    # "BR-020…023", "P-DOC-1...5", "U-REL-1–6"
    rng = re.compile(r"\b(" + id_pattern + r")\s*(?:…|\.{2,3}|–|—)\s*(\d{1,4})\b")
    # "P-ORG-1/2", "U-SEC-1/2/3"
    slashed = re.compile(r"\b(" + id_pattern + r")((?:\s*/\s*\d{1,4})+)")
    return ident, definition, rng, slashed


def _split_stem(req_id):
    stem = re.match(r"^(.*?)(\d+)$", req_id)
    if not stem:
        return None, None, None
    prefix, first = stem.group(1), stem.group(2)
    return prefix, first, len(first)


def expand_ids(text, ident_re, range_re, slash_re):
    """Every requirement id in `text`, expanding `N…M` ranges and `N/M` lists."""
    ids = set(ident_re.findall(text))

    for match in range_re.finditer(text):
        prefix, first, width = _split_stem(match.group(1))
        if prefix is None:
            continue
        try:
            lo, hi = int(first), int(match.group(2))
        except ValueError:
            continue
        if hi < lo or hi - lo > 200:  # guard against nonsense ranges
            continue
        for num in range(lo, hi + 1):
            ids.add(f"{prefix}{str(num).zfill(width)}")

    for match in slash_re.finditer(text):
        prefix, _first, width = _split_stem(match.group(1))
        if prefix is None:
            continue
        for part in re.findall(r"\d{1,4}", match.group(2)):
            ids.add(f"{prefix}{part.zfill(width)}")

    return ids


def parse_spec(path, regexes):
    """Return {req_id: {"file","line","block","descriptive","cites"}}.

    `cites` are the OTHER requirement ids named inside the definition block —
    e.g. PRD `P-DOC-1` citing `BR-010` — which is the traceability edge used to
    propagate coverage transitively.
    """
    ident_re, definition_re, range_re, slash_re = regexes
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()

    defs = []  # (id, line_no, start_index)
    for index, line in enumerate(lines):
        match = definition_re.match(line)
        if match:
            defs.append((match.group(1), index + 1, index))

    found = {}
    for position, (req_id, line_no, start) in enumerate(defs):
        end = defs[position + 1][2] if position + 1 < len(defs) else len(lines)
        block = "".join(lines[start:end])
        found[req_id] = {
            "file": os.path.basename(path),
            "line": line_no,
            "block": block,
            "descriptive": bool(DESCRIPTIVE_RE.search(lines[start])),
            "cites": expand_ids(block, ident_re, range_re, slash_re) - {req_id},
        }
    return found


def parse_backlog(path, regexes):
    """Return list of stories: {id,size,line,text,cites,non_atomic,infra}."""
    ident_re, _definition_re, range_re, slash_re = regexes
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()

    starts = []
    for index, line in enumerate(lines):
        match = STORY_RE.match(line)
        if match:
            starts.append((match.group(1), match.group(2) or "", index))

    stories = []
    for position, (story_id, size, start) in enumerate(starts):
        end = starts[position + 1][2] if position + 1 < len(starts) else len(lines)
        text = "".join(lines[start:end])
        non_atomic = bool(NON_ATOMIC_SIZE_RE.search(size) or NON_ATOMIC_TEXT_RE.search(text))
        stories.append(
            {
                "id": story_id,
                "size": size.strip(),
                "line": start + 1,
                "text": text,
                "cites": expand_ids(text, ident_re, range_re, slash_re),
                "non_atomic": non_atomic,
                "infra": bool(INFRA_RE.search(text)),
            }
        )
    return stories


def propagate_coverage(direct, spec_cites):
    """Transitive closure: covering X also covers what X derives from.

    Returns {req_id: parent_id_or_None} — None means covered directly by a story.
    """
    covered = {req: None for req in direct}
    queue = list(direct)
    while queue:
        current = queue.pop(0)
        for child in spec_cites.get(current, ()):  # noqa: B007
            if child not in covered:
                covered[child] = current
                queue.append(child)
    return covered


def has_verifiable_form(block):
    return bool(ACCEPTANCE_RE.search(block) or EARS_RE.search(block))


def main():
    parser = argparse.ArgumentParser(description="Spec<->backlog coverage gate.")
    parser.add_argument("--spec", action="append", required=True,
                        help="requirement source (repeatable): docs/07-…, PRD-v2.md")
    parser.add_argument("--backlog", required=True, help="BACKLOG.md path")
    parser.add_argument("--out", default=".", help="output directory")
    parser.add_argument("--id-pattern", default=DEFAULT_ID_PATTERN,
                        help="regex for requirement ids")
    parser.add_argument("--strict-acceptance", action="store_true",
                        help="missing acceptance criteria fails the gate too")
    parser.add_argument("--warn-only", action="store_true",
                        help="always exit 0 (report without gating)")
    args = parser.parse_args()

    regexes = build_regexes(args.id_pattern)

    requirements = {}
    for spec_path in args.spec:
        if not os.path.exists(spec_path):
            print(f"spec not found: {spec_path}", file=sys.stderr)
            sys.exit(2)
        for req_id, meta in parse_spec(spec_path, regexes).items():
            requirements.setdefault(req_id, meta)

    if not requirements:
        print("No requirement ids found in --spec files. Check --id-pattern.", file=sys.stderr)
        sys.exit(2)

    stories = parse_backlog(args.backlog, regexes)
    if not stories:
        print(f"No stories parsed from {args.backlog}.", file=sys.stderr)
        sys.exit(2)

    known = set(requirements)
    cited = set()
    for story in stories:
        cited |= story["cites"]

    direct_by = {req: sorted(s["id"] for s in stories if req in s["cites"])
                 for req in requirements}
    direct = {req for req, owners in direct_by.items() if owners}
    spec_cites = {req: (meta["cites"] & known) for req, meta in requirements.items()}
    covered_via = propagate_coverage(direct, spec_cites)

    covered_by = {}
    for req in requirements:
        if direct_by[req]:
            covered_by[req] = {"how": "direct", "stories": direct_by[req]}
        elif req in covered_via:
            parent = covered_via[req]
            covered_by[req] = {"how": "indirect", "via": parent,
                               "stories": direct_by.get(parent, [])}
        else:
            covered_by[req] = {"how": "none", "stories": []}

    uncovered = sorted(req for req, info in covered_by.items() if info["how"] == "none")
    indirect_count = sum(1 for info in covered_by.values() if info["how"] == "indirect")
    orphan_stories = sorted(
        s["id"] for s in stories if not s["infra"] and not (s["cites"] & known)
    )
    infra_stories = sorted(s["id"] for s in stories if s["infra"])
    non_atomic = sorted((s["id"], s["size"]) for s in stories if s["non_atomic"])
    unknown_citations = sorted(cited - known)
    missing_acceptance = sorted(
        req for req, meta in requirements.items()
        if not meta["descriptive"] and not has_verifiable_form(meta["block"])
    )

    total = len(requirements)
    covered = total - len(uncovered)
    coverage_pct = round(100.0 * covered / total, 1) if total else 100.0
    verifiable = total - len(missing_acceptance)

    gate_failed = bool(uncovered or orphan_stories or non_atomic) or (
        args.strict_acceptance and bool(missing_acceptance)
    )

    summary = {
        "requirements_total": total,
        "requirements_covered": covered,
        "requirements_covered_indirectly": indirect_count,
        "coverage_pct": coverage_pct,
        "stories_total": len(stories),
        "stories_marked_infra": len(infra_stories),
        "orphan_stories": len(orphan_stories),
        "non_atomic_stories": len(non_atomic),
        "requirements_verifiable": verifiable,
        "requirements_missing_acceptance": len(missing_acceptance),
        "unknown_citations": len(unknown_citations),
        "strict_acceptance": args.strict_acceptance,
        "gate": "FAIL" if gate_failed else "PASS",
    }

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "spec-coverage.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "summary": summary,
                "uncovered_requirements": uncovered,
                "orphan_stories": orphan_stories,
                "infra_stories": infra_stories,
                "non_atomic_stories": [{"id": i, "size": s} for i, s in non_atomic],
                "requirements_missing_acceptance": missing_acceptance,
                "unknown_citations": unknown_citations,
                "coverage": {req: owners for req, owners in sorted(covered_by.items())},
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )

    out = []
    out.append("# Spec coverage — requisitos vs. backlog\n\n")
    out.append(
        f"- Requisitos: **{total}** · cobertos: **{covered}** (**{coverage_pct}%**) "
        f"— {covered - indirect_count} direto, {indirect_count} via requisito derivado\n"
        f"- Stories: **{len(stories)}** · órfãs: **{len(orphan_stories)}** · "
        f"marcadas `[infra]`: {len(infra_stories)} · "
        f"não decompostas: **{len(non_atomic)}**\n"
        f"- Verificáveis (aceite ou forma EARS): **{verifiable}/{total}**\n"
        f"- **Gate: {summary['gate']}**"
        f"{' (strict-acceptance)' if args.strict_acceptance else ''}\n"
    )

    out.append("\n## 1 · Requisitos sem story que os execute (GATE)\n\n")
    if uncovered:
        out.append("Cada linha é uma feature documentada que ninguém vai construir:\n\n")
        for req in uncovered:
            meta = requirements[req]
            out.append(f"- `{req}` — definido em {meta['file']}:{meta['line']}\n")
    else:
        out.append("_Nenhum. Todo requisito tem ao menos uma story._\n")

    out.append("\n## 2 · Stories que não citam requisito (GATE)\n\n")
    if orphan_stories:
        out.append(
            "Story sem requisito = escopo inventado ou rastreabilidade perdida. "
            "Se ela é fundação/migração/cutover (não implementa requisito de produto), "
            "marque `[infra]` na story:\n\n"
        )
        for story_id in orphan_stories:
            out.append(f"- `{story_id}`\n")
    else:
        out.append("_Nenhuma._\n")
    if infra_stories:
        out.append(
            f"\n_{len(infra_stories)} story(s) marcada(s) `[infra]` (isentas): "
            + ", ".join(f"`{s}`" for s in infra_stories)
            + "._\n"
        )

    out.append("\n## 3 · Stories não decompostas (GATE)\n\n")
    if non_atomic:
        out.append("Story grande é onde o executor improvisa — decomponha antes de entregar:\n\n")
        for story_id, size in non_atomic:
            out.append(f"- `{story_id}` (tamanho: {size or '—'})\n")
    else:
        out.append("_Nenhuma._\n")

    out.append(
        "\n## 4 · Requisitos sem forma verificável"
        f" ({'GATE' if args.strict_acceptance else 'aviso'})\n\n"
    )
    if missing_acceptance:
        out.append(
            "Sem `Aceite:` nem forma EARS (QUANDO … DEVE). Reescreva o comportamento "
            "de forma testável ou marque `[descritivo]` se for contexto, não regra:\n\n"
        )
        for req in missing_acceptance:
            meta = requirements[req]
            out.append(f"- `{req}` — {meta['file']}:{meta['line']}\n")
    else:
        out.append("_Nenhum._\n")

    if unknown_citations:
        out.append("\n## 5 · Citações a requisitos inexistentes (aviso)\n\n")
        out.append("O backlog cita ids que nenhum spec define — typo ou requisito removido:\n\n")
        for req in unknown_citations:
            out.append(f"- `{req}`\n")

    out.append(
        "\n## Como fechar o gate\n\n"
        "1. **Requisito sem story** → criar story que o cite (ou descopar com decisão "
        "datada do dono no doc 08 e remover o requisito).\n"
        "2. **Story órfã** → citar o(s) requisito(s) que ela implementa.\n"
        "3. **Story não decomposta** → quebrar em stories com critério de aceite próprio.\n"
        "4. **Requisito não verificável** → reescrever como QUANDO/DEVE + `Aceite:`.\n"
    )

    md_path = os.path.join(args.out, "spec-coverage.md")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("".join(out))

    print(
        f"Spec coverage: {coverage_pct}% ({covered}/{total} requisitos com story), "
        f"{len(orphan_stories)} story órfã(s), {len(non_atomic)} não decomposta(s), "
        f"{len(missing_acceptance)} sem forma verificável."
    )
    print(f"  {md_path}")
    print(f"  Gate: {summary['gate']}")

    if gate_failed and not args.warn_only:
        sys.exit(1)


if __name__ == "__main__":
    main()
