import pandas as pd
import os

FICHIERS = {
    2023: "dvf_2023.csv.gz",
    2024: "dvf_2024.csv.gz",
    2025: "dvf_2025.csv.gz",
}

sortie = "dvf_clean.csv"
if os.path.exists(sortie):
    os.remove(sortie)

total = 0
for annee, fichier in FICHIERS.items():
    print(f"\nChargement {annee}...")
    df = pd.read_csv(fichier, compression="gzip", low_memory=False)
    print(f"  Brut : {len(df):,}")

    df["annee"] = annee
    df = df[df["nature_mutation"] == "Vente"]
    df = df[df["type_local"].isin(["Appartement", "Maison"])]
    df = df.dropna(subset=["valeur_fonciere", "surface_reelle_bati", "latitude", "longitude"])
    df = df[df["surface_reelle_bati"] > 9]
    df = df[df["valeur_fonciere"] > 10_000]
    df = df[df["valeur_fonciere"] < 5_000_000]
    df["prix_m2"] = (df["valeur_fonciere"] / df["surface_reelle_bati"]).round(0)
    df = df[df["prix_m2"] > 500]
    df = df[df["prix_m2"] < 30_000]
    df["code_departement"] = df["code_departement"].astype(str).str.zfill(2)

    # Dédoublonnage : pour un même id_mutation, garder la ligne
    # avec la plus grande surface (lot principal)
    avant = len(df)
    df = df.sort_values("surface_reelle_bati", ascending=False)
    df = df.drop_duplicates(subset=["id_mutation", "type_local"])
    print(f"  Doublons supprimés : {avant - len(df):,}")

    # Filtre aberrants : exclure prix > 5x médiane nationale par type
    # Appartement : médiane ~3500 → seuil 17500
    # Maison      : médiane ~2500 → seuil 12500
    seuils = {"Appartement": 17_500, "Maison": 12_500}
    avant2 = len(df)
    df = df[df.apply(lambda r: r["prix_m2"] <= seuils.get(r["type_local"], 15_000), axis=1)]
    print(f"  Aberrants supprimés : {avant2 - len(df):,}")

    colonnes = [
        "annee", "date_mutation", "nature_mutation", "type_local",
        "id_mutation", "valeur_fonciere", "surface_reelle_bati",
        "nombre_pieces_principales", "code_postal", "code_commune",
        "nom_commune", "code_departement", "latitude", "longitude", "prix_m2"
    ]
    df = df[[c for c in colonnes if c in df.columns]]

    print(f"  Propre : {len(df):,}")
    total += len(df)

    header = not os.path.exists(sortie)
    df.to_csv(sortie, mode="a", header=header, index=False)
    print(f"  ✅ Écrit dans {sortie}")
    del df

print(f"\n💾 Total final : {total:,} ventes propres dans dvf_clean.csv")