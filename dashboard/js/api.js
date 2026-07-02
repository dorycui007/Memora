/**
 * Memora API client — fetch wrapper for all backend routes.
 */
const MemoraAPI = {
    BASE: '/api',

    async _fetch(path, options = {}) {
        try {
            const res = await fetch(this.BASE + path, {
                headers: { 'Content-Type': 'application/json', ...options.headers },
                ...options,
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            return await res.json();
        } catch (err) {
            console.error(`API error: ${path}`, err);
            throw err;
        }
    },

    // Capture
    capture(text, metadata) {
        return this._fetch('/capture', {
            method: 'POST',
            body: JSON.stringify({ text, metadata }),
        });
    },

    // Entities
    getEntities(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this._fetch(`/entities?${qs}`);
    },

    getEntity(id) {
        return this._fetch(`/entities/${id}`);
    },

    updateEntity(id, updates) {
        return this._fetch(`/entities/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ updates }),
        });
    },

    // Edges
    getEdges(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this._fetch(`/edges?${qs}`);
    },

    // Search
    search(q, params = {}) {
        const qs = new URLSearchParams({ q, ...params }).toString();
        return this._fetch(`/search?${qs}`);
    },

    // Investigation
    investigate(id) {
        return this._fetch(`/investigate/${id}`);
    },

    findPath(sourceId, targetId, maxHops = 5) {
        return this._fetch(`/investigate/path?source_id=${sourceId}&target_id=${targetId}&max_hops=${maxHops}`);
    },

    // Timeline
    getTimeline(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this._fetch(`/timeline?${qs}`);
    },

    // People
    getPeople(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this._fetch(`/people?${qs}`);
    },

    // Briefing
    getBriefing() {
        return this._fetch('/briefing');
    },

    // Positions
    getPositions() {
        return this._fetch('/positions');
    },

    // Academic
    getAcademicRoadmap() {
        return this._fetch('/academic/roadmap');
    },

    getGPA() {
        return this._fetch('/academic/gpa');
    },

    // Deadlines
    getDeadlines(days = 30) {
        return this._fetch(`/deadlines?days=${days}`);
    },

    // Patterns
    getPatterns(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this._fetch(`/patterns?${qs}`);
    },

    // Health
    getHealth() {
        return this._fetch('/health');
    },

    // Ontology
    getOntology() {
        return this._fetch('/ontology');
    },

    // Graph
    getSubgraph(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this._fetch(`/graph/subgraph?${qs}`);
    },

    getGraphStats() {
        return this._fetch('/graph/stats');
    },

    // Events history
    getEventHistory(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this._fetch(`/events/history?${qs}`);
    },
};
