"""
Carte « Explorer le marché » à l'échelle des intercommunalités (EPCI).

Pour chaque EPCI et type de bien :
- prix au m² : médiane des prix communaux (non lissés) pondérée par le nombre de ventes ;
- loyer au m² : moyenne des loyers communaux pondérée par le nombre de ventes ;
- vacance locative : logements vacants / (vacants + loués) sur l'ensemble de l'EPCI ;
- rendement : loyer × 12 / prix × coefficient de vacance (même règle que 16_prep_vacance.py).
Contours : union des communes de l'EPCI (communes_small.geojson), anciennes communes
rattachées via vacance_communes.csv (code_commune_2023).

- taux de rotation : ventes / 3 ans / logements sur l'ensemble de l'EPCI (règle de 19_prep_rotation.py).
Entrées : dvf_carte.csv (05_prep_carte.py), vacance_communes.csv, loyers_anil_2025.csv
Sorties : geojson_cache/EPCI_Appartement.json, geojson_cache/EPCI_Maison.json
"""
import json
import pandas as pd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

SEUIL_VACANCE = 0.30  # identique à 16_prep_vacance.py
SEUIL_ROTATION, PENTE, PLANCHER = 0.015, 2, 0.25  # identiques à 19_prep_rotation.py

def arrondir(coords, decimales=4):
    if isinstance(coords[0], (int, float)):
        return [round(c, decimales) for c in coords]
    return [arrondir(c, decimales) for c in coords]

def mediane_ponderee(valeurs, poids):
    d = pd.DataFrame({"v": valeurs, "p": poids}).sort_values("v")
    cumul = d["p"].cumsum()
    return d.loc[cumul >= cumul.iloc[-1] / 2, "v"].iloc[0]

# Commune (actuelle) → EPCI, et anciennes communes → commune actuelle
anil = pd.read_csv("loyers_anil_2025.csv", sep=";", encoding="latin-1", dtype=str)
epci_de = dict(zip(anil["INSEE_C"].str.zfill(5), anil["EPCI"]))
vac = pd.read_csv("vacance_communes.csv", dtype={"code_commune": str, "code_commune_2023": str})
actuelle_de = dict(zip(vac["code_commune"], vac["code_commune_2023"]))

# Vacance et commune principale (la plus grande) par EPCI, sur les communes actuelles
vac_actuelles = vac[vac["code_commune"] == vac["code_commune_2023"]].copy()
vac_actuelles["EPCI"] = vac_actuelles["code_commune"].map(epci_de)
rot = pd.read_csv("rotation_communes.csv", dtype={"code_commune": str})
vac_actuelles = vac_actuelles.merge(rot[["code_commune", "ventes_3ans"]], on="code_commune", how="left")
par_epci = vac_actuelles.groupby("EPCI").agg(vacants=("logements_vacants", "sum"),
                                             loues=("logements_loues", "sum"),
                                             logements=("logements", "sum"),
                                             ventes=("ventes_3ans", "sum"),
                                             nb_communes=("code_commune", "count"))
par_epci["rotation"] = par_epci["ventes"] / 3 / par_epci["logements"]
par_epci["coef_rot"] = (1 - PENTE * ((SEUIL_ROTATION - par_epci["rotation"]) / SEUIL_ROTATION).clip(lower=0)).clip(lower=PLANCHER)
par_epci["vacance"] = par_epci["vacants"] / (par_epci["vacants"] + par_epci["loues"])
par_epci["coef"] = (1 - (par_epci["vacance"] - SEUIL_VACANCE).clip(lower=0)).clip(lower=0)

# Contours : union des communes de chaque EPCI
with open("communes_small.geojson", encoding="utf-8") as f:
    communes = json.load(f)
noms_communes, formes = {}, {}
for feat in communes["features"]:
    code = str(feat["properties"].get("code", "")).zfill(5)
    epci = epci_de.get(actuelle_de.get(code, code))
    if epci is None or feat["geometry"] is None:
        continue
    formes.setdefault(epci, []).append(shape(feat["geometry"]).buffer(0))
contours = {e: unary_union(g).simplify(0.001, preserve_topology=True) for e, g in formes.items()}
print(f"✅ {len(contours):,} intercommunalités dessinées")

grande_commune = (vac_actuelles.merge(anil.assign(code_commune=anil["INSEE_C"].str.zfill(5))[["code_commune", "LIBGEO"]],
                                      on="code_commune")
                  .sort_values("logements").groupby("EPCI")["LIBGEO"].last())

carte = pd.read_csv("dvf_carte.csv", dtype={"code_commune": str, "EPCI": str})
for type_local in ["Appartement", "Maison"]:
    d = carte[(carte["type_local"] == type_local) & (carte["nb_ventes"] > 0) & carte["EPCI"].notna()]
    features = []
    for epci, g in d.groupby("EPCI"):
        if epci not in contours:
            continue
        prix  = mediane_ponderee(g["prix_m2_brut"], g["nb_ventes"])
        loyer = (g["loyer_m2_estime"] * g["nb_ventes"]).sum() / g["nb_ventes"].sum()
        info  = par_epci.loc[epci] if epci in par_epci.index else None
        coef  = float(info["coef"] * info["coef_rot"]) if info is not None else 1.0
        rdt   = loyer * 12 / prix * 100 * coef
        geom  = mapping(contours[epci])
        geom["coordinates"] = arrondir(json.loads(json.dumps(geom["coordinates"])))
        features.append({"type": "Feature", "geometry": geom, "properties": {
            "nom":       f"Autour de {grande_commune.get(epci, '?')}",
            "val_prix_m2_median":   round(float(prix)),
            "val_rendement_median": round(float(rdt), 2),
            "rendement": f"{rdt:.2f} %",
            "prix_m2":   f"{prix:,.0f} €/m²",
            "loyer_m2":  f"{loyer:.2f} €/m²",
            "vacance":   f"{info['vacance']:.0%}" if info is not None else "—",
            "rotation":  (f"{info['rotation']:.1%} des logements vendus / an (× {info['coef_rot']:.2f})"
                          if info is not None else "—"),
            "ventes":    f"{int(g['nb_ventes'].sum()):,}".replace(",", " "),
        }})
    nom = f"geojson_cache/EPCI_{type_local}.json"
    with open(nom, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f,
                  separators=(",", ":"), ensure_ascii=False)
    print(f"  ✅ {nom} — {len(features):,} intercommunalités")
