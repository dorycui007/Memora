/**
 * Memora App — Router, SSE client, view lifecycle management.
 */
const MemoraApp = {
    currentView: 'graph',
    sseConnection: null,
    ontology: null,
    views: {},

    async init() {
        // Load ontology first
        try {
            this.ontology = await MemoraAPI.getOntology();
        } catch (e) {
            console.warn('Failed to load ontology:', e);
            this.ontology = { entity_types: {}, edge_types: {}, networks: [] };
        }

        // Initialize views
        this.views = {
            graph: GraphView,
            positions: PositionsView,
            briefing: BriefingView,
            timeline: TimelineView,
            people: PeopleView,
            academic: AcademicView,
        };

        // Setup navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const view = link.dataset.view;
                this.navigate(view);
            });
        });

        // Setup investigation panel close
        document.getElementById('panel-close').addEventListener('click', () => {
            InvestigateView.close();
        });

        // Setup search
        SearchBar.init();

        // Connect SSE
        this.connectSSE();

        // Route to initial view
        const hash = window.location.hash.slice(1) || 'graph';
        this.navigate(hash);
    },

    navigate(viewName) {
        if (!this.views[viewName]) return;

        this.currentView = viewName;

        // Update nav active state
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        const activeLink = document.querySelector(`[data-view="${viewName}"]`);
        if (activeLink) activeLink.classList.add('active');

        // Show/hide views
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        const viewEl = document.getElementById(`view-${viewName}`);
        if (viewEl) viewEl.classList.add('active');

        // Initialize view
        const view = this.views[viewName];
        if (view && view.init) {
            view.init();
        }

        window.location.hash = viewName;
    },

    connectSSE() {
        const statusDot = document.querySelector('.status-dot');
        const statusText = document.getElementById('connection-status');

        try {
            const evtSource = new EventSource('/api/events');
            this.sseConnection = evtSource;

            evtSource.onopen = () => {
                statusDot.classList.add('connected');
                statusDot.classList.remove('error');
                statusText.innerHTML = '<span class="status-dot connected"></span> Connected';
            };

            evtSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleEvent(data);
                } catch (e) {
                    console.warn('Failed to parse SSE event:', e);
                }
            };

            evtSource.onerror = () => {
                statusDot.classList.remove('connected');
                statusDot.classList.add('error');
                statusText.innerHTML = '<span class="status-dot error"></span> Disconnected';
                // Reconnect after 5s
                setTimeout(() => this.connectSSE(), 5000);
            };
        } catch (e) {
            console.warn('SSE not available:', e);
            statusText.innerHTML = '<span class="status-dot error"></span> Offline';
        }
    },

    handleEvent(event) {
        // Show toast notification
        NotificationToast.show(event.type, event.payload);

        // Notify active view
        const view = this.views[this.currentView];
        if (view && view.onEvent) {
            view.onEvent(event);
        }
    },

    getColor(nodeType) {
        if (this.ontology && this.ontology.entity_types[nodeType]) {
            return this.ontology.entity_types[nodeType].color;
        }
        return '#94a3b8';
    },
};

// Boot the app
document.addEventListener('DOMContentLoaded', () => MemoraApp.init());
