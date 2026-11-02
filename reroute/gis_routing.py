"""GIS routing helpers for ReRoute. Coordinates are (latitude, longitude)."""

import folium
import networkx as nx
import osmnx as ox
from folium.plugins import Fullscreen, MousePosition


def load_road_network(start, end):
    """Download a drivable OpenStreetMap network covering both endpoints."""
    north = max(start[0], end[0]) + 0.025
    south = min(start[0], end[0]) - 0.025
    east = max(start[1], end[1]) + 0.025
    west = min(start[1], end[1]) - 0.025
    bbox = (west, south, east, north)  # OSMnx 2.x order

    ox.settings.requests_timeout = 180
    ox.settings.use_cache = True

    graph = ox.graph.graph_from_bbox(
        bbox,
        network_type="drive",
        simplify=True,
    )

    if graph.number_of_nodes() == 0:
        raise ValueError("OpenStreetMap returned an empty road network.")

    graph = ox.routing.add_edge_speeds(graph)
    graph = ox.routing.add_edge_travel_times(graph)
    return graph


def nearest_node(graph, location):
    """Return the graph node nearest to a (latitude, longitude) point."""
    lat, lon = location
    return ox.distance.nearest_nodes(graph, X=lon, Y=lat)


def calculate_route(graph, start, end, objective="length"):
    """Calculate the original route using distance or travel time."""
    source = nearest_node(graph, start)
    target = nearest_node(graph, end)
    return nx.shortest_path(
        graph,
        source,
        target,
        weight=objective,
        method="dijkstra",
    )


def calculate_reroute(graph, original_route, segment_index, objective="length"):
    """Temporarily remove one road segment and find an alternative route."""
    if not 0 <= segment_index < len(original_route) - 1:
        raise IndexError("Selected road segment is outside the route.")

    u = original_route[segment_index]
    v = original_route[segment_index + 1]
    modified = graph.copy()

    # OSMnx road graphs are commonly MultiDiGraphs. Remove all parallel
    # directed edges in both directions so the selected segment is blocked.
    for a, b in ((u, v), (v, u)):
        if modified.has_edge(a, b):
            for key in list(modified[a][b].keys()):
                modified.remove_edge(a, b, key)

    alternative = nx.shortest_path(
        modified,
        source=original_route[0],
        target=original_route[-1],
        weight=objective,
        method="dijkstra",
    )
    return alternative, (u, v)


def _edge(graph, u, v, weight):
    """Select the parallel edge with the lowest requested weight."""
    edges = graph.get_edge_data(u, v)
    if not edges:
        raise ValueError(f"Missing road edge: {u} -> {v}")
    return min(
        edges.values(),
        key=lambda edge: edge.get(weight, float("inf")),
    )


