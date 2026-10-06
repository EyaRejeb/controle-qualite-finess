# Contrôle qualité du référentiel FINESS

Mesurer la qualité du fichier national des établissements sanitaires et sociaux (FINESS), attribuer un score par région et par catégorie, et produire une liste d'anomalies avec une action corrective pour chacune.

**Résultat principal : 95,7 % des 102 939 établissements ne présentent aucune anomalie bloquante ni majeure.** Les 4 428 établissements restants concentrent trois problèmes : catégories fermées depuis 2018 et jamais recodées, adresses incomplètes, doublons probables.

## Le problème

FINESS est le référentiel national des établissements sanitaires, sociaux et médico-sociaux. Il est réutilisé par des logiciels de santé, des statistiques publiques et des cartographies. Une erreur dans ce fichier se propage dans tous ces usages.

Ce projet répond à trois besoins :

| Utilisateur | Besoin | Ce que le projet fournit |
|---|---|---|
| Chargé de mission données en agence régionale de santé | Savoir si les établissements de sa région sont bien référencés | Score par région et liste de ses anomalies |
| Data analyst chez un éditeur de logiciel de santé | Ne pas importer d'erreurs dans son produit | Règles bloquantes à appliquer avant import |
| Réutilisateur de données ouvertes | Connaître les limites du fichier | Synthèse des points de vigilance (ce README) |

## Données

