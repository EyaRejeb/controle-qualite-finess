"""Un cas positif (la règle se déclenche) et un cas négatif (elle ne se déclenche pas) par règle."""
import pytest

from finess_qc.rules import RULES

from conftest import etab, geo, siret_valide

ID = "330000011"
AUTRE_SIRET = siret_valide("9876543210001")

# (règle, paramètres de run, identifiant attendu)
POSITIFS = [
    ("R01", dict(etabs=[etab(), etab(siret=AUTRE_SIRET)]), ID),
    ("R02", dict(etabs=[etab(nofinesset="33000011")]), "33000011"),
    ("R03", dict(etabs=[etab(rs=None)]), ID),
    ("R04", dict(etabs=[etab(categetab="999")]), ID),
    ("R04", dict(etabs=[etab(categagretab="9999")]), ID),
    ("R05", dict(etabs=[etab(nofinessej="339999999")]), ID),
    ("R06", dict(etabs=[etab(siret="12345678900011")]), ID),
    ("R06", dict(etabs=[etab(siret="1234567890")]), ID),
    ("R07", dict(etabs=[etab(nofinesset="240000011")], geos=[geo(nofinesset="240000011")]), "240000011"),
    ("R07B", dict(etabs=[etab(ligneacheminement="24000 PERIGUEUX")]), ID),
    ("R08B", dict(etabs=[etab(), etab(nofinesset="330000029")]), "330000029"),
    ("R08", dict(etabs=[etab(), etab(nofinesset="330000029", rs="AUTRE NOM")]), "330000029"),
    ("R09", dict(geos=[geo(dist_dept_km=5.0, dept_geo="24")]), ID),
    ("R10", dict(etabs=[etab(voie=None, lieuditbp=None)]), ID),
    ("R11", dict(etabs=[etab(siret=None)]), ID),
    ("R12", dict(geos=[geo(latitude=None, longitude=None)]), ID),
    ("R12", dict(geos=[]), ID),
    ("R13", dict(geos=[geo(niveau_geocodage="4", referentiel="ADMIN-EXPRESS-2023")]), ID),
    ("R14", dict(etabs=[etab(telephone="0056000000")]), ID),
    ("R15", dict(date_execution="2026-10-06"), "(fichier)"),
    ("R16", dict(etabs=[etab(categetab="382", categagretab="4402")]), ID),
    ("R17", dict(etabs=[etab(datemaj="2010-01-01")]), ID),
    ("R18", dict(etabs=[etab(dateouv="1901-01-01")]), ID),
]

NEGATIFS = [
    ("R01", dict(etabs=[etab(), etab(nofinesset="330000029", siret=AUTRE_SIRET)])),
    ("R02", dict(etabs=[etab(nofinesset="2A0000011", departement="2A", ligneacheminement="20000 AJACCIO")])),
    ("R03", dict()),
    ("R04", dict()),
    ("R05", dict()),
    ("R06", dict(etabs=[etab(siret="35600000000001")])),          # La Poste : règle de la somme des chiffres
    ("R07", dict(etabs=[etab(nofinesset="970000011", departement="9A", ligneacheminement="97100 BASSE TERRE")],
                 geos=[geo(nofinesset="970000011")])),             # outre-mer : préfixe 97 pour 9A
    ("R07B", dict(etabs=[etab(departement="9A", nofinesset="970000011", ligneacheminement="97004 POINTE A PITRE CEDEX")],
                  geos=[geo(nofinesset="970000011")])),
    ("R08B", dict(etabs=[etab(), etab(nofinesset="330000029", categetab="382", categagretab="4402")])),
    ("R08", dict(etabs=[etab(), etab(nofinesset="330000029", rs="AUTRE NOM", numvoie="14")])),
    ("R09", dict(geos=[geo(dist_dept_km=0.5)])),                  # dans la tolérance
    ("R09", dict(etabs=[etab(nofinesset="970000011", departement="9A", ligneacheminement="97150 ST MARTIN")],
                 geos=[geo(nofinesset="970000011", dist_dept_km=233.0)])),  # Saint-Martin
    ("R10", dict(etabs=[etab(voie=None, lieuditbp="LIEU DIT LES PINS")])),
    ("R11", dict()),
    ("R12", dict()),
    ("R13", dict(geos=[geo(niveau_geocodage="2")])),
    ("R14", dict()),
    ("R15", dict(date_execution="2026-06-01")),
    ("R16", dict()),
    ("R17", dict(etabs=[etab(datemaj="2020-01-01")])),
    ("R18", dict(etabs=[etab(dateouv="1950-06-01")])),
]


def test_etablissement_de_reference_sans_anomalie(run):
    assert run() == set()


@pytest.mark.parametrize("regle,params,attendu", POSITIFS, ids=[f"{p[0]}-{i}" for i, p in enumerate(POSITIFS)])
def test_cas_positif(run, regle, params, attendu):
    assert (attendu, regle) in run(**params)


@pytest.mark.parametrize("regle,params", NEGATIFS, ids=[f"{n[0]}-{i}" for i, n in enumerate(NEGATIFS)])
def test_cas_negatif(run, regle, params):
    assert regle not in {r for _, r in run(**params)}


def test_chaque_regle_a_ses_deux_cas():
    ids = {r.id for r in RULES}
    assert ids <= {p[0] for p in POSITIFS}
    assert ids <= {n[0] for n in NEGATIFS}


def test_categorie_fermee_ne_compte_pas_comme_inconnue(run):
    regles = {r for _, r in run(etabs=[etab(categetab="382", categagretab="4402")])}
    assert "R16" in regles and "R04" not in regles
