
import geopandas as gpd
from shapely.geometry import LineString, Point
from shapely.ops import linemerge
from scipy.spatial import cKDTree
import networkx as nx
from pyproj import Transformer
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import numpy as np

# ---------- CONFIG ----------
layer_fp = r"C:\Users\pucci\Desktop\progetto GIS-20251125T133821Z-1-001\progetto GIS\irradiazioneMedia_Autunno_Mattina.gpkg"
target_crs = "EPSG:25833"  
print("Caricamento layer...")
layer = gpd.read_file(layer_fp)
print("Layer caricato:", layer.shape)

# Normalizza costo_Ombra per renderlo simile a costo_Sole
layer["costo_Ombra"] = layer["costo_Ombra"] * 10000
print("Valori normalizzati costo_Ombra:", layer["costo_Ombra"].describe())
print("Valori costo_Sole:", layer["costo_Sole"].describe())

layer = layer.to_crs(target_crs)

# ---------- Converti poligoni in linee ----------
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
}, crs=target_crs)

lines_gdf = lines_gdf.explode(index_parts=False).reset_index(drop=True)
print("Linee create:", len(lines_gdf))
print(lines_gdf.geometry.length.describe())

# ---------- Costruzione grafo ----------
G = nx.DiGraph()
for _, row in lines_gdf.iterrows():
    coords = list(row.geometry.coords)
    for a, b in zip(coords[:-1], coords[1:]):
        u = (round(a[0],3), round(a[1],3))
        v = (round(b[0],3), round(b[1],3))
        length = Point(u).distance(Point(v))
        G.add_edge(u, v, length=length, costo_sole=row["costo_Sole"], costo_ombra=row["costo_Ombra"], geometry=LineString([u,v]))
        G.add_edge(v, u, length=length, costo_sole=row["costo_Sole"], costo_ombra=row["costo_Ombra"], geometry=LineString([v,u]))

nodes = list(G.nodes())
print("Grafo costruito:", G.number_of_nodes(), "nodi,", G.number_of_edges(), "archi")

# KDTree dei nodi
tree = cKDTree(nodes)
transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)

# ---------- Funzione helper: aggancio al segmento più vicino ----------
def snap_to_graph(pt):
    # pt in CRS target
    min_dist = np.inf
    closest_point = None
    closest_edge = None
    for u,v,data in G.edges(data=True):
        line = data['geometry']
        proj_pt = line.interpolate(line.project(Point(pt)))
        dist = Point(pt).distance(proj_pt)
        if dist < min_dist:
            min_dist = dist
            closest_point = (proj_pt.x, proj_pt.y)
            closest_edge = (u,v)
    return closest_point, closest_edge

# ---------- Calcolo percorso ----------
def compute_path(start_pt, end_pt, weight):
    # Trasforma coordinate cliccate in CRS target
    sx, sy = transformer.transform(start_pt[0], start_pt[1])
    ex, ey = transformer.transform(end_pt[0], end_pt[1])
    start_node = (sx, sy)
    end_node = (ex, ey)

    # Aggancio start e end al segmento più vicino
    start_snap, _ = snap_to_graph(start_node)
    end_snap, _ = snap_to_graph(end_node)

    # Aggiungi nodi temporanei
    G.add_node(start_snap)
    G.add_node(end_snap)

    # Collega start_snap ai due estremi del segmento più vicino
    _, start_edge = snap_to_graph(start_snap)
    if start_edge:
        u,v = start_edge
        G.add_edge(start_snap, u, length=Point(start_snap).distance(Point(u)), costo_sole=0, costo_ombra=0, geometry=LineString([start_snap,u]))
        G.add_edge(start_snap, v, length=Point(start_snap).distance(Point(v)), costo_sole=0, costo_ombra=0, geometry=LineString([start_snap,v]))
        G.add_edge(u, start_snap, length=Point(start_snap).distance(Point(u)), costo_sole=0, costo_ombra=0, geometry=LineString([u,start_snap]))
        G.add_edge(v, start_snap, length=Point(start_snap).distance(Point(v)), costo_sole=0, costo_ombra=0, geometry=LineString([v,start_snap]))

    # Collega end_snap ai due estremi del segmento più vicino
    _, end_edge = snap_to_graph(end_snap)
    if end_edge:
        u,v = end_edge
        G.add_edge(end_snap, u, length=Point(end_snap).distance(Point(u)), costo_sole=0, costo_ombra=0, geometry=LineString([end_snap,u]))
        G.add_edge(end_snap, v, length=Point(end_snap).distance(Point(v)), costo_sole=0, costo_ombra=0, geometry=LineString([end_snap,v]))
        G.add_edge(u, end_snap, length=Point(end_snap).distance(Point(u)), costo_sole=0, costo_ombra=0, geometry=LineString([u,end_snap]))
        G.add_edge(v, end_snap, length=Point(end_snap).distance(Point(v)), costo_sole=0, costo_ombra=0, geometry=LineString([v,end_snap]))

    # Calcolo percorso
    try:
        path_nodes = nx.shortest_path(G, source=start_snap, target=end_snap, weight=weight)
        print(f"Percorso trovato con {weight}: {len(path_nodes)} nodi")
        segs = [G[u][v]['geometry'] for u,v in zip(path_nodes[:-1], path_nodes[1:])]
        merged = linemerge(segs)
        gdf = gpd.GeoDataFrame(geometry=[merged], crs=target_crs).to_crs("EPSG:4326")
        # Rimuovi nodi temporanei
        G.remove_node(start_snap)
        G.remove_node(end_snap)
        return json.loads(gdf.to_json())
    except nx.NetworkXNoPath:
        print(f"⚠️ Nessun percorso trovato con {weight}")
        G.remove_node(start_snap)
        G.remove_node(end_snap)
        return None

# ---------- Flask ----------
app = Flask(__name__)
CORS(app)

@app.route("/percorsi", methods=["POST"])
def percorsi():
    data = request.get_json()
    start = (data["start_lon"], data["start_lat"])
    end = (data["end_lon"], data["end_lat"])
    percorso_sole = compute_path(start, end, "costo_sole")
    percorso_ombra = compute_path(start, end, "costo_ombra")
    return jsonify({"sole": percorso_sole, "ombra": percorso_ombra})

if __name__ == "__main__":
    print("Server Flask avviato sulla porta 8002...")
    app.run(host="127.0.0.1", port=8002, debug=True)
