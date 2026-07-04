import pandas as pd
import numpy as np
from math import radians, sin, cos, sqrt, atan2

print("Chargement...")
# Recharger depuis la source originale pour éviter les conflits
loyers = pd.read_csv("loyers_anil_2025.csv", sep=";", encoding="latin-1", low_memory=False)
loyers["loyer_m2"] = loyers["loypredm2"].astype(str).str.replace(",", ".").astype(float)
loyers["code_commune"] = loyers["INSEE_C"].astype(str).str.zfill(5)
loyers["nb_obs"]    = loyers["nbobs_com"]
loyers["type_pred"] = loyers["TYPPRED"]
loyers = loyers[["code_commune","loyer_m2","nb_obs","type_pred"]].copy()

# Coordonnées des communes depuis le GeoJSON (centroïdes)
import json
with open("communes.geojson", "r", encoding="utf-8") as f:
    geojson = json.load(f)

# Extraire centroïdes
centroides = []
for feature in geojson["features"]:
    code = str(feature["properties"].get("code", "")).zfill(5)
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
    centroides.append({"code_commune": code, "lat": lat, "lon": lon})

geo = pd.DataFrame(centroides)
print(f"✅ {len(geo):,} centroïdes extraits")

# Jointure loyers + coordonnées
loyers = loyers.merge(geo, on="code_commune", how="left")
print(f"   Coordonnées manquantes : {loyers['lat'].isna().sum()}")

# Identifier communes peu fiables
loyers["fiable"] = (loyers["nb_obs"] >= 10) | (loyers["type_pred"] == "commune")
peu_fiables = loyers[~loyers["fiable"] & loyers["lat"].notna()].copy()
fiables_all = loyers[loyers["lat"].notna()].copy()

print(f"   Communes peu fiables  : {len(peu_fiables):,}")
print(f"   Communes avec coords  : {len(fiables_all):,}")

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# Pour chaque commune peu fiable, moyenne pondérée des voisines à 10 km
print("Calcul lissage (peut prendre 1-2 min)...")
loyers_arr  = fiables_all[["lat","lon","loyer_m2"]].values
lats_all    = loyers_arr[:,0]
lons_all    = loyers_arr[:,1]
loyers_vals = loyers_arr[:,2]

nouveaux_loyers = {}
RAYON_KM = 10

for _, row in peu_fiables.iterrows():
    lat0, lon0 = row["lat"], row["lon"]

    # Filtre grossier par boîte (1° ≈ 111 km)
    marge = RAYON_KM / 111.0
    masque = (
        (lats_all >= lat0 - marge) & (lats_all <= lat0 + marge) &
        (lons_all >= lon0 - marge) & (lons_all <= lon0 + marge)
    )
    candidats_lat  = lats_all[masque]
    candidats_lon  = lons_all[masque]
    candidats_loyer = loyers_vals[masque]

    if len(candidats_lat) == 0:
        continue

    distances = np.array([
        haversine_km(lat0, lon0, la, lo)
        for la, lo in zip(candidats_lat, candidats_lon)
    ])

    dans_rayon = distances <= RAYON_KM
    if dans_rayon.sum() == 0:
        continue

    d = distances[dans_rayon]
    l = candidats_loyer[dans_rayon]

    # Pondération inverse distance (évite division par 0)
    poids = 1 / (d + 0.1)
    loyer_lisse = np.average(l, weights=poids)
    nouveaux_loyers[row["code_commune"]] = round(loyer_lisse, 2)

print(f"✅ {len(nouveaux_loyers):,} communes lissées")

# Appliquer les loyers lissés
loyers["loyer_m2_final"] = loyers.apply(
    lambda r: nouveaux_loyers.get(r["code_commune"], r["loyer_m2"])
              if not r["fiable"] else r["loyer_m2"],
    axis=1
)

# Vérification Saint-Léger-Magnazeix
slm = loyers[loyers["code_commune"] == "87160"]
print(f"\nSaint-Léger-Magnazeix :")
print(f"  Loyer ANIL original : {slm['loyer_m2'].values[0]:.2f} €/m²")
print(f"  Loyer lissé         : {slm['loyer_m2_final'].values[0]:.2f} €/m²")
print(f"  Fiable              : {slm['fiable'].values[0]}")

loyers.to_csv("loyers_clean.csv", index=False)
print("\n💾 loyers_clean.csv mis à jour avec loyer_m2_final")