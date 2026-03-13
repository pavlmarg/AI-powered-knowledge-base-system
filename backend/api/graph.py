"""
api/graph.py
------------
Graph visualization endpoints — backend/developer tooling only.
NOT exposed to end users via the frontend.

Two endpoints:

  POST /api/graph/visualize
  ─────────────────────────
  Accepts a knowledge_graph JSON directly and returns interactive HTML.

  GET /api/graph/view/{session_id}
  ─────────────────────────────────
  Opens the latest knowledge graph for a session directly in the browser.
  The judge/reviewer just needs the session_id from the query response.

  Usage for reviewers:
    1. Call POST /api/query  →  note the session_id in the response
    2. Open in browser:  http://localhost:8080/api/graph/view/<session_id>
    3. Interactive graph renders immediately — no extra steps needed
    4. Refresh after a new query to see the updated graph

Node colors by type:
  Company   → #4A90D9  (blue)
  Filing    → #F5A623  (orange)
  Sentiment → #7ED321  (green)
  Event     → #BD10E0  (purple)
  Price     → #E74C3C  (red)
  default   → #95A5A6  (grey)
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from pyvis.network import Network

router = APIRouter()


# ── In-memory graph store ─────────────────────────────────────────────────────
# { session_id: {"nodes": [...], "edges": [...], "title": "..."} }
# Populated automatically by store_graph() after every /api/query call.
_graph_store: Dict[str, dict] = {}


# ── Models ────────────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id    : str
    label : str
    type  : str
    detail: str


class GraphEdge(BaseModel):
    id    : str
    source: str
    target: str
    label : str


class GraphRequest(BaseModel):
    nodes      : List[GraphNode]
    edges      : List[GraphEdge]
    title      : Optional[str] = "Knowledge Graph"
    session_id : Optional[str] = None


# ── Styling ───────────────────────────────────────────────────────────────────

NODE_COLORS = {
    "Company"  : {"color": "#4A90D9", "shape": "ellipse",  "size": 35},
    "Filing"   : {"color": "#F5A623", "shape": "box",       "size": 25},
    "Sentiment": {"color": "#7ED321", "shape": "diamond",   "size": 25},
    "Event"    : {"color": "#BD10E0", "shape": "star",      "size": 25},
    "Price"    : {"color": "#E74C3C", "shape": "triangle",  "size": 25},
}
DEFAULT_STYLE     = {"color": "#95A5A6", "shape": "dot", "size": 20}

EDGE_COLORS = {
    "CONTRADICTS"  : "#E74C3C",
    "ALIGNS"       : "#27AE60",
    "ALIGNS_WITH"  : "#27AE60",
    "AMPLIFIES"    : "#F39C12",
    "REPORTS"      : "#3498DB",
    "DISCLOSES"    : "#3498DB",
    "FILES"        : "#3498DB",
    "HAS_PRICE"    : "#E74C3C",
    "HAS_SENTIMENT": "#7ED321",
    "MENTIONED_IN" : "#95A5A6",
    "MENTIONED_ON" : "#95A5A6",
    "REFLECTED_IN" : "#F39C12",
}
DEFAULT_EDGE_COLOR = "#BDC3C7"


# ── Internal: build HTML ──────────────────────────────────────────────────────

def _build_graph_html(nodes: list, edges: list, title: str) -> str:
    net = Network(
        height     = "100vh",
        width      = "100%",
        bgcolor    = "#1a1a2e",
        font_color = "#ffffff",
        directed   = True,
        notebook   = False,
    )

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -8000,
          "centralGravity": 0.3,
          "springLength": 180,
          "springConstant": 0.04,
          "damping": 0.09
        },
        "stabilization": { "iterations": 150 }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "navigationButtons": true,
        "keyboard": true
      },
      "edges": {
        "smooth": { "type": "curvedCW", "roundness": 0.2 },
        "arrows": { "to": { "enabled": true, "scaleFactor": 0.8 } },
        "font":  { "size": 11, "color": "#cccccc", "strokeWidth": 0 }
      },
      "nodes": {
        "font": { "size": 13, "color": "#ffffff" },
        "borderWidth": 2,
        "shadow": true
      }
    }
    """)

    for node in nodes:
        node_id     = node.get("id","")     if isinstance(node, dict) else node.id
        node_label  = node.get("label","")  if isinstance(node, dict) else node.label
        node_type   = node.get("type","")   if isinstance(node, dict) else node.type
        node_detail = node.get("detail","") if isinstance(node, dict) else node.detail

        style = NODE_COLORS.get(node_type, DEFAULT_STYLE)
        net.add_node(
            node_id,
            label = node_label,
            title = f"<b>{node_label}</b><br>{node_detail}",
            color = style["color"],
            shape = style["shape"],
            size  = style["size"],
        )

    for edge in edges:
        src   = edge.get("source","") if isinstance(edge, dict) else edge.source
        tgt   = edge.get("target","") if isinstance(edge, dict) else edge.target
        lbl   = edge.get("label", "") if isinstance(edge, dict) else edge.label
        color = EDGE_COLORS.get(lbl, DEFAULT_EDGE_COLOR)
        net.add_edge(src, tgt, label=lbl, color=color, title=lbl)

    html = net.generate_html()

    title_banner = f"""
    <div style="
        position:fixed; top:0; left:0; right:0;
        background:rgba(26,26,46,0.95); color:#4A90D9;
        font-family:'Segoe UI',Arial,sans-serif;
        font-size:16px; font-weight:bold;
        padding:10px 20px; z-index:1000;
        border-bottom:1px solid #4A90D9; letter-spacing:1px;">
        🧠 {title} &nbsp;|&nbsp;
        <span style="color:#aaa;font-size:12px;font-weight:normal;">
            {len(nodes)} nodes &nbsp;·&nbsp; {len(edges)} edges
            &nbsp;·&nbsp; Drag · Scroll to zoom · Hover for details
        </span>
    </div>
    <div style="margin-top:50px;">
    """

    legend_html = """
    <div style="
        position:fixed; bottom:20px; left:20px;
        background:rgba(26,26,46,0.9); color:#ccc;
        font-family:'Segoe UI',Arial,sans-serif; font-size:12px;
        padding:12px 16px; border-radius:8px;
        border:1px solid #333; z-index:1000;">
        <div style="font-weight:bold;color:#4A90D9;margin-bottom:8px;">Node Types</div>
        <div>🔵 Company</div>
        <div>🟠 Filing</div>
        <div>🟢 Sentiment</div>
        <div>🟣 Event</div>
        <div>🔴 Price</div>
        <div style="font-weight:bold;color:#4A90D9;margin:8px 0;">Edge Colors</div>
        <div><span style="color:#E74C3C">■</span> CONTRADICTS</div>
        <div><span style="color:#27AE60">■</span> ALIGNS</div>
        <div><span style="color:#F39C12">■</span> AMPLIFIES</div>
        <div><span style="color:#3498DB">■</span> REPORTS / FILES</div>
        <div><span style="color:#95A5A6">■</span> MENTIONED</div>
    </div>
    """

    html = html.replace("<body>", f"<body>{title_banner}{legend_html}")
    return html


