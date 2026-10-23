"""
Prix au m² par quartier pour les 50 communes les plus peuplées (prototype_quartiers.py).

Découpage : « grands quartiers » de l'INSEE (ex. Angers : Belle Beille, Roseraie Orgemont…),
reconstitués par union des contours IRIS (IGN, Licence Ouverte, via OpenDataSoft
« georef-france-iris »). Les communes qui n'en définissent pas au moins 3 (ex. Brest, Avignon)
sont ignorées et restent à l'échelle de la commune.

Prix : médiane des ventes DVF géolocalisées situées dans le contour, par type de bien.
Entrées : dvf_clean.parquet, API geo.api.gouv.fr (population), API OpenDataSoft (IRIS)
Sorties : geojson_cache/quartiers/<code_insee>.json, quartiers_villes.csv,
          quartiers_iris.csv (IRIS de chaque quartier, pour 22_prep_loyers_quartiers.py)
"""
import json
import os
import time

import pandas as pd
import requests
import shapely
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

NB_VILLES   = 50
MIN_GRANDS  = 3          # en dessous, la commune n'a pas de vrai découpage en grands quartiers
SIMPLIFIER  = 0.00005    # ~5 m : allège les contours sans déformer les quartiers
DOSSIER     = "geojson_cache/quartiers"
API_IRIS    = ("https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
               "georef-france-iris/exports/geojson")
TYPES       = {"Appartement": "app", "Maison": "mai"}


def arrondir(coords, decimales=5):
    if isinstance(coords[0], (int, float)):
        return [round(c, decimales) for c in coords]
    return [arrondir(c, decimales) for c in coords]


def premier(v):
    # OpenDataSoft renvoie parfois les champs texte sous forme de liste
    return v[0] if isinstance(v, list) else v


def plus_grandes_communes(n):
    r = requests.get("https://geo.api.gouv.fr/communes",
                     params={"fields": "nom,code,population", "format": "json"}, timeout=60)
    r.raise_for_status()
    return sorted(r.json(), key=lambda c: -c.get("population", 0))[:n]


def iris_commune(code):
    for essai in range(3):
        try:
            r = requests.get(API_IRIS, params={
                "where": f'com_code="{code}"',
                "select": "iris_code,iris_grd_quart_code,iris_grd_quart_name,geo_shape",
            }, timeout=120)
            r.raise_for_status()
            return r.json()["features"]
        except requests.RequestException:
            time.sleep(5 * (essai + 1))
    raise RuntimeError(f"IRIS indisponibles pour {code}")


def stats(geom, ventes):
    # Ventes contenues dans le contour (test vectorisé sur la boîte englobante puis le polygone)
    x0, y0, x1, y1 = geom.bounds
    v = ventes[(ventes.longitude >= x0) & (ventes.longitude <= x1) &
               (ventes.latitude >= y0) & (ventes.latitude <= y1)]
    v = v[shapely.contains_xy(geom, v.longitude.values, v.latitude.values)]
    props = {}
    for type_local, suffixe in TYPES.items():
        p = v.loc[v.type_local == type_local, "prix_m2"]
        props[f"nb_{suffixe}"] = int(len(p))
        props[f"prix_{suffixe}"] = round(float(p.median())) if len(p) else None
    return props


def feature(nom, geom, ventes):
    geom = geom.simplify(SIMPLIFIER, preserve_topology=True)
    g = mapping(geom)
    return {"type": "Feature",
            "properties": {"nom": nom, **stats(geom, ventes)},
            "geometry": {"type": g["type"], "coordinates": arrondir(g["coordinates"])}}


def main():
    os.makedirs(DOSSIER, exist_ok=True)
    print("Chargement DVF...")
    dvf = pd.read_parquet("dvf_clean.parquet",
                          columns=["type_local", "prix_m2", "latitude", "longitude"]).dropna()

    index, liens = [], []
    for c in plus_grandes_communes(NB_VILLES):
        code, nom = c["code"], c["nom"]
        feats = iris_commune(code)
        iris = pd.DataFrame([{
            "iris": premier(f["properties"]["iris_code"]),
            "code_quartier": premier(f["properties"]["iris_grd_quart_code"]),
            "grand": premier(f["properties"]["iris_grd_quart_name"]),
            "geom": shape(f["geometry"]),
        } for f in feats])
        if iris.empty or iris.grand.nunique() < MIN_GRANDS:
            print(f"  {nom} ({code}) : pas de grands quartiers INSEE, ignorée")
            continue

        contour = unary_union(iris.geom.tolist())
        x0, y0, x1, y1 = contour.bounds
        ventes = dvf[(dvf.longitude.between(x0, x1)) & (dvf.latitude.between(y0, y1))]

        sortie = [feature(q, unary_union(grp.geom.tolist()), ventes) for q, grp in iris.groupby("grand")]

        with open(f"{DOSSIER}/{code}.json", "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": sortie}, f, ensure_ascii=False)

        liens += [{"iris": r.iris, "code_commune": code, "code_quartier": r.code_quartier, "quartier": r.grand}
                  for r in iris.itertuples()]
        index.append({"code_commune": code, "nom": nom, "nb_quartiers": len(sortie), "nb_ventes": len(ventes)})
        print(f"  {nom} ({code}) : {len(sortie)} quartiers")
        time.sleep(1)  # politesse envers l'API publique

    pd.DataFrame(index).to_csv("quartiers_villes.csv", index=False)
    pd.DataFrame(liens).to_csv("quartiers_iris.csv", index=False)
    print(f"✅ {len(index)} communes → {DOSSIER}/, quartiers_villes.csv")


if __name__ == "__main__":
    main()
