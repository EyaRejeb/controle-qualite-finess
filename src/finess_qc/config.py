"""Paramètres du projet : sources, chemins et seuils des règles."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"          # données brutes, non versionnées
REF_DIR = ROOT / "ref"            # référentiels légers, versionnés
EXPORT_DIR = ROOT / "exports"     # sorties pour Power BI et le README
DB_PATH = DATA_DIR / "finess.duckdb"

# Sources (Licence Ouverte / Open Licence)
SOURCES = {
    "etab_geo.csv": "https://www.data.gouv.fr/api/1/datasets/r/98f3161f-79ff-4f16-8f6a-6d571a80fea2",
    "ej.csv": "https://www.data.gouv.fr/api/1/datasets/r/2cba77b2-f1de-4ef8-8428-bfe660e86844",
    "departements.geojson": "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements-avec-outre-mer.geojson",
    "r397.fsh": "https://raw.githubusercontent.com/ansforge/IG-terminologie-de-sante/main/DM/input/fsh/Template/ontoserver/TRE/TreR397CategorieEntiteGeographiqueExercice.fsh",
}

# Métadonnées relevées sur la page data.gouv.fr du jeu de données (6 octobre 2026)
FREQUENCE_ANNONCEE_JOURS = 61          # « Tous les deux mois »
DATE_ARRET_FLUX = "2026-07-20"         # nouvelle version de FINESS, flux etalab arrêtés

# Seuils
TOLERANCE_GEO_KM = 1.0                 # R09 : marge pour les contours simplifiés
ANCIENNETE_MAJ_ANNEES = 10             # R17 : établissement non mis à jour depuis N ans

# Projections déclarées dans le champ sourcecoordet -> code EPSG
PROJECTIONS = {
    "EPSG:2154": "EPSG:2154",                         # Lambert-93, métropole
    "EPSG:5490": "EPSG:5490",                         # UTM 20N, Antilles
    "EPSG:2975": "EPSG:2975",                         # UTM 40S, La Réunion
    "EPSG:2972": "EPSG:2972",                         # UTM 22N, Guyane
    "EPSG:4471": "EPSG:4471",                         # UTM 38S, Mayotte
    "WGS84/UTM zone 21N": "EPSG:32621",               # Saint-Pierre-et-Miquelon
    "WGS84/UTM zone 1S": "EPSG:32701",                # Wallis-et-Futuna
}
