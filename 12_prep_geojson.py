import pandas as pd
import json
import os

print("Chargement des données...")
carte = pd.read_csv("dvf_carte.csv", dtype={"code_commune": str})

with open("communes_small.geojson", "r", encoding="utf-8") as f:
    geojson_base = json.load(f)

print(f"✅ {len(geojson_base['features']):,} communes dans le GeoJSON")

combinations = [
    ("Appartement", "prix_m2_median"),
    ("Appartement", "rendement_median"),
    ("Maison",      "prix_m2_median"),
    ("Maison",      "rendement_median"),
]

os.makedirs("geojson_cache", exist_ok=True)

for type_local, col_val in combinations:
    print(f"Génération {type_local} × {col_val}...")

    data = carte[carte["type_local"] == type_local].copy()
    data_ok = data.copy()

    lookup_val  = data_ok.set_index("code_commune")[col_val].to_dict()
    lookup_rdt  = data_ok.set_index("code_commune")["rendement_median"].to_dict()
    lookup_prix = data_ok.set_index("code_commune")["prix_m2_median"].to_dict()
    lookup_loy  = data_ok.set_index("code_commune")["loyer_m2_estime"].to_dict()

    import copy
    geojson = copy.deepcopy(geojson_base)

    for feature in geojson["features"]:
        code = str(feature["properties"].get("code", "")).zfill(5)
        feature["properties"]["val"]       = lookup_val.get(code)
        feature["properties"]["rendement"] = f"{lookup_rdt[code]:.2f} %"      if code in lookup_rdt  else "—"
        feature["properties"]["prix_m2"]   = f"{lookup_prix[code]:,.0f} €/m²" if code in lookup_prix else "—"
        feature["properties"]["loyer_m2"]  = f"{lookup_loy[code]:.2f} €/m²"   if code in lookup_loy  else "—"

    nom = f"geojson_cache/{type_local}_{col_val}.json"
    with open(nom, "w", encoding="utf-8") as f:
        json.dump(geojson, f)

    taille = os.path.getsize(nom) / 1024 / 1024
    print(f"  ✅ {nom} — {taille:.1f} Mo")

print("\n✅ Tous les GeoJSON pré-générés !")