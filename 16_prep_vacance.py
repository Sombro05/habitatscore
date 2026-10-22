"""
Vacance locative par commune, à partir du recensement INSEE 2021.

Source : INSEE, « Logement en 2021 – Recensement de la population – Base des principaux
indicateurs », fichier base-cc-logement-2021_csv.zip (Licence Ouverte)
https://www.insee.fr/fr/statistiques/8202349

Vacance locative = logements vacants / (logements vacants + résidences principales louées).
Les locations à la semaine (meublés de tourisme) sont classées par l'INSEE en résidences
secondaires : elles ne comptent ni comme vacantes ni comme louées.

Coefficient de vacance (appliqué au loyer pour le rendement) :
    coef = 1 − max(0, vacance_locative − SEUIL)   (minimum 0)

Usage : python 16_prep_vacance.py base-cc-logement-2021_csv.zip [table_passage_geo2003_geo2023.zip]
Sortie : vacance_communes.csv
"""
import sys
import zipfile
import pandas as pd

SEUIL = 0.30  # vacance locative tolérée sans pénalité

with zipfile.ZipFile(sys.argv[1]) as z:
    with z.open("base-cc-logement-2021.CSV") as f:
        log = pd.read_csv(f, sep=";", dtype={"CODGEO": str},
                          usecols=["CODGEO", "P21_LOG", "P21_LOGVAC", "P21_RP_LOC", "P21_RSECOCC"])

vac = pd.DataFrame({
    "code_commune":           log["CODGEO"].str.zfill(5),
    "logements":              log["P21_LOG"].round(0),
    "logements_vacants":      log["P21_LOGVAC"].round(0),
    "logements_loues":        log["P21_RP_LOC"].round(0),
    "residences_secondaires": log["P21_RSECOCC"].round(0),
})
parc_locatif = log["P21_LOGVAC"] + log["P21_RP_LOC"]
vac["vacance_locative"] = (log["P21_LOGVAC"] / parc_locatif).where(parc_locatif > 0).round(4)
vac["coef_vacance"]     = (1 - (vac["vacance_locative"] - SEUIL).clip(lower=0)).clip(lower=0).round(4)

vac["code_commune_2023"] = vac["code_commune"]

# Anciennes communes fusionnées (encore dessinées sur le fond de carte) : elles reprennent
# les valeurs de leur commune actuelle. Source : INSEE, table de passage géographie
# 2003-2023, https://www.insee.fr/fr/information/7671867 (Licence Ouverte)
if len(sys.argv) > 2:
    with zipfile.ZipFile(sys.argv[2]) as z:
        with z.open("table_passage_geo2003_geo2023.xlsx") as f:
            passage = pd.read_excel(f, header=5, dtype=str)[["CODGEO_INI", "CODGEO_2023"]]
    passage = passage[passage["CODGEO_INI"] != passage["CODGEO_2023"]]
    passage = passage[~passage["CODGEO_INI"].isin(vac["code_commune"])].drop_duplicates("CODGEO_INI")
    anciennes = passage.merge(vac.drop(columns="code_commune"), left_on="CODGEO_2023",
                              right_on="code_commune_2023", how="inner")
    anciennes = anciennes.rename(columns={"CODGEO_INI": "code_commune"}).drop(columns="CODGEO_2023")
    vac = pd.concat([vac, anciennes[vac.columns]], ignore_index=True)
    print(f"✅ {len(anciennes):,} anciennes communes rattachées à leur commune actuelle")

vac.to_csv("vacance_communes.csv", index=False)
print(f"✅ {len(vac):,} communes · vacance locative médiane {vac['vacance_locative'].median():.1%} "
      f"· {vac['vacance_locative'].isna().sum()} sans parc locatif")
print("💾 vacance_communes.csv sauvegardé")
