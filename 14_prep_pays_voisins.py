"""
Fond de carte « Explorer le marché » : terres autour de la France.
- France : union exacte des contours des communes (communes_small.geojson), dessinée sous
  les communes pour que leurs couleurs semi-transparentes restent fidèles et que le fond
  colle aux communes quand on zoome.
- Pays voisins : Natural Earth (contours simplifiés). Leurs frontières étant moins précises
  que celles des communes, chaque pays frontalier est étendu jusqu'à la France dans une bande
  de quelques kilomètres, puis découpé le long des communes : plus de trou à la frontière.

Source : Natural Earth, ne_50m_admin_0_countries.geojson (domaine public)
https://github.com/nvkelso/natural-earth-vector/tree/master/geojson

Usage : python 14_prep_pays_voisins.py chemin/vers/ne_50m_admin_0_countries.geojson
Sortie : geojson_cache/pays_voisins.json
"""
import json
import sys
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

# Zone utile autour de la France (lon min, lat min, lon max, lat max)
ZONE = box(-30, 25, 45, 65)
TOLERANCE = 0.005   # simplification des contours des pays voisins, en degrés (~500 m)
COMBLEMENT = 0.06   # largeur de la bande où les voisins sont étendus jusqu'à la France (~6 km)

def arrondir(coords, decimales):
    # Arrondit récursivement les coordonnées (réduit la taille du fichier)
    if isinstance(coords[0], (int, float)):
        return [round(c, decimales) for c in coords]
    return [arrondir(c, decimales) for c in coords]

# France = union des communes (mêmes contours que la carte)
with open("communes_small.geojson", encoding="utf-8") as f:
    communes = json.load(f)
france = unary_union([shape(c["geometry"]).buffer(0) for c in communes["features"] if c["geometry"]])
abords_france = france.buffer(COMBLEMENT)

with open(sys.argv[1], encoding="utf-8") as f:
    pays = json.load(f)

features = []
for feat in pays["features"]:
    if feat["properties"].get("ADM0_A3") == "FRA":
        continue  # France : contours des communes
    geom = shape(feat["geometry"]).buffer(0)
    if not geom.intersects(ZONE):
        continue
    if geom.intersects(abords_france):
        # Pays frontalier : comble l'écart avec la France, puis découpe le long des communes
        comblement = geom.buffer(COMBLEMENT).intersection(abords_france)
        geom = geom.union(comblement).difference(france)
    geom = geom.intersection(ZONE).simplify(TOLERANCE, preserve_topology=True)
    if geom.is_empty:
        continue
    g = mapping(geom)
    g["coordinates"] = arrondir(json.loads(json.dumps(g["coordinates"])), 4)
    features.append({
        "type": "Feature",
        "properties": {"nom": feat["properties"].get("NAME_FR") or feat["properties"]["NAME"]},
        "geometry": g,
    })

geom_france = mapping(france.simplify(0.0005, preserve_topology=True))
geom_france["coordinates"] = arrondir(json.loads(json.dumps(geom_france["coordinates"])), 4)
features.append({"type": "Feature", "properties": {"nom": "France", "france": True},
                 "geometry": geom_france})

with open("geojson_cache/pays_voisins.json", "w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection", "features": features}, f,
              separators=(",", ":"), ensure_ascii=False)

print(f"✅ {len(features)} terres : {', '.join(sorted(f['properties']['nom'] for f in features))}")
