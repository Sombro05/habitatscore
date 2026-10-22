import pandas as pd
import json
import gzip
import streamlit as st

@st.cache_data
def charger_villes():
    villes = pd.read_csv("dvf_villes.csv")
    return villes

@st.cache_data
def charger_kde():
    with gzip.open("dvf_kde.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def charger_geojson_cache(type_local, col_val):
    nom = f"geojson_cache/{type_local}_{col_val}.json"
    with open(nom, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def charger_pays_voisins():
    # Généré par 14_prep_pays_voisins.py (Natural Earth, domaine public)
    with open("geojson_cache/pays_voisins.json", "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def charger_ventes_commune(code_commune, type_local):
    # Ventes DVF d'une commune (lecture filtrée du parquet, sans charger tout le fichier)
    return pd.read_parquet(
        "dvf_clean.parquet",
        columns=["date_mutation", "valeur_fonciere", "surface_reelle_bati", "prix_m2"],
        filters=[("code_commune", "==", code_commune), ("type_local", "==", type_local)],
    )

@st.cache_data
def charger_carte_data():
    df    = pd.read_parquet("dvf_clean.parquet")
    carte = pd.read_csv("dvf_carte.csv")
    return df, carte

def get_labels_uniques(villes):
    return sorted(villes["label"].unique().tolist())

def get_row(villes, choix, type_bien):
    return villes[
        (villes["label"] == choix) &
        (villes["type_local"] == type_bien)
    ].iloc[0]

def get_prix_kde(kde_data, commune, dept, type_local):
    key = f"{commune}|||{dept}|||{type_local}"
    return kde_data.get(key, [])