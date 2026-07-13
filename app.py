import streamlit as st
import folium
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from scoring import scorer, calculer_frais_notaire, calculer_budget_dpe, FRAIS_NOTAIRE_ANCIEN, BUDGET_DPE
from tracker import track, feedback
import uuid

# Session ID unique par visiteur
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
from streamlit_folium import st_folium
from data import charger_donnees, charger_kde, get_labels_uniques, get_row, get_prix_kde
from scoring import scorer, calculer_frais_notaire, calculer_budget_dpe, FRAIS_NOTAIRE_ANCIEN
from scipy.stats import gaussian_kde as scipy_kde

st.set_page_config(page_title="ImmoScore", page_icon="🏠", layout="wide")

df, villes = charger_donnees()
kde_data   = charger_kde()
# Récupérer les paramètres URL transmis par l'extension Chrome
qp = st.query_params
qp_ville      = qp.get("ville", "")
qp_prix       = int(qp.get("prix", 0))
qp_surface    = int(qp.get("surface", 0))
qp_type_bien  = qp.get("type_bien", "")
qp_dpe        = qp.get("dpe", "")

st.sidebar.title("🏠 ImmoScore")
page = st.sidebar.radio("Navigation", ["Analyser un bien", "Explorer le marché"])

# ════════════════════════════════════════════
# PAGE 1 — ANALYSER UN BIEN
# ════════════════════════════════════════════
if page == "Analyser un bien":
    st.title("Analyser un bien")

    labels = get_labels_uniques(villes)
    choix  = st.selectbox(
        "Choisir une localisation",
        options=[""] + labels, index=0,
        format_func=lambda x: "Tapez pour rechercher une ville..." if x == "" else x,
    )
    if not choix:
        st.stop()

    types_dispo = villes[villes["label"] == choix]["type_local"].unique().tolist()
    type_index  = 0
    if qp_type_bien in types_dispo:
        type_index = types_dispo.index(qp_type_bien)
    type_bien = st.radio("Type de bien", types_dispo, index=type_index, horizontal=True)

    usage = st.radio("Usage du bien",
                     ["Location", "Résidence principale", "Achat / revente"],
                     horizontal=True)

    row = get_row(villes, choix, type_bien)
    prix_m2_median  = float(row["prix_m2_median"])
    loyer_m2_estime = float(row["loyer_m2_estime"])
    nb_ventes       = int(row["nb_ventes"])
    surface_moyenne = float(row["surface_moyenne"])

    st.divider()

    surface = st.number_input("Surface (m²)",
                              value=qp_surface if qp_surface > 0 else int(surface_moyenne),
                              min_value=10, max_value=500)

    prix_achat = st.number_input(
        f"Prix d'achat (€) — médiane marché : {prix_m2_median:,.0f} €/m²",
        value=qp_prix if qp_prix > 0 else int(prix_m2_median * surface),
        step=1000
    )

    frais_notaire = st.number_input(
        f"Frais de notaire (€) — défaut {FRAIS_NOTAIRE_ANCIEN*100:.0f}%",
        value=calculer_frais_notaire(prix_achat),
        step=100
    )

    travaux = st.number_input("Travaux (€)", value=0, step=500, min_value=0)

    # DPE
    dpe_options = ["", "A", "B", "C", "D", "E", "F", "G"]
    dpe_defaut  = qp_dpe if qp_dpe in dpe_options else ""
    dpe = st.selectbox(
        "DPE (optionnel)",
        options=dpe_options,
        index=dpe_options.index(dpe_defaut),
        format_func=lambda x: "Non renseigné" if x == "" else x,
    )

    # Budget DPE
    budget_dpe_auto = int(calculer_budget_dpe(dpe, surface)) if dpe else 0
    budget_dpe = st.number_input(
        f"Budget rénovation énergétique (€) — estimé : {budget_dpe_auto:,} €",
        value=budget_dpe_auto,
        step=500,
        min_value=0,
    )

    loyer = None
    if usage == "Location":
        loyer = st.number_input(
            f"Loyer mensuel estimé (€) — base marché : {loyer_m2_estime:.1f} €/m²",
            value=int(loyer_m2_estime * surface), step=10
        )

    cout_total_affiche = prix_achat + frais_notaire + travaux + budget_dpe
    st.caption(
        f"**{type_bien}s** · {choix} · "
        f"médiane {prix_m2_median:,.0f} €/m² · "
        f"surface moy. {surface_moyenne:.0f} m² · "
        f"{nb_ventes:,} ventes 2023–2025 · "
        f"Coût total : **{cout_total_affiche:,} €**"
    )

    # ── CALCUL ───────────────────────────────
    res = scorer(
        prix_achat=prix_achat, surface=surface,
        type_bien=type_bien, usage=usage,
        prix_m2_median=prix_m2_median,
        loyer_m2_estime=loyer_m2_estime,
        nb_ventes=nb_ventes,
        loyer_mensuel=loyer, frais_notaire=frais_notaire,
        travaux=travaux,
        dpe=dpe,
        budget_dpe_override=budget_dpe if budget_dpe != budget_dpe_auto else None,
    )

    track(
        type="analyse_bien",
        source="app",
        ville=choix,
        type_bien=type_bien,
        score=res["score_pct"],
        session_id=st.session_state.session_id,
    )

    st.divider()

    pct    = res["score_pct"]
    emoji  = "🟢" if pct >= 65 else "🟡" if pct >= 40 else "🔴"
    st.subheader(f"{emoji} Score : {pct}/100")
    st.progress(pct / 100)

    # ── MÉTRIQUES ────────────────────────────
    if usage == "Location":
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Prix au m²",               f"{res['prix_m2_achat_travaux']:,} €", f"{res['ecart']:+.1f}% vs marché")
        c2.metric("Coût au m² (tout compris)", f"{res['prix_m2_tout_compris']:,} €",  f"{res['ecart_tout_compris']:+.1f}% vs marché")
        c3.metric("Coût total",               f"{res['cout_total']:,} €")
        c4.metric("Rendement brut",           f"{res['rdt_brut']} %",)
        delta_rdt = round(res['rdt_brut'] - res['rdt_neutre'], 2)
        c4.metric("Rendement brut", f"{res['rdt_brut']} %",
                  f"{delta_rdt:+.2f}% vs neutre ville ({res['rdt_neutre']} %)")
        delta_loyer = loyer - int(loyer_m2_estime * surface)
        c5.metric("Loyer mensuel", f"{loyer:,} €", f"{delta_loyer:+,} € vs marché")
        c6.metric("DPE", dpe if dpe else "—")

    elif usage == "Résidence principale":
        c1, c2, c3,c4 = st.columns(4)
        c1.metric("Prix au m²",               f"{res['prix_m2_achat_travaux']:,} €", f"{res['ecart']:+.1f}% vs marché")
        c2.metric("Coût au m² (tout compris)", f"{res['prix_m2_tout_compris']:,} €",  f"{res['ecart_tout_compris']:+.1f}% vs marché")
        c3.metric("Coût total",               f"{res['cout_total']:,} €")
        c4.metric("DPE", dpe if dpe else "—")

    else:  # Achat / revente
        c1, c2, c3, c4,c5 = st.columns(5)
        c1.metric("Prix au m²",               f"{res['prix_m2_achat_travaux']:,} €", f"{res['ecart']:+.1f}% vs marché")
        c2.metric("Coût au m² (tout compris)", f"{res['prix_m2_tout_compris']:,} €",  f"{res['ecart_tout_compris']:+.1f}% vs marché")
        c3.metric("Coût total",               f"{res['cout_total']:,} €")
        c4.metric("Frais notaire",            f"{res['frais_notaire']:,} €")
        c5.metric("DPE", dpe if dpe else "—")

    # Budget DPE
    if res["budget_dpe"] > 0:
        st.info(f"🏠 Budget rénovation DPE {dpe} estimé : {res['budget_dpe']:,} € ({BUDGET_DPE.get(dpe, 0):,} €/m²)")

    # ── DÉTAIL DU SCORE ───────────────────────
    st.divider()

    scores = res["scores"]
    noms   = {"rendement": "Rendement locatif", "prix": "Prix vs marché"}
    poids  = res["poids"]

    col_bars, col_gauss = st.columns([1, 2])

    with col_bars:
        for k, label in noms.items():
            if k in scores:
                v = scores[k]
                st.metric(label, f"{v}/100", f"poids {poids[k]}")
                st.progress(v / 100)

    with col_gauss:
        commune  = row["nom_commune"]
        dept     = str(row["code_departement"])
        prix_raw = get_prix_kde(kde_data, commune, dept, type_bien)

        if len(prix_raw) >= 10:
            prix_arr = np.array(prix_raw)
            kde_fn   = scipy_kde(prix_arr, bw_method="scott")

            x_min = max(0, np.percentile(prix_arr, 1))
            x_max = np.percentile(prix_arr, 99)
            x     = np.linspace(x_min, x_max, 500)
            y     = kde_fn(x)
            y     = y / y.max()

            fig, ax = plt.subplots(figsize=(5, 2.8))
            fig.patch.set_alpha(0)
            ax.set_facecolor("none")
            ax.plot(x, y, color="#4C8BF5", linewidth=2)
            ax.fill_between(x, y, alpha=0.15, color="#4C8BF5")

            prix_trace = res["prix_m2_achat_travaux"]

            ax.axvline(prix_trace,     color="#E74C3C", linewidth=2,
                       label=f"Votre bien : {prix_trace:,.0f} €/m²")
            ax.axvline(prix_m2_median, color="#27AE60", linewidth=1.5,
                       linestyle="--", label=f"Médiane : {prix_m2_median:,.0f} €/m²")

            ax.set_xlabel("Prix au m²  (€)", fontsize=9, color="gray")
            ax.set_yticks([])
            ax.tick_params(colors="gray", labelsize=8)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.legend(fontsize=8, framealpha=0)
            st.pyplot(fig, use_container_width=True)
        else:
            st.caption("Pas assez de données pour afficher la distribution.")
