"""Build docker/presidio-analyzer/pii_recognizers/data/fr_first_names.txt from INSEE's first names file.

Source: INSEE, "Fichier des prénoms", 2022 edition (births in France since 1900, Licence Ouverte / Etalab).
Keeps the spellings given to at least MIN_BIRTHS children, title-cased as in a text ("JEAN-PIERRE" -> "Jean-Pierre"),
minus first names that are far more often something else in a French text.

Run with `uv run python scripts/build_first_names.py`; the download is checked against its SHA-256.
"""

import csv
import hashlib
import io
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

URL = "https://www.insee.fr/fr/statistiques/fichier/7633685/nat2022_csv.zip"
SHA256 = "c13b45e770c684b3c8531f28b6e3eae62194dc6dc86205fa17e4c6447b01b81d"
MIN_BIRTHS = 500
# Also first names, but in a letter they are nearly always the capital or the country ("France Travail").
EXCLUDED = {"Paris", "France"}
OUTPUT = Path(__file__).resolve().parents[1] / "docker/presidio-analyzer/pii_recognizers/data/fr_first_names.txt"


def main() -> None:
    archive = urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(archive).hexdigest() != SHA256:
        raise SystemExit(f"{URL} changed: check it, then update SHA256")
    table = zipfile.ZipFile(io.BytesIO(archive)).read("nat2022.csv").decode("utf-8")

    births: Counter[str] = Counter()
    for row in csv.DictReader(io.StringIO(table), delimiter=";"):
        # _PRENOMS_RARES groups the rare names; XXXX is an unknown birth year, still a birth.
        if not row["preusuel"].startswith("_"):
            births[row["preusuel"].title()] += int(row["nombre"])

    names = sorted(name for name, count in births.items() if count >= MIN_BIRTHS and name not in EXCLUDED)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    header = f"# INSEE, Fichier des prénoms 2022, at least {MIN_BIRTHS} births; built by scripts/build_first_names.py\n"
    OUTPUT.write_text(header + "\n".join(names) + "\n")
    print(f"{len(names)} first names written to {OUTPUT}")


if __name__ == "__main__":
    main()
