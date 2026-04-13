// Garden Calendar - Vanilla JavaScript (No React, No Bundling)

class GardenCalendar {
    constructor() {
        this.currentMonth = new Date();
        this.selectedSite = null;
        this.crops = [];
        this.sites = [];
        this.plantTypes = [];
        this.varieties = [];
        this.selectedCrop = null;
        this.timeline = null;
        this.companions = [];
        this.loading = false;

        this.init();
    }

    async init() {
        await this.fetchSites();
        await this.fetchPlantTypes();
        this.renderCalendar();
    }

    async fetchSites() {
        try {
            const res = await fetch('/api/sites');
            const data = await res.json();
            this.sites = data.sites || [];
            if (this.sites.length > 0) {
                this.selectedSite = this.sites[0].id;
                await this.fetchCrops();
                this.renderSiteSelector();
            }
        } catch (err) {
            this.showError('Failed to load sites');
        }
    }

    async fetchPlantTypes() {
        try {
            const res = await fetch('/api/plant-profiles/types');
            const data = await res.json();
            this.plantTypes = data.plant_types || [];
        } catch (err) {
            this.showError('Failed to load plant types');
        }
    }

    async fetchCrops() {
        try {
            this.loading = true;
            const res = await fetch(`/api/calendar/crops/site/${this.selectedSite}`);
            const data = await res.json();
            this.crops = data.crops || [];
            this.renderCalendar();
        } catch (err) {
            this.showError('Failed to load crops');
        } finally {
            this.loading = false;
        }
    }

    async fetchVarietiesForType(typeId) {
        try {
            const res = await fetch(`/api/plant-profiles/types/${typeId}/varieties`);
            const data = await res.json();
            this.varieties = data.varieties || [];
            this.renderVarieties();
        } catch (err) {
            console.error('Failed to load varieties:', err);
        }
    }

    async fetchTimeline(varietyId, seedDate) {
        try {
            const res = await fetch(
                `/api/calendar/timeline/${varietyId}?seed_start_date=${seedDate}`
            );
            const data = await res.json();
            this.timeline = data;
            this.renderTimeline();
        } catch (err) {
            console.error('Failed to fetch timeline:', err);
        }
    }

    async fetchCompanions(varietyId) {
        try {
            const res = await fetch(`/api/calendar/companions/${varietyId}`);
            const data = await res.json();
            this.companions = data.companions || [];
            this.renderCompanions();
        } catch (err) {
            console.error('Failed to fetch companions:', err);
        }
    }

    renderSiteSelector() {
        const selector = document.querySelector('.site-selector select');
        if (!selector) return;

        selector.innerHTML = this.sites
            .map(
                (site) =>
                    `<option value="${site.id}">${site.friendly_name || site.site_code}</option>`
            )
            .join('');

        selector.value = this.selectedSite;
        selector.addEventListener('change', (e) => {
            this.selectedSite = parseInt(e.target.value);
            this.fetchCrops();
        });
    }

    renderVarieties() {
        const select = document.querySelector('select[name="plant_variety_id"]');
        if (!select) return;

        select.innerHTML =
            '<option value="">Select variety...</option>' +
            this.varieties
                .map((v) => `<option value="${v.id}">${v.name}</option>`)
                .join('');
    }

    renderTimeline() {
        const container = document.querySelector('.timeline-box');
        if (!container || !this.timeline) return;

        container.innerHTML = `
            <strong>Timeline</strong>
            <div class="timeline-grid">
                <div class="timeline-item">
                    <div class="timeline-item-label">Germination</div>
                    <div class="timeline-item-value">${this.timeline.germination_days} days</div>
                </div>
                ${
                    this.timeline.transplant_ready_date
                        ? `
                    <div class="timeline-item">
                        <div class="timeline-item-label">Transplant Ready</div>
                        <div class="timeline-item-value">${this.timeline.transplant_ready_days} days</div>
                    </div>
                `
                        : ''
                }
                <div class="timeline-item">
                    <div class="timeline-item-label">Harvest</div>
                    <div class="timeline-item-value">~${this.timeline.harvest_days_from_seed} days</div>
                </div>
            </div>
        `;
    }

