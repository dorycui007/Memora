/**
 * People View — relationship CRM directory.
 */
const PeopleView = {
    initialized: false,

    async init() {
        const container = document.getElementById('view-people');
        container.innerHTML = '<div class="loading">Loading people...</div>';

        try {
            const data = await MemoraAPI.getPeople({ limit: 100 });
            this.render(container, data.people);
        } catch (err) {
            container.innerHTML = '<div class="empty-state">No people tracked yet</div>';
        }
        this.initialized = true;
    },

    render(container, people) {
        if (!people.length) {
            container.innerHTML = '<div class="empty-state">No people in the graph yet</div>';
            return;
        }

        container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">People Directory</h2>
                <span class="badge">${people.length} people</span>
            </div>
            <div class="people-grid">
                ${people.map(p => this.renderCard(p)).join('')}
            </div>
        `;

        container.querySelectorAll('.person-card').forEach(card => {
            card.addEventListener('click', () => {
                InvestigateView.open(card.dataset.id);
            });
        });
    },

    renderCard(person) {
        const strength = person.strength || person.relationship_strength || 0.5;
        const strengthPct = Math.round(strength * 100);
        const color = strength > 0.7 ? 'var(--success)' : strength > 0.4 ? 'var(--warning)' : 'var(--danger)';

        return `
            <div class="person-card" data-id="${person.id || person.node_id}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="font-size:14px;font-weight:500">${person.name || person.title}</span>
                    <span style="font-size:10px;color:var(--text-muted)">${person.organization || ''}</span>
                </div>
                <div style="font-size:11px;color:var(--text-secondary);margin-top:4px">${person.role || person.relationship_to_user || ''}</div>
                <div class="strength-bar">
                    <div class="strength-fill" style="width:${strengthPct}%;background:${color}"></div>
                </div>
                <div style="font-size:10px;color:var(--text-muted);margin-top:4px">${strengthPct}% strength</div>
            </div>
        `;
    },
};
