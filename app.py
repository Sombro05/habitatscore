import streamlit as st
import streamlit.components.v1 as components
import folium
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from streamlit_folium import st_folium
from scipy.stats import gaussian_kde as scipy_kde
from scoring import scorer, calculer_frais_notaire, calculer_budget_dpe, FRAIS_NOTAIRE_ANCIEN, BUDGET_DPE
from tracker import track, feedback
from data import charger_villes, charger_kde, charger_geojson_cache, charger_carte_data, charger_pays_voisins, charger_geojson_epci, charger_ventes_commune, get_labels_uniques, get_row, get_prix_kde
import uuid
import os

st.set_page_config(page_title="HabitatScore", page_icon="🏠", layout="wide")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

villes   = charger_villes()
kde_data = charger_kde()

qp = st.query_params
qp_ville     = qp.get("ville", "")
qp_prix      = int(qp.get("prix", 0) or 0)
qp_surface   = int(qp.get("surface", 0) or 0)
qp_type_bien = qp.get("type_bien", "")
qp_dpe       = qp.get("dpe", "")

# Forcer la page via URL
qp_page = qp.get("page", "")
if qp_page == "carte" and "page_forcee" not in st.session_state:
    st.session_state["page_forcee"] = "Explorer le marché"

st.sidebar.title("🏠 HabitatScore")
index_defaut = 1 if st.session_state.get("page_forcee") == "Explorer le marché" else 0
page = st.sidebar.radio("Navigation", ["Analyser un bien", "Explorer le marché"],
                        index=index_defaut)
