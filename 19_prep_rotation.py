"""
Taux de rotation par commune : part des logements vendus chaque année (marché actif ou figé).

Taux de rotation = ventes DVF (maisons + appartements, 3 ans) / 3 / logements INSEE 2021
Coefficient de rotation (appliqué au rendement, comme le coefficient de vacance) :
    coef = max(PLANCHER, 1 − PENTE × max(0, (SEUIL − rotation) / SEUIL))
Sous 1,5 % de logements vendus par an, chaque pourcent d'écart au seuil retire 1 % au
rendement, jusqu'à −75 % au maximum (plancher 0,25, atteint vers 0,375 %/an) :
- la faible rotation pèse sur la revente, pas sur les loyers encaissés (le risque locatif
  est déjà compté par le coefficient de vacance) : le rendement ne tombe pas à 0 ;
- sous le plancher, les communes ont surtout 0 à 2 ventes en 3 ans : la mesure n'y est
  plus fiable (une vente de plus ou de moins = ±50 à 100 %), on cesse de les différencier.

Entrées : dvf_clean.parquet, vacance_communes.csv (16_prep_vacance.py)
Sortie : rotation_communes.csv (anciennes communes fusionnées incluses)
"""
import pandas as pd

SEUIL = 0.015            # 1,5 % des logements vendus par an
PENTE = 1                # % de rendement retiré par % d'écart relatif au seuil
PLANCHER = 0.25          # coefficient minimal (marché quasi inexistant)
NB_ANNEES = 3            # ventes DVF 2023-2025

ventes = (pd.read_parquet("dvf_clean.parquet", columns=["code_commune"])
            .assign(code_commune=lambda d: d["code_commune"].astype(str).str.zfill(5))
            .groupby("code_commune").size().rename("ventes_3ans"))

vac = pd.read_csv("vacance_communes.csv", dtype={"code_commune": str, "code_commune_2023": str})
actuelles = vac[vac["code_commune"] == vac["code_commune_2023"]][["code_commune", "logements"]]
actuelles = actuelles.merge(ventes, left_on="code_commune", right_index=True, how="left")
actuelles["ventes_3ans"] = actuelles["ventes_3ans"].fillna(0).astype(int)
actuelles["rotation"] = (actuelles["ventes_3ans"] / NB_ANNEES / actuelles["logements"]).where(
    actuelles["logements"] > 0).round(4)
actuelles["coef_rotation"] = (1 - PENTE * ((SEUIL - actuelles["rotation"]) / SEUIL).clip(lower=0)).clip(lower=PLANCHER).round(4)

# Toutes les communes (anciennes comprises) reprennent les valeurs de leur commune actuelle
rot = vac[["code_commune", "code_commune_2023"]].merge(
    actuelles.rename(columns={"code_commune": "code_commune_2023"}).drop(columns="logements"),
    on="code_commune_2023", how="left")
rot.drop(columns="code_commune_2023").to_csv("rotation_communes.csv", index=False)

print(f"✅ {len(rot):,} communes · rotation médiane {actuelles['rotation'].median():.2%}/an · "
      f"{(actuelles['rotation'] < SEUIL).mean():.0%} sous le seuil de {SEUIL:.1%}")
print("💾 rotation_communes.csv sauvegardé")
