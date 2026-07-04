from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from scoring import scorer, FRAIS_NOTAIRE_ANCIEN

app = FastAPI()

# Autoriser les requêtes depuis l'extension Chrome
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Charger les données au démarrage
print("Chargement des données...")
villes = pd.read_csv("dvf_villes.csv")
print(f"✅ {len(villes):,} entrées chargées")

def trouver_ville(nom_ville: str, type_bien: str):
    """Cherche la ville dans dvf_villes.csv avec normalisation."""
    import unicodedata, re
    def norm(t):
        t = str(t).lower().strip()
        t = unicodedata.normalize("NFD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        t = re.sub(r"\bsaint\b", "st", t)
        t = re.sub(r"[-_'\s]+", " ", t)
        return t.strip()

    nom_norm = norm(nom_ville)
    filtre = villes[
        (villes["nom_normalise"].str.contains(nom_norm, na=False)) &
        (villes["type_local"] == type_bien)
    ]
    if filtre.empty:
        return None
    # Prendre la ville avec le plus de ventes
    return filtre.loc[filtre["nb_ventes"].idxmax()]

@app.get("/score")
def calculer_score(
    ville:      str,
    surface:    float,
    prix:       float,
    type_bien:  str = "Appartement",
    usage:      str = "Résidence principale",
):
    row = trouver_ville(ville, type_bien)
    if row is None:
        return {"erreur": f"Ville '{ville}' introuvable"}

    prix_m2_median  = float(row["prix_m2_median"])
    loyer_m2_estime = float(row["loyer_m2_estime"])
    nb_ventes       = int(row["nb_ventes"])
    frais_notaire   = round(prix * FRAIS_NOTAIRE_ANCIEN)

    res = scorer(
        prix_achat=prix,
        surface=surface,
        type_bien=type_bien,
        usage=usage,
        prix_m2_median=prix_m2_median,
        nb_ventes=nb_ventes,
        loyer_m2_estime=loyer_m2_estime,
        frais_notaire=frais_notaire,
        travaux=0,
    )

    return {
        "score":          res["score_pct"],
        "ecart":          res["ecart"],
        "prix_m2_bien":   res["prix_m2_achat_travaux"],
        "prix_m2_marche": round(prix_m2_median),
        "rendement":      res["rdt_brut"],
        "rdt_neutre":     res["rdt_neutre"],
        "ville_trouvee":  row["nom_commune"],
        "dept":           row["dept_affiche"],
    }

@app.get("/health")
def health():
    return {"status": "ok"}