    renderCompanions() {
        const container = document.querySelector('.companions-box');
        if (!container) return;

        if (this.companions.length === 0) {
            container.style.display = 'none';
            return;
        }

        container.style.display = 'block';
        container.innerHTML = `
            <strong>Companion Plants</strong>
            <div class="companions-list">
                ${this.companions
                    .map(
                        (comp) => `
                    <div class="companion-item">
                        <span class="companion-name">${comp.companion_name}</span>
                        ${comp.relationship === 'companion' ? ' ✓' : ' ✗'} — ${comp.benefit || comp.notes}
                    </div>
                `
                    )
                    .join('')}
            </div>
        `;
    }

    renderCalendar() {
        const daysInMonth = (date) =>
            new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
        const firstDayOfMonth = (date) => new Date(date.getFullYear(), date.getMonth(), 1).getDay();

        const monthName = this.currentMonth.toLocaleDateString('en-US', {
            month: 'long',
            year: 'numeric',
        });

        // Update month header
        const navH2 = document.querySelector('.calendar-nav h2');
        if (navH2) navH2.textContent = monthName;

        // Generate calendar grid
        let html = '';
        const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        dayHeaders.forEach((day) => {
            html += `<div class="calendar-header-day">${day}</div>`;
        });

        // Empty cells
        for (let i = 0; i < firstDayOfMonth(this.currentMonth); i++) {
            html += '<div></div>';
        }

        // Day cells
        for (let day = 1; day <= daysInMonth(this.currentMonth); day++) {
            const dayCrops = this.getCropsForDate(day);
            html += `
                <div class="calendar-day" data-day="${day}">
                    <div class="calendar-day-number">${day}</div>
                    ${dayCrops
                        .map(
                            (crop) =>
                                `<div class="crop-badge" data-crop-id="${crop.id}">
                                ${crop.emoji} ${crop.crop_name.split(' - ')[1]}
                            </div>`
                        )
                        .join('')}
                </div>
            `;
        }

        const grid = document.querySelector('.calendar-grid');
        if (grid) {
            grid.innerHTML = html;
            // Add click handlers
            grid.querySelectorAll('.crop-badge').forEach((badge) => {
                badge.addEventListener('click', (e) => {
                    const cropId = parseInt(e.currentTarget.dataset.cropId);
                    const crop = this.crops.find((c) => c.id === cropId);
                    if (crop) this.showCropDetail(crop);
                });
            });
        }
    }

    getCropsForDate(day) {
        const dateStr = new Date(
            this.currentMonth.getFullYear(),
            this.currentMonth.getMonth(),
            day
        )
            .toISOString()
            .split('T')[0];

        return this.crops.filter(
            (crop) =>
                crop.seed_start_date === dateStr ||
                crop.expected_harvest_date === dateStr ||
                crop.transplant_date === dateStr
        );
    }

    showCropDetail(crop) {
        const container = document.querySelector('.crop-detail');
        if (!container) return;

        container.innerHTML = `
            <div class="crop-detail-header">
                <h3>${crop.emoji} ${crop.crop_name}</h3>
                <button class="crop-detail-close">✕</button>
            </div>
            <div class="crop-detail-grid">
                <div class="crop-detail-item">
                    <div class="crop-detail-label">Location</div>
                    <div class="crop-detail-value">${crop.bed_location}</div>
                </div>
                <div class="crop-detail-item">
                    <div class="crop-detail-label">Quantity</div>
                    <div class="crop-detail-value">${crop.quantity_planted}</div>
                </div>
                <div class="crop-detail-item">
                    <div class="crop-detail-label">Sown</div>
                    <div class="crop-detail-value">${crop.seed_start_date}</div>
                </div>
                <div class="crop-detail-item">
                    <div class="crop-detail-label">Expected Harvest</div>
                    <div class="crop-detail-value">${crop.expected_harvest_date}</div>
                </div>
                ${
                    crop.transplant_date
                        ? `
                    <div class="crop-detail-item">
                        <div class="crop-detail-label">Transplant</div>
                        <div class="crop-detail-value">${crop.transplant_date}</div>
                    </div>
                `
                        : ''
                }
                <div class="crop-detail-item">
                    <div class="crop-detail-label">Status</div>
                    <div class="crop-detail-value">${crop.status}</div>
                </div>
            </div>
        `;

        container.style.display = 'block';
        container.querySelector('.crop-detail-close').addEventListener('click', () => {
            container.style.display = 'none';
        });

        this.selectedCrop = crop;
    }

