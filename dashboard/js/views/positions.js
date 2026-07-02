/**
 * Positions View — strategic position cards with detail.
 */
const PositionsView = {
    initialized: false,

    async init() {
        const container = document.getElementById('view-positions');
        container.innerHTML = '<div class="loading">Loading positions...</div>';

        try {
            const data = await MemoraAPI.getPositions();
            this.render(container, data.positions);
        } catch (err) {
            container.innerHTML = '<div class="empty-state">No positions tracked yet</div>';
        }
        this.initialized = true;
    },

    render(container, positions) {
        if (!positions.length) {
            container.innerHTML = '<div class="empty-state">No positions tracked yet. Capture position data to begin.</div>';
            return;
        }

        container.innerHTML = `
            <div class="section-header">
                <h2 class="section-title">Strategic Positions</h2>
                <span class="badge">${positions.length} tracked</span>
            </div>
            <div class="position-grid">
                ${positions.map(p => this.renderCard(p)).join('')}
            </div>
        `;

        container.querySelectorAll('.position-card').forEach(card => {
            card.addEventListener('click', () => {
                InvestigateView.open(card.dataset.id);
            });
        });
    },

    renderCard(pos) {
        const statusClass = pos.status || 'target';
        const blockerCount = (pos.blockers || []).length;

        return `
            <div class="position-card" data-id="${pos.id}">
                <div class="card-header">
                    <span class="position-status ${statusClass}">${pos.status || 'unknown'}</span>
                </div>
                <h3 style="font-size: 15px; margin: 8px 0">${pos.title}</h3>
                <p style="font-size: 12px; color: var(--text-secondary)">${pos.organization || ''}</p>
                <div style="margin-top: 12px; display: flex; gap: 16px; font-size: 11px; color: var(--text-muted)">
                    <span>${pos.commitment_count || 0} commitments</span>
                    ${blockerCount ? `<span style="color: var(--danger)">${blockerCount} blockers</span>` : ''}
                </div>
            </div>
        `;
    },
};