# ════════════════════════════════════════════
# PAGE 2 — EXPLORER LE MARCHÉ
# ════════════════════════════════════════════
else:
    st.title("Explorer le marché")
    st.caption("Carte des rendements estimés par commune (2023–2025)")

    import json
    import branca.colormap as cm
    import copy

    @st.cache_data
    def charger_carte():
        import pandas as pd
        carte = pd.read_csv("dvf_carte.csv", dtype={"code_commune": str})
        with open("communes_small.geojson", "r", encoding="utf-8") as f:
            geojson = json.load(f)
        return carte, geojson

    @st.cache_data
    def enrichir_geojson(type_carte, col_val):
        import pandas as pd, copy
        carte, geojson = charger_carte()
        geojson = copy.deepcopy(geojson)

        data_ok     = carte[carte["type_local"] == type_carte].copy()
        lookup_val  = data_ok.set_index("code_commune")[col_val].to_dict()
        lookup_rdt  = data_ok.set_index("code_commune")["rendement_median"].to_dict()
        lookup_prix = data_ok.set_index("code_commune")["prix_m2_median"].to_dict()
        lookup_loy  = data_ok.set_index("code_commune")["loyer_m2_estime"].to_dict()

        for feature in geojson["features"]:
            code = str(feature["properties"].get("code", "")).zfill(5)
            feature["properties"]["rendement"] = f"{lookup_rdt[code]:.2f} %"      if code in lookup_rdt  else "—"
            feature["properties"]["prix_m2"]   = f"{lookup_prix[code]:,.0f} €/m²" if code in lookup_prix else "—"
            feature["properties"]["loyer_m2"]  = f"{lookup_loy[code]:.2f} €/m²"   if code in lookup_loy  else "—"

        return geojson, data_ok, lookup_val

    carte, _ = charger_carte()

    track(type="carte_ouverte", source="app",
          session_id=st.session_state.session_id)

    type_carte = st.radio("Type de bien", ["Appartement", "Maison"], index=1, horizontal=True)
    metrique   = st.radio("Afficher", ["Prix au m² médian (€)", "Rendement estimé (%)"], index=1, horizontal=True)

    col_val = "prix_m2_median" if metrique == "Prix au m² médian (€)" else "rendement_median"
    legende = "Prix €/m²"      if metrique == "Prix au m² médian (€)" else "Rendement (%)"

    geojson, data_ok, lookup = enrichir_geojson(type_carte, col_val)

    val_min = data_ok[col_val].quantile(0.05)
    val_max = data_ok[col_val].quantile(0.95)

    if col_val == "prix_m2_median":
        colors = ["#1a9850","#a6d96a","#d9ef8b","#fee08b","#fdae61","#f46d43","#d73027"]
    else:
        colors = ["#d73027","#f46d43","#fdae61","#fee08b","#d9ef8b","#a6d96a","#1a9850"]

    colormap = cm.LinearColormap(
        colors=colors, vmin=val_min, vmax=val_max,
        caption=f"{legende} — {val_min:.0f} à {val_max:.0f}"
    )

    def style_fn(feature):
        code = str(feature["properties"].get("code", "")).zfill(5)
        val  = lookup.get(code)
        if val is None:
            return {"fillColor": "#cccccc", "fillOpacity": 0.15,
                    "color": "#ffffff", "weight": 0.3}
        return {"fillColor": colormap(val), "fillOpacity": 0.55,
                "color": "#ffffff", "weight": 0.3}

    def highlight_fn(feature):
        return {"weight": 1.5, "color": "#333", "fillOpacity": 0.95}

    m = folium.Map(
        location=[46.8, 2.3], zoom_start=6,
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
        prefer_canvas=True,
    )

    folium.GeoJson(
        geojson,
        style_function=style_fn,
        highlight_function=highlight_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=["nom", "rendement", "prix_m2", "loyer_m2"],
            aliases=["Commune", "Rendement estimé", "Prix médian / m²", "Loyer médian / m²"],
            localize=True,
        ),
    ).add_to(m)

    colormap.add_to(m)
    st_folium(m, width="100%", height=800, returned_objects=[])