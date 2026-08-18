"""Build bidirectional index: case citations <-> legislation sections from catchwords."""

import json
import re
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path('/home/harrison/legislation-explorer/data')

# ---------------------------------------------------------------------------
# Load available sections per act
# ---------------------------------------------------------------------------

def load_section_ids(act: str) -> set[str]:
    tree = json.loads((DATA_DIR / act / 'tree.json').read_text())
    ids = set()
    for part in tree.get('parts', []):
        for sec in part.get('sections', []):
            ids.add(sec['id'])
        for div in part.get('divisions', []):
            for sec in div.get('sections', []):
                ids.add(sec['id'])
            for sub in div.get('subdivisions', []):
                for sec in sub.get('sections', []):
                    ids.add(sec['id'])
    return ids

ACT_SECTIONS = {
    'itaa-1997': load_section_ids('itaa-1997'),
    'gst-1999': load_section_ids('gst-1999'),
    'itaa-1936': load_section_ids('itaa-1936'),
    'taa-1953': load_section_ids('taa-1953'),
    'fbt-1986': load_section_ids('fbt-1986'),
    'sis-1993': load_section_ids('sis-1993'),
}

BASE_RE = r'([0-9]+\s*-\s*[0-9]+(?:\s*-\s*[0-9]+)?|[A-Z]*[0-9]+[A-Z]*|[0-9]+)'

BASE_LOOKUP: dict[str, list[tuple[str, str]]] = defaultdict(list)
for act, ids in ACT_SECTIONS.items():
    for sid in ids:
        m = re.match(BASE_RE, sid)
        base = m.group(1) if m else sid
        BASE_LOOKUP[base].append((act, sid))

# Bases that exist in multiple acts — require explicit context
AMBIGUOUS_BASES = {
    b for b, acts in BASE_LOOKUP.items()
    if len({a for a, _ in acts}) > 1
}

# Well-known ITAA 1936 sections safe to infer without context
ITAA1936_KNOWN = {
    '6', '26', '46', '47', '48', '50', '51', '63', '79', '80', '82',
    '97', '99', '100', '102', '109', '121', '128', '160', '165', '166',
    '177', '178', '179', '180', '190', '193', '222', '254', '255',
}

# Generic plain numbers that should NOT be inferred to TAA without context
TAA_GENERIC_BLOCK = {str(i) for i in range(1, 100)}

# ---------------------------------------------------------------------------
# Act detection
# ---------------------------------------------------------------------------

ACT_PATTERNS = [
    (r'Income Tax Assessment Act\s+1997|ITAA\s*1997|Assessment Act\s+1997', 'itaa-1997'),
    (r'Income Tax Assessment Act\s+1936|ITAA\s*1936|Assessment Act\s+1936', 'itaa-1936'),
    (r'Goods and Services Tax Act\s+1999|A New Tax System \(Goods and Services Tax\) Act\s+1999|GST Act', 'gst-1999'),
    (r'Taxation Administration Act\s+1953|TAA\s*1953', 'taa-1953'),
    (r'Fringe Benefits Tax Assessment Act|FBT\s*Act|FBTAA', 'fbt-1986'),
    (r'Superannuation Industry \(Supervision\) Act|SIS\s*Act', 'sis-1993'),
    (r'Luxury Car Tax Act\s+1999|LCT Act', 'gst-1999'),
]


def detect_act(text: str) -> str | None:
    text = text.replace('\n', ' ')
    for pattern, act_id in ACT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return act_id
    return None


# ---------------------------------------------------------------------------
# Section reference extraction
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(
    BASE_RE +
    r'(?:\(\d+[A-Z]?\))?'   # (1), (1A)
    r'(?:\(\d+\))?'         # (2)
    r'(?:\([a-z]\))?'       # (a)
    r'(?:\([ivx]+\))?',     # (i)
    re.IGNORECASE
)

REF_START_RE = re.compile(
    r'\b(?:[sS][sS]\.?|[sS]\.?|section|sections)\s*',
    re.IGNORECASE
)


