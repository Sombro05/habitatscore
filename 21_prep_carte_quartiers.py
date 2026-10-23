"""
Carte « Explorer le marché » (échelle Commune) : les grandes villes découpées en quartiers.

Chaque commune préparée par 20_prep_quartiers.py est remplacée par ses grands quartiers INSEE,
nommés « Ville : Quartier » (ex. « Angers : Belle Beille »).
- Prix au m² : médiane DVF du quartier ; repli sur le prix de la commune sous MIN_VENTES ventes.
- Loyer : loyer ANIL de la commune × écart du quartier (coef_loyer, 22_prep_loyers_quartiers.py,
  encadrement des loyers ou observatoires locaux).
- Rendement : loyer hors charges récupérables (scoring.py) × 12 / prix × coefficients de vacance et de rotation (règle de 05_prep_carte.py),
  seulement si le quartier a assez de ventes ET un écart de loyer connu.
  Sinon, rendement de la commune si elle a assez de ventes (signalé), sinon « données insuffisantes » :
  jamais de mélange ; un loyer communal divisé par un prix
  de quartier surestimerait le rendement des quartiers bon marché, dont les loyers sont aussi plus bas.
- Paris, Lyon, Marseille : la commune n'a pas de ventes DVF propres (elles sont par arrondissement) ;
  chaque quartier prend les valeurs de son arrondissement (5 premiers chiffres du code quartier INSEE).
Contours : les quartiers (IGN) sont découpés sur le contour de la commune de la carte
(communes_small.geojson, autre source) et les chutes rattachées au quartier le plus proche,
pour éviter trous et chevauchements avec les communes voisines.
Entrées : geojson_cache/<type>_<métrique>.json (12_prep_geojson.py), geojson_cache/quartiers/,
          quartiers_iris.csv, loyers_quartiers.csv, dvf_carte.csv (05_prep_carte.py)
Sorties : geojson_cache/<type>_<métrique>_quartiers.json
"""
import json
import os

import pandas as pd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from scoring import loyer_hors_charges

MIN_VENTES = 20   # identique à prototype_quartiers.py
TYPES      = {"Appartement": "app", "Maison": "mai"}
METRIQUES  = ["prix_m2_median", "rendement_median"]
DOSSIER_Q  = "geojson_cache/quartiers"

def arrondir(coords, decimales=4):
    if isinstance(coords[0], (int, float)):
        return [round(c, decimales) for c in coords]
    return [arrondir(c, decimales) for c in coords]


def ajuster(contour_commune, features_q):
    # Quartiers ∩ commune, puis chaque morceau de commune non couvert → quartier le plus proche
    commune = shape(contour_commune).buffer(0)
    geoms = [shape(q["geometry"]).buffer(0).intersection(commune) for q in features_q]
    reste = commune.difference(unary_union(geoms))
    for morceau in getattr(reste, "geoms", [reste]):
        if morceau.is_empty:
            continue
        i = min(range(len(geoms)), key=lambda k: geoms[k].distance(morceau))
        geoms[i] = unary_union([geoms[i], morceau])
    sortie = []
    for g in geoms:
        g = mapping(g.buffer(0))
        sortie.append({"type": g["type"], "coordinates": arrondir(g["coordinates"])}
                      if g["type"] in ("Polygon", "MultiPolygon") else None)
    return sortie


# Valeurs de référence par commune (ou arrondissement) et type de bien
carte = pd.read_csv("dvf_carte.csv", dtype={"code_commune": str}).set_index(["code_commune", "type_local"])
codes_q = (pd.read_csv("quartiers_iris.csv", dtype=str).drop_duplicates(["code_commune", "quartier"])
             .set_index(["code_commune", "quartier"]).code_quartier)
loyers_q = pd.read_csv("loyers_quartiers.csv", dtype={"code_commune": str}).set_index(["code_commune", "quartier"])


COMMUNES_A_ARRONDISSEMENTS = {"75056", "69123", "13055"}


def reference(code_commune, nom_quartier, type_local):
    # Arrondissement du quartier (Paris, Lyon, Marseille), sinon la commune. La ligne « commune »
    # de Paris, Lyon et Marseille n'a aucune vente propre (valeurs interpolées) : jamais utilisée
    arr = str(codes_q.get((code_commune, nom_quartier), ""))[:5]
    if (arr, type_local) in carte.index:
        return carte.loc[(arr, type_local)]
    if code_commune in COMMUNES_A_ARRONDISSEMENTS or (code_commune, type_local) not in carte.index:
        return None
    return carte.loc[(code_commune, type_local)]


