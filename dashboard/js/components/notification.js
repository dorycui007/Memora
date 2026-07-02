/**
 * Toast Notification Component — SSE-driven alerts.
 */
const NotificationToast = {
    show(type, payload, severity = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${severity}`;

        const message = payload?.message || payload?.description || type;

        toast.innerHTML = `
            <div class="toast-header">
                <span class="toast-type">${type}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="btn-close" style="font-size:14px">&times;</button>
            </div>
            <div>${message}</div>
        `;

        container.appendChild(toast);

        // Auto-remove after 8 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.3s';
                setTimeout(() => toast.remove(), 300);
            }
        }, 8000);
    },
};
