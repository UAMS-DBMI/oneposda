"""Compare Posda's PubDataDict VM/VR against pydicom's, for every tag the
ingestion modules actually reference.

Posda's parser decides array-ness from the DICTIONARY VM, not the runtime
value, so any VM disagreement between the two dictionaries becomes a
scalar-vs-list divergence in the ported code.
"""

import re
import sys
from pathlib import Path

# tools/ -> python/ -> posdatools/
POSDATOOLS = Path(__file__).resolve().parents[2]

from pydicom.datadict import dictionary_VM, dictionary_VR

POSDA = POSDATOOLS
DICT_PM = POSDA / "Posda/include/Posda/PubDataDict.pm"
SOURCES = [
    POSDA / "Posda/include/Posda/DB/Modules.pm",
    POSDA / "Posda/include/Posda/DB/DicomIod.pm",
]

ENTRY_RE = re.compile(
    r"\$Posda::DataDict::Dict->\{(\d+)\}->\{(\d+)\} = \{(.*?)\n\};", re.DOTALL
)
FIELD_RE = re.compile(r'(\w+) => "([^"]*)"')
# "(0008,0016)" style signatures used by ExtractElementBySig / Get
SIG_RE = re.compile(r'"\((?:[0-9a-fA-F]{4}),(?:[0-9a-fA-F]{4})\)"')
SIG_PARTS_RE = re.compile(r'"\(([0-9a-fA-F]{4}),([0-9a-fA-F]{4})\)"')


def load_posda_dict() -> dict[tuple[int, int], dict[str, str]]:
    text = DICT_PM.read_text(errors="replace")
    out = {}
    for group, ele, body in ENTRY_RE.findall(text):
        fields = dict(FIELD_RE.findall(body))
        out[(int(group), int(ele))] = fields
    return out


def referenced_tags() -> set[tuple[int, int]]:
    tags = set()
    for src in SOURCES:
        for grp, ele in SIG_PARTS_RE.findall(src.read_text(errors="replace")):
            tags.add((int(grp, 16), int(ele, 16)))
    return tags


def main() -> int:
    posda = load_posda_dict()
    tags = sorted(referenced_tags())
    print(f"Posda dictionary entries: {len(posda)}")
    print(f"Distinct tags referenced by the ingest modules: {len(tags)}\n")

    vm_diff, vr_diff, missing_posda, missing_pydicom = [], [], [], []

    for grp, ele in tags:
        tag_int = (grp << 16) | ele
        label = f"({grp:04x},{ele:04x})"

        p = posda.get((grp, ele))
        try:
            py_vm, py_vr = dictionary_VM(tag_int), dictionary_VR(tag_int)
        except KeyError:
            py_vm = py_vr = None

        if p is None and py_vm is None:
            continue
        if p is None:
            missing_posda.append((label, py_vm, py_vr))
            continue
        if py_vm is None:
            missing_pydicom.append((label, p.get("VM"), p.get("VR"), p.get("Name")))
            continue

        # Only array-ness matters: VM "1" -> scalar, anything else -> list.
        posda_is_list = p.get("VM") != "1"
        pydicom_is_list = py_vm != "1"
        if posda_is_list != pydicom_is_list:
            vm_diff.append((label, p.get("VM"), py_vm, p.get("Name")))
        if p.get("VR") != py_vr:
            vr_diff.append((label, p.get("VR"), py_vr, p.get("Name")))

    def section(title, rows, fmt):
        print(f"--- {title}: {len(rows)} ---")
        for r in rows:
            print("   " + fmt(r))
        if not rows:
            print("   (none)")
        print()

    section(
        "ARRAY-NESS DISAGREEMENT (breaks the port)",
        vm_diff,
        lambda r: f"{r[0]}  posda VM={r[1]!r:8} pydicom VM={r[2]!r:8} {r[3]}",
    )
    section(
        "VR disagreement (affects coercion)",
        vr_diff,
        lambda r: f"{r[0]}  posda VR={r[1]!r:6} pydicom VR={r[2]!r:6} {r[3]}",
    )
    section(
        "Referenced but absent from Posda dict",
        missing_posda,
        lambda r: f"{r[0]}  pydicom VM={r[1]!r} VR={r[2]!r}",
    )
    section(
        "Referenced but absent from pydicom dict",
        missing_pydicom,
        lambda r: f"{r[0]}  posda VM={r[1]!r} VR={r[2]!r} {r[3]}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