| Ressource | Producteur | Date | Licence |
|---|---|---|---|
| [FINESS – Extraction du fichier des établissements géolocalisés](https://www.data.gouv.fr/datasets/finess-extraction-du-fichier-des-etablissements) | Ministère chargé de la santé | **extraction du 12 mai 2026** | Licence Ouverte |
| [FINESS – Extraction des entités juridiques](https://www.data.gouv.fr/datasets/finess-extraction-des-entites-juridiques) | Ministère chargé de la santé | extraction du 12 mai 2026 | Licence Ouverte |
| [Nomenclature TRE-R397, catégories d'établissement](https://github.com/ansforge/IG-terminologie-de-sante) | Agence du numérique en santé | version du 5 mai 2026 | Licence Ouverte |
| [Contours des départements](https://github.com/gregoiredavid/france-geojson) | G. David, d'après IGN ADMIN EXPRESS | 2018 | Licence Ouverte |

> **Ce jeu de données est arrêté.** Une nouvelle version de FINESS a été déployée le 20 juillet 2026 et la génération de ces fichiers a cessé. L'ANS publie désormais des flux quotidiens ([FINESS Structures](https://www.data.gouv.fr/datasets/finess-structures-1), [FINESS Activités](https://www.data.gouv.fr/datasets/finess-activites-1)). Ce projet analyse donc la dernière extraction publiée ; la migration vers les nouveaux flux est la suite naturelle (projet 6).

### Ce que la lecture du fichier a révélé

La documentation PDF fournie date de 2019 et ne décrit plus fidèlement le fichier. Rien n'a été supposé : tout a été vérifié à la lecture.

- **Séparateur** : `;`, alors que la documentation annonce une tabulation.
- **Encodage** : UTF-8.
- **Structure** : une ligne d'en-tête technique (`finess;etalab;98;2026-05-12`), puis deux sections dans le même fichier, `structureet` (31 champs) et `geolocalisation` (5 champs).
- **Guillemets** : une entité juridique contient un `;` dans une valeur entre guillemets. Un découpage naïf décale ses colonnes ; le projet utilise un vrai parseur CSV.
- **Outre-mer** : le département est codé `9A` à `9F` et `9J` (et non 971, 972…), et le numéro FINESS commence par `97` ou `98`.
- **Coordonnées** : 7 projections différentes (Lambert-93 en métropole, une projection UTM par territoire d'outre-mer). Toutes sont reprojetées en latitude/longitude WGS84.
- **Précision du géocodage** : le champ `sourcecoordet` contient un niveau (1 à 4) et le référentiel utilisé (BAN, BD ADRESSE, ADMIN-EXPRESS…).

## Méthode

```
data.gouv.fr ──► lecture contrôlée ──► DuckDB ──► reprojection ──► 20 règles SQL ──► anomalies + scores ──► Power BI
```

1. **Téléchargement** des quatre sources (`src/finess_qc/download.py`).
2. **Lecture** avec un parseur CSV strict, qui signale toute ligne au nombre de champs inattendu (`load.py`).
3. **Géographie** : reprojection en WGS84 et test d'appartenance de chaque point à son département déclaré (`geo.py`).
4. **Règles** : 20 requêtes DuckDB, chacune documentée par ce qu'elle vérifie, pourquoi c'est un problème métier et l'action corrective (`rules.py`).
5. **Scores et exports** (`report.py`).

**Score de qualité** = part des établissements sans anomalie bloquante ni majeure. Les anomalies mineures et les informations ne pénalisent pas le score.

### Sévérités

- **Bloquante** : l'enregistrement ne peut pas être importé tel quel (identifiant ou nom inutilisable, doublon quasi certain).
- **Majeure** : importable, mais faux ou incohérent sur une donnée de référence.
- **Mineure** : donnée absente ou imprécise, sans erreur avérée.
- **Information** : signal à connaître, souvent légitime.

## Résultats

Exécution du 6 octobre 2026 sur l'extraction du 12 mai 2026.

| Sévérité | Anomalies | Établissements touchés | Part des 102 939 établissements |
|---|---:|---:|---:|
| Bloquante | 32 | 32 | 0,03 % |
| Majeure | 4 465 | 4 398 | 4,3 % |
| Mineure | 23 389 | 20 478 | 19,9 % |
| Information | 1 615 | 1 613 | 1,6 % |

### Détail par règle (6 dimensions)

| ID | Dimension | Règle | Sévérité | Anomalies |
|---|---|---|---|---:|
| R01 | Unicité | Numéro FINESS présent plusieurs fois | Bloquante | 0 |
| R02 | Validité | Numéro FINESS hors format | Bloquante | 0 |
| R03 | Complétude | Raison sociale vide | Bloquante | 0 |
| R04 | Cohérence | Catégorie absente de la nomenclature ou mal rattachée à son agrégat | Majeure | 0 |
| R05 | Cohérence | Entité juridique de rattachement absente | Majeure | 13 |
| R06 | Validité | SIRET mal formé ou clé de Luhn invalide | Majeure | 12 |
| R07 | Cohérence | Préfixe du numéro FINESS incohérent avec le département | Majeure | 0 |
| R07B | Cohérence | Code postal d'un autre département | Information | 9 |
| R08 | Unicité | Doublon probable : même SIRET, adresse et catégorie | Majeure | 972 |
| R08B | Unicité | Doublon quasi certain : idem, avec la même raison sociale | Bloquante | 32 |
| R09 | Géographie | Coordonnées hors du département déclaré (> 1 km) | Majeure | 0 |
| R10 | Complétude | Adresse incomplète | Majeure | 1 185 |
| R11 | Complétude | SIRET absent | Mineure | 12 080 |
| R12 | Géographie | Pas de coordonnées exploitables | Mineure | 2 |
| R13 | Géographie | Géocodage à la commune seulement | Mineure | 4 665 |
| R14 | Validité | Téléphone au format invalide | Mineure | 9 |
| R15 | Fraîcheur | Fichier plus ancien que la fréquence annoncée (2 mois) | Information | 2 |
| R16 | Cohérence | Catégorie fermée dans la nomenclature | Majeure | 2 283 |
| R17 | Fraîcheur | Fiche non mise à jour depuis plus de 10 ans | Mineure | 6 633 |
| R18 | Validité | Date d'ouverture par défaut (1900 ou 1901) | Information | 1 604 |

**Les règles à zéro ne sont pas inutiles.** R01 à R04, R07 et R09 confirment que le fichier publié est sain sur ces points. Elles restent les garde-fous à appliquer avant tout import, à chaque nouvelle version.

### Ce que je recommanderais au producteur

1. **Recoder 2 283 établissements dont la catégorie est fermée depuis 2018** (R16). Trois catégories du handicap concentrent l'essentiel : foyers de vie (1 059), foyers d'hébergement (708) et foyers d'accueil médicalisés (363). La réforme de la nomenclature n'a pas été répercutée sur ces fiches ; elles dominent le top 10 des catégories les plus touchées.
2. **Compléter 1 185 adresses** sans voie ni lieu-dit (R10), qui empêchent tout géocodage précis.
3. **Arbitrer 1 004 doublons probables ou quasi certains** (R08 et R08B) : même SIRET, même adresse, même catégorie sous plusieurs numéros FINESS.

### Scores par région

Les territoires d'outre-mer ont les scores les plus bas : Saint-Pierre-et-Miquelon et Wallis-et-Futuna 88,9 % (sur 18 établissements seulement), Guadeloupe 91,9 %, Guyane 92,0 %, Mayotte 92,1 %. En métropole, l'écart va de 93,2 % (Bourgogne-Franche-Comté) à 98,1 % (Provence-Alpes-Côte d'Azur). Le détail est dans `exports/scores_region.csv`.

## Éviter les faux positifs

Trois règles du cahier des charges initial auraient produit des alertes en masse sur des situations légitimes. Elles ont été recalibrées après examen des cas.

- **Code postal et département (R07 → R07B)** : les écarts concernent des communes limitrophes (Port-Sainte-Foy, en Dordogne, a un code postal 33 ; Saint-Pierre-Laval, dans l'Allier, un code postal 42) et des adresses CEDEX. La règle majeure compare donc le préfixe du numéro FINESS au département ; l'écart de code postal devient une simple information.
- **Doublons (R08)** : « même SIRET et même adresse » remontait 6 187 établissements, car une même structure gère souvent plusieurs activités distinctes à la même adresse (un service d'aide à domicile et un EHPAD, par exemple). Ajouter la catégorie ramène à 1 004 cas, et la raison sociale identique isole 32 doublons quasi certains.
- **Coordonnées hors département (R09)** : la première version signalait 65 établissements situés à plus de 200 km de la Guadeloupe. Ce sont tous des établissements de Saint-Martin et Saint-Barthélemy : collectivités distinctes depuis 2007, mais toujours rattachées au département 9A dans FINESS, et absentes du contour de la Guadeloupe. Ils sont exclus de la règle. Une tolérance de 1 km absorbe aussi l'imprécision des contours simplifiés.
- **SIRET (R06)** : la clé de Luhn ne s'applique pas aux établissements de La Poste (SIREN 356 000 000), contrôlés par la somme de leurs chiffres. L'exception est codée et testée.
- **SIRET absent (R11)** : classée mineure, car le taux d'absence dépend de la catégorie (6,6 % pour les EHPAD, 35,6 % pour les centres de PMI). Le taux par catégorie figure dans `exports/scores_categorie.csv`.

## Limites

- **Jeu de données arrêté** au 12 mai 2026 : les résultats décrivent un état figé, pas la situation actuelle.
- **Niveau de géocodage** : la signification des niveaux 1 à 4 n'est pas documentée. L'interprétation retenue (4 = position de la commune) repose sur le référentiel associé (ADMIN-EXPRESS, le référentiel des communes).
- **Contours départementaux** de 2018, simplifiés ; Saint-Pierre-et-Miquelon et Wallis-et-Futuna n'y figurent pas, R09 ne les contrôle donc pas.
- **Fréquence annoncée** (« tous les deux mois ») relevée manuellement sur data.gouv.fr le 6 octobre 2026.
- **Règle R17** : une fiche ancienne n'est pas forcément fausse, d'où la sévérité mineure.

## Lancer le projet

Prérequis : Python 3.10 ou plus.

```bash
pip install -e ".[dev]"
finess-qc                     # télécharge, contrôle et exporte, en une commande
pytest                        # 47 tests : un cas positif et un cas négatif par règle
```

Options : `--force-download` pour retélécharger les sources, `--raw-dir <dossier>` pour utiliser des fichiers déjà téléchargés, `--date-execution AAAA-MM-JJ` pour fixer la date de référence de la règle de fraîcheur. Durée : une dizaine de secondes après téléchargement.

## Exports

| Fichier | Contenu |
|---|---|
| `exports/anomalies.csv` | Une ligne par anomalie : numéro FINESS, règle, dimension, sévérité, valeur fautive, action corrective |
| `exports/etablissements.csv` | Un établissement par ligne, avec région, latitude/longitude, nombre d'anomalies par sévérité et indicateur de conformité (régénéré, non versionné) |
| `exports/regles.csv` | Catalogue des règles et nombre d'anomalies |
| `exports/scores_region.csv` | Score et anomalies par région |
| `exports/scores_categorie.csv` | Score, anomalies et taux de SIRET absent par catégorie |
| `exports/synthese.json` | Chiffres clés de l'exécution |

Pour Power BI : importer `etablissements.csv` et `anomalies.csv`, relier `etablissements[nofinesset]` à `anomalies[nofinesset]` (un à plusieurs), et `regles[id]` à `anomalies[regle]`. Le score se calcule ainsi :

```DAX
Score qualité = DIVIDE(
    CALCULATE(COUNTROWS(etablissements), etablissements[conforme] = TRUE()),
    COUNTROWS(etablissements))
```

## Structure du dépôt

```
src/finess_qc/
  config.py      sources, seuils, projections
  download.py    téléchargement
  load.py        lecture contrôlée et chargement DuckDB
  geo.py         reprojection et appartenance au département
  rules.py       catalogue des 20 règles
  report.py      scores et exports
  __main__.py    point d'entrée `finess-qc`
ref/departements.csv   correspondance département FINESS → code INSEE, préfixe, région
tests/                 un cas positif et un cas négatif par règle
exports/               sorties pour Power BI
```

## Sources

Consultées le 6 octobre 2026.

- [FINESS – Extraction du fichier des établissements, data.gouv.fr](https://www.data.gouv.fr/datasets/finess-extraction-du-fichier-des-etablissements)
- [FINESS – Extraction des entités juridiques, data.gouv.fr](https://www.data.gouv.fr/datasets/finess-extraction-des-entites-juridiques)
- [Spécifications FINESS, dépôt ansforge/finess](https://github.com/ansforge/finess)
- [Terminologies de santé de l'ANS, dépôt ansforge/IG-terminologie-de-sante](https://github.com/ansforge/IG-terminologie-de-sante)
- [Contours des départements, dépôt gregoiredavid/france-geojson](https://github.com/gregoiredavid/france-geojson)
