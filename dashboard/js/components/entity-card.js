/**
 * Entity Card Component — reusable entity detail display.
 */
const EntityCard = {
    render(entity) {
        const color = MemoraApp.getColor(entity.node_type);
        return `
            <div class="entity-card" onclick="InvestigateView.open('${entity.id}')">
                <span class="entity-type-badge" style="background:${color}20;color:${color}">${entity.node_type}</span>
                <div class="entity-title">${entity.title}</div>
                <div class="entity-meta">
                    ${entity.networks ? entity.networks.join(', ') : ''}
                    ${entity.confidence ? ` | ${Math.round(entity.confidence * 100)}%` : ''}
                </div>
            </div>
        `;
    },
};
