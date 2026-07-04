import pandas as pd
import unicodedata
import re

print("Chargement...")
df     = pd.read_csv("dvf_clean.csv", low_memory=False)
loyers = pd.read_csv("loyers_clean.csv", dtype={"code_commune": str})

def normaliser(texte):
    texte = str(texte).lower().strip()
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = re.sub(r"\bsaint\b", "st", texte)
    texte = re.sub(r"[-_']", " ", texte)
    texte = re.sub(r"\s+", " ", texte)
    return texte

# Normaliser code commune DVF sur 5 caractères
df["code_commune"] = df["code_commune"].astype(str).str.zfill(5)

# Agrégation DVF par ville + département + type de bien
villes = df.groupby(["code_commune", "nom_commune", "code_departement", "type_local"]).agg(
    nb_ventes       = ("valeur_fonciere", "count"),
    prix_m2_median  = ("prix_m2",         "median"),
    prix_m2_moyen   = ("prix_m2",         "mean"),
    surface_moyenne = ("surface_reelle_bati", "mean"),
    prix_moyen      = ("valeur_fonciere", "mean"),
    prix_m2_p10     = ("prix_m2", lambda x: x.quantile(0.10)),
    prix_m2_p25     = ("prix_m2", lambda x: x.quantile(0.25)),
    prix_m2_p75     = ("prix_m2", lambda x: x.quantile(0.75)),
    prix_m2_p90     = ("prix_m2", lambda x: x.quantile(0.90)),
    prix_m2_std     = ("prix_m2", "std"),
).reset_index()

for col in ["prix_m2_median","prix_m2_moyen","surface_moyenne","prix_moyen",
            "prix_m2_p10","prix_m2_p25","prix_m2_p75","prix_m2_p90","prix_m2_std"]:
    villes[col] = villes[col].round(0)

# Jointure avec loyers ANIL
villes = villes.merge(loyers[["code_commune","loyer_m2","nb_obs","type_pred"]],
                      on="code_commune", how="left")

# Coefficient maison vs appartement (+15%)
villes["loyer_m2_estime"] = villes.apply(
    lambda r: round(r["loyer_m2"] * 1.15, 2)
              if r["type_local"] == "Maison" and pd.notna(r["loyer_m2"])
              else round(r["loyer_m2"], 2) if pd.notna(r["loyer_m2"])
              else round(r["prix_m2_median"] * 0.045 / 12, 2),  # fallback si pas de données
    axis=1
).clip(4, 40)

# Stats jointure
jointure_ok = villes["loyer_m2"].notna().sum()
print(f"✅ Jointure loyers : {jointure_ok:,}/{len(villes):,} lignes ({jointure_ok/len(villes)*100:.1f}%)")
print(f"   Fallback (pas de loyer ANIL) : {villes['loyer_m2'].isna().sum():,} lignes")

villes["nom_normalise"] = villes["nom_commune"].apply(normaliser)
villes["dept_affiche"]  = villes["code_departement"].astype(str).str.zfill(2)
villes["label"]         = villes["nom_commune"] + " (" + villes["dept_affiche"] + ")"

villes = villes.sort_values(["nom_commune", "type_local"]).reset_index(drop=True)
villes.to_csv("dvf_villes.csv", index=False)

print(f"✅ {len(villes):,} entrées dans dvf_villes.csv")
print(f"\nLoyer m² médian (Appartement) : {villes[villes['type_local']=='Appartement']['loyer_m2_estime'].median():.2f} €")
print(f"Loyer m² médian (Maison)      : {villes[villes['type_local']=='Maison']['loyer_m2_estime'].median():.2f} €")