# ════════════════════════════════════════════
# PAGE 1 — ANALYSER UN BIEN
# ════════════════════════════════════════════
if page == "Analyser un bien":
    st.title("Analyser un bien")
    # Marges réduites pour que la page tienne sur un écran ; zone de résultats sur fond
    # teinté (cartes blanches) pour la distinguer de la saisie ; graphique en hauteur relative
    st.markdown("""<style>
        .block-container {padding-top: 2rem; padding-bottom: 1rem;
                          min-height: 100vh; display: flex; flex-direction: column;}
        /* La zone de résultats occupe toute la hauteur restante de l'écran */
        .block-container > [data-testid="stVerticalBlock"],
        [data-testid="stLayoutWrapper"]:has(> .st-key-resultats) {flex: 1;}
        .st-key-resultats {background: #F1F4F8; border-radius: 12px; padding: 14px 16px; flex: 1;}
        .st-key-resultats > [data-testid="stHorizontalBlock"]:first-of-type {flex: 1;}
        .st-key-resultats [data-testid="stMetric"] {background: #FFFFFF;}
        .st-key-graphique {background: #FFFFFF; border-radius: 8px;}
        .st-key-graphique img {max-height: 20vh; object-fit: contain;}
        /* Le script invisible (saisie automatique) ne doit pas créer d'espace */
        .st-key-saisie [data-testid="stElementContainer"]:has(iframe[title="st.iframe"]) {display: none;}
    </style>""", unsafe_allow_html=True)

    def fmt(n, dec=0):
        # Nombre au format français : 281 119
        return f"{n:,.{dec}f}".replace(",", " ").replace(".", ",")

    # ══ SAISIE : VOTRE BIEN ══════════════════
    with st.container(border=True, key="saisie"):
        st.markdown("**✎ Votre bien**")
        # À gauche : localisation, puis type de bien et usage ; à droite : montants (3 × 2)
        col_lieu, col_montants = st.columns([1.1, 1.4], gap="large")
        with col_lieu:
            labels = get_labels_uniques(villes)
            choix  = st.selectbox(
                "Localisation",
                options=labels, index=None,
                placeholder="Tapez pour rechercher une ville...",
            )
            # Désactive la saisie automatique d'adresses du navigateur sur les champs de recherche,
            # qui masquait la liste des villes (Streamlit ne permet pas de régler cet attribut)
            components.html("""
                <script>
                const doc = window.parent.document;
                const desactiver = () => doc
                    .querySelectorAll('div[data-baseweb="select"] input:not([autocomplete="off"])')
                    .forEach(champ => champ.setAttribute("autocomplete", "off"));
                desactiver();
                new MutationObserver(desactiver).observe(doc.body, {childList: true, subtree: true});
                </script>
            """, height=0)
            if not choix:
                st.stop()

            types_dispo = villes[villes["label"] == choix]["type_local"].unique().tolist()
            # Maison en premier (et donc par défaut) quand elle est disponible
            types_dispo.sort(key=lambda t: t != "Maison")
            type_defaut = qp_type_bien if qp_type_bien in types_dispo else types_dispo[0]
            c_type, c_usage = st.columns([1, 1.7])
            type_bien = c_type.segmented_control("Type de bien", types_dispo,
                                                 default=type_defaut, required=True)

            usage = c_usage.segmented_control(
                "Usage", ["Résidence principale", "Location", "Achat / revente"],
                default="Résidence principale", required=True,
            )

        row = get_row(villes, choix, type_bien)
        prix_m2_median  = float(row["prix_m2_median"])
        loyer_m2_estime = float(row["loyer_m2_estime"])
        nb_ventes       = int(row["nb_ventes"])
        surface_moyenne = float(row["surface_moyenne"])

        # Montants sur 2 lignes (détails dans les infobulles « ? ») : 3 colonnes,
        # 4 en location pour placer le loyer sans ajouter de ligne
        with col_montants:
            if usage == "Location":
                c_surf, c_prix, c_notaire, c_travaux = st.columns(4)
                c_dpe, c_budget, *c_loyer = st.columns(4)
            else:
                c_surf, c_prix, c_notaire = st.columns(3)
                c_travaux, c_dpe, c_budget = st.columns(3)

        surface = c_surf.number_input("Surface (m²)",
                                      value=qp_surface if qp_surface > 0 else int(surface_moyenne),
                                      min_value=10, max_value=500)

        prix_achat = c_prix.number_input(
            "Prix d'achat (€)", help=f"Médiane du marché : {fmt(prix_m2_median)} €/m²",
            value=qp_prix if qp_prix > 0 else int(prix_m2_median * surface),
            step=1000
        )

        frais_notaire = c_notaire.number_input(
            "Frais de notaire (€)", help=f"Par défaut : {FRAIS_NOTAIRE_ANCIEN*100:.0f} % du prix",
            value=calculer_frais_notaire(prix_achat),
            step=100
        )

        travaux = c_travaux.number_input("Travaux (€)", value=0, step=500, min_value=0)

        # DPE
        dpe_options = ["", "A", "B", "C", "D", "E", "F", "G"]
        dpe_defaut  = qp_dpe if qp_dpe in dpe_options else ""
        dpe = c_dpe.selectbox(
            "DPE (optionnel)",
            options=dpe_options,
            index=dpe_options.index(dpe_defaut),
            format_func=lambda x: "Non renseigné" if x == "" else x,
        )

        # Budget DPE
        budget_dpe_auto = int(calculer_budget_dpe(dpe, surface)) if dpe else 0
        budget_dpe = c_budget.number_input(
            "Rénovation énergie (€)", help=f"Budget de rénovation énergétique estimé : {fmt(budget_dpe_auto)} €",
            value=budget_dpe_auto,
            step=500,
            min_value=0,
        )

        loyer = None
        if usage == "Location":
            loyer = c_loyer[0].number_input(
                "Loyer mensuel (€)", help=f"Loyer de marché : {loyer_m2_estime:.1f} €/m²",
                value=int(loyer_m2_estime * surface), step=10
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
        coef_vacance=float(row.get("coef_vacance", 1.0)),
    )

    track(
        type="analyse_bien",
        source="app",
        ville=choix,
        code_postal=str(row["dept_affiche"]) if "dept_affiche" in row else None,
        type_bien=type_bien,
        score=res["score_pct"],
        session_id=st.session_state.session_id,
    )

    # ══ RÉSULTAT ════════════════════════════
    pct = res["score_pct"]
    # En location, le score mêle prix et rendement (vacance comprise) : libellés d'investissement
    libelles = (("Bon investissement", "Investissement moyen", "Investissement risqué")
                if usage == "Location" else ("Bonne affaire", "Prix dans la moyenne", "Prix élevé"))
    if pct >= 65:
        verdict, fond, texte = libelles[0], "#EAF3DE", "#27500A"
    elif pct >= 40:
        verdict, fond, texte = libelles[1], "#FAEEDA", "#633806"
    else:
        verdict, fond, texte = libelles[2], "#FCEBEB", "#791F1F"

    # Prix au m² retenu par le score (tout compris en achat / revente, cf. scoring.py)
    prix_ref = res["prix_m2_tout_compris"] if usage == "Achat / revente" else res["prix_m2_achat_travaux"]

    def regle_prix(prix, mediane, p_bas, p_haut):
        """Règle verte / jaune / rouge : zones déduites du barème du score
        (score 65 à 85 % de la médiane, score 40 à 110 %)."""
        bas  = min(p_bas, mediane * 0.7, prix * 0.95)
        haut = max(p_haut, mediane * 1.3, prix * 1.05)
        pos  = lambda v: max(0.0, min(100.0, (v - bas) / (haut - bas) * 100))
        vert, jaune, m = pos(mediane * 0.85), pos(mediane * 1.10), pos(prix)
        ancre = "0" if m < 15 else "-100%" if m > 85 else "-50%"
        return f"""
        <div style="position:relative;height:64px;margin:4px 6px 0">
          <div style="position:absolute;top:0;left:0;font-size:12px;color:#3B6D11">Bonne affaire</div>
          <div style="position:absolute;top:0;left:{(vert + jaune) / 2}%;transform:translateX(-50%);font-size:12px;color:#854F0B;white-space:nowrap">Dans la moyenne</div>
          <div style="position:absolute;top:0;right:0;font-size:12px;color:#A32D2D">Cher</div>
          <div style="position:absolute;top:22px;left:0;right:0;height:14px;display:flex;border-radius:7px;overflow:hidden">
            <div style="width:{vert}%;background:#97C459"></div>
            <div style="width:{jaune - vert}%;background:#FAC775"></div>
            <div style="flex:1;background:#F09595"></div>
          </div>
          <div style="position:absolute;top:15px;left:{m}%;height:28px;border-left:3px solid #2C2C2A;transform:translateX(-1.5px)"></div>
          <div style="position:absolute;top:46px;left:{m}%;transform:translateX({ancre});font-size:13px;font-weight:600;white-space:nowrap">Votre bien : {fmt(prix)} €/m²</div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:#888780;margin:0 6px">
          <span>{fmt(bas)} €/m²</span><span>médiane {fmt(mediane)} €/m²</span><span>{fmt(haut)} €/m²</span>
        </div>"""

    with st.container(key="resultats"):
        st.markdown("**📊 Résultat**")

        # Synthèse à gauche (verdict, indicateurs, règle) | marché à droite (distribution, ventes)
        c_synthese, c_marche = st.columns(2, gap="medium")

        with c_synthese:
            st.markdown(f"""
                <div style="background:{fond};color:{texte};border-radius:8px;padding:14px 16px;
                            display:flex;align-items:center;gap:14px;height:100%">
                  <span style="font-size:40px;font-weight:600;line-height:1">{pct}</span>
                  <div><div style="font-size:16px;font-weight:600">{verdict}</div>
                       <div style="font-size:13px">score sur 100</div></div>
                </div>""", unsafe_allow_html=True)

            c_prix_m2, c_cout = st.columns(2)
            c_prix_m2.metric("Prix au m² de votre bien", f"{fmt(res['prix_m2_achat_travaux'])} €",
                             f"{res['ecart']:+.1f} % vs médiane".replace(".", ","), delta_color="inverse", border=True)
            c_cout.metric("Coût tout compris", f"{fmt(res['cout_total'])} €",
                          f"{res['ecart_tout_compris']:+.1f} % vs marché".replace(".", ","), delta_color="inverse", border=True,
                          help=f"Prix + notaire + travaux + rénovation, soit {fmt(res['prix_m2_tout_compris'])} €/m²")

            regle = regle_prix(prix_ref, prix_m2_median,
                               float(row["prix_m2_p10"]), float(row["prix_m2_p90"]))
            st.markdown(f'<div style="background:#FFFFFF;border-radius:8px;padding:10px 8px">{regle}</div>',
                        unsafe_allow_html=True)
            if usage == "Location":
                delta_rdt   = res["rdt_ajuste"] - res["rdt_neutre"]
                delta_loyer = loyer - int(loyer_m2_estime * surface)
                vacance     = row.get("vacance_locative")
                texte_vac   = f"{vacance:.0%}".replace(".", ",") if pd.notna(vacance) else "inconnue"
                c_rdt, c_loy = st.columns(2)
                c_rdt.metric("Rendement ajusté (vacance)", f"{fmt(res['rdt_ajuste'], 2)} %",
                             f"{delta_rdt:+.2f}".replace(".", ",") + f" pt vs ville ({fmt(res['rdt_neutre'], 2)} %)", border=True,
                             help=f"Rendement brut {fmt(res['rdt_brut'], 2)} % × coefficient de vacance "
                                  f"{fmt(res['coef_vacance'], 2)}. Vacance locative de la commune : {texte_vac} "
                                  f"(logements vides / (vides + loués), INSEE 2021) ; au-delà de 30 %, chaque point "
                                  f"de vacance retire 1 % au loyer.")
                c_loy.metric("Loyer vs marché", f"{fmt(loyer)} €",
                             f"{fmt(delta_loyer)} € / mois", border=True)


        with c_marche:
            prix_raw = get_prix_kde(kde_data, row["nom_commune"], str(row["code_departement"]), type_bien)
            with st.container(key="graphique"):
                if len(prix_raw) >= 10:
                    prix_arr = np.array(prix_raw)
                    kde_fn   = scipy_kde(prix_arr, bw_method="scott")
                    x = np.linspace(max(0, np.percentile(prix_arr, 1)), np.percentile(prix_arr, 99), 300)
                    y = kde_fn(x)
                    y = y / y.max()

                    fig, ax = plt.subplots(figsize=(6, 1.9))
                    fig.patch.set_alpha(0)
                    ax.set_facecolor("none")
                    ax.plot(x, y, color="#378ADD", linewidth=2)
                    ax.fill_between(x, y, alpha=0.18, color="#378ADD")
                    ax.axvline(prix_ref, color="#E24B4A", linewidth=2, label="Votre bien")
                    ax.axvline(prix_m2_median, color="#27AE60", linewidth=1.5, linestyle="--", label="Médiane")
                    ax.set_title(f"Position parmi {fmt(nb_ventes)} ventes (€/m²)", fontsize=9, color="gray", loc="left")
                    ax.set_yticks([])
                    ax.tick_params(colors="gray", labelsize=8)
                    for spine in ax.spines.values():
                        spine.set_visible(False)
                    ax.legend(fontsize=7, framealpha=0, loc="upper right")
                    st.pyplot(fig, use_container_width=True)
                    plt.close(fig)
                else:
                    st.caption("Pas assez de ventes pour afficher la distribution.")

            # Ventes DVF de la commune, même type de bien, surface à ±10 %, triées par prix
            ventes = charger_ventes_commune(str(row["code_commune"]).zfill(5), type_bien)
            similaires = ventes[ventes["surface_reelle_bati"].between(surface * 0.9, surface * 1.1)]
            similaires = similaires.sort_values("valeur_fonciere")
            st.markdown(f"**Ventes similaires** · {type_bien.lower()}s de {fmt(surface * 0.9)} "
                        f"à {fmt(surface * 1.1)} m² · {len(similaires)} vente(s)")
            if similaires.empty:
                st.caption("Aucune vente de surface comparable dans la commune.")
            else:
                # Tableau HTML : hauteur relative à l'écran, défilement interne, en-tête fixe
                lignes = "".join(
                    f"<tr><td>{fmt(v.surface_reelle_bati)} m²</td><td>{fmt(v.valeur_fonciere)} €</td>"
                    f"<td>{fmt(v.prix_m2)} €</td><td>{v.date_mutation:%m/%Y}</td></tr>"
                    for v in similaires.itertuples()
                )
                st.markdown(f"""
                    <div style="max-height:22vh;overflow-y:auto;background:#FFFFFF;border-radius:8px;
                                border:1px solid #E3E6EA">
                      <table style="width:100%;border-collapse:collapse;font-size:13px">
                        <thead><tr style="position:sticky;top:0;background:#F7F8FA;text-align:left">
                          <th style="padding:6px 10px">Surface</th><th style="padding:6px 10px">Prix</th>
                          <th style="padding:6px 10px">Prix/m²</th><th style="padding:6px 10px">Date</th>
                        </tr></thead>
                        <tbody>{lignes}</tbody>
                      </table>
                    </div>
                    <style>.st-key-resultats td {{padding:4px 10px;border-top:1px solid #EEF0F3}}</style>
                """, unsafe_allow_html=True)
