"""Préparation géographique : reprojection en WGS84 et contrôle d'appartenance au département.

Le champ sourcecoordet est une liste « niveau,producteur,score,référentiel,projection ».
Exemple : « 1,ATLASANTE,96,BAN,EPSG:2154 RGF93 / Lambert-93 (Métropole) ».
Les coordonnées X/Y sont exprimées dans la projection indiquée (7 projections dans le fichier).
"""
import json
from collections import defaultdict
from pathlib import Path

import duckdb
import pyarrow as pa
from pyproj import Geod, Transformer
from shapely.geometry import Point, shape
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from .config import PROJECTIONS
from .load import create_table

GEOD = Geod(ellps="WGS84")
GEO_PREP_COLS = ["nofinesset", "niveau_geocodage", "referentiel", "epsg", "latitude", "longitude",
                 "dept_geo", "dist_dept_km"]


def _epsg(source: str | None) -> str | None:
    if not source:
        return None
    proj = source.split(",")[-1]
    for key, epsg in PROJECTIONS.items():
        if proj.startswith(key):
            return epsg
    return None


def build_geo_prep(con: duckdb.DuckDBPyConnection, geojson_path: Path) -> dict:
    rows = con.execute("""
        SELECT g.nofinesset, g.coordxet, g.coordyet, g.sourcecoordet, r.code_insee
        FROM geo g JOIN etab e USING (nofinesset)
        LEFT JOIN ref_departement r ON r.departement_finess = e.departement""").fetchall()

    features = json.load(open(geojson_path, encoding="utf-8"))["features"]
    polys = {f["properties"]["code"]: shape(f["geometry"]) for f in features}
    codes = list(polys)
    tree = STRtree([polys[c] for c in codes])

    transformers: dict[str, Transformer] = {}
    by_epsg: dict[str, list] = defaultdict(list)
    out, projections_inconnues = [], 0
    for nofiness, x, y, src, dept_decl in rows:
        parts = (src or "").split(",")
        niveau = parts[0] if len(parts) > 1 else None
        referentiel = parts[3] if len(parts) > 3 else None
        epsg = _epsg(src)
        if x is None or y is None or epsg is None:
            projections_inconnues += int(x is not None and epsg is None)
            out.append([nofiness, niveau, referentiel, epsg, None, None, None, None])
            continue
        by_epsg[epsg].append((len(out), float(x), float(y)))
        out.append([nofiness, niveau, referentiel, epsg, None, None, None, dept_decl])

    for epsg, pts in by_epsg.items():
        t = transformers.setdefault(epsg, Transformer.from_crs(epsg, "EPSG:4326", always_xy=True))
        lons, lats = t.transform([p[1] for p in pts], [p[2] for p in pts])
        for (i, _, _), lon, lat in zip(pts, lons, lats):
            out[i][4], out[i][5] = round(lat, 6), round(lon, 6)

    for row in out:
        lat, lon, dept_decl = row[4], row[5], row[7]
        row[7] = None
        if lat is None:
            continue
        p = Point(lon, lat)
        hits = [codes[i] for i in tree.query(p, predicate="within")]
        row[6] = hits[0] if hits else None
        if dept_decl in polys:          # 975 et 986 n'ont pas de contour : distance inconnue
            if dept_decl in hits:
                row[7] = 0.0
            else:
                _, q = nearest_points(p, polys[dept_decl])
                row[7] = round(GEOD.inv(lon, lat, q.x, q.y)[2] / 1000, 3)

    dbl = pa.float64()
    create_table(con, "geo_prep", GEO_PREP_COLS, out,
                 types={"latitude": dbl, "longitude": dbl, "dist_dept_km": dbl})
    return {"points_reprojetes": sum(1 for r in out if r[4] is not None),
            "projections_inconnues": projections_inconnues}
