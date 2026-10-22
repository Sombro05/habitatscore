"""
Fond de carte « Explorer le marché » : terres autour de la France (France incluse,
dessinée sous les communes pour que leurs couleurs semi-transparentes restent fidèles).

Source : Natural Earth, ne_50m_admin_0_countries.geojson (domaine public)
https://github.com/nvkelso/natural-earth-vector/tree/master/geojson

Usage : python 14_prep_pays_voisins.py chemin/vers/ne_50m_admin_0_countries.geojson
Sortie : geojson_cache/pays_voisins.json (contours découpés et simplifiés)
"""
import json
import sys
from shapely.geometry import box, mapping, shape

# Zone utile autour de la France (lon min, lat min, lon max, lat max)
ZONE = box(-30, 25, 45, 65)
TOLERANCE = 0.02  # simplification des contours, en degrés (~2 km)

with open(sys.argv[1], encoding="utf-8") as f:
    pays = json.load(f)

features = []
for feat in pays["features"]:
    geom = shape(feat["geometry"])
    if not geom.intersects(ZONE):
        continue
    geom = geom.intersection(ZONE).simplify(TOLERANCE, preserve_topology=True)
    if geom.is_empty:
        continue
    features.append({
        "type": "Feature",
        "properties": {"nom": feat["properties"].get("NAME_FR") or feat["properties"]["NAME"]},
        "geometry": mapping(geom),
    })

sortie = {"type": "FeatureCollection", "features": features}
texte = json.dumps(sortie, separators=(",", ":"))
# Arrondi des coordonnées à 3 décimales (~100 m) pour réduire la taille du fichier
sortie = json.loads(texte, parse_float=lambda x: round(float(x), 3))

with open("geojson_cache/pays_voisins.json", "w", encoding="utf-8") as f:
    json.dump(sortie, f, separators=(",", ":"), ensure_ascii=False)

print(f"✅ {len(features)} pays : {', '.join(sorted(f['properties']['nom'] for f in features))}")
