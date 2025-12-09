import geopandas as gpd
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, snap
from scipy.spatial import cKDTree
import networkx as nx
from pyproj import Transformer
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import numpy as np
import os

# ----------------------------------------------------
# FUNZIONE PER CARICARE IL LAYER IN BASE A SCELTA UTENTE
# ----------------------------------------------------
def load_layer(stagione, fascia):
    base_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "irradiazione")
)
    filename = f"irradiazioneMedia_{stagione.capitalize()}_{fascia.capitalize()}.gpkg"
    fp = os.path.join(base_dir, filename)

    print(">>> Carico:", fp)

    layer = gpd.read_file(fp)

    # Normalizzazione come prima
    layer["costo_Ombra"] = layer["costo_Ombra"] * 5
    layer = layer.to_crs("EPSG:25833")

    return layer


# ----------------------------------------------------
# FUNZIONE PER COSTRUIRE IL GRAFO DA UN LAYER
# ----------------------------------------------------
def build_graph(layer):
    lines, costo_sole_list, costo_ombra_list = [], [], []

    for idx, row in layer.iterrows():
        geom = row.geometry
        costo_sole = row["costo_Sole"]
        costo_ombra = row["costo_Ombra"]
        boundary = geom.boundary
        if boundary.is_empty:
            continue
        if boundary.geom_type == 'MultiLineString':
            for l in boundary.geoms:
                lines.append(l)
                costo_sole_list.append(costo_sole)
                costo_ombra_list.append(costo_ombra)
        elif boundary.geom_type == 'LineString':
            lines.append(boundary)
            costo_sole_list.append(costo_sole)
            costo_ombra_list.append(costo_ombra)

    lines_gdf = gpd.GeoDataFrame({
        'costo_Sole': costo_sole_list,
        'costo_Ombra': costo_ombra_list,
        'geometry': lines
    }, crs="EPSG:25833")

    lines_gdf = lines_gdf.explode(index_parts=False).reset_index(drop=True)

    # Snap
    tolerance = 0.5
    union = lines_gdf.unary_union
    snapped = [snap(geom, union, tolerance) for geom in lines_gdf.geometry]
    lines_gdf["geometry"] = snapped

    # Costruzione grafo
    G = nx.DiGraph()
    for _, row in lines_gdf.iterrows():
        coords = list(row.geometry.coords)
        for a, b in zip(coords[:-1], coords[1:]):
            u = (a[0], a[1])
            v = (b[0], b[1])
            length = Point(u).distance(Point(v))

            G.add_edge(u, v, length=length,
                       costo_sole=row["costo_Sole"],
                       costo_ombra=row["costo_Ombra"],
                       geometry=LineString([u, v]))

            G.add_edge(v, u, length=length,
                       costo_sole=row["costo_Sole"],
                       costo_ombra=row["costo_Ombra"],
                       geometry=LineString([v, u]))

    return G


# ----------------------------------------------------
# CREIAMO IL SERVER
# ----------------------------------------------------
app = Flask(__name__)
CORS(app)

transformer = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)


def snap_to_graph(G, pt):
    min_dist = np.inf
    closest_point = None
    closest_edge = None

    for u, v, data in G.edges(data=True):
        line = data['geometry']
        proj_pt = line.interpolate(line.project(Point(pt)))
        dist = Point(pt).distance(proj_pt)
        if dist < min_dist:
            min_dist = dist
            closest_point = (proj_pt.x, proj_pt.y)
            closest_edge = (u, v)

    return closest_point, closest_edge


def compute_path(G, start_pt, end_pt, weight):
    sx, sy = transformer.transform(start_pt[0], start_pt[1])
    ex, ey = transformer.transform(end_pt[0], end_pt[1])

    start_snap, _ = snap_to_graph(G, (sx, sy))
    end_snap, _ = snap_to_graph(G, (ex, ey))

    G.add_node(start_snap)
    G.add_node(end_snap)

    _, start_edge = snap_to_graph(G, start_snap)
    if start_edge:
        u, v = start_edge
        G.add_edge(start_snap, u, length=Point(start_snap).distance(Point(u)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([start_snap, u]))
        G.add_edge(start_snap, v, length=Point(start_snap).distance(Point(v)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([start_snap, v]))
        G.add_edge(u, start_snap, length=Point(start_snap).distance(Point(u)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([u, start_snap]))
        G.add_edge(v, start_snap, length=Point(start_snap).distance(Point(v)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([v, start_snap]))

    _, end_edge = snap_to_graph(G, end_snap)
    if end_edge:
        u, v = end_edge
        G.add_edge(end_snap, u, length=Point(end_snap).distance(Point(u)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([end_snap, u]))
        G.add_edge(end_snap, v, length=Point(end_snap).distance(Point(v)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([end_snap, v]))
        G.add_edge(u, end_snap, length=Point(end_snap).distance(Point(u)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([u, end_snap]))
        G.add_edge(v, end_snap, length=Point(end_snap).distance(Point(v)),
                   costo_sole=0, costo_ombra=0, geometry=LineString([v, end_snap]))

    try:
        nodes = nx.shortest_path(G, start_snap, end_snap, weight=weight)
        segs = [G[u][v]["geometry"] for u, v in zip(nodes[:-1], nodes[1:])]
        merged = linemerge(segs)
        gdf = gpd.GeoDataFrame(geometry=[merged], crs="EPSG:25833").to_crs("EPSG:4326")
        G.remove_node(start_snap)
        G.remove_node(end_snap)
        return json.loads(gdf.to_json())

    except:
        G.remove_node(start_snap)
        G.remove_node(end_snap)
        return None


# ----------------------------------------------------
# ROUTE PRINCIPALE
# ----------------------------------------------------
@app.route("/percorsi", methods=["POST"])
def percorsi():
    data = request.get_json()
    stagione = data["stagione"]
    fascia = data["fascia"]

    layer = load_layer(stagione, fascia)
    G = build_graph(layer)

    start = (data["start_lon"], data["start_lat"])
    end = (data["end_lon"], data["end_lat"])

    percorso_sole = compute_path(G, start, end, "costo_sole")
    percorso_ombra = compute_path(G, start, end, "costo_ombra")

    return jsonify({"sole": percorso_sole, "ombra": percorso_ombra})


if __name__ == "__main__":
    print("Server Flask attivo sulla porta 8002")
    app.run(host="127.0.0.1", port=8002, debug=True)
