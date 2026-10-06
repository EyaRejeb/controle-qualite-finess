"""Mini-base de test : un établissement de référence qui ne déclenche aucune règle,
que chaque test modifie pour créer un cas positif ou négatif."""
import copy

import duckdb
import pyarrow as pa
import pytest

from finess_qc.config import REF_DIR
from finess_qc.geo import GEO_PREP_COLS
from finess_qc.load import EJ_COLS, ETAB_COLS, create_table
from finess_qc.rules import run_rules


def siret_valide(base13: str) -> str:
    """Complète 13 chiffres avec la clé de Luhn."""
    for k in range(10):
        s = base13 + str(k)
        total = sum((2 * int(c) - 9 if 2 * int(c) > 9 else 2 * int(c)) if (len(s) - i) % 2 == 0 else int(c)
                    for i, c in enumerate(s))
        if total % 10 == 0:
            return s
    raise ValueError


ETAB_OK = {c: None for c in ETAB_COLS} | {
    "nofinesset": "330000011", "nofinessej": "330000003", "rs": "CLINIQUE DES LILAS",
    "numvoie": "12", "typvoie": "R", "voie": "DES LILAS", "commune": "063", "departement": "33",
    "libdepartement": "GIRONDE", "ligneacheminement": "33000 BORDEAUX", "telephone": "0556000000",
    "categetab": "355", "libcategetab": "Centre Hospitalier (C.H.)", "categagretab": "1102",
    "libcategagretab": "Centres Hospitaliers", "siret": siret_valide("1234567890001"),
    "dateouv": "2000-01-01", "dateautor": "2000-01-01", "datemaj": "2025-01-01",
}
GEO_OK = {"nofinesset": "330000011", "niveau_geocodage": "1", "referentiel": "BAN", "epsg": "EPSG:2154",
          "latitude": 44.84, "longitude": -0.58, "dept_geo": "33", "dist_dept_km": 0.0}
EJ_OK = {c: None for c in EJ_COLS} | {"nofiness": "330000003", "rs": "GESTIONNAIRE"}
NOMENCLATURE = [
    ["355", "Centre Hospitalier (C.H.)", "4", "1102", "active", None],
    ["382", "Foyer de Vie pour Adultes Handicapés", "4", "4402", "deprecated", "2018-10-26"],
]


def etab(**changes) -> dict:
    return copy.deepcopy(ETAB_OK) | changes


def geo(**changes) -> dict:
    return copy.deepcopy(GEO_OK) | changes


@pytest.fixture
def run():
    """run(etabs=[...], geos=[...], date_extraction=..., date_execution=...) -> {(nofinesset, regle)}"""
    def _run(etabs=None, geos=None, date_extraction="2026-05-12", date_execution="2026-06-01"):
        etabs = etabs if etabs is not None else [etab()]
        geos = geos if geos is not None else [geo(nofinesset=e["nofinesset"]) for e in etabs]
        con = duckdb.connect()
        create_table(con, "etab", ETAB_COLS, [[e[c] for c in ETAB_COLS] for e in etabs])
        create_table(con, "ej", EJ_COLS, [[EJ_OK[c] for c in EJ_COLS]])
        create_table(con, "geo_prep", GEO_PREP_COLS, [[g[c] for c in GEO_PREP_COLS] for g in geos],
                     types={"latitude": pa.float64(), "longitude": pa.float64(), "dist_dept_km": pa.float64()})
        create_table(con, "nomenclature", ["code", "libelle", "niveau", "parent", "statut", "date_fin"], NOMENCLATURE)
        create_table(con, "meta", ["fichier", "emetteur", "num_flux", "date_extraction"],
                     [["etab_geo.csv", "etalab", "1", date_extraction]])
        con.execute(f"CREATE TABLE ref_departement AS SELECT * FROM read_csv('{REF_DIR / 'departements.csv'}', all_varchar=true)")
        run_rules(con, date_execution)
        return set(con.execute("SELECT coalesce(nofinesset, '(fichier)'), regle FROM anomalies").fetchall())
    return _run
