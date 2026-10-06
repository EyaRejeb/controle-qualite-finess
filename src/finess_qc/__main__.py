"""Point d'entrée unique : python -m finess_qc

Télécharge les sources (si absentes), charge, prépare la géographie,
exécute les règles et produit les exports dans exports/.
"""
import argparse
import datetime as dt
from pathlib import Path

import duckdb

from .config import DATA_DIR, DB_PATH, EXPORT_DIR, REF_DIR
from .download import download_all
from .geo import build_geo_prep
from .load import load_all
from .report import build_outputs
from .rules import run_rules


def main() -> None:
    p = argparse.ArgumentParser(description="Contrôle qualité du référentiel FINESS")
    p.add_argument("--force-download", action="store_true", help="retélécharger les sources")
    p.add_argument("--raw-dir", type=Path, help="dossier contenant des sources déjà téléchargées")
    p.add_argument("--date-execution", default=dt.date.today().isoformat(),
                   help="date de référence pour la règle de fraîcheur (AAAA-MM-JJ)")
    args = p.parse_args()

    print("1/5 Sources")
    download_all(force=args.force_download, raw_dir=args.raw_dir)
    con = duckdb.connect(str(DB_PATH))

    print("2/5 Chargement")
    info = load_all(con, DATA_DIR, REF_DIR)
    print(f"  {info['etablissements']} établissements, {info['entites_juridiques']} entités juridiques, "
          f"extraction du {info['date_extraction']}")
    for pb in info["problemes_structure"]:
        print("  [structure]", pb)

    print("3/5 Géographie")
    info.update(build_geo_prep(con, DATA_DIR / "departements.geojson"))

    print("4/5 Règles")
    run_rules(con, args.date_execution)

    print("5/5 Scores et exports")
    info["date_execution"] = args.date_execution
    s = build_outputs(con, EXPORT_DIR, info)
    print(f"  Score de qualité global : {s['score_global']} %")
    for sev in ["Bloquante", "Majeure", "Mineure", "Information"]:
        print(f"  {sev:12s} {s['anomalies_par_severite'].get(sev, 0):>7} anomalies")
    print(f"  Exports écrits dans {EXPORT_DIR}")


if __name__ == "__main__":
    main()
