"""
Écart de loyer de chaque grand quartier par rapport à sa commune (coef_loyer), pour le
rendement par quartier de la carte (21_prep_carte_quartiers.py).

Sources ouvertes, téléchargées dans un dossier temporaire puis réduites aux seules colonnes utiles :
- Paris : loyers de référence de l'encadrement, par quartier administratif (Ville de Paris, ODbL) ;
- Lyon et Villeurbanne : loyers de référence de l'encadrement, par IRIS (Métropole de Lyon, Licence Ouverte) ;
- ailleurs : loyers médians des observatoires locaux des loyers (OLL, Licence Ouverte), par zone,
  chaque zone étant une liste d'IRIS ou de communes.
Pour l'encadrement, loyer d'un IRIS ou d'un quartier = moyenne des loyers de référence « non meublé »
toutes tailles et époques confondues ; pour les OLL, loyer médian de la zone, tous logements confondus.

Seul l'écart relatif est conservé : coef_loyer = loyer du quartier / loyer moyen de la commune
(moyennes sur les IRIS). Le niveau reste celui des loyers ANIL de la commune (charges comprises,
loyers d'annonce), que ces sources (hors charges, baux en cours) ne permettent pas de remplacer.
Sans découpage intra-communal (une seule zone) ou avec moins de la moitié des IRIS couverts : coef 1.

Entrées : quartiers_iris.csv (20_prep_quartiers.py), API data.gouv.fr, exports Paris et Lyon
Sorties réduites (relecture sans téléchargement ; --telecharger pour les rafraîchir) :
  loyers_oll_zones.csv, loyers_oll_zonage.csv, loyers_encadrement.csv
Sortie : loyers_quartiers.csv (code_commune, quartier, coef_loyer, source, couverture)
"""
import io
import json
import os
import re
import sys
import tempfile
import zipfile

import pandas as pd
import requests

API_OLL = ("https://www.data.gouv.fr/api/1/datasets/"
           "resultats-des-observatoires-locaux-des-loyers-par-agglomeration/")
URL_PARIS = ("https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
             "logement-encadrement-des-loyers/exports/csv?use_labels=true")
URL_LYON = ("https://data.grandlyon.com/geoserver/metropole-de-lyon/ows?SERVICE=WFS&VERSION=2.0.0"
            "&request=GetFeature&typename=metropole-de-lyon:car_care.carencadrmtloyer_2024_2025"
            "&outputFormat=CSV&SRSNAME=EPSG:4326")
# Colonnes de croisement des OLL : la ligne « tous logements » d'une zone les a toutes vides
DIMENSIONS = ["Type_habitat", "epoque_construction_local", "epoque_construction_homogene",
              "anciennete_locataire_local", "anciennete_locataire_homogene",
              "nombre_pieces_local", "nombre_pieces_homogene"]
COUVERTURE_MIN = 0.5


def telecharger(url, dossier, nom):
    chemin = os.path.join(dossier, nom)
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with open(chemin, "wb") as f:
        f.write(r.content)
    return chemin


def colonne(df, *motifs, exclure="lib"):
    for motif in motifs:
        for c in df.columns:
            if motif in c and exclure not in c:
                return c
    return None


