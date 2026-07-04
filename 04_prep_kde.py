import pandas as pd
import json

print("Chargement...")
df = pd.read_csv("dvf_clean.csv", low_memory=False)

print("Calcul KDE par ville × département × type...")
result = {}

for (commune, dept, type_local), grp in df.groupby(["nom_commune", "code_departement", "type_local"]):
    prix = grp["prix_m2"].dropna().tolist()
    if len(prix) < 10:
        continue
    key = f"{commune}|||{dept}|||{type_local}"
    result[key] = prix

with open("dvf_kde.json", "w") as f:
    json.dump(result, f)

print(f"✅ {len(result):,} entrées sauvegardées dans dvf_kde.json")