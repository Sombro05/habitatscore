# Prototype local (non déployé) : prix par quartier à partir des ventes DVF géolocalisées,
# localisation probable d'une annonce via les DPE publics de l'ADEME, et liens de recherche
# Leboncoin préfiltrés (aucune annonce n'est collectée ni stockée).
# Lancement : python -m streamlit run prototype_quartiers.py --server.port 8502
import json
import math
import os
import re
import urllib.parse

import folium
import pandas as pd
import requests
import streamlit as st
from shapely.geometry import Point, box, mapping, shape
from streamlit_folium import st_folium

from data import charger_villes, get_labels_uniques, get_row
from scoring import scorer

PAS_GRILLE_M   = 400                        # côté d'un carré « quartier »
MIN_VENTES     = 20                         # en dessous, le carré est jugé peu fiable
RAYONS_M       = [300, 500, 800, 1200]      # recherche élargie autour d'une adresse
API_DPE        = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"
API_COMMUNES   = "https://geo.api.gouv.fr/communes/{}"
M_PAR_DEG_LAT  = 111_320
ARRONDISSEMENTS = {"751": "75056", "693": "69123", "132": "13055"}

st.set_page_config(page_title="HabitatScore – prototype quartiers", page_icon="🧪", layout="wide")


# ── Données ──────────────────────────────────────────────

@st.cache_data
def ventes_commune(code_commune, type_local):
    return pd.read_parquet(
        "dvf_clean.parquet",
        columns=["prix_m2", "latitude", "longitude", "date_mutation"],
        filters=[("code_commune", "==", code_commune), ("type_local", "==", type_local)],
    ).dropna(subset=["latitude", "longitude"])


@st.cache_data
def ventes_autour(lat, lon, rayon_m, type_local):
    # Lecture filtrée sur une boîte englobante, puis distance exacte : déborde sur les communes voisines
    dlat = rayon_m / M_PAR_DEG_LAT
    dlon = rayon_m / (M_PAR_DEG_LAT * math.cos(math.radians(lat)))
    df = pd.read_parquet(
        "dvf_clean.parquet",
        columns=["prix_m2", "latitude", "longitude"],
        filters=[("type_local", "==", type_local),
                 ("latitude", ">=", lat - dlat), ("latitude", "<=", lat + dlat),
                 ("longitude", ">=", lon - dlon), ("longitude", "<=", lon + dlon)],
    )
    dy = (df.latitude - lat) * M_PAR_DEG_LAT
    dx = (df.longitude - lon) * M_PAR_DEG_LAT * math.cos(math.radians(lat))
    return df[(dx ** 2 + dy ** 2) ** 0.5 <= rayon_m]


def prix_quartier(lat, lon, type_local):
    # Élargit le rayon jusqu'à disposer d'assez de ventes ; None si la zone est trop vide
    for r in RAYONS_M:
        v = ventes_autour(lat, lon, r, type_local)
        if len(v) >= MIN_VENTES:
            return {"prix_m2": float(v.prix_m2.median()), "nb": len(v), "rayon": r}
    return None