def lire_oll(chemin_zip):
    """Zone → loyer médian, et zonage IRIS/commune → zone, d'une archive d'observatoire."""
    z = zipfile.ZipFile(chemin_zip)   # lève BadZipFile si l'archive est corrompue
    noms = z.namelist()
    base = next(n for n in noms if n.startswith("Base_OP") and n.endswith(".csv"))
    zonage = next((n for n in noms if "Zonage" in n and n.endswith(".csv")), None)
    b = pd.read_csv(io.BytesIO(z.read(base)), sep=";", encoding="latin1", dtype=str)
    tot = b[b.Zone_calcul.fillna("").str.match(r"^L\d{4}\.\d+\.\d+$") & b[DIMENSIONS].isna().all(axis=1)]
    zones = pd.DataFrame({
        "observatoire": tot.agglomeration,
        "annee": tot.Data_year,
        "zone": tot.Zone_calcul.str.split(".").str[-1].astype(int),
        "loyer_median": pd.to_numeric(tot.loyer_median.str.replace(",", "."), errors="coerce"),
        "nb_obs": pd.to_numeric(tot.nombre_observations, errors="coerce"),
    }).dropna(subset=["loyer_median"])
    if zonage is None:
        return zones, pd.DataFrame()
    zz = pd.read_csv(io.BytesIO(z.read(zonage)), sep=";", encoding="latin1", dtype=str)
    zz.columns = [c.strip().lstrip("﻿").lower() for c in zz.columns]
    c_com = colonne(zz, "insee") or "commune"
    c_iris = colonne(zz, "iris")
    zz = zz[pd.to_numeric(zz["zone"], errors="coerce").notna()]
    communes = zz[c_com].str.strip().str.zfill(5)
    iris = zz[c_iris].str.strip() if c_iris else pd.Series(None, index=zz.index, dtype=str)
    # Certains observatoires ne donnent que les 4 derniers chiffres de l'IRIS (ex. « 1101 »)
    courts = iris.str.len() <= 4
    iris = iris.where(~courts, communes + iris.str.zfill(4)).str.zfill(9)
    lien = pd.DataFrame({
        "observatoire": zones.observatoire.iloc[0] if len(zones) else None,
        "code_commune": communes, "iris": iris, "zone": zz["zone"].astype(int),
    })
    return zones, lien


def preparer_oll(dossier):
    ressources = requests.get(API_OLL, timeout=60).json()["resources"]
    editions = {}
    for r in ressources:
        m = re.search(r"/(\d{4})/Base_OP_\d{4}_(L\d{4})\.zip$", r["url"])
        if m:
            editions.setdefault(m.group(2), []).append((int(m.group(1)), r["url"]))
    toutes_zones, tous_liens = [], []
    for code, liste in sorted(editions.items()):
        for annee, url in sorted(liste, reverse=True):   # édition la plus récente lisible
            try:
                zones, lien = lire_oll(telecharger(url, dossier, f"{code}_{annee}.zip"))
            except (zipfile.BadZipFile, requests.RequestException, StopIteration) as e:
                print(f"  {code} {annee} illisible ({type(e).__name__}), édition précédente")
                continue
            toutes_zones.append(zones)
            tous_liens.append(lien)
            print(f"  {code} {annee} : {len(zones)} zones")
            break
    pd.concat(toutes_zones).to_csv("loyers_oll_zones.csv", index=False)
    pd.concat(tous_liens).to_csv("loyers_oll_zonage.csv", index=False)


def preparer_encadrement(dossier):
    p = pd.read_csv(telecharger(URL_PARIS, dossier, "paris.csv"), sep=";",
                    usecols=["Année", "Numéro INSEE du quartier", "Type de location", "Loyers de référence"])
    p = p[(p["Année"] == p["Année"].max()) & (p["Type de location"] == "non meublé")]
    paris = (p.groupby("Numéro INSEE du quartier")["Loyers de référence"].mean().reset_index()
              .rename(columns={"Numéro INSEE du quartier": "cle", "Loyers de référence": "loyer_ref"})
              .assign(source="encadrement Paris", annee=int(p["Année"].max())))

    lyon = pd.read_csv(telecharger(URL_LYON, dossier, "lyon.csv"), usecols=["codeiris", "valeurs"])
    def moyenne_non_meuble(valeurs):
        v = json.loads(valeurs)
        refs = [e["non meuble"]["loyer_reference"] for pieces in v.values() for e in pieces.values()]
        return sum(refs) / len(refs)
    lyon = pd.DataFrame({"cle": lyon.codeiris.astype(str).str.zfill(9),
                         "loyer_ref": lyon.valeurs.map(moyenne_non_meuble),
                         "source": "encadrement Lyon", "annee": 2024})
    pd.concat([paris, lyon]).round({"loyer_ref": 2}).to_csv("loyers_encadrement.csv", index=False)


