"""Catalogue des règles de qualité.

Chaque règle est une requête DuckDB qui renvoie une ligne par anomalie,
avec deux colonnes : nofinesset (NULL pour une anomalie qui porte sur le fichier)
et valeur_fautive. Les tables lues sont préparées par load.py et geo.py :
etab, ej, geo_prep, nomenclature, ref_departement, meta.

Les sévérités suivent une logique d'usage :
- Bloquante : l'enregistrement ne peut pas être importé tel quel (identifiant ou nom inutilisable, doublon certain).
- Majeure : l'enregistrement est importable mais faux ou incohérent sur une donnée de référence.
- Mineure : donnée absente ou imprécise, sans erreur avérée.
- Information : signal à connaître, souvent légitime ; n'entre pas dans le score.
"""
from dataclasses import dataclass

from .config import ANCIENNETE_MAJ_ANNEES, DATE_ARRET_FLUX, FREQUENCE_ANNONCEE_JOURS, TOLERANCE_GEO_KM

SEVERITES = ["Bloquante", "Majeure", "Mineure", "Information"]


@dataclass(frozen=True)
class Rule:
    id: str
    dimension: str
    severite: str
    libelle: str
    pourquoi: str
    action: str
    sql: str


MACROS = """
CREATE OR REPLACE MACRO luhn_ok(s) AS (
    SELECT sum(CASE WHEN (length(s) - i) % 2 = 1
                    THEN (CASE WHEN 2 * d > 9 THEN 2 * d - 9 ELSE 2 * d END)
                    ELSE d END) % 10 = 0
    FROM (SELECT i, CAST(substr(s, i, 1) AS INTEGER) AS d FROM range(1, length(s) + 1) t(i)));
CREATE OR REPLACE MACRO somme_chiffres(s) AS (
    SELECT sum(CAST(substr(s, i, 1) AS INTEGER)) FROM range(1, length(s) + 1) t(i));
CREATE OR REPLACE MACRO siret_ok(s) AS (
    regexp_full_match(s, '[0-9]{14}')
    AND (luhn_ok(s) OR (s LIKE '356000000%' AND somme_chiffres(s) % 5 = 0)));
"""

_ADRESSE = "coalesce(numvoie,''), coalesce(typvoie,''), coalesce(voie,''), coalesce(lieuditbp,''), commune, departement"

