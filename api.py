from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, Literal
import pandas as pd
import os
import re
import unicodedata
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
DTYPES_DEPT = {"code_departement": str, "dept_affiche": str}
villes = pd.read_csv("dvf_villes.csv", dtype=DTYPES_DEPT)
print(f"✅ {len(villes):,} entrées chargées")

# Alsace-Moselle : absente de DVF (Livre foncier), seuls les loyers ANIL sont disponibles
# (fichier généré par 13_prep_alsace_moselle.py). Optionnel : l'API démarre sans.
FICHIER_AM = "loyers_alsace_moselle.csv"
if os.path.exists(FICHIER_AM):
    loyers_am = pd.read_csv(FICHIER_AM, dtype=DTYPES_DEPT)
    print(f"✅ {len(loyers_am):,} entrées de loyers Alsace-Moselle chargées")
else:
    loyers_am = pd.DataFrame(columns=villes.columns)
    print(f"⚠️ {FICHIER_AM} absent : pas de données Alsace-Moselle")

# Contraintes sur les paramètres d'entrée (FastAPI renvoie 422 si non respectées)
TypeBien = Literal["Appartement", "Maison"]
Usage    = Literal["Résidence principale", "Location", "Achat / revente"]
Ville    = Annotated[str,   Query(min_length=1, max_length=100)]
Surface  = Annotated[float, Query(gt=0, le=10_000)]
Montant  = Annotated[float, Query(gt=0, le=100_000_000)]
Dpe      = Annotated[str,   Query(pattern=r"^[A-G]?$")]
Uid      = Annotated[str,   Query(max_length=64, pattern=r"^[A-Za-z0-9-]*$")]
CodePostal = Annotated[str, Query(pattern=r"^(\d{5})?$")]

def norm(t):
    # Même normalisation que nom_normalise (03_prep_villes.py)
    t = str(t).lower().strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"\bsaint\b", "st", t)
    t = re.sub(r"[-_'\s]+", " ", t)
    return t.strip()

def depts_depuis_cp(code_postal: str):
    # Département déduit du code postal (Corse : 20xxx → 2A ou 2B, outre-mer : 3 chiffres)
    if not code_postal:
        return None
    if code_postal.startswith("20"):
        return ["2A", "2B"]
    if code_postal.startswith("97"):
        return [code_postal[:3]]
    return [code_postal[:2]]

def trouver_ville(nom_ville: str, type_bien: str, table=villes, depts=None):
    nom_norm = norm(nom_ville)
    if not nom_norm:
        return None
    du_type = table[table["type_local"] == type_bien]
    if depts:
        du_type = du_type[du_type["dept_affiche"].isin(depts)]
    noms    = du_type["nom_normalise"]
    # 1. Nom exact ; 2. sinon nom suivi d'un complément (ex. "paris" → "paris 15e arrondissement")
    filtre = du_type[noms == nom_norm]
    if filtre.empty:
        filtre = du_type[noms.str.startswith(nom_norm + " ", na=False)]
    if filtre.empty:
        return None
    if "nb_ventes" not in filtre.columns:
        return filtre.iloc[0]
    return filtre.loc[filtre["nb_ventes"].idxmax()]

def localiser(nom_ville: str, type_bien: str, code_postal: str = ""):
    """Renvoie (ligne, source) avec source "dvf" ou "alsace_moselle", ou (None, None).
    Le département du code postal départage les homonymes ; si rien n'y correspond
    (code postal à cheval sur deux départements), on cherche sans ce filtre."""
    depts = depts_depuis_cp(code_postal)
    for filtre_dept in ([depts, None] if depts else [None]):
        for source, table in (("dvf", villes), ("alsace_moselle", loyers_am)):
            row = trouver_ville(nom_ville, type_bien, table, filtre_dept)
            if row is not None:
                return row, source
    return None, None

@app.get("/score")
async def calculer_score(
    request: Request,
    ville:     Ville,
    surface:   Surface,
    prix:      Montant,
    type_bien: TypeBien = "Appartement",
    usage:     Usage    = "Résidence principale",
    dpe:       Dpe      = "",
    uid:       Uid      = "",
    code_postal: CodePostal = "",
):
    row, source = localiser(ville, type_bien, code_postal)
    if source == "alsace_moselle":
        return {
            "erreur": "Prix de vente non disponibles en Alsace-Moselle",
            "code":   "prix_indisponible",
            "message": "Les ventes y relèvent du Livre foncier et ne sont pas publiées dans DVF."
        }
    if row is None:
        return {
            "erreur": f"Ville '{ville}' introuvable",
            "message": "Données non disponibles pour cette ville."
        }

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
        type_bien=type_bien,
        score=res["score_pct"],
        session_id=uid or None,
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
@app.get("/score_loyer")
async def calculer_score_loyer(
    request: Request,
    ville:     Ville,
    surface:   Surface,
    loyer:     Montant,
    type_bien: TypeBien = "Appartement",
    code_postal: CodePostal = "",
):
    from scoring import scorer_loyer
    row, _ = localiser(ville, type_bien, code_postal)
    if row is None:
        return {"erreur": f"Ville '{ville}' introuvable"}

    loyer_m2_marche = float(row["loyer_m2_estime"])
    res = scorer_loyer(loyer, surface, loyer_m2_marche)

    user_agent = request.headers.get("user-agent", "")
    track(
        type="score_loyer",
        source="extension",
        ville=row["nom_commune"],
        type_bien=type_bien,
        score=res["score_pct"],
        user_agent=user_agent[:200] if user_agent else None,
    )

    return {
        "score":           res["score_pct"],
        "ecart":           res["ecart"],
        "loyer_m2_bien":   res["loyer_m2_bien"],
        "loyer_m2_marche": res["loyer_m2_marche"],
        "ville_trouvee":   row["nom_commune"],
        "dept":            row["dept_affiche"],
        "type": "loyer",
    }
from fastapi import Response

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}