def loyers_iris(quartiers):
    """Loyer de chaque IRIS des grandes villes, selon la meilleure source disponible."""
    enc = pd.read_csv("loyers_encadrement.csv", dtype={"cle": str})
    zones = pd.read_csv("loyers_oll_zones.csv")
    zonage = pd.read_csv("loyers_oll_zonage.csv", dtype={"code_commune": str, "iris": str})
    oll = zonage.merge(zones[["observatoire", "zone", "loyer_median"]], on=["observatoire", "zone"])
    # Observatoires imbriqués (ex. agglomération parisienne / hors Paris) : le plus finement zoné
    finesse = zones.groupby("observatoire").zone.nunique().rename("finesse")
    oll = oll.merge(finesse, on="observatoire").sort_values("finesse", ascending=False)
    par_iris = oll.dropna(subset=["iris"]).drop_duplicates("iris").set_index("iris")
    par_commune = oll[oll.iris.isna()].drop_duplicates("code_commune").set_index("code_commune")

    paris = enc[enc.source == "encadrement Paris"].set_index("cle").loyer_ref
    lyon = enc[enc.source == "encadrement Lyon"].set_index("cle").loyer_ref
    loyer, source = [], []
    for r in quartiers.itertuples():
        if r.code_commune == "75056" and str(r.code_quartier) in paris.index:
            loyer.append(paris[str(r.code_quartier)]); source.append("encadrement Paris")
        elif r.iris in lyon.index:
            loyer.append(lyon[r.iris]); source.append("encadrement Lyon")
        elif r.iris in par_iris.index:
            loyer.append(par_iris.loyer_median[r.iris]); source.append("OLL " + par_iris.observatoire[r.iris])
        elif r.iris[:5] in par_commune.index:   # zone définie à la commune (ou à l'arrondissement)
            c = r.iris[:5]
            loyer.append(par_commune.loyer_median[c]); source.append("OLL " + par_commune.observatoire[c])
        else:
            loyer.append(None); source.append(None)
    return quartiers.assign(loyer=loyer, source=source)


def main():
    if "--telecharger" in sys.argv or not os.path.exists("loyers_oll_zones.csv"):
        with tempfile.TemporaryDirectory() as dossier:   # archives brutes jamais conservées
            print("Observatoires locaux des loyers...")
            preparer_oll(dossier)
            print("Encadrement des loyers Paris et Lyon...")
            preparer_encadrement(dossier)

    q = loyers_iris(pd.read_csv("quartiers_iris.csv", dtype=str))
    sortie = []
    for code, ville in q.groupby("code_commune"):
        couverture = ville.loyer.notna().mean()
        ref = ville.loyer.mean()
        variee = ville.loyer.nunique() > 1
        for quartier, grp in ville.groupby("quartier"):
            ok = couverture >= COUVERTURE_MIN and variee and grp.loyer.notna().any()
            sortie.append({"code_commune": code, "quartier": quartier,
                           "coef_loyer": round(grp.loyer.mean() / ref, 3) if ok else 1.0,
                           "source": grp.source.dropna().mode().iloc[0] if ok else "",
                           "couverture": round(couverture, 2)})
    sortie = pd.DataFrame(sortie)
    sortie.to_csv("loyers_quartiers.csv", index=False)
    villes = sortie.groupby("code_commune").agg(source=("source", "max"), mini=("coef_loyer", "min"),
                                                 maxi=("coef_loyer", "max"))
    print(villes.to_string())
    print(f"✅ {len(sortie)} quartiers, dont {(sortie.source != '').sum()} avec un écart de loyer")


if __name__ == "__main__":
    main()
