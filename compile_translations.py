from pathlib import Path

from babel.messages import mofile, pofile

for po in sorted(Path("translations").glob("*/LC_MESSAGES/messages.po")):
    with open(po, "rb") as f:
        catalog = pofile.read_po(f)
    with open(po.with_suffix(".mo"), "wb") as f:
        mofile.write_mo(f, catalog)
    print(f"compilé : {po}  ({len([m for m in catalog if m.id])} textes)")