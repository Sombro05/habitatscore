import pandas as pd

print("Chargement loyers ANIL 2025...")
loyers = pd.read_csv("loyers_anil_2025.csv", sep=";", encoding="latin-1", low_memory=False)

# Convertir loypredm2 (virgule → point)
loyers["loypredm2"] = loyers["loypredm2"].astype(str).str.replace(",", ".").astype(float)
loyers["lwr.IPm2"]  = loyers["lwr.IPm2"].astype(str).str.replace(",", ".").astype(float)
loyers["upr.IPm2"]  = loyers["upr.IPm2"].astype(str).str.replace(",", ".").astype(float)

# Normaliser le code INSEE sur 5 caractères
loyers["INSEE_C"] = loyers["INSEE_C"].astype(str).str.zfill(5)

# Garder uniquement les colonnes utiles
loyers = loyers[["INSEE_C", "LIBGEO", "DEP", "loypredm2", "nbobs_com", "TYPPRED"]].copy()
loyers.columns = ["code_commune", "commune", "dept", "loyer_m2", "nb_obs", "type_pred"]

print(f"✅ {len(loyers):,} communes chargées")
print(f"Loyer m² moyen national : {loyers['loyer_m2'].mean():.2f} €")
print(f"Loyer m² médian national : {loyers['loyer_m2'].median():.2f} €")
print(f"\nRépartition TYPPRED :")
print(loyers["type_pred"].value_counts())
print(f"\nCommunes avec obs directes (nbobs_com > 0) : {(loyers['nb_obs'] > 0).sum():,}")

# Sauvegarder
loyers.to_csv("loyers_clean.csv", index=False)
print("\n💾 loyers_clean.csv sauvegardé")