def route_coordinates(graph, route):
    """Convert a sequence of graph nodes to a detailed [(lat, lon), ...] line."""
    coords = []

    for u, v in zip(route[:-1], route[1:]):
        edge = _edge(graph, u, v, "length")

        if "geometry" in edge:
            points = list(edge["geometry"].coords)
            ux, uy = graph.nodes[u]["x"], graph.nodes[u]["y"]

            # Ensure the edge geometry follows the route direction u -> v.
            d0 = (points[0][0] - ux) ** 2 + (points[0][1] - uy) ** 2
            d1 = (points[-1][0] - ux) ** 2 + (points[-1][1] - uy) ** 2
            if d1 < d0:
                points.reverse()
        else:
            points = [
                (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                (graph.nodes[v]["x"], graph.nodes[v]["y"]),
            ]

        for lon, lat in points:
            point = (lat, lon)
            if not coords or coords[-1] != point:
                coords.append(point)

    # A one-node route still needs a point for map fitting.
    if len(route) == 1:
        node = graph.nodes[route[0]]
        coords.append((node["y"], node["x"]))

    return coords


def route_statistics(graph, route):
    """Return route distance in km and estimated travel time in minutes."""
    distance_m = 0.0
    seconds = 0.0

    for u, v in zip(route[:-1], route[1:]):
        edge = _edge(graph, u, v, "length")
        distance_m += float(edge.get("length", 0))
        seconds += float(edge.get("travel_time", 0))

    return {
        "distance_km": round(distance_m / 1000, 2),
        "time_min": round(seconds / 60, 1),
    }


def create_route_map(
    graph,
    start,
    end,
    original,
    alternative=None,
    blocked=None,
):
    """Create a Folium map with original, blocked and alternative routes."""
    # These coordinate lists were missing in the earlier version and caused
    # NameError: original_coords is not defined.
    original_coords = route_coordinates(graph, original)

    blocked_coords = []
    if blocked is not None:
        blocked_u, blocked_v = blocked
        blocked_coords = route_coordinates(graph, [blocked_u, blocked_v])

    alternative_coords = []
    if alternative:
        alternative_coords = route_coordinates(graph, alternative)

    # Fit the map to all displayed route geometry and both endpoints.
    all_coords = list(original_coords)
    all_coords.extend(blocked_coords)
    all_coords.extend(alternative_coords)
    all_coords.extend([start, end])

    center = (
        (start[0] + end[0]) / 2,
        (start[1] + end[1]) / 2,
    )

    # Use the standard OpenStreetMap tile layer. Do not add a second copy
    # of the same tile layer; that can cause confusing layer controls.
    m = folium.Map(
        location=center,
        zoom_start=12,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Original route: blue.
    original_layer = folium.FeatureGroup(
        name="Original route (blue)",
        show=True,
    )
    if original_coords:
        folium.PolyLine(
            original_coords,
            color="#155EEF",
            weight=8,
            opacity=0.95,
            tooltip="Original delivery route",
            popup="Original route before disruption",
        ).add_to(original_layer)
    original_layer.add_to(m)

    # Disrupted road: red dashed line with a visible midpoint marker.
    if blocked_coords:
        blocked_layer = folium.FeatureGroup(
            name="Disrupted road (red)",
            show=True,
        )
        folium.PolyLine(
            blocked_coords,
            color="#7F1D1D",
            weight=15,
            opacity=1,
        ).add_to(blocked_layer)
        folium.PolyLine(
            blocked_coords,
            color="#EF4444",
            weight=10,
            opacity=1,
            dash_array="8, 7",
            tooltip="Blocked / disrupted road",
            popup=(
                "Simulated disruption: this road segment is excluded "
                "from rerouting."
            ),
        ).add_to(blocked_layer)

        midpoint = blocked_coords[len(blocked_coords) // 2]
        folium.CircleMarker(
            midpoint,
            radius=8,
            color="#7F1D1D",
            weight=2,
            fill=True,
            fill_color="#EF4444",
            fill_opacity=1,
            tooltip="Disruption location",
        ).add_to(blocked_layer)
        blocked_layer.add_to(m)

    # Alternative route: green.
    if alternative_coords:
        alternative_layer = folium.FeatureGroup(
            name="Alternative route (green)",
            show=True,
        )
        folium.PolyLine(
            alternative_coords,
            color="#047857",
            weight=10,
            opacity=0.35,
        ).add_to(alternative_layer)
        folium.PolyLine(
            alternative_coords,
            color="#16A34A",
            weight=7,
            opacity=1,
            tooltip="New alternative delivery route",
            popup="Automatically calculated route avoiding the blocked segment",
        ).add_to(alternative_layer)
        alternative_layer.add_to(m)

    # Endpoint markers.
    folium.Marker(
        start,
        tooltip="Bidadi plant",
        popup="Kaveri EV Motors – Bidadi Plant",
        icon=folium.Icon(color="blue", icon="industry", prefix="fa"),
    ).add_to(m)

    folium.Marker(
        end,
        tooltip="Destination supplier",
        popup="Selected supplier",
        icon=folium.Icon(color="red", icon="industry", prefix="fa"),
    ).add_to(m)

    # Fixed map legend.
    legend = """
    <div style="position: fixed; bottom: 28px; left: 28px; z-index: 9999;
      background: white; padding: 12px 15px; border: 1px solid #cbd5e1;
      border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,.18);
      font: 13px Arial; color: #1e293b; min-width: 190px;">
      <b style="display:block;margin-bottom:8px">ReRoute · Route legend</b>
      <div style="margin:5px 0"><span style="display:inline-block;width:25px;border-top:5px solid #155EEF;margin-right:8px"></span>Original route</div>
      <div style="margin:5px 0"><span style="display:inline-block;width:25px;border-top:5px dashed #EF4444;margin-right:8px"></span>Disrupted road</div>
      <div style="margin:5px 0"><span style="display:inline-block;width:25px;border-top:5px solid #16A34A;margin-right:8px"></span>Alternative route</div>
      <div style="margin:5px 0">🔵 Plant &nbsp; 🔴 Supplier</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    Fullscreen(
        position="topright",
        title="Full screen",
        title_cancel="Exit full screen",
    ).add_to(m)

    MousePosition(
        position="bottomright",
        separator=" | ",
        prefix="Lat/Lon:",
        num_digits=5,
    ).add_to(m)

    folium.LayerControl(
        collapsed=False,
        position="topright",
    ).add_to(m)

    if all_coords:
        m.fit_bounds(all_coords, padding=(45, 45), max_zoom=14)
    else:
        m.fit_bounds([start, end], padding=(45, 45), max_zoom=14)

    return m
