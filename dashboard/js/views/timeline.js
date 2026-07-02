/**
 * Timeline View — vis-timeline horizontal timeline.
 */
const TimelineView = {
    timeline: null,
    initialized: false,

    async init() {
        const container = document.getElementById('view-timeline');
        container.innerHTML = '<div class="timeline-container"><div id="timeline-canvas" style="height:calc(100vh - 40px)"></div></div>';

        try {
            const data = await MemoraAPI.getTimeline({ limit: 200 });
            this.render(data.items);
        } catch (err) {
            container.innerHTML = '<div class="empty-state">No timeline data available</div>';
        }
        this.initialized = true;
    },

    render(items) {
        const canvas = document.getElementById('timeline-canvas');
        if (!canvas || !items.length) return;

        const dataset = new vis.DataSet(items.map((item, i) => ({
            id: i,
            content: item.title || item.label || 'Event',
            start: item.date || item.start || item.event_date || new Date().toISOString(),
            className: item.type || 'event',
            _data: item,
        })));

        const options = {
            height: '100%',
            zoomMin: 1000 * 60 * 60 * 24,
            zoomMax: 1000 * 60 * 60 * 24 * 365 * 2,
            orientation: 'top',
            stack: true,
            margin: { item: 10 },
        };

        this.timeline = new vis.Timeline(canvas, dataset, options);
        this.timeline.on('select', (props) => {
            if (props.items.length) {
                const item = dataset.get(props.items[0]);
                if (item._data && item._data.id) {
                    InvestigateView.open(item._data.id);
                }
            }
        });
    },
};