    async handlePlanSubmit(e) {
        e.preventDefault();

        const formData = {
            site_id: this.selectedSite,
            plant_variety_id: parseInt(document.querySelector('select[name="plant_variety_id"]').value),
            bed_location: document.querySelector('input[name="bed_location"]').value,
            seed_start_date: document.querySelector('input[name="seed_start_date"]').value,
            quantity_planted: parseInt(
                document.querySelector('input[name="quantity_planted"]').value
            ),
            notes: document.querySelector('textarea[name="notes"]').value,
        };

        try {
            const res = await fetch('/api/calendar/crops/plant', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });

            if (res.ok) {
                // Reset form
                e.target.reset();
                this.timeline = null;
                this.companions = [];
                this.closePlanForm();
                await this.fetchCrops();
            } else {
                this.showError('Failed to plant crop');
            }
        } catch (err) {
            this.showError('Error planting crop');
        }
    }

    openPlanForm() {
        const form = document.querySelector('.form-container');
        if (form) {
            form.style.display = 'block';
        }
    }

    closePlanForm() {
        const form = document.querySelector('.form-container');
        if (form) {
            form.style.display = 'none';
        }
    }

    showError(message) {
        const container = document.querySelector('.error-message');
        if (container) {
            container.textContent = message;
            container.style.display = 'block';
            setTimeout(() => {
                container.style.display = 'none';
            }, 5000);
        }
    }

    previousMonth() {
        this.currentMonth = new Date(
            this.currentMonth.getFullYear(),
            this.currentMonth.getMonth() - 1
        );
        this.renderCalendar();
    }

    nextMonth() {
        this.currentMonth = new Date(
            this.currentMonth.getFullYear(),
            this.currentMonth.getMonth() + 1
        );
        this.renderCalendar();
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const calendar = new GardenCalendar();

    // Wire up event listeners
    const planBtn = document.querySelector('button[data-action="open-plan"]');
    if (planBtn) {
        planBtn.addEventListener('click', () => calendar.openPlanForm());
    }

    const cancelBtn = document.querySelector('button[data-action="cancel-plan"]');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => calendar.closePlanForm());
    }

    const plantTypeSelect = document.querySelector('select[name="plant_type_id"]');
    if (plantTypeSelect) {
        plantTypeSelect.addEventListener('change', (e) => {
            if (e.target.value) {
                calendar.fetchVarietiesForType(parseInt(e.target.value));
            }
        });
    }

    const varietySelect = document.querySelector('select[name="plant_variety_id"]');
    if (varietySelect) {
        varietySelect.addEventListener('change', (e) => {
            if (e.target.value) {
                calendar.fetchCompanions(parseInt(e.target.value));
            }
        });
    }

    const seedDateInput = document.querySelector('input[name="seed_start_date"]');
    if (seedDateInput) {
        seedDateInput.addEventListener('change', (e) => {
            const varietyId = parseInt(
                document.querySelector('select[name="plant_variety_id"]').value
            );
            if (varietyId && e.target.value) {
                calendar.fetchTimeline(varietyId, e.target.value);
            }
        });
    }

    const planForm = document.querySelector('form[data-form="plan-crop"]');
    if (planForm) {
        planForm.addEventListener('submit', (e) => calendar.handlePlanSubmit(e));
    }

    const prevBtn = document.querySelector('button[data-action="prev-month"]');
    if (prevBtn) {
        prevBtn.addEventListener('click', () => calendar.previousMonth());
    }

    const nextBtn = document.querySelector('button[data-action="next-month"]');
    if (nextBtn) {
        nextBtn.addEventListener('click', () => calendar.nextMonth());
    }

    // Store calendar instance globally for debugging
    window.gardenCalendar = calendar;
});