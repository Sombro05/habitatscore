FRAIS_NOTAIRE_ANCIEN = 0.08

BUDGET_DPE = {
    "A": 0,
    "B": 0,
    "C": 0,
    "D": 0,
    "E": 200,
    "F": 500,
    "G": 800,
}

# Loyers ANIL et loyers d'annonce : charges comprises. Le rendement se calcule hors charges
# récupérables (eau, chauffage collectif, entretien…), payées par le locataire mais reversées.
# Mesure (oct. 2026) : loyer hors charges des locataires de moins d'un an des observatoires locaux
# des loyers / loyer ANIL, médiane sur 214 zones : 0,895 (appartements), 0,908 (maisons)
PART_CHARGES_RECUPERABLES = {"Appartement": 0.105, "Maison": 0.09}


def loyer_hors_charges(loyer, type_bien):
    return loyer * (1 - PART_CHARGES_RECUPERABLES.get(type_bien, 0.10))


def calculer_frais_notaire(prix_achat, taux=FRAIS_NOTAIRE_ANCIEN):
    return round(prix_achat * taux)

def calculer_budget_dpe(dpe, surface):
    if not dpe or dpe not in BUDGET_DPE:
        return 0
    return BUDGET_DPE[dpe] * surface

def _score_prix(prix_ref_m2, prix_m2_median):
    score = 50 + (prix_m2_median - prix_ref_m2) / prix_m2_median * 100
    return max(0, min(100, round(score)))

def _score_rendement(rdt_brut, rdt_neutre):
    if rdt_brut < 1.0:
        return 0
    score = (rdt_brut - rdt_neutre) / rdt_neutre * 100 + 50
    return max(0, min(100, round(score)))

def scorer(
    prix_achat, surface, type_bien, usage,
    prix_m2_median, nb_ventes, loyer_m2_estime,
    loyer_mensuel=None, frais_notaire=None, travaux=0,
    dpe="", budget_dpe_override=None, coef_vacance=1.0, coef_rotation=1.0,
):
    if frais_notaire is None:
        frais_notaire = calculer_frais_notaire(prix_achat)

    travaux = travaux or 0

    # Budget DPE — calculé automatiquement ou override manuel
    if budget_dpe_override is not None:
        budget_dpe = budget_dpe_override
    else:
        budget_dpe = calculer_budget_dpe(dpe, surface)

    cout_total = prix_achat + frais_notaire + travaux + budget_dpe

    prix_m2_achat_travaux = (prix_achat + travaux + budget_dpe) / surface
    prix_m2_tout_compris  = cout_total / surface
    ecart = (prix_m2_achat_travaux - prix_m2_median) / prix_m2_median * 100

    rdt_brut = rdt_net = rdt_neutre = rdt_ajuste = None

    if usage == "Location" and loyer_mensuel:
        # Loyer saisi et loyer de marché : charges comprises → hors charges pour le rendement
        loyer_annuel = loyer_hors_charges(loyer_mensuel, type_bien) * 12
        rdt_brut     = loyer_annuel / (prix_achat + travaux + budget_dpe) * 100
        rdt_net      = loyer_annuel * 0.75 / (prix_achat + travaux + budget_dpe) * 100
        loyer_marche_an = loyer_hors_charges(loyer_m2_estime, type_bien) * surface * 12
        prix_marche_tot = prix_m2_median * surface
        rdt_neutre      = loyer_marche_an / prix_marche_tot * 100
        # Rendement ajusté du risque de vacance locative (16_prep_vacance.py) et de la faible
        # rotation du marché (19_prep_rotation.py), comparé au rendement neutre du marché :
        # pénalise les communes où l'on loue mal ou revend difficilement
        rdt_ajuste      = rdt_brut * coef_vacance * coef_rotation

    if usage == "Achat / revente":
        prix_m2_ref_score = prix_m2_tout_compris
    else:
        prix_m2_ref_score = prix_m2_achat_travaux

    s_prix = _score_prix(prix_m2_ref_score, prix_m2_median)

    if usage == "Location" and rdt_brut is not None:
        s_rendement = _score_rendement(rdt_ajuste, rdt_neutre)
        score_pct   = round(s_rendement * 0.70 + s_prix * 0.30)
        scores = {"rendement": s_rendement, "prix": s_prix}
        poids  = {"rendement": "70%", "prix": "30%"}
    else:
        score_pct = s_prix
        scores = {"prix": s_prix}
        poids  = {"prix": "100%"}

    return {
        "score_pct":             score_pct,
        "scores":                scores,
        "poids":                 poids,
        "prix_m2_achat_travaux": round(prix_m2_achat_travaux),
        "prix_m2_tout_compris":  round(prix_m2_tout_compris),
        "cout_total":            round(cout_total),
        "frais_notaire":         frais_notaire,
        "travaux":               travaux,
        "budget_dpe":            round(budget_dpe),
        "dpe":                   dpe,
        "ecart":                 round(ecart, 1),
        "ecart_tout_compris":    round((prix_m2_tout_compris - prix_m2_median) / prix_m2_median * 100, 1),
        "rdt_brut":              round(rdt_brut, 2) if rdt_brut else None,
        "rdt_net":               round(rdt_net,  2) if rdt_net  else None,
        "rdt_neutre":            round(rdt_neutre, 2) if rdt_neutre else None,
        "rdt_ajuste":            round(rdt_ajuste, 2) if rdt_ajuste is not None else None,
        "coef_vacance":          coef_vacance,
        "coef_rotation":         coef_rotation,
    }
def scorer_loyer(loyer_mensuel, surface, loyer_m2_marche):
    """
    Score pour une annonce de location.
    Ancre : loyer_m2_bien == loyer_m2_marche → 50%
    En dessous du marché = bonne affaire pour le locataire → score > 50
    """
    loyer_m2_bien = loyer_mensuel / surface
    ecart = (loyer_m2_bien - loyer_m2_marche) / loyer_m2_marche * 100
    score = 50 - ecart
    return {
        "score_pct":      max(0, min(100, round(score))),
        "loyer_m2_bien":  round(loyer_m2_bien, 2),
        "loyer_m2_marche": round(loyer_m2_marche, 2),
        "ecart":          round(ecart, 1),
    }