def extract_refs(text: str) -> list[tuple[str, str, str]]:
    found = []
    for m in REF_START_RE.finditer(text):
        start = m.end()
        ctx_start = max(0, m.start() - 200)
        ctx_end = min(len(text), m.end() + 100)
        context = text[ctx_start:ctx_end]
        act = detect_act(context)

        pos = start
        while pos < len(text) and text[pos] in ' \t\n,;':
            pos += 1

        tokens = []
        while pos < len(text):
            tm = TOKEN_RE.match(text[pos:])
            if not tm:
                break
            token = tm.group(0)
            tokens.append(token)
            pos += tm.end()
            while pos < len(text) and text[pos] in ' \t\n':
                pos += 1
            if pos < len(text) and text[pos] == ',':
                pos += 1
                while pos < len(text) and text[pos] in ' \t\n':
                    pos += 1
                continue
            if pos < len(text) and text[pos:pos+3].lower() == 'and':
                pos += 3
                while pos < len(text) and text[pos] in ' \t\n':
                    pos += 1
                continue
            if pos < len(text) and text[pos:pos+2].lower() == 'or':
                pos += 2
                while pos < len(text) and text[pos] in ' \t\n':
                    pos += 1
                continue
            break

        for token in tokens:
            base_m = re.match(BASE_RE, token)
            if not base_m:
                continue
            base = base_m.group(1).replace(' ', '')
            resolved_act = act if act else infer_act(base)
            if resolved_act and base in BASE_LOOKUP:
                candidates = BASE_LOOKUP[base]
                for a, sid in candidates:
                    if a == resolved_act:
                        found.append((base, sid, resolved_act))
                        break

    seen = set()
    deduped = []
    for base, sid, act in found:
        key = (act, sid)
        if key not in seen:
            seen.add(key)
            deduped.append((base, sid, act))
    return deduped


def infer_act(base: str) -> str | None:
    """Infer act for unambiguous bases when no explicit context exists."""
    if base not in BASE_LOOKUP:
        return None
    candidates = BASE_LOOKUP[base]
    acts = {a for a, _ in candidates}
    if len(acts) == 1:
        act = candidates[0][0]
        # Block generic TAA numbers without context
        if act == 'taa-1953' and base in TAA_GENERIC_BLOCK:
            return None
        return act

    # ITAA 1936 anti-avoidance / well-known sections
    if re.match(r'^[A-Z]*[0-9]+[A-Z]+$', base) or base in ITAA1936_KNOWN:
        for a, _ in candidates:
            if a == 'itaa-1936':
                return 'itaa-1936'

    # TAA specific sections
    if base in ('14ZZO', '14ZZ', '14ZZK', '14ZZL', '14ZZN', '298-20', '255-1', '350-10'):
        for a, _ in candidates:
            if a == 'taa-1953':
                return 'taa-1953'

    # Dashed sections: prefer GST for known prefixes, otherwise ITAA 1997
    if re.match(r'^[0-9]+-[0-9]+$', base):
        gst_prefixes = (
            '9-', '15-', '17-', '23-', '29-', '33-', '37-', '38-', '39-', '40-',
            '48-', '54-', '57-', '58-', '75-', '78-', '79-', '81-', '82-', '83-',
            '84-', '87-', '90-', '93-', '96-', '99-', '105-', '110-', '111-',
            '117-', '123-', '129-', '132-', '135-', '141-', '144-', '150-',
            '153-', '156-', '162-', '165-', '168-', '171-', '177-', '183-',
            '189-', '195-'
        )
        if base.startswith(gst_prefixes):
            for a, _ in candidates:
                if a == 'gst-1999':
                    return 'gst-1999'
        for a, _ in candidates:
            if a == 'itaa-1997':
                return 'itaa-1997'
        for a, _ in candidates:
            if a == 'taa-1953':
                return 'taa-1953'

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with open(DATA_DIR / 'case_catchwords.json') as f:
        catchwords = json.load(f)

    section_to_cases = defaultdict(list)
    case_to_sections = defaultdict(list)

    for citation, text in catchwords.items():
        refs = extract_refs(text)
        for base, sid, act in refs:
            key = f"{act}:{sid}"
            if not any(c['citation'] == citation for c in section_to_cases[key]):
                section_to_cases[key].append({'citation': citation, 'catchwords': text})
            case_to_sections[citation].append({'act': act, 'section': sid, 'base': base})

    with open(DATA_DIR / 'section_case_index.json', 'w') as f:
        json.dump(dict(section_to_cases), f, indent=2)
    with open(DATA_DIR / 'case_section_refs.json', 'w') as f:
        json.dump(dict(case_to_sections), f, indent=2)

    print(f"Section->Cases: {len(section_to_cases)} entries")
    print(f"Case->Sections: {len(case_to_sections)} entries")
    act_counts = defaultdict(int)
    for key, cases in section_to_cases.items():
        act_counts[key.split(':')[0]] += len(cases)
    for act, count in sorted(act_counts.items()):
        print(f"  {act}: {count} links")


if __name__ == '__main__':
    main()
