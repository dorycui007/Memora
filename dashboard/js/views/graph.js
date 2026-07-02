/**
 * Graph View — vis.js force-directed knowledge graph with glassmorphic UI.
 * Ported from the original graph_viewer.html design.
 */
const GraphView = {
    network: null,
    initialized: false,
    nodesDataset: null,
    edgesDataset: null,
    rawNodes: [],
    rawEdges: [],
    nodeMap: {},
    adjMap: {},

    // Color map for all 17 node types
    TYPE_COLORS: {
        PERSON: '#f97316', EVENT: '#3b82f6', COMMITMENT: '#ef4444',
        DECISION: '#eab308', GOAL: '#10b981', FINANCIAL_ITEM: '#14b8a6',
        NOTE: '#64748b', IDEA: '#ec4899', PROJECT: '#a855f7',
        CONCEPT: '#8b5cf6', REFERENCE: '#06b6d4', INSIGHT: '#f59e0b',
        ORGANIZATION: '#6366f1', POSITION: '#8b5cf6', ELECTION: '#ec4899',
        COURSE: '#06b6d4', METRIC: '#10b981',
    },

    getColor(nodeType) {
        return this.TYPE_COLORS[nodeType] || '#64748b';
    },

    hexToRgba(hex, alpha) {
        const r = parseInt(hex.slice(1,3), 16);
        const g = parseInt(hex.slice(3,5), 16);
        const b = parseInt(hex.slice(5,7), 16);
        return `rgba(${r},${g},${b},${alpha})`;
    },

    buildGroup(color) {
        return {
            shape: 'box',
            color: {
                background: this.hexToRgba(color, 0.12),
                border: color,
                highlight: { background: this.hexToRgba(color, 0.25), border: color },
                hover: { background: this.hexToRgba(color, 0.2), border: color },
            },
            font: { color: '#e2e8f0', face: 'Inter, sans-serif', size: 13 },
            borderWidth: 2,
            shadow: { enabled: true, color: this.hexToRgba(color, 0.35), size: 18, x: 0, y: 0 },
            shapeProperties: { borderRadius: 8 },
            margin: { top: 10, bottom: 10, left: 14, right: 14 },
        };
    },

    async init() {
        if (this.initialized && this.network) return;

        const container = document.getElementById('view-graph');
        container.innerHTML = `
            <div class="graph-filters">
                <button class="filter-btn active" data-filter="all">All</button>
                <button class="filter-btn" data-filter="PERSON">People</button>
                <button class="filter-btn" data-filter="COMMITMENT">Commitments</button>
                <button class="filter-btn" data-filter="GOAL">Goals</button>
                <button class="filter-btn" data-filter="PROJECT">Projects</button>
                <button class="filter-btn" data-filter="ORGANIZATION">Organizations</button>
                <button class="filter-btn" data-filter="POSITION">Positions</button>
                <button class="filter-btn" data-filter="COURSE">Courses</button>
            </div>
            <div class="graph-container" id="graph-canvas"></div>
            <div class="graph-stats-badge" id="graph-stats">
                <h2>Memora &mdash; Knowledge Graph</h2>
                <p>Loading...</p>
            </div>
            <div class="help-hint">Click node for details &middot; Hover for info &middot; Scroll to zoom</div>
        `;

        container.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                container.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.applyFilter(btn.dataset.filter);
            });
        });

        await this.loadGraph();
        this.setupTooltip();
        this.setupModal();
        this.initialized = true;
    },

    async loadGraph() {
        try {
            const [graphData, stats] = await Promise.all([
                MemoraAPI.getSubgraph({ limit: 300 }),
                MemoraAPI.getGraphStats().catch(() => ({})),
            ]);

            this.rawNodes = graphData.nodes || [];
            this.rawEdges = graphData.edges || [];

            // Build lookup maps
            this.nodeMap = {};
            this.rawNodes.forEach(n => { this.nodeMap[n.id] = n; });

            this.adjMap = {};
            this.rawEdges.forEach(e => {
                if (!this.adjMap[e.from]) this.adjMap[e.from] = [];
                if (!this.adjMap[e.to]) this.adjMap[e.to] = [];
                this.adjMap[e.from].push({ id: e.to, type: e.edge_type, dir: 'outgoing' });
                this.adjMap[e.to].push({ id: e.from, type: e.edge_type, dir: 'incoming' });
            });

            // Update stats badge
            const nc = stats.node_count || this.rawNodes.length;
            const ec = stats.edge_count || this.rawEdges.length;
            const badge = document.getElementById('graph-stats');
            if (badge) {
                badge.querySelector('p').textContent = `${nc} nodes \u00b7 ${ec} edges`;
            }

            this.renderGraph();
        } catch (err) {
            document.getElementById('graph-canvas').innerHTML = '<div class="empty-state">Failed to load graph data</div>';
        }
    },

    renderGraph() {
        const canvas = document.getElementById('graph-canvas');
        if (!canvas) return;

        // Build vis.js groups from color map
        const groups = {};
        for (const [type, color] of Object.entries(this.TYPE_COLORS)) {
            groups[type] = this.buildGroup(color);
        }

        // Build vis.js nodes
        const visNodes = this.rawNodes.map(n => {
            const ntype = n.node_type || 'NOTE';
            return {
                id: n.id,
                label: n.label || n.title || 'Unknown',
                group: ntype,
                size: n.id === '00000000-0000-0000-0000-000000000001' ? 45 : 40,
                _data: n,
            };
        });

        // Build vis.js edges with type-colored styling
        const visEdges = this.rawEdges.map(e => {
            // Color edge by source node type
            const sourceNode = this.nodeMap[e.from];
            const color = sourceNode ? this.getColor(sourceNode.node_type) : '#64748b';
            return {
                from: e.from,
                to: e.to,
                arrows: 'to',
                width: Math.max(1, (e.weight || 0.5) * 2),
                color: {
                    color: this.hexToRgba(color, 0.4),
                    hover: color,
                    highlight: color,
                },
                _data: e,
            };
        });

        this.nodesDataset = new vis.DataSet(visNodes);
        this.edgesDataset = new vis.DataSet(visEdges);

        const options = {
            groups: groups,
            edges: {
                width: 1.5, hoverWidth: 3, selectionWidth: 2.5,
                smooth: { type: 'continuous', roundness: 0.25 },
                font: { size: 0 },
            },
            physics: {
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {
                    gravitationalConstant: -45,
                    centralGravity: 0.01,
                    springLength: 160,
                    springConstant: 0.04,
                    damping: 0.5,
                    avoidOverlap: 0.5,
                },
                stabilization: { iterations: 500, fit: true },
                maxVelocity: 30,
                minVelocity: 0.75,
            },
            interaction: {
                hover: true, tooltipDelay: 0,
                hideEdgesOnDrag: true, zoomView: true, dragView: true,
            },
            layout: { randomSeed: 42 },
        };

        this.network = new vis.Network(
            canvas,
            { nodes: this.nodesDataset, edges: this.edgesDataset },
            options,
        );

        // Node click -> modal
        this.network.on('click', (params) => {
            if (params.nodes.length > 0) {
                this.openModal(params.nodes[0]);
            }
        });
    },

    setupTooltip() {
        const tooltip = document.getElementById('graph-tooltip');
        const ttLabel = document.getElementById('tt-label');
        const ttBody = document.getElementById('tt-body');
        let active = false;

        const show = (labelHtml, bodyHtml) => {
            ttLabel.innerHTML = labelHtml;
            ttBody.innerHTML = bodyHtml;
            tooltip.classList.add('visible');
            active = true;
        };
        const hide = () => { tooltip.classList.remove('visible'); active = false; };

        if (!this.network) return;

        // Node hover
        this.network.on('hoverNode', (params) => {
            const visNode = this.nodesDataset.get(params.node);
            if (!visNode || !visNode._data) return;
            const n = visNode._data;
            const color = this.getColor(n.node_type);
            const nets = (n.networks || []).join(', ');

            const label = `<span style="color:${color}">${n.node_type}</span>`;
            let body = `<div style="font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:8px">${(n.label || '').replace(/</g,'&lt;')}</div>`;
            if (nets) body += `<div style="margin-top:6px;color:#64748b;font-size:10px">Networks: ${nets}</div>`;
            body += `<div style="color:#64748b;font-size:10px;margin-top:2px">Confidence: ${Math.round((n.confidence||0)*100)}% | Decay: ${Math.round((n.decay_score||0)*100)}%</div>`;
            show(label, body);
        });
        this.network.on('blurNode', hide);

        // Edge hover
        this.network.on('hoverEdge', (params) => {
            const visEdge = this.edgesDataset.get(params.edge);
            if (!visEdge || !visEdge._data) return;
            const e = visEdge._data;
            const fromNode = this.nodeMap[e.from];
            const toNode = this.nodeMap[e.to];
            const fromLabel = fromNode ? fromNode.label : e.from.slice(0,8);
            const toLabel = toNode ? toNode.label : e.to.slice(0,8);

            const label = `<span style="color:#e2e8f0">${fromLabel}</span>  \u2192  <span style="color:#e2e8f0">${toLabel}</span>`;
            const body = `<span class="tt-type">${e.edge_type || ''}</span><br>Weight: ${(e.weight||0).toFixed(2)}`;
            show(label, body);
        });
        this.network.on('blurEdge', hide);

        // Follow cursor
        document.addEventListener('mousemove', (ev) => {
            if (!active) return;
            const x = ev.clientX + 18, y = ev.clientY + 18;
            const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
            tooltip.style.left = (x + tw > window.innerWidth ? ev.clientX - tw - 10 : x) + 'px';
            tooltip.style.top = (y + th > window.innerHeight ? ev.clientY - th - 10 : y) + 'px';
        });
    },

    setupModal() {
        const backdrop = document.getElementById('modal-backdrop');
        const closeBtn = document.getElementById('modal-close');

        const closeModal = () => {
            backdrop.classList.remove('visible');
            setTimeout(() => { backdrop.style.display = 'none'; }, 250);
        };

        closeBtn.addEventListener('click', closeModal);
        backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closeModal(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
    },

    async openModal(nodeId) {
        const backdrop = document.getElementById('modal-backdrop');
        const modalCat = document.getElementById('modal-category');
        const modalTitle = document.getElementById('modal-title');
        const modalNetworks = document.getElementById('modal-networks');
        const modalBody = document.getElementById('modal-body');
        const modalConnList = document.getElementById('modal-conn-list');
        const modalCard = document.getElementById('modal-card');

        const node = this.nodeMap[nodeId];
        if (!node) return;

        const color = this.getColor(node.node_type);

        modalCat.textContent = node.node_type;
        modalCat.style.color = color;
        modalTitle.textContent = node.label || node.title || '';
        modalCard.style.setProperty('--modal-glow', color + '30');

        // Network badges
        modalNetworks.innerHTML = '';
        (node.networks || []).forEach(net => {
            const span = document.createElement('span');
            span.className = 'net-badge';
            span.textContent = net;
            modalNetworks.appendChild(span);
        });

        // Fetch investigation data for body
        let bodyText = `Confidence: ${Math.round((node.confidence||0)*100)}%\nDecay Score: ${Math.round((node.decay_score||0)*100)}%`;
        try {
            const data = await MemoraAPI.investigate(nodeId);
            const e = data.entity;
            if (e.content) bodyText = e.content + '\n\n' + bodyText;
            // Add properties
            if (e.properties && Object.keys(e.properties).length) {
                bodyText += '\n\nProperties:';
                for (const [k,v] of Object.entries(e.properties)) {
                    if (v !== null && v !== '' && v !== undefined) {
                        bodyText += `\n  ${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`;
                    }
                }
            }
        } catch (err) { /* use basic info */ }
        modalBody.textContent = bodyText;

        // Connections
        modalConnList.innerHTML = '';
        const conns = this.adjMap[nodeId] || [];
        conns.forEach(c => {
            const target = this.nodeMap[c.id];
            if (!target) return;
            const div = document.createElement('div');
            div.className = 'conn-item';
            const targetColor = this.getColor(target.node_type);
            div.style.setProperty('--dot-color', targetColor);
            const arrow = c.dir === 'outgoing' ? '\u2192' : '\u2190';
            div.innerHTML = `<strong>${c.type}</strong> ${arrow} ${target.label || target.title || c.id.slice(0,8)}`;
            div.addEventListener('click', () => {
                backdrop.classList.remove('visible');
                setTimeout(() => {
                    backdrop.style.display = 'none';
                    this.openModal(c.id);
                }, 250);
            });
            modalConnList.appendChild(div);
        });

        backdrop.style.display = 'flex';
        requestAnimationFrame(() => { backdrop.classList.add('visible'); });
    },

    applyFilter(filter) {
        if (!this.nodesDataset || !this.rawNodes) return;
        if (filter === 'all') {
            this.rawNodes.forEach(n => { this.nodesDataset.update({ id: n.id, hidden: false }); });
        } else {
            this.rawNodes.forEach(n => { this.nodesDataset.update({ id: n.id, hidden: n.node_type !== filter }); });
        }
    },

    onEvent(event) {
        if (event.type && event.type.startsWith('entity.') && this.network) {
            this.loadGraph();
        }
    },
};
