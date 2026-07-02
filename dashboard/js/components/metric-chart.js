/**
 * Metric Chart Component — sparkline/trend for METRIC nodes.
 */
const MetricChart = {
    render(history, width = 120, height = 30) {
        if (!history || !history.length) return '';

        const values = history.map(h => h.value || 0);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min || 1;

        const points = values.map((v, i) => {
            const x = (i / (values.length - 1)) * width;
            const y = height - ((v - min) / range) * height;
            return `${x},${y}`;
        }).join(' ');

        return `
            <svg width="${width}" height="${height}" style="overflow:visible">
                <polyline points="${points}" fill="none" stroke="var(--accent)" stroke-width="1.5" />
            </svg>
        `;
    },
};
