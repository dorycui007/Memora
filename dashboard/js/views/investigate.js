/**
 * Investigation Panel — entity deep-dive slide-in.
 */
const InvestigateView = {
    currentEntityId: null,

    async open(entityId) {
        this.currentEntityId = entityId;
        const panel = document.getElementById('investigation-panel');
        const content = document.getElementById('panel-content');
        const title = document.getElementById('panel-title');

        panel.classList.remove('hidden');
        panel.classList.add('visible');
        content.innerHTML = '<div class="loading">Loading...</div>';

        try {
            const data = await MemoraAPI.investigate(entityId);
            title.textContent = data.entity.title;
            content.innerHTML = this.renderContent(data);
        } catch (err) {
            content.innerHTML = `<div class="empty-state">Failed to load entity</div>`;
        }
    },

    close() {
        const panel = document.getElementById('investigation-panel');
        panel.classList.remove('visible');
        setTimeout(() => panel.classList.add('hidden'), 300);
        this.currentEntityId = null;
    },

    renderContent(data) {
        const e = data.entity;
        const color = MemoraApp.getColor(e.node_type);

        let html = `
            <div class="entity-type-badge" style="background:${color}20;color:${color}">${e.node_type}</div>
            <p style="font-size:13px;margin:12px 0;color:var(--text-secondary)">${e.content || ''}</p>
        `;

        // Properties
        if (e.properties && Object.keys(e.properties).length) {
            html += `<div class="card"><h4 style="font-size:12px;margin-bottom:8px;color:var(--text-muted)">Properties</h4>`;
            for (const [k, v] of Object.entries(e.properties)) {
                if (v !== null && v !== '' && v !== undefined) {
                    html += `<div style="font-size:12px;margin:4px 0"><span style="color:var(--text-muted)">${k}:</span> ${JSON.stringify(v)}</div>`;
                }
            }
            html += '</div>';
        }

        // Networks
        if (e.networks && e.networks.length) {
            html += `<div style="margin:12px 0;display:flex;gap:4px;flex-wrap:wrap">`;
            e.networks.forEach(n => {
                html += `<span class="badge" style="background:var(--bg-tertiary)">${n}</span>`;
            });
            html += '</div>';
        }

        // Connections
        if (data.edges && data.edges.length) {
            html += `<div class="card"><h4 style="font-size:12px;margin-bottom:8px;color:var(--text-muted)">Connections (${data.edges.length})</h4>`;
            data.edges.slice(0, 20).forEach(edge => {
                const otherId = edge.source_id === e.id ? edge.target_id : edge.source_id;
                html += `<div class="entity-card" onclick="InvestigateView.open('${otherId}')" style="padding:8px">
                    <span style="font-size:10px;color:var(--text-muted)">${edge.edge_type}</span>
                    <span style="font-size:11px;margin-left:8px">${otherId.substring(0, 8)}...</span>
                </div>`;
            });
            html += '</div>';
        }

        // Facts
        if (data.facts && data.facts.length) {
            html += `<div class="card"><h4 style="font-size:12px;margin-bottom:8px;color:var(--text-muted)">Verified Facts</h4>`;
            data.facts.forEach(f => {
                html += `<div style="font-size:12px;margin:4px 0;padding:4px 8px;background:var(--bg-tertiary);border-radius:4px">${f.statement || f}</div>`;
            });
            html += '</div>';
        }

        // Metadata
        html += `
            <div style="margin-top:16px;font-size:10px;color:var(--text-muted)">
                <div>Confidence: ${(e.confidence * 100).toFixed(0)}%</div>
                <div>Decay: ${(e.decay_score * 100).toFixed(0)}%</div>
                <div>Created: ${e.created_at || ''}</div>
            </div>
        `;

        return html;
    },
};
