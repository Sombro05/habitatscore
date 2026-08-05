from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os
from scoring import scorer, FRAIS_NOTAIRE_ANCIEN
from tracker import track

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Chargement des données...")
villes = pd.read_csv("dvf_villes.csv")
print(f"✅ {len(villes):,} entrées chargées")

def trouver_ville(nom_ville: str, type_bien: str):
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
    return filtre.loc[filtre["nb_ventes"].idxmax()]

@app.get("/score")
async def calculer_score(
    request: Request,
    ville:     str,
    surface:   float,
    prix:      float,
    type_bien: str = "Appartement",
    usage:     str = "Résidence principale",
):
    row = trouver_ville(ville, type_bien)
    if row is None:
        return {"erreur": f"Ville '{ville}' introuvable"}

    prix_m2_median  = float(row["prix_m2_median"])
    loyer_m2_estime = float(row["loyer_m2_estime"])
    nb_ventes       = int(row["nb_ventes"])
    frais_notaire   = round(prix * FRAIS_NOTAIRE_ANCIEN)

    res = scorer(
        prix_achat=prix, surface=surface,
        type_bien=type_bien, usage=usage,
        prix_m2_median=prix_m2_median, nb_ventes=nb_ventes,
        loyer_m2_estime=loyer_m2_estime,
        frais_notaire=frais_notaire, travaux=0,
    )

    # Tracking
    user_agent = request.headers.get("user-agent", "")
    code_postal = str(row.get("dept_affiche", "")) if row is not None else None
    track(
        type="score_annonce",
        source="extension",
        ville=row["nom_commune"],
        code_postal=code_postal,
        type_bien=type_bien,
        score=res["score_pct"],
        user_agent=user_agent[:200] if user_agent else None,
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

from fastapi import Response

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}