# ════════════════════════════════════════════
# PAGE 2 — EXPLORER LE MARCHÉ
# ════════════════════════════════════════════
else:
    st.title("Explorer le marché")
    st.caption("Carte des rendements estimés par commune (2023–2025)")

    import json
    import branca.colormap as cm
    from branca.element import MacroElement
    from jinja2 import Template

    df, carte = charger_carte_data()

    track(type="carte_ouverte", source="app",
          session_id=st.session_state.session_id)

    type_carte = st.radio("Type de bien", ["Appartement", "Maison"], index=1, horizontal=True)
    metrique   = st.radio("Afficher", ["Prix au m² médian (€)", "Rendement estimé (%)"], index=1, horizontal=True)
    echelle    = st.radio("Échelle", ["Commune", "Intercommunalité"], horizontal=True,
                          help="Intercommunalité : vue d'ensemble des bassins, moins sensible aux "
                               "communes avec peu de ventes. Commune : détail, prix lissés vers "
                               "l'intercommunalité quand il y a peu de ventes.")
    par_epci   = echelle == "Intercommunalité"

    col_val = "prix_m2_median" if metrique == "Prix au m² médian (€)" else "rendement_median"
    legende = "Prix €/m²"      if metrique == "Prix au m² médian (€)" else "Rendement (%)"

    # Charger le GeoJSON pré-généré (communes : 12_prep_geojson.py, EPCI : 18_prep_epci.py)
    if par_epci:
        geojson = charger_geojson_epci(type_carte)
        cle_val = "val_" + col_val
        valeurs = pd.Series([f["properties"][cle_val] for f in geojson["features"]])
    else:
        geojson = charger_geojson_cache(type_carte, col_val)
        cle_val = "val"
        valeurs = carte.loc[carte["type_local"] == type_carte, col_val]

    val_min = valeurs.quantile(0.05)
    val_max = valeurs.quantile(0.95)

    if col_val == "prix_m2_median":
        colors = ["#1a9850","#a6d96a","#d9ef8b","#fee08b","#fdae61","#f46d43","#d73027"]
    else:
        colors = ["#d73027","#f46d43","#fdae61","#fee08b","#d9ef8b","#a6d96a","#1a9850"]

    colormap = cm.LinearColormap(
        colors=colors, vmin=val_min, vmax=val_max,
        caption=f"{legende} — {val_min:.0f} à {val_max:.0f}"
    )

    def style_fn(feature):
        val = feature["properties"].get(cle_val)
        trait = 0.8 if par_epci else 0.3
        if val is None:
            return {"fillColor": "#cccccc", "fillOpacity": 0.15,
                    "color": "#ffffff", "weight": trait}
        return {"fillColor": colormap(val), "fillOpacity": 0.55,
                "color": "#ffffff", "weight": trait}

    def highlight_fn(feature):
        return {"weight": 1.5, "color": "#333", "fillOpacity": 0.95}

    m = folium.Map(
        location=[46.8, 2.3], zoom_start=6,
        tiles=None,       # fond maison : mer (couleur de fond) + terres Natural Earth, sans routes
        prefer_canvas=True,
        zoom_snap=0.25,   # zoom fractionnaire : la France remplit la carte au cadrage
        zoom_delta=0.5,   # pas des boutons +/- (défaut Leaflet : 1 niveau)
        wheel_px_per_zoom_level=150,  # molette plus douce (défaut 60 ; plus grand = zoom plus lent)
        max_bounds=True,  # déplacement limité à la zone des terres dessinées
        min_lat=25, max_lat=65, min_lon=-30, max_lon=45,  # = ZONE de 14_prep_pays_voisins.py
    )

    # Terres (France et pays voisins) en gris clair, sous les communes
    folium.GeoJson(
        charger_pays_voisins(),
        # Frontières et côtes en gris ; pas de trait pour la France (les communes le dessinent)
        style_function=lambda f: {"fillColor": "#ececec", "fillOpacity": 1, "color": "#9e9e9e",
                                  "weight": 0 if f["properties"].get("france") else 1},
        interactive=False,
    ).add_to(m)

    folium.GeoJson(
        geojson,
        style_function=style_fn,
        highlight_function=highlight_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=["nom", "rendement", "prix_m2", "loyer_m2", "vacance"] + (["ventes"] if par_epci else []),
            aliases=["Intercommunalité" if par_epci else "Commune", "Rendement estimé",
                     "Prix médian / m²", "Loyer médian / m²", "Vacance locative"]
                    + (["Ventes analysées"] if par_epci else []),
            localize=True,
        ),
    ).add_to(m)

    # Noms des villes CARTO (sans fond ni routes), au-dessus des communes et sans bloquer
    # les infobulles. Clé gratuite : https://carto.com/basemaps/apikey/ — à placer dans les
    # secrets Streamlit (CARTO_API_KEY), jamais dans le code. Sans clé : pas de noms.
    try:
        cle_carto = st.secrets.get("CARTO_API_KEY", "")
    except Exception:  # pas de fichier de secrets en local
        cle_carto = os.environ.get("CARTO_API_KEY", "")
    if cle_carto:
        folium.map.CustomPane("noms", z_index=650, pointer_events=False).add_to(m)
        folium.TileLayer(
            tiles="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png?key=" + cle_carto,
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
                 '&copy; <a href="https://carto.com/attributions">CARTO</a>',
            pane="noms", overlay=True, control=False,
        ).add_to(m)

    colormap.add_to(m)
    # Cadrage sur la France métropolitaine (Corse incluse), une fois la carte à sa taille
    # finale, et dézoom limité à un demi-niveau au-delà (s'adapte à la taille de l'écran)
    # (script rattaché à la carte : st_folium n'exécute que les éléments enfants de la carte ;
    # le fit_bounds Python reste nécessaire pour la vue de départ)
    m.fit_bounds([[41.3, -5.2], [51.1, 9.6]])
    class CadrageFrance(MacroElement):
        _template = Template("""
            {% macro script(this, kwargs) %}
            {{ this._parent.get_name() }}.whenReady(() => setTimeout(() => {
                const carte  = {{ this._parent.get_name() }};
                const france = L.latLngBounds([[41.3, -5.2], [51.1, 9.6]]);
                carte.invalidateSize();
                carte.setMinZoom(carte.getBoundsZoom(france) - 0.5);
                carte.fitBounds(france);
            }, 0));
            {% endmacro %}
        """)
    m.add_child(CadrageFrance())


    # Hauteur adaptée à l'écran : l'iframe du composant prend la hauteur de la fenêtre
    # moins l'en-tête de la page, et la carte occupe toute l'iframe
    st.markdown(
        "<style>iframe[title='streamlit_folium.st_folium']"
        "{height: calc(100vh - 430px) !important; min-height: 450px;}</style>",
        unsafe_allow_html=True,
    )
    m.get_root().header.add_child(folium.Element(
        "<style>#map_div, #map_div2 {height: 100vh !important;}"
        " .leaflet-container {background: #d4e6f1;}</style>"  # mer et océan
    ))

    st_folium(m, use_container_width=True, height=600, returned_objects=[])