def grille(ventes, lat0):
    pas_lat = PAS_GRILLE_M / M_PAR_DEG_LAT
    pas_lon = PAS_GRILLE_M / (M_PAR_DEG_LAT * math.cos(math.radians(lat0)))
    g = ventes.assign(i=(ventes.latitude // pas_lat).astype(int),
                      j=(ventes.longitude // pas_lon).astype(int))
    g = g.groupby(["i", "j"]).prix_m2.agg(nb="count", prix_m2="median").reset_index()
    g["lat_min"], g["lon_min"] = g.i * pas_lat, g.j * pas_lon
    g["lat_max"], g["lon_max"] = g.lat_min + pas_lat, g.lon_min + pas_lon
    g["lat_c"], g["lon_c"] = g.lat_min + pas_lat / 2, g.lon_min + pas_lon / 2
    return g


def zones_grille(g):
    # Carrés de la grille, au même format que les quartiers
    return pd.DataFrame({
        "nom": "Secteur de 400 m", "prix_m2": g.prix_m2, "nb": g.nb,
        "lat_c": g.lat_c, "lon_c": g.lon_c, "rayon": PAS_GRILLE_M,
        "geometrie": [mapping(box(r.lon_min, r.lat_min, r.lon_max, r.lat_max)) for r in g.itertuples()],
    })


def code_ville(code_insee):
    # Arrondissements de Paris, Lyon et Marseille → commune (les quartiers sont préparés par commune)
    return ARRONDISSEMENTS.get(code_insee[:3], code_insee)


@st.cache_data
def charger_quartiers(code_insee):
    # Généré par 20_prep_quartiers.py (communes à grands quartiers INSEE parmi les 50 plus peuplées)
    chemin = f"geojson_cache/quartiers/{code_insee}.json"
    if not os.path.exists(chemin):
        return None
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def zones_quartiers(fc, type_local):
    suffixe = "app" if type_local == "Appartement" else "mai"
    lignes = []
    for f in fc["features"]:
        p = f["properties"]
        geom = shape(f["geometry"])
        c = geom.representative_point()   # toujours à l'intérieur, même pour un contour en croissant
        aire_m2 = geom.area * M_PAR_DEG_LAT ** 2 * math.cos(math.radians(c.y))
        lignes.append({"nom": p["nom"], "prix_m2": p[f"prix_{suffixe}"] or 0, "nb": p[f"nb_{suffixe}"],
                       "lat_c": c.y, "lon_c": c.x, "geometrie": f["geometry"], "geom": geom,
                       # Rayon du disque de même surface, borné pour rester une recherche « de quartier »
                       "rayon": int(min(3000, max(400, round(math.sqrt(aire_m2 / math.pi), -2))))})
    return pd.DataFrame(lignes)


def quartier_de(fc, lat, lon, type_local):
    if not fc:
        return None
    pt = Point(lon, lat)
    for z in zones_quartiers(fc, type_local).itertuples():
        if z.geom.contains(pt):
            return z
    return None


@st.cache_data(ttl=86400)
def infos_commune(code_insee):
    r = requests.get(API_COMMUNES.format(code_insee),
                     params={"fields": "nom,codesPostaux,centre,contour"}, timeout=10)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=3600)
def chercher_dpe(code_insee, type_bat, surface, conso, ges):
    # Valeurs numériques uniquement (issues de widgets) : pas d'injection possible dans la requête
    filtres = [f"code_insee_ban:{code_insee}", f"type_batiment:{type_bat}",
               f"surface_habitable_logement:[{surface * 0.93:.1f} TO {surface * 1.07:.1f}]",
               f"conso_5_usages_par_m2_ep:[{conso * 0.97:.1f} TO {conso * 1.03:.1f}]"]
    if ges:
        filtres.append(f"emission_ges_5_usages_par_m2:[{ges * 0.95:.1f} TO {ges * 1.05:.1f}]")
    r = requests.get(API_DPE, timeout=15, params={
        "qs": " AND ".join(filtres), "size": 50,
        "select": "adresse_ban,surface_habitable_logement,conso_5_usages_par_m2_ep,"
                  "emission_ges_5_usages_par_m2,etiquette_dpe,date_etablissement_dpe,"
                  "numero_etage_appartement,_geopoint",
    })
    r.raise_for_status()
    df = pd.DataFrame(r.json().get("results", []))
    if df.empty:
        return df
    # Écart relatif cumulé → proximité de 0 à 100 (100 = valeurs identiques à l'annonce)
    ecart = ((df.surface_habitable_logement - surface).abs() / surface
             + (df.conso_5_usages_par_m2_ep - conso).abs() / conso)
    if ges:
        ecart += (df.emission_ges_5_usages_par_m2 - ges).abs() / ges
    df["proximite"] = (100 * (1 - ecart * 5)).clip(lower=0).round()
    df[["lat", "lon"]] = df._geopoint.str.split(",", expand=True).astype(float)
    return df.sort_values("proximite", ascending=False).reset_index(drop=True)


def lien_leboncoin(nom, code_postal, type_local, prix_max=None, surface=None, lat=None, lon=None, rayon_m=None):
    params = {"category": "9", "real_estate_type": "1" if type_local == "Maison" else "2"}
    if lat is not None:
        # Format Leboncoin « ville_cp__lat_lon_rayonVille_rayon »
        params["locations"] = f"{nom}_{code_postal}__{lat:.5f}_{lon:.5f}_5000_{rayon_m}"
    else:
        params["locations"] = f"{nom}_{code_postal}"
    if prix_max:
        params["price"] = f"min-{int(prix_max)}"
    if surface:
        params["square"] = f"{surface[0]}-{surface[1]}"
    return "https://www.leboncoin.fr/recherche?" + urllib.parse.urlencode(params, safe="_-")


def fr(x):
    return f"{x:,.0f}".replace(",", " ")


def couleur(ratio):
    # Vert = moins cher que la commune, rouge = plus cher
    if ratio < 0.85: return "#1a9850"
    if ratio < 0.95: return "#91cf60"
    if ratio < 1.05: return "#fee08b"
    if ratio < 1.15: return "#fc8d59"
    return "#d73027"


# ── Interface ────────────────────────────────────────────

st.sidebar.title("🧪 Prototype local")
st.sidebar.caption("Non déployé. Données DVF 2023-2025, DPE ADEME, grands quartiers INSEE/IGN, "
                   "API Géo, fond © contributeurs OpenStreetMap.")
villes = charger_villes()
labels = get_labels_uniques(villes)
choix = st.sidebar.selectbox("Commune", labels,
                             index=labels.index("Angers (49)") if "Angers (49)" in labels else 0)
type_bien = st.sidebar.radio("Type de bien", ["Appartement", "Maison"])

try:
    row = get_row(villes, choix, type_bien)
except IndexError:
    st.warning(f"Pas de données « {type_bien} » pour {choix}.")
    st.stop()

code_insee = str(row["code_commune"]).zfill(5)
if not re.fullmatch(r"[0-9AB]{5}", code_insee):
    st.error("Code commune invalide.")
    st.stop()
commune = infos_commune(code_insee)
cp = commune["codesPostaux"][0]
lon0, lat0 = commune["centre"]["coordinates"]
prix_commune = float(row["prix_m2_median"])
fc_quartiers = charger_quartiers(code_ville(code_insee))

onglet1, onglet2 = st.tabs(["🗺️ Prix par quartier", "📍 Localiser une annonce"])

# ── Onglet 1 : carte des quartiers ───────────────────────
with onglet1:
    st.subheader(f"{commune['nom']} — {type_bien.lower()}s : prix par quartier")
    if fc_quartiers:
        zones = zones_quartiers(fc_quartiers, type_bien)
        if code_ville(code_insee) != code_insee:
            # Arrondissement de Paris, Lyon ou Marseille : seulement ses quartiers
            arr = shape(commune["contour"])
            zones = zones[[arr.contains(Point(r.lon_c, r.lat_c)) for r in zones.itertuples()]]
        legende = "Grands quartiers INSEE (contours IGN). "
    else:
        zones = zones_grille(grille(ventes_commune(code_insee, type_bien), lat0))
        legende = "Pas de quartiers préparés pour cette commune : carrés de 400 m. "
    fiables = zones[zones.nb >= MIN_VENTES]
    c1, c2, c3 = st.columns(3)
    c1.metric("Prix médian de la commune", f"{fr(prix_commune)} €/m²")
    c2.metric("Zones fiables (≥ 20 ventes)", f"{len(fiables)} / {len(zones)}")
    if len(fiables):
        c3.metric("Écart entre zones (€/m²)", f"{fr(fiables.prix_m2.min())} → {fr(fiables.prix_m2.max())}")

    s_min, s_max = st.slider("Surface recherchée (m²)", 15, 200, (35, 60), key="surf")
    # Les 8 zones fiables les moins chères, numérotées sur la carte et dans la liste
    top = fiables.assign(ecart=(fiables.prix_m2 / prix_commune - 1) * 100).nsmallest(8, "prix_m2")

    cadre = fiables if len(fiables) else zones   # centrage sur les zones fiables (ignore les ventes isolées)
    zoom = 15 if code_ville(code_insee) != code_insee else 13   # arrondissement : vue rapprochée
    m = folium.Map(location=[cadre.lat_c.mean(), cadre.lon_c.mean()], zoom_start=zoom, tiles="OpenStreetMap")
    for _, z in zones.iterrows():
        fiable = z.nb >= MIN_VENTES
        style = {"color": "#555" if fiable else "#bbb", "weight": 1, "dashArray": None if fiable else "4",
                 "fillColor": couleur(z.prix_m2 / prix_commune) if fiable else "#ddd",
                 "fillOpacity": 0.55 if fiable else 0.25}
        prix_txt = f"{fr(z.prix_m2)} €/m²" if z.nb else "aucune vente"
        folium.GeoJson(z.geometrie, style_function=lambda _, s=style: s,
                       tooltip=f"<b>{z.nom}</b><br>{prix_txt} · {int(z.nb)} ventes"
                               f"{'' if fiable else ' (peu fiable)'}").add_to(m)
    for n, (_, z) in enumerate(top.iterrows(), 1):
        folium.Marker([z.lat_c, z.lon_c], tooltip=z.nom, icon=folium.DivIcon(
            icon_size=(22, 22), icon_anchor=(11, 11),
            html=f'<div style="background:#1B3A5C;color:#fff;border-radius:50%;width:22px;height:22px;'
                 f'text-align:center;line-height:22px;font:bold 12px sans-serif">{n}</div>')).add_to(m)
    st_folium(m, height=520, use_container_width=True, returned_objects=[])
    st.caption(legende + "Vert : moins cher que la médiane communale ; rouge : plus cher. "
               "Pointillés gris : moins de 20 ventes. Numéros : zones listées ci-dessous.")

    st.markdown("#### Les quartiers les moins chers, avec une recherche Leboncoin prête")
    for n, (_, z) in enumerate(top.iterrows(), 1):
        budget = z.prix_m2 * s_max
        url = lien_leboncoin(commune["nom"], cp, type_bien, budget, (s_min, s_max),
                             z.lat_c, z.lon_c, z.rayon)
        st.markdown(f"{n}. **{z.nom}** — {fr(z.prix_m2)} €/m² ({z.ecart:+.0f} % vs commune, {int(z.nb)} ventes) · "
                    f"budget ≤ {fr(budget)} € pour {s_max} m² · [voir les annonces]({url})")

# ── Onglet 2 : localiser une annonce ─────────────────────
with onglet2:
    st.subheader("Retrouver l'adresse probable d'une annonce grâce à son DPE")
    st.caption("Saisissez les valeurs affichées dans l'annonce. Recherche dans la base publique "
               "des DPE de l'ADEME (logements existants depuis juillet 2021).")
    a1, a2, a3, a4 = st.columns(4)
    surface = a1.number_input("Surface (m²)", 9.0, 1000.0, 43.0, step=1.0)
    conso   = a2.number_input("Énergie (kWh/m²/an)", 1.0, 1500.0, 305.0, step=1.0)
    ges     = a3.number_input("GES (kg CO₂/m²/an, 0 si absent)", 0.0, 300.0, 66.0, step=1.0)
    prix    = a4.number_input("Prix affiché (€)", 10_000, 10_000_000, 99_000, step=1_000)

    try:
        cands = chercher_dpe(code_insee, type_bien.lower(), surface, conso, ges or None)
    except requests.RequestException as e:
        st.error(f"API ADEME indisponible : {e}")
        st.stop()

    if cands.empty:
        st.info("Aucun DPE correspondant dans cette commune (DPE antérieur à 2021, valeurs arrondies, "
                "ou annonce sans DPE).")
        st.stop()

    st.markdown(f"**{len(cands)} logement(s) candidat(s)**" +
                (" — un seul : adresse quasi certaine." if len(cands) == 1 else ""))
    st.dataframe(
        cands[["proximite", "adresse_ban", "surface_habitable_logement", "conso_5_usages_par_m2_ep",
               "emission_ges_5_usages_par_m2", "date_etablissement_dpe"]].rename(columns={
            "proximite": "Proximité", "adresse_ban": "Adresse", "surface_habitable_logement": "m²",
            "conso_5_usages_par_m2_ep": "kWh/m²", "emission_ges_5_usages_par_m2": "GES",
            "date_etablissement_dpe": "Date DPE"}),
        hide_index=True, use_container_width=True)

    idx = st.selectbox("Adresse retenue", cands.index,
                       format_func=lambda i: f"{cands.adresse_ban[i]} (proximité {cands.proximite[i]:.0f})")
    cand = cands.loc[idx]
    # Quartier nommé contenant l'adresse s'il a assez de ventes, sinon médiane dans un rayon
    nq = quartier_de(fc_quartiers, cand.lat, cand.lon, type_bien)
    if nq is not None and nq.nb >= MIN_VENTES:
        q = {"prix_m2": nq.prix_m2, "nb": int(nq.nb), "libelle": f"quartier {nq.nom}", "geometrie": nq.geometrie}
    else:
        q = prix_quartier(cand.lat, cand.lon, type_bien)
        if q:
            q["libelle"] = f"à moins de {q['rayon']} m"

    m2 = folium.Map(location=[cand.lat, cand.lon], zoom_start=15, tiles="OpenStreetMap")
    for i, c in cands.iterrows():
        folium.CircleMarker([c.lat, c.lon], radius=8 if i == idx else 5,
                            color="#1B3A5C" if i == idx else "#888", fill=True,
                            tooltip=c.adresse_ban).add_to(m2)
    if q and "geometrie" in q:
        folium.GeoJson(q["geometrie"], style_function=lambda _: {"color": "#27AE60", "fillOpacity": 0.05}).add_to(m2)
    elif q:
        folium.Circle([cand.lat, cand.lon], radius=q["rayon"], color="#27AE60", fill=False).add_to(m2)
    st_folium(m2, height=380, use_container_width=True, returned_objects=[])

    # Score avec le prix de la commune vs le prix du quartier
    base = dict(prix_achat=prix, surface=surface, type_bien=type_bien, usage="Achat / revente",
                nb_ventes=int(row["nb_ventes"]), loyer_m2_estime=float(row["loyer_m2_estime"]))
    s_commune = scorer(prix_m2_median=prix_commune, **base)
    b1, b2 = st.columns(2)
    b1.metric("Score avec le prix de la commune", f"{s_commune['score_pct']} / 100",
              help=f"Médiane communale : {fr(prix_commune)} €/m²")
    if q:
        s_quartier = scorer(prix_m2_median=q["prix_m2"], **base)
        b2.metric("Score avec le prix du quartier", f"{s_quartier['score_pct']} / 100",
                  delta=s_quartier["score_pct"] - s_commune["score_pct"],
                  help=f"Médiane de {q['nb']} ventes ({q['libelle']}) : {fr(q['prix_m2'])} €/m²")
        st.caption(f"Quartier : {fr(q['prix_m2'])} €/m² ({q['nb']} ventes, {q['libelle']}) · "
                   f"commune : {fr(prix_commune)} €/m² · annonce : {fr(prix / surface)} €/m²")
    else:
        b2.info("Trop peu de ventes autour de cette adresse : le prix de la commune s'applique.")
