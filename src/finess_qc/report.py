"""Scores de qualité et exports pour Power BI."""
import json
from pathlib import Path

from .rules import RULES

SCORE_SQL = """round(100.0 * count(*) FILTER (WHERE nb_bloquantes = 0 AND nb_majeures = 0) / count(*), 2)"""


def build_outputs(con, export_dir: Path, run_info: dict) -> dict:
    export_dir.mkdir(parents=True, exist_ok=True)

    con.execute("""CREATE OR REPLACE TABLE etab_qualite AS
        WITH a AS (
            SELECT nofinesset,
                   count(*) FILTER (WHERE severite = 'Bloquante')   AS nb_bloquantes,
                   count(*) FILTER (WHERE severite = 'Majeure')     AS nb_majeures,
                   count(*) FILTER (WHERE severite = 'Mineure')     AS nb_mineures,
                   count(*) FILTER (WHERE severite = 'Information') AS nb_informations
            FROM anomalies WHERE nofinesset IS NOT NULL GROUP BY 1)
        SELECT e.nofinesset, e.nofinessej, e.rs AS raison_sociale,
               e.categetab AS categorie_code, e.libcategetab AS categorie,
               e.categagretab AS agregat_code, e.libcategagretab AS agregat,
               r.code_insee AS departement_code, e.libdepartement AS departement, r.region,
               e.ligneacheminement AS commune, g.latitude, g.longitude, g.niveau_geocodage,
               coalesce(a.nb_bloquantes, 0) AS nb_bloquantes, coalesce(a.nb_majeures, 0) AS nb_majeures,
               coalesce(a.nb_mineures, 0) AS nb_mineures, coalesce(a.nb_informations, 0) AS nb_informations,
               coalesce(a.nb_bloquantes, 0) + coalesce(a.nb_majeures, 0) = 0 AS conforme
        FROM etab e
        LEFT JOIN ref_departement r ON r.departement_finess = e.departement
        LEFT JOIN geo_prep g USING (nofinesset)
        LEFT JOIN a USING (nofinesset)""")

    con.execute(f"COPY (SELECT * FROM anomalies ORDER BY regle, nofinesset) TO '{export_dir / 'anomalies.csv'}' (HEADER, DELIMITER ',')")
    con.execute(f"COPY (SELECT * FROM etab_qualite ORDER BY nofinesset) TO '{export_dir / 'etablissements.csv'}' (HEADER, DELIMITER ',')")

    con.execute("CREATE OR REPLACE TABLE regles (id VARCHAR, dimension VARCHAR, severite VARCHAR, libelle VARCHAR, pourquoi VARCHAR, action VARCHAR)")
    con.executemany("INSERT INTO regles VALUES (?, ?, ?, ?, ?, ?)",
                    [[r.id, r.dimension, r.severite, r.libelle, r.pourquoi, r.action] for r in RULES])
    con.execute(f"""COPY (SELECT r.*, count(a.regle) AS nb_anomalies FROM regles r
                         LEFT JOIN anomalies a ON a.regle = r.id GROUP BY ALL ORDER BY r.id)
                   TO '{export_dir / 'regles.csv'}' (HEADER, DELIMITER ',')""")

    con.execute(f"""COPY (SELECT region, count(*) AS etablissements, {SCORE_SQL} AS score_qualite,
                                 sum(nb_bloquantes) AS bloquantes, sum(nb_majeures) AS majeures, sum(nb_mineures) AS mineures
                          FROM etab_qualite GROUP BY region ORDER BY score_qualite)
                   TO '{export_dir / 'scores_region.csv'}' (HEADER, DELIMITER ',')""")
    con.execute(f"""COPY (SELECT categorie_code, categorie, agregat, count(*) AS etablissements, {SCORE_SQL} AS score_qualite,
                                 sum(nb_bloquantes) + sum(nb_majeures) AS anomalies_bloquantes_majeures,
                                 round(100.0 * count(*) FILTER (WHERE nofinesset IN (SELECT nofinesset FROM anomalies WHERE regle = 'R11')) / count(*), 1) AS pct_siret_absent
                          FROM etab_qualite GROUP BY ALL ORDER BY anomalies_bloquantes_majeures DESC)
                   TO '{export_dir / 'scores_categorie.csv'}' (HEADER, DELIMITER ',')""")

    q = lambda s: con.execute(s).fetchall()
    n_etab = q("SELECT count(*) FROM etab_qualite")[0][0]
    synthese = {
        **run_info,
        "etablissements": n_etab,
        "score_global": q(f"SELECT {SCORE_SQL} FROM etab_qualite")[0][0],
        "anomalies_par_severite": dict(q("SELECT severite, count(*) FROM anomalies GROUP BY 1")),
        "etablissements_touches_par_severite": dict(q(
            "SELECT severite, count(DISTINCT nofinesset) FROM anomalies WHERE nofinesset IS NOT NULL GROUP BY 1")),
        "anomalies_par_regle": dict(q("SELECT regle, count(*) FROM anomalies GROUP BY 1 ORDER BY 1")),
        "top10_categories": [dict(zip(["categorie", "anomalies", "etablissements"], r)) for r in q("""
            SELECT categorie, sum(nb_bloquantes + nb_majeures) AS n, count(*) FROM etab_qualite
            GROUP BY 1 ORDER BY n DESC LIMIT 10""")],
    }
    (export_dir / "synthese.json").write_text(json.dumps(synthese, ensure_ascii=False, indent=2), encoding="utf-8")
    return synthese
