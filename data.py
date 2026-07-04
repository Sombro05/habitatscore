import pandas as pd
import json
import gzip
import streamlit as st

@st.cache_data
def charger_donnees():
    # Lire le parquet au lieu du CSV
    df     = pd.read_parquet("dvf_clean.parquet")
    villes = pd.read_csv("dvf_villes.csv")
    return df, villes

@st.cache_data
def charger_kde():
    # Lire le JSON gzippé
    with gzip.open("dvf_kde.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)

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