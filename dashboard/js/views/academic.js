/**
 * Academic View — D3.js course dependency DAG.
 */
const AcademicView = {
    initialized: false,

    async init() {
        const container = document.getElementById('view-academic');
        container.innerHTML = '<div class="loading">Loading academic roadmap...</div>';

        try {
            const [roadmap, gpa] = await Promise.all([
                MemoraAPI.getAcademicRoadmap(),
                MemoraAPI.getGPA().catch(() => ({ gpa: 0, total_credits: 0 })),
            ]);
            this.render(container, roadmap, gpa);
        } catch (err) {
            container.innerHTML = '<div class="empty-state">No courses tracked yet</div>';
        }
        this.initialized = true;
    },

    render(container, roadmap, gpa) {
        if (!roadmap.courses.length) {
            container.innerHTML = '<div class="empty-state">No courses in the graph yet. Capture course data to begin.</div>';
            return;
        }

        container.innerHTML = `
            <div class="academic-container">
                <div class="section-header" style="border:none;padding-left:0">
                    <h2 class="section-title">Academic Roadmap</h2>
                    <div>
                        <span class="badge" style="background:var(--bg-tertiary);margin-right:8px">GPA: ${gpa.gpa}</span>
                        <span class="badge" style="background:var(--bg-tertiary)">${gpa.total_credits} credits</span>
                    </div>
                </div>
                <div class="course-dag" id="course-dag-container"></div>
                <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
                    ${roadmap.courses.map(c => this.renderCourseCard(c)).join('')}
                </div>
            </div>
        `;
    },

    renderCourseCard(course) {
        const statusColors = {
            completed: 'var(--success)',
            enrolled: 'var(--accent)',
            planned: 'var(--text-muted)',
            dropped: 'var(--danger)',
        };
        const color = statusColors[course.status] || 'var(--text-muted)';

        return `
            <div class="entity-card" style="flex:0 0 200px;border-left:3px solid ${color}">
                <div style="font-size:12px;font-weight:600;color:${color}">${course.code || ''}</div>
                <div style="font-size:12px;margin-top:4px">${course.name || course.title}</div>
                <div style="font-size:10px;color:var(--text-muted);margin-top:4px">
                    ${course.semester || ''} ${course.grade ? '| ' + course.grade : ''}
                </div>
            </div>
        `;
    },
};
