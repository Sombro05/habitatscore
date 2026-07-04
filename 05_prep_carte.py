import pandas as pd
import json
import numpy as np
from math import radians, sin, cos, sqrt, atan2

print("Chargement...")
df     = pd.read_csv("dvf_clean.csv", low_memory=False)
loyers = pd.read_csv("loyers_clean.csv", dtype={"code_commune": str})

df["code_commune"] = df["code_commune"].astype(str).str.zfill(5)

carte = df.groupby(["code_commune", "nom_commune", "code_departement", "type_local"]).agg(
    prix_m2_median = ("prix_m2", "median"),
    nb_ventes      = ("valeur_fonciere", "count"),
).reset_index()

carte["prix_m2_median"] = carte["prix_m2_median"].round(0)
carte["code_commune"]   = carte["code_commune"].astype(str).str.zfill(5)

# Jointure loyers ANIL
carte = carte.merge(loyers[["code_commune","loyer_m2"]], on="code_commune", how="left")
carte["loyer_m2_estime"] = carte.apply(
    lambda r: round(r["loyer_m2"] * 1.15, 2)
              if r["type_local"] == "Maison" and pd.notna(r["loyer_m2"])
              else round(r["loyer_m2"], 2) if pd.notna(r["loyer_m2"])
              else round(r["prix_m2_median"] * 0.045 / 12, 2),
    axis=1
).clip(4, 40)

carte["rendement_median"] = (carte["loyer_m2_estime"] * 12 / carte["prix_m2_median"] * 100).round(2)

print(f"Communes avec données DVF : {len(carte['code_commune'].unique()):,}")

# ── Lissage des communes sans données (blanc sur la carte) ──────────────
# Extraire centroïdes depuis GeoJSON
print("Extraction centroïdes communes...")
with open("communes.geojson", "r", encoding="utf-8") as f:
    geojson = json.load(f)

centroides = []
for feature in geojson["features"]:
    code = str(feature["properties"].get("code", "")).zfill(5)
    nom  = feature["properties"].get("nom", "")
    geom = feature["geometry"]
    if geom is None:
        continue
    if geom["type"] == "Polygon":
        coords = geom["coordinates"][0]
    elif geom["type"] == "MultiPolygon":
        coords = geom["coordinates"][0][0]
    else:
        continue
    lon = np.mean([c[0] for c in coords])
    lat = np.mean([c[1] for c in coords])
    centroides.append({"code_commune": code, "nom_commune": nom, "lat": lat, "lon": lon})

geo = pd.DataFrame(centroides)
print(f"✅ {len(geo):,} centroïdes extraits")

# Communes présentes dans le GeoJSON mais absentes du DVF
codes_dvf = set(carte["code_commune"].unique())
geo_manquantes = geo[~geo["code_commune"].isin(codes_dvf)].copy()
print(f"Communes sans données DVF : {len(geo_manquantes):,}")

# Pour chaque type de bien, interpoler depuis les voisines
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

RAYON_KM = 15
lignes_interpolees = []

# Joindre coordonnées aux communes avec données
carte_geo = carte.merge(geo[["code_commune","lat","lon"]], on="code_commune", how="left")

for type_bien in ["Appartement", "Maison"]:
    source = carte_geo[
        (carte_geo["type_local"] == type_bien) &
        (carte_geo["nb_ventes"] >= 3) &
        (carte_geo["lat"].notna())
    ].copy()

    src_arr = source[["lat","lon","prix_m2_median","loyer_m2_estime","rendement_median"]].values

    print(f"Interpolation {type_bien} pour {len(geo_manquantes):,} communes...")

    for _, row in geo_manquantes.iterrows():
        lat0, lon0 = row["lat"], row["lon"]
        marge = RAYON_KM / 111.0
        masque = (
            (src_arr[:,0] >= lat0 - marge) & (src_arr[:,0] <= lat0 + marge) &
            (src_arr[:,1] >= lon0 - marge) & (src_arr[:,1] <= lon0 + marge)
        )
        candidats = src_arr[masque]
        if len(candidats) == 0:
            continue

        distances = np.array([
            haversine_km(lat0, lon0, c[0], c[1])
            for c in candidats
        ])
        dans_rayon = distances <= RAYON_KM
        if dans_rayon.sum() == 0:
            continue

        d = distances[dans_rayon]
        c = candidats[dans_rayon]
        poids = 1 / (d + 0.1)

        lignes_interpolees.append({
            "code_commune":    row["code_commune"],
            "nom_commune":     row["nom_commune"],
            "code_departement": row["code_commune"][:2],
            "type_local":      type_bien,
            "prix_m2_median":  round(np.average(c[:,2], weights=poids)),
            "nb_ventes":       0,  # marqueur = interpolé
            "loyer_m2":        None,
            "loyer_m2_estime": round(float(np.average(c[:,3], weights=poids)), 2),
            "rendement_median":round(float(np.average(c[:,4], weights=poids)), 2),
        })

if lignes_interpolees:
    df_interp = pd.DataFrame(lignes_interpolees)
    print(f"✅ {len(df_interp):,} communes interpolées")
    carte = pd.concat([carte, df_interp], ignore_index=True)
else:
    print("Aucune interpolation possible")

carte.to_csv("dvf_carte.csv", index=False)
print(f"✅ {len(carte):,} entrées totales dans dvf_carte.csv")
print(f"   Dont interpolées (nb_ventes=0) : {(carte['nb_ventes']==0).sum():,}")