# ── Public helper: called by api/query.py ────────────────────────────────────

def store_graph(session_id: str, nodes: list, edges: list, title: str) -> None:
    """
    Store the latest knowledge graph for a session.
    Called automatically by /api/query after every successful synthesis.
    Makes the graph available via GET /api/graph/view/{session_id}.
    """
    _graph_store[session_id] = {"nodes": nodes, "edges": edges, "title": title}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/graph/visualize",
    response_class=HTMLResponse,
    summary="Render a knowledge graph as interactive HTML (manual)",
    tags=["Graph"],
)
async def visualize_graph(request: GraphRequest):
    """
    Manually render a knowledge_graph JSON as interactive HTML.
    Paste the knowledge_graph directly from a /api/query response.
    Optionally pass session_id to also store it for GET access.
    """
    nodes = [n.model_dump() for n in request.nodes]
    edges = [e.model_dump() for e in request.edges]
    title = request.title or "Knowledge Graph"

    if request.session_id:
        store_graph(request.session_id, nodes, edges, title)

    return HTMLResponse(content=_build_graph_html(nodes, edges, title))


@router.get(
    "/graph/view/{session_id}",
    response_class=HTMLResponse,
    summary="View the latest knowledge graph for a session in the browser",
    tags=["Graph"],
)
async def view_graph(session_id: str):
    """
    Open the latest knowledge graph for a session directly in the browser.

    Steps for reviewers:
      1. Run POST /api/query  →  copy session_id from response
      2. Open: http://localhost:8080/api/graph/view/<session_id>
      3. Graph renders immediately — refresh after new queries to update
    """
    graph = _graph_store.get(session_id)
    if not graph:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No graph found for session '{session_id}'. "
                "Run at least one /api/query with this session_id first."
            )
        )
    return HTMLResponse(
        content=_build_graph_html(graph["nodes"], graph["edges"], graph["title"])
    )


@router.get(
    "/graph/sessions",
    summary="List all session IDs that have a stored graph",
    tags=["Graph"],
)
async def list_graph_sessions():
    """Returns all session IDs that have a graph stored. For debugging."""
    return {"count": len(_graph_store), "sessions": list(_graph_store.keys())}