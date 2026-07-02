"""Interactive strategy network graph — Textual TUI with netext."""

from __future__ import annotations

from cli.strategy.data import GRAPH_EDGES, GRAPH_NODES, GROUP_LABELS, NODE_DATA


def _build_nx_graph():
    """Build networkx graph with styled attributes."""
    import networkx as nx

    G = nx.Graph()
    for node in GRAPH_NODES:
        label = node["label"].replace("\n", " ")
        G.add_node(node["id"], label=label, group=node["group"])
    for edge in GRAPH_EDGES:
        G.add_edge(edge["from"], edge["to"], label=edge.get("label", ""))
    return G


def run_strategy_graph():
    """Entry point for the strategy graph TUI."""
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Footer, Header, RichLog, Static
    except ImportError:
        raise ImportError("textual is required: pip install textual")

    try:
        from netext import GraphView
        _has_netext = True
    except ImportError:
        _has_netext = False

    graph = _build_nx_graph()

    class StrategyGraphApp(App):
        """Interactive strategy network graph viewer."""

        CSS = """
        Screen {
            layout: horizontal;
        }
        #graph-container {
            width: 3fr;
            height: 100%;
        }
        #sidebar {
            width: 1fr;
            min-width: 30;
            max-width: 45;
            height: 100%;
            border-left: solid $accent;
            overflow-y: auto;
        }
        #sidebar-log {
            height: 100%;
        }
        """

        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("escape", "quit", "Quit"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal():
                if _has_netext:
                    yield GraphView(graph, id="graph-container")
                else:
                    yield Static(
                        "[bold]netext not installed[/bold]\n\n"
                        "pip install netext\n\n"
                        "Showing node list instead:\n\n" +
                        "\n".join(f"  {n['id']}: {n['label'].replace(chr(10), ' ')}" for n in GRAPH_NODES[:30]),
                        id="graph-container",
                    )
                with Vertical(id="sidebar"):
                    yield RichLog(id="sidebar-log", wrap=True, markup=True)
            yield Footer()

        def on_mount(self) -> None:
            sidebar = self.query_one("#sidebar-log", RichLog)
            sidebar.write("[bold cyan]STRATEGY GRAPH[/bold cyan]")
            sidebar.write(f"\n{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
            sidebar.write("\n[dim]Click a node to see details[/dim]")
            sidebar.write("\n[bold]GROUPS:[/bold]")
            for gid, label in GROUP_LABELS.items():
                sidebar.write(f"  {label}")

            sidebar.write("\n[bold]TOP CONNECTED:[/bold]")
            degrees = sorted(graph.degree(), key=lambda x: x[1], reverse=True)
            for nid, deg in degrees[:10]:
                label = nid.replace("_", " ").title()
                sidebar.write(f"  {label} ({deg})")

    app = StrategyGraphApp()
    app.run()
