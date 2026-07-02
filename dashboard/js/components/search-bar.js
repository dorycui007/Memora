/**
 * Search Bar Component — global search with results dropdown.
 */
const SearchBar = {
    debounceTimer: null,

    init() {
        const input = document.getElementById('global-search');
        if (!input) return;

        input.addEventListener('input', () => {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => this.search(input.value), 300);
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                input.value = '';
                this.hideResults();
            }
        });
    },

    async search(query) {
        if (!query || query.length < 2) {
            this.hideResults();
            return;
        }

        try {
            const data = await MemoraAPI.search(query);
            this.showResults(data.results);
        } catch (err) {
            this.hideResults();
        }
    },

    showResults(results) {
        let container = document.getElementById('search-results');
        if (!container) {
            container = document.createElement('div');
            container.id = 'search-results';
            document.getElementById('search-container').appendChild(container);
        }

        if (!results.length) {
            container.innerHTML = '<div class="search-result-item" style="color:var(--text-muted)">No results</div>';
        } else {
            container.innerHTML = results.slice(0, 10).map(r => `
                <div class="search-result-item" data-id="${r.id}">
                    <span class="entity-type-badge" style="background:${MemoraApp.getColor(r.node_type)}20;color:${MemoraApp.getColor(r.node_type)}">${r.node_type}</span>
                    ${r.title}
                </div>
            `).join('');

            container.querySelectorAll('.search-result-item[data-id]').forEach(item => {
                item.addEventListener('click', () => {
                    InvestigateView.open(item.dataset.id);
                    this.hideResults();
                    document.getElementById('global-search').value = '';
                });
            });
        }

        container.style.display = 'block';
    },

    hideResults() {
        const container = document.getElementById('search-results');
        if (container) container.style.display = 'none';
    },
};
