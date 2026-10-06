"""Lecture des fichiers FINESS et chargement dans DuckDB.

Constats faits à la lecture (à ne pas supposer, voir README) :
- séparateur « ; » alors que la documentation annonce une tabulation ;
- encodage UTF-8 ;
- ligne 1 = en-tête technique « finess;etalab;<n° de flux>;<date d'extraction> » ;
- le fichier des établissements mélange deux sections : lignes « structureet »
  puis lignes « geolocalisation » ;
- certaines valeurs sont entre guillemets et contiennent un « ; »
  (ex. une adresse d'entité juridique) : il faut un vrai parseur CSV.
"""
import csv
import re
from pathlib import Path

import duckdb
import pyarrow as pa

ETAB_COLS = ["nofinesset", "nofinessej", "rs", "rslongue", "complrs", "compldistrib", "numvoie",
             "typvoie", "voie", "compvoie", "lieuditbp", "commune", "departement", "libdepartement",
             "ligneacheminement", "telephone", "telecopie", "categetab", "libcategetab",
             "categagretab", "libcategagretab", "siret", "codeape", "codemft", "libmft", "codesph",
             "libsph", "dateouv", "dateautor", "datemaj", "numuai"]
GEO_COLS = ["nofinesset", "coordxet", "coordyet", "sourcecoordet", "datemaj_geo"]
EJ_COLS = ["nofiness", "rs", "rslongue", "complrs", "numvoie", "typvoie", "voie", "compvoie",
           "compldistrib", "lieuditbp", "commune", "ligneacheminement", "departement",
           "libdepartement", "telephone", "statutjuridique", "libstatutjuridique", "categetab",
           "libcategetab", "siren", "codeape", "datecrea"]
SECTIONS = {"structureet": ETAB_COLS, "geolocalisation": GEO_COLS, "structureej": EJ_COLS}


def read_finess_file(path: Path) -> tuple[dict, dict[str, list[list]], list[str]]:
    """Retourne (en-tête, lignes par section, anomalies de structure)."""
    rows: dict[str, list[list]] = {k: [] for k in SECTIONS}
    problems: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        head = next(reader)
        header = {"fichier": path.name, "emetteur": head[1], "num_flux": head[2],
                  "date_extraction": head[3]}
        for n, rec in enumerate(reader, start=2):
            if not rec:
                continue
            section, values = rec[0], rec[1:]
            cols = SECTIONS.get(section)
            if cols is None:
                problems.append(f"ligne {n} : section inconnue « {section} »")
                continue
            if len(values) != len(cols):
                problems.append(f"ligne {n} : {len(values)} champs au lieu de {len(cols)}")
                values = (values + [""] * len(cols))[: len(cols)]
            rows[section].append([v.strip() or None for v in values])
    return header, rows, problems


def parse_nomenclature(path: Path) -> list[dict]:
    """Extrait les concepts de la terminologie ANS TRE-R397 (fichier FSH)."""
    concepts: dict[str, dict] = {}
    head = re.compile(r'^\* #(\w+) "(.*)"\s*$')
    prop = re.compile(r'^\* #(\w+) \^property\[[^\]]*\]\.(code|value\w+) = (.*)$')
    last_prop: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = head.match(line)
            if m:
                code, lib = m.groups()
                concepts[code] = {"code": code, "libelle": lib, "niveau": None, "parent": None,
                                  "statut": None, "date_fin": None}
                continue
            m = prop.match(line)
            if not m:
                continue
            code, kind, val = m.groups()
            val = val.strip().strip('"').lstrip("#")
            if kind == "code":
                last_prop[code] = val
            elif code in concepts:
                key = {"niveau": "niveau", "parent": "parent", "status": "statut",
                       "dateFin": "date_fin"}.get(last_prop.get(code))
                if key:
                    concepts[code][key] = val[:10] if key == "date_fin" else val
    return list(concepts.values())


def create_table(con, name: str, cols: list[str], rows: list[list], types: dict | None = None) -> None:
    """Crée une table à partir de lignes Python (via Arrow : bien plus rapide qu'INSERT ligne à ligne)."""
    types = types or {}
    arrays = {c: pa.array([r[i] for r in rows], type=types.get(c, pa.string())) for i, c in enumerate(cols)}
    tbl = pa.table(arrays)
    con.register("_arrow_src", tbl)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _arrow_src")
    con.unregister("_arrow_src")


_create = create_table


def load_all(con: duckdb.DuckDBPyConnection, data_dir: Path, ref_dir: Path) -> dict:
    """Charge établissements, géolocalisation, entités juridiques et référentiels."""
    h_et, r_et, p_et = read_finess_file(data_dir / "etab_geo.csv")
    h_ej, r_ej, p_ej = read_finess_file(data_dir / "ej.csv")
    _create(con, "etab", ETAB_COLS, r_et["structureet"])
    _create(con, "geo", GEO_COLS, r_et["geolocalisation"])
    _create(con, "ej", EJ_COLS, r_ej["structureej"])

    nom = parse_nomenclature(data_dir / "r397.fsh")
    _create(con, "nomenclature", ["code", "libelle", "niveau", "parent", "statut", "date_fin"],
            [[c[k] for k in ("code", "libelle", "niveau", "parent", "statut", "date_fin")] for c in nom])

    con.execute(f"""CREATE OR REPLACE TABLE ref_departement AS
        SELECT * FROM read_csv('{ref_dir / 'departements.csv'}', all_varchar=true, header=true)""")
    _create(con, "meta", ["fichier", "emetteur", "num_flux", "date_extraction"],
            [list(h_et.values()), list(h_ej.values())])
    return {"etablissements": len(r_et["structureet"]), "geolocalisations": len(r_et["geolocalisation"]),
            "entites_juridiques": len(r_ej["structureej"]), "concepts_r397": len(nom),
            "problemes_structure": p_et + p_ej, "date_extraction": h_et["date_extraction"]}