RULES: list[Rule] = [
    Rule("R01", "Unicité", "Bloquante", "Numéro FINESS présent plusieurs fois",
         "Le numéro FINESS est la clé de jointure de tous les systèmes : un doublon rend l'import ambigu.",
         "Signaler au producteur ; ne garder qu'un enregistrement après arbitrage.",
         """SELECT nofinesset, 'présent ' || count(*) || ' fois' AS valeur_fautive
            FROM etab GROUP BY nofinesset HAVING count(*) > 1"""),
    Rule("R02", "Validité", "Bloquante", "Numéro FINESS hors format (9 caractères, motif [0-9][0-9A-Z][0-9]{7})",
         "Un identifiant mal formé ne se joint à aucun autre référentiel.",
         "Corriger le numéro à la source.",
         """SELECT nofinesset, coalesce(nofinesset, '(vide)') AS valeur_fautive FROM etab
            WHERE nofinesset IS NULL OR NOT regexp_full_match(nofinesset, '[0-9][0-9A-Z][0-9]{7}')"""),
    Rule("R03", "Complétude", "Bloquante", "Raison sociale vide",
         "Sans nom, l'établissement ne peut pas être présenté à un utilisateur.",
         "Compléter la raison sociale.",
         "SELECT nofinesset, '(vide)' AS valeur_fautive FROM etab WHERE rs IS NULL"),
    Rule("R04", "Cohérence", "Majeure", "Catégorie absente de la nomenclature TRE-R397 ou incohérente avec son agrégat",
         "La catégorie pilote les usages (autorisations, statistiques) : un code inconnu ou mal rattaché fausse les regroupements.",
         "Recoder la catégorie selon la nomenclature en vigueur.",
         """SELECT e.nofinesset,
                   CASE WHEN n.code IS NULL THEN 'catégorie ' || coalesce(e.categetab, '(vide)') || ' inconnue'
                        ELSE 'agrégat ' || e.categagretab || ' au lieu de ' || n.parent END AS valeur_fautive
            FROM etab e LEFT JOIN nomenclature n ON n.code = e.categetab
            WHERE n.code IS NULL OR e.categagretab IS DISTINCT FROM n.parent"""),
    Rule("R05", "Cohérence", "Majeure", "Entité juridique de rattachement absente du fichier des entités juridiques",
         "Impossible de connaître le gestionnaire ni le statut juridique de l'établissement.",
         "Vérifier le numéro d'EJ ; créer ou réactiver l'EJ dans FINESS.",
         """SELECT e.nofinesset, 'EJ ' || coalesce(e.nofinessej, '(vide)') AS valeur_fautive
            FROM etab e LEFT JOIN ej ON ej.nofiness = e.nofinessej WHERE ej.nofiness IS NULL"""),
    Rule("R06", "Validité", "Majeure", "SIRET renseigné mais pas sur 14 chiffres, ou clé de contrôle (Luhn) invalide",
         "Un SIRET faux empêche le rapprochement avec le répertoire SIRENE (facturation, conventionnement).",
         "Vérifier le SIRET dans SIRENE et le corriger.",
         "SELECT nofinesset, siret AS valeur_fautive FROM etab WHERE siret IS NOT NULL AND NOT siret_ok(siret)"),
    Rule("R07", "Cohérence", "Majeure", "Préfixe du numéro FINESS incohérent avec le département déclaré",
         "Le numéro FINESS est attribué par département : un écart signale un transfert mal enregistré ou une erreur de saisie.",
         "Vérifier le département de l'établissement et, si besoin, son numéro.",
         """SELECT e.nofinesset, 'préfixe ' || substr(e.nofinesset, 1, 2) || ', département ' || e.departement AS valeur_fautive
            FROM etab e LEFT JOIN ref_departement r ON r.departement_finess = e.departement
            WHERE r.prefixe_finess IS NULL OR substr(e.nofinesset, 1, 2) <> r.prefixe_finess"""),
    Rule("R07B", "Cohérence", "Information", "Code postal situé dans un autre département que le département déclaré",
         "Souvent légitime (commune limitrophe desservie par un bureau de poste voisin, CEDEX) : à connaître, pas à corriger d'office.",
         "Aucune correction automatique ; vérifier seulement si d'autres règles se déclenchent.",
         """SELECT e.nofinesset, e.ligneacheminement || ' (département ' || r.code_insee || ')' AS valeur_fautive
            FROM etab e JOIN ref_departement r ON r.departement_finess = e.departement
            WHERE CASE WHEN length(r.code_insee) = 3
                       -- outre-mer : les codes CEDEX suivent une numérotation propre (97004, 978xx...)
                       THEN substr(e.ligneacheminement, 1, 3) <> r.code_insee AND e.ligneacheminement NOT LIKE '%CEDEX%'
                       WHEN r.code_insee IN ('2A', '2B') THEN substr(e.ligneacheminement, 1, 2) <> '20'
                       ELSE substr(e.ligneacheminement, 1, 2) <> r.code_insee END"""),
    Rule("R08B", "Unicité", "Bloquante", "Doublon quasi certain : même SIRET, même adresse, même catégorie et même raison sociale",
         "Deux numéros pour le même établissement : double comptage dans les statistiques et dans les annuaires.",
         "Fusionner les deux numéros après vérification ; fermer le numéro en trop.",
         f"""WITH g AS (SELECT siret, {_ADRESSE}, categetab, rs, list(nofinesset ORDER BY nofinesset) AS ids
                       FROM etab WHERE siret IS NOT NULL AND (voie IS NOT NULL OR lieuditbp IS NOT NULL)
                       GROUP BY ALL HAVING count(*) > 1)
            SELECT unnest(ids) AS nofinesset, 'SIRET ' || siret || ' partagé avec ' || array_to_string(ids, ', ') AS valeur_fautive FROM g"""),
    Rule("R08", "Unicité", "Majeure", "Doublon probable : même SIRET, même adresse et même catégorie sous deux numéros",
         "Une même entité exerce rarement deux fois la même activité à la même adresse : probable double enregistrement.",
         "Comparer les deux fiches ; fusionner ou différencier l'activité.",
         f"""WITH g AS (SELECT siret, {_ADRESSE}, categetab, list(nofinesset ORDER BY nofinesset) AS ids,
                              count(DISTINCT rs) AS nb_rs
                       FROM etab WHERE siret IS NOT NULL AND (voie IS NOT NULL OR lieuditbp IS NOT NULL)
                       GROUP BY ALL HAVING count(*) > 1 AND count(DISTINCT rs) > 1)
            SELECT unnest(ids) AS nofinesset, 'SIRET ' || siret || ' partagé avec ' || array_to_string(ids, ', ') AS valeur_fautive FROM g"""),
    Rule("R09", "Géographie", "Majeure", f"Coordonnées situées hors du département déclaré (au-delà de {TOLERANCE_GEO_KM:g} km)",
         "L'établissement apparaît au mauvais endroit sur les cartes et dans les calculs d'accessibilité.",
         "Regéocoder l'adresse ; vérifier le département et l'adresse.",
         f"""SELECT g.nofinesset, 'déclaré ' || r.code_insee || ', point en ' || coalesce(g.dept_geo, 'hors contours')
                   || ' à ' || g.dist_dept_km || ' km' AS valeur_fautive
            FROM geo_prep g JOIN etab e USING (nofinesset) JOIN ref_departement r ON r.departement_finess = e.departement
            WHERE g.dist_dept_km > {TOLERANCE_GEO_KM}
              -- Saint-Barthélemy (97133) et Saint-Martin (97150) : collectivités séparées de la Guadeloupe
              -- depuis 2007 mais toujours rattachées au département 9A dans FINESS ; absentes du contour 971.
              AND substr(e.ligneacheminement, 1, 5) NOT IN ('97133', '97150')"""),
    Rule("R10", "Complétude", "Majeure", "Adresse incomplète (ni voie ni lieu-dit, ou commune manquante)",
         "Courrier, géocodage et orientation des usagers deviennent impossibles.",
         "Compléter l'adresse.",
         """SELECT nofinesset, coalesce(ligneacheminement, '(commune vide)') AS valeur_fautive FROM etab
            WHERE (voie IS NULL AND lieuditbp IS NULL) OR commune IS NULL"""),
    Rule("R11", "Complétude", "Mineure", "SIRET absent",
         "Le rapprochement avec SIRENE est impossible ; le taux d'absence varie fortement selon la catégorie (voir export par catégorie).",
         "Renseigner le SIRET quand l'établissement en a un.",
         "SELECT nofinesset, libcategagretab AS valeur_fautive FROM etab WHERE siret IS NULL"),
    Rule("R12", "Géographie", "Mineure", "Établissement sans coordonnées exploitables",
         "L'établissement n'apparaît sur aucune carte.",
         "Géocoder l'adresse.",
         """SELECT e.nofinesset, coalesce(g.epsg, 'projection inconnue ou coordonnées vides') AS valeur_fautive
            FROM etab e LEFT JOIN geo_prep g USING (nofinesset) WHERE g.latitude IS NULL"""),
    Rule("R13", "Géographie", "Mineure", "Géocodage peu précis (niveau 4 ou contours de commune ADMIN-EXPRESS)",
         "Le point est placé au centre de la commune : distances et cartes fines faussées.",
         "Regéocoder à l'adresse.",
         """SELECT nofinesset, 'niveau ' || niveau_geocodage || ', ' || referentiel AS valeur_fautive FROM geo_prep
            WHERE latitude IS NOT NULL AND (niveau_geocodage = '4' OR referentiel LIKE 'ADMIN-EXPRESS%')"""),
    Rule("R14", "Validité", "Mineure", "Téléphone renseigné au format invalide (attendu : 0 suivi de 9 chiffres, 2e chiffre non nul)",
         "Numéro inutilisable pour joindre l'établissement.",
         "Corriger le numéro.",
         """SELECT nofinesset, telephone AS valeur_fautive FROM etab
            WHERE telephone IS NOT NULL AND NOT regexp_full_match(telephone, '0[1-9][0-9]{8}')"""),
    Rule("R15", "Fraîcheur", "Information", "Fichier plus ancien que la fréquence de mise à jour annoncée",
         "Les réutilisateurs croient disposer de données à jour.",
         "Afficher la date d'extraction partout ; migrer vers les nouveaux flux FINESS de l'ANS.",
         f"""SELECT NULL AS nofinesset,
                   fichier || ' extrait le ' || date_extraction || ', âgé de '
                   || date_diff('day', CAST(date_extraction AS DATE), CAST(getvariable('date_execution') AS DATE))
                   || ' jours pour une fréquence annoncée de {FREQUENCE_ANNONCEE_JOURS} jours ; flux arrêtés le {DATE_ARRET_FLUX}' AS valeur_fautive
            FROM meta
            WHERE date_diff('day', CAST(date_extraction AS DATE), CAST(getvariable('date_execution') AS DATE)) > {FREQUENCE_ANNONCEE_JOURS}"""),
    Rule("R16", "Cohérence", "Majeure", "Catégorie fermée dans la nomenclature (statut « deprecated »)",
         "La catégorie n'existe plus : l'établissement n'a pas été recodé lors de la réforme de la nomenclature.",
         "Recoder vers la catégorie qui a remplacé l'ancienne.",
         """SELECT e.nofinesset, e.categetab || ' ' || n.libelle || ' (fermée le ' || coalesce(n.date_fin, '?') || ')' AS valeur_fautive
            FROM etab e JOIN nomenclature n ON n.code = e.categetab WHERE n.statut = 'deprecated'"""),
    Rule("R17", "Fraîcheur", "Mineure", f"Établissement non mis à jour depuis plus de {ANCIENNETE_MAJ_ANNEES} ans",
         "Fiche probablement obsolète (contacts, adresse, activité).",
         "Faire valider la fiche par l'agence régionale de santé.",
         f"""SELECT e.nofinesset, 'dernière mise à jour ' || e.datemaj AS valeur_fautive
            FROM etab e, (SELECT max(CAST(date_extraction AS DATE)) AS d FROM meta) m
            WHERE CAST(e.datemaj AS DATE) < m.d - INTERVAL {ANCIENNETE_MAJ_ANNEES} YEAR"""),
    Rule("R18", "Validité", "Information", "Date d'ouverture par défaut (1900 ou 1901)",
         "Date de remplissage technique, pas la vraie date d'ouverture : à exclure des analyses d'ancienneté.",
         "Renseigner la date d'ouverture réelle si elle est connue.",
         "SELECT nofinesset, dateouv AS valeur_fautive FROM etab WHERE dateouv <= '1901-01-01'"),
]

RULES_BY_ID = {r.id: r for r in RULES}


def run_rules(con, date_execution: str, rules: list[Rule] = RULES) -> None:
    """Exécute les règles et remplit la table anomalies."""
    con.execute(MACROS)
    con.execute(f"SET VARIABLE date_execution = '{date_execution}'")
    con.execute("""CREATE OR REPLACE TABLE anomalies (nofinesset VARCHAR, regle VARCHAR, dimension VARCHAR,
                   severite VARCHAR, valeur_fautive VARCHAR, action_corrective VARCHAR)""")
    for r in rules:
        con.execute(f"""INSERT INTO anomalies
            SELECT nofinesset, ?, ?, ?, valeur_fautive, ? FROM ({r.sql})""",
                    [r.id, r.dimension, r.severite, r.action])
