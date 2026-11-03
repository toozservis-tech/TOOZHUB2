"""Human-readable summaries; original notes and audit evidence stay unchanged."""
import re

EVENT = re.compile(r'^\d{4}-\d{2}-\d{2}T\S+\s+\[(received|in_progress|completed|cancelled)\]\s*(.*)$')
ATTACHMENT = ('Fotografie:', 'Fotografie doplněná po dokončení:', 'Dokument:', 'Dokument doplněný po dokončení:')


def work_note(note):
    """Remove only generated event envelopes/upload notifications, never free text."""
    result = []
    for line in (note or '').splitlines():
        match = EVENT.match(line)
        if match:
            line = match.group(2).strip()
            if line.startswith(ATTACHMENT):
                continue
        if line and (not result or result[-1] != line):
            result.append(line)
    return '\n'.join(result)


def display_summary(record):
    description = (record.description or '').strip()
    note = work_note(record.note)
    if description.casefold() in ('vše', 'hotovo', 'dokončeno', 'opraveno') and note:
        return note[:1200]
    return description or note[:1200] or 'Servisní záznam'
