FRAIS_NOTAIRE_ANCIEN = 0.08

def calculer_frais_notaire(prix_achat, taux=FRAIS_NOTAIRE_ANCIEN):
    return round(prix_achat * taux)

def _score_prix(prix_ref_m2, prix_m2_median):
    """
    Ancre : prix_ref_m2 == prix_m2_median → 50%
    (médiane - prix_ref) / médiane * 100 + 50, clampé [0, 100]
    """
    score = 50 + (prix_m2_median - prix_ref_m2) / prix_m2_median * 100
    return max(0, min(100, round(score)))

def _score_rendement(rdt_brut, rdt_neutre):
    """
    Ancre : rdt_brut == rdt_neutre → 50%
    (rdt - rdt_neutre) / rdt_neutre * 100 + 50, clampé [0, 100]
    Sous 1% → 0
    """
    if rdt_brut < 1.0:
        return 0
    score = (rdt_brut - rdt_neutre) / rdt_neutre * 100 + 50
    return max(0, min(100, round(score)))

def scorer(
    prix_achat, surface, type_bien, usage,
    prix_m2_median, nb_ventes, loyer_m2_estime,
    loyer_mensuel=None, frais_notaire=None, travaux=0,
):
    if frais_notaire is None:
        frais_notaire = calculer_frais_notaire(prix_achat)

    travaux    = travaux or 0
    cout_total = prix_achat + frais_notaire + travaux

    # Prix au m² achat + travaux (sans notaire) — affiché
    prix_m2_achat_travaux = (prix_achat + travaux) / surface

    # Prix au m² tout compris — avec notaire
    prix_m2_tout_compris = cout_total / surface

    # Écart pour affichage — sur prix achat + travaux (sans notaire)
    ecart = (prix_m2_achat_travaux - prix_m2_median) / prix_m2_median * 100

    # Écart pour affichage — sur prix achat + travaux (sans notaire) + notaire
    ecart_tout_compris = (prix_m2_tout_compris - prix_m2_median) / prix_m2_median * 100

    rdt_brut = rdt_net = rdt_neutre = None

    if usage == "Location" and loyer_mensuel:
        loyer_annuel = loyer_mensuel * 12
        rdt_brut     = loyer_annuel / (prix_achat + travaux) * 100
        rdt_net      = loyer_annuel * 0.75 / (prix_achat + travaux) * 100
        loyer_marche_an = loyer_m2_estime * surface * 12
        prix_marche_tot = prix_m2_median * surface
        rdt_neutre      = loyer_marche_an / prix_marche_tot * 100

    # ── Base de comparaison selon l'usage ────
    if usage == "Achat / revente":
        prix_m2_ref_score = prix_m2_tout_compris
    else:
        prix_m2_ref_score = prix_m2_achat_travaux

    # ── SCORE ────────────────────────────────
    s_prix = _score_prix(prix_m2_ref_score, prix_m2_median)

    if usage == "Location" and rdt_brut is not None:
        s_rendement = _score_rendement(rdt_brut, rdt_neutre)
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
        "ecart":                 round(ecart, 1),
        "ecart_tout_compris":    round(ecart_tout_compris, 1),
        "rdt_brut":              round(rdt_brut, 2) if rdt_brut else None,
        "rdt_net":               round(rdt_net,  2) if rdt_net  else None,
        "rdt_neutre":            round(rdt_neutre, 2) if rdt_neutre else None,
    }