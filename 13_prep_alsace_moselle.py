"""
Loyers de marché pour l'Alsace-Moselle (départements 57, 67, 68).

Ces départements relèvent du Livre foncier et sont absents de DVF : aucun prix
de vente n'est disponible. On ne prépare donc que les loyers (source ANIL,
Licence Ouverte), utilisés par l'API pour le score des annonces de location.
"""
import pandas as pd
import unicodedata
import re

DEPTS_ALSACE_MOSELLE = ["57", "67", "68"]

# Même normalisation que 03_prep_villes.py (nom_normalise)
def normaliser(texte):
    texte = str(texte).lower().strip()
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = re.sub(r"\bsaint\b", "st", texte)
    texte = re.sub(r"[-_']", " ", texte)
    texte = re.sub(r"\s+", " ", texte)
    return texte

print("Chargement loyers ANIL 2025...")
anil = pd.read_csv("loyers_anil_2025.csv", sep=";", encoding="latin-1", dtype=str)
anil = anil[anil["DEP"].isin(DEPTS_ALSACE_MOSELLE)].copy()

anil["code_commune"]     = anil["INSEE_C"].str.zfill(5)
anil["loyer_m2"]         = anil["loypredm2"].str.replace(",", ".").astype(float)
anil = anil.rename(columns={"LIBGEO": "nom_commune", "DEP": "code_departement"})
anil = anil[["code_commune", "nom_commune", "code_departement", "loyer_m2"]]

# Loyers des maisons : fichier ANIL dédié (même règle que 03_prep_villes.py)
maisons = pd.read_csv("loyers_anil_maisons_2025.csv", sep=";", encoding="latin-1", dtype=str)
maisons["code_commune"] = maisons["INSEE_C"].str.zfill(5)
maisons["loyer_m2_maison"] = maisons["loypredm2"].str.replace(",", ".").astype(float)
anil = anil.merge(maisons[["code_commune", "loyer_m2_maison"]], on="code_commune", how="left")

# Une ligne par type de bien
lignes = []
for type_local, colonne in [("Appartement", "loyer_m2"), ("Maison", "loyer_m2_maison")]:
    t = anil.copy()
    t["type_local"]      = type_local
    t["loyer_m2_estime"] = t[colonne].round(2).clip(4, 40)
    lignes.append(t.drop(columns="loyer_m2_maison"))
loyers = pd.concat(lignes, ignore_index=True)

loyers["nom_normalise"] = loyers["nom_commune"].apply(normaliser)
loyers["dept_affiche"]  = loyers["code_departement"].str.zfill(2)
loyers["label"]         = loyers["nom_commune"] + " (" + loyers["dept_affiche"] + ")"

loyers = loyers.dropna(subset=["loyer_m2_estime"])
loyers = loyers.sort_values(["nom_commune", "type_local"]).reset_index(drop=True)
loyers.to_csv("loyers_alsace_moselle.csv", index=False)

print(f"✅ {loyers['code_commune'].nunique():,} communes, {len(loyers):,} lignes")
print(loyers.groupby(["code_departement", "type_local"])["loyer_m2_estime"].median())
print("💾 loyers_alsace_moselle.csv sauvegardé")
