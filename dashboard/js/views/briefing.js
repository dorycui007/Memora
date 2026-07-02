/**
 * Briefing View — daily strategic intelligence briefing.
 */
const BriefingView = {
    initialized: false,

    async init() {
        const container = document.getElementById('view-briefing');
        container.innerHTML = '<div class="loading">Generating briefing...</div>';

        try {
            const data = await MemoraAPI.getBriefing();
            this.render(container, data);
        } catch (err) {
            container.innerHTML = '<div class="empty-state">Briefing unavailable</div>';
        }
        this.initialized = true;
    },

    render(container, briefing) {
        const sections = [];

        if (briefing.summary) {
            sections.push(`<div class="card" style="margin: 20px"><p style="font-size: 14px; line-height: 1.6">${briefing.summary}</p></div>`);
        }

        if (briefing.urgent && briefing.urgent.length) {
            sections.push(this.renderSection('Critical', briefing.urgent, 'urgent'));
        }
        if (briefing.upcoming && briefing.upcoming.length) {
            sections.push(this.renderSection('Upcoming', briefing.upcoming, 'warning'));
        }
        if (briefing.people_followup && briefing.people_followup.length) {
            sections.push(this.renderSection('People Follow-up', briefing.people_followup, 'info'));
        }
        if (briefing.wins && briefing.wins.length) {
            sections.push(this.renderSection('Wins', briefing.wins, 'info'));
        }
        if (briefing.stalled_attention && briefing.stalled_attention.length) {
            sections.push(this.renderSection('Needs Attention', briefing.stalled_attention, 'warning'));
        }

        if (!sections.length && briefing.data) {
            sections.push('<div class="card" style="margin: 20px"><pre style="font-size: 12px; white-space: pre-wrap">' +
                JSON.stringify(briefing.data, null, 2) + '</pre></div>');
        }

        container.innerHTML = `
            <div class="briefing-container">
                <div class="section-header" style="border: none; padding-left: 0">
                    <h2 class="section-title">Strategic Briefing</h2>
                    <span class="badge">${new Date().toLocaleDateString()}</span>
                </div>
                ${sections.join('')}
            </div>
        `;
    },

    renderSection(title, items, severity) {
        return `
            <div class="briefing-section">
                <h3>${title}</h3>
                ${items.map(item => {
                    const text = typeof item === 'string' ? item : (item.message || item.title || JSON.stringify(item));
                    return `<div class="briefing-item ${severity}">${text}</div>`;
                }).join('')}
            </div>
        `;
    },
};
