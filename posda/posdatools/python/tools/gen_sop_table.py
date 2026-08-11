"""Generate the Python SOP-class handler table from DicomIod.pm.

Transcribing ~90 entries by hand invites silent drift, so the table is
machine-translated from the Perl and the generator is kept for re-running if
the Perl changes.
"""

import re
from pathlib import Path

# tools/ -> python/ -> posdatools/
POSDATOOLS = Path(__file__).resolve().parents[2]

SRC = POSDATOOLS / "Posda/include/Posda/DB/DicomIod.pm"

ENTRY_RE = re.compile(
    r"'([0-9.]+)'\s*=>\s*\{\s*name\s*=>\s*'([^']*)',\s*"
    r"handlers\s*=>\s*\[(.*?)\],\s*\},",
    re.DOTALL,
)
HANDLER_RE = re.compile(r"^\s*\\&Posda::DB::Modules::(\w+),\s*$", re.MULTILINE)

text = SRC.read_text()
# Cut to the $SopHandlers literal so nothing else is matched.
start = text.index("my $SopHandlers = {")
end = text.index("my $sop_common_parms")
body = text[start:end]

entries = ENTRY_RE.findall(body)
print(f"# parsed {len(entries)} SOP classes")

lines = ["SOP_HANDLERS: dict[str, SopClass] = {"]
handler_names: set[str] = set()
for uid, name, handlers in entries:
    active = HANDLER_RE.findall(handlers)
    handler_names.update(active)
    escaped = name.replace('"', '\\"')
    lines.append(f'    "{uid}": SopClass(')
    lines.append(f'        name="{escaped}",')
    if active:
        lines.append("        handlers=(")
        for h in active:
            lines.append(f'            "{h}",')
        lines.append("        ),")
    else:
        lines.append("        handlers=(),")
    lines.append("    ),")
lines.append("}")

Path("sop_table.py.txt").write_text("\n".join(lines) + "\n")
print("handlers referenced:", ", ".join(sorted(handler_names)))
print(f"wrote sop_table.py.txt ({len(lines)} lines)")