quartiers = {}
for fichier in os.listdir(DOSSIER_Q):
    with open(f"{DOSSIER_Q}/{fichier}", encoding="utf-8") as f:
        quartiers[fichier.removesuffix(".json")] = json.load(f)["features"]
print(f"{len(quartiers)} communes découpées en quartiers")

for type_local, suffixe in TYPES.items():
    for metrique in METRIQUES:
        with open(f"geojson_cache/{type_local}_{metrique}.json", encoding="utf-8") as f:
            base = json.load(f)

        sortie, remplacees = [], 0
        for commune in base["features"]:
            p = commune["properties"]
            code = str(p.get("code", "")).zfill(5)
            if code not in quartiers:
                sortie.append(commune)
                continue
            remplacees += 1
            contours = ajuster(commune["geometry"], quartiers[code])
            for q, contour in zip(quartiers[code], contours):
                if contour is None:   # quartier hors du contour communal de la carte
                    continue
                qp = q["properties"]
                nb, prix = qp[f"nb_{suffixe}"], qp[f"prix_{suffixe}"]
                ref = reference(code, qp["nom"], type_local)
                props = {**p, "nom": f"{p['nom']} : {qp['nom']}"}
                fiable = nb >= MIN_VENTES and prix is not None
                # Commune (ou arrondissement) elle-même fondée sur assez de ventes ; sinon son prix est
                # lissé vers l'intercommunalité (ex. maisons du 7e : 1 vente, prix du Grand Paris)
                ref_fiable = ref is not None and ref.nb_ventes >= MIN_VENTES
                lq = loyers_q.loc[(code, qp["nom"])] if (code, qp["nom"]) in loyers_q.index else None
                ecart_connu = lq is not None and lq.source != "" and pd.notna(lq.source)

                if ref is None or not (fiable or ref_fiable) or (fiable and not ecart_connu and not ref_fiable):
                    props.update(val=None, rendement="—", loyer_m2="—", vacance="—", rotation="—",
                                 prix_m2=f"données insuffisantes ({nb} ventes dans le quartier)")
                    sortie.append({"type": "Feature", "properties": props, "geometry": contour})
                    continue

                if fiable and ecart_connu:
                    # Quartier complet : son prix et son loyer
                    loyer = ref.loyer_m2_estime * lq.coef_loyer
                    rendement = (loyer_hors_charges(loyer, type_local) * 12 / prix * 100
                                 * ref.coef_vacance * ref.coef_rotation)
                    props["loyer_m2"] = f"{loyer:.2f} €/m² (quartier : {lq.source}, {lq.coef_loyer - 1:+.0%} vs commune)"
                    props["rendement"] = f"{rendement:.2f} %"
                else:
                    # Loyer ou prix du quartier inconnu : rendement de la commune, jamais un mélange
                    # (loyer communal / prix de quartier ou l'inverse)
                    rendement = ref.rendement_median
                    props["loyer_m2"] = f"{ref.loyer_m2_estime:.2f} €/m² (commune)"
                    props["rendement"] = f"{rendement:.2f} % (commune)"
                if fiable:
                    props["prix_m2"] = f"{prix:,.0f} €/m² ({nb} ventes)"
                else:
                    prix = ref.prix_m2_median
                    props["prix_m2"] = f"{prix:,.0f} €/m² (commune, {nb} ventes dans le quartier)"
                props["vacance"] = f"{ref.vacance_locative:.0%}" if pd.notna(ref.vacance_locative) else "—"
                props["rotation"] = (f"{ref.rotation:.1%} des logements vendus / an (× {ref.coef_rotation:.2f})"
                                     if pd.notna(ref.rotation) else "N/D (× 1.00)")
                props["val"] = float(prix) if metrique == "prix_m2_median" else round(float(rendement), 2)
                sortie.append({"type": "Feature", "properties": props, "geometry": contour})

        with open(f"geojson_cache/{type_local}_{metrique}_quartiers.json", "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": sortie}, f, ensure_ascii=False)
        print(f"✅ {type_local} × {metrique} : {remplacees} communes remplacées, {len(sortie):,} zones")
