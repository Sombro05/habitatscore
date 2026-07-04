import pandas as pd
import json
import gzip
import os

# ── 1. dvf_clean.csv → dvf_clean.parquet ────────────────────────────────
print("Réduction dvf_clean.csv...")
df = pd.read_csv("dvf_clean.csv", low_memory=False)
print(f"  Colonnes actuelles : {list(df.columns)}")

# Garder uniquement les colonnes utiles à l'app
colonnes_utiles = [
    "annee", "type_local", "valeur_fonciere", "surface_reelle_bati",
    "code_commune", "nom_commune", "code_departement", "prix_m2",
    "latitude", "longitude"
]
df = df[[c for c in colonnes_utiles if c in df.columns]]
df.to_parquet("dvf_clean.parquet", index=False, compression="snappy")

taille_avant = os.path.getsize("dvf_clean.csv") / 1024 / 1024
taille_apres = os.path.getsize("dvf_clean.parquet") / 1024 / 1024
print(f"  {taille_avant:.0f} Mo → {taille_apres:.0f} Mo")

# ── 2. dvf_kde.json → dvf_kde.json.gz ───────────────────────────────────
print("\nRéduction dvf_kde.json...")
with open("dvf_kde.json", "r") as f:
    kde = json.load(f)

# Réduire à 300 points max par distribution
kde_reduit = {}
for k, v in kde.items():
    if len(v) > 300:
        pas = len(v) // 300
        kde_reduit[k] = v[::pas][:300]
    else:
        kde_reduit[k] = v

with gzip.open("dvf_kde.json.gz", "wt", encoding="utf-8") as f:
    json.dump(kde_reduit, f)

taille_avant = os.path.getsize("dvf_kde.json") / 1024 / 1024
taille_apres = os.path.getsize("dvf_kde.json.gz") / 1024 / 1024
print(f"  {taille_avant:.0f} Mo → {taille_apres:.0f} Mo")

# ── 3. communes.geojson → communes_small.geojson ────────────────────────
print("\nRéduction communes.geojson...")
with open("communes.geojson", "r", encoding="utf-8") as f:
    geo = json.load(f)

def simplifier_polygone(coords, facteur=3):
    """Garder 1 point sur facteur"""
    return coords[::facteur]

for feature in geo["features"]:
    geom = feature["geometry"]
    if geom is None:
        continue
    if geom["type"] == "Polygon":
        geom["coordinates"] = [simplifier_polygone(ring) for ring in geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        geom["coordinates"] = [
            [simplifier_polygone(ring) for ring in poly]
            for poly in geom["coordinates"]
        ]

with open("communes_small.geojson", "w", encoding="utf-8") as f:
    json.dump(geo, f)

taille_avant = os.path.getsize("communes.geojson") / 1024 / 1024
taille_apres = os.path.getsize("communes_small.geojson") / 1024 / 1024
print(f"  {taille_avant:.0f} Mo → {taille_apres:.0f} Mo")

print("\n✅ Réduction terminée")
print(f"\nTaille totale estimée GitHub :")
total = 0
for f in ["dvf_clean.parquet", "dvf_kde.json.gz", "communes_small.geojson",
          "dvf_villes.csv", "dvf_carte.csv", "loyers_clean.csv"]:
    if os.path.exists(f):
        t = os.path.getsize(f) / 1024 / 1024
        total += t
        print(f"  {f} : {t:.1f} Mo")
print(f"  TOTAL : {total:.0f} Mo")