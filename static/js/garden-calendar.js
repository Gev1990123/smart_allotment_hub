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
        const d = new Date(
            this.currentMonth.getFullYear(),
            this.currentMonth.getMonth(),
            day
        );

        const dateStr = d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
 
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
            <div class="crop-detail-actions">
                <button class="crop-detail-delete">🗑️ Delete Crop</button>
            </div>
        `;
 
        container.style.display = 'block';
        
        container.querySelector('.crop-detail-close').addEventListener('click', () => {
            container.style.display = 'none';
        });
 
        container.querySelector('.crop-detail-delete').addEventListener('click', () => {
            if (confirm(`Are you sure you want to delete "${crop.crop_name}"? This cannot be undone.`)) {
                this.deleteCrop(crop.id);
            }
        });
 
        this.selectedCrop = crop;
    }
 
    async deleteCrop(cropId) {
        try {
            const res = await fetch(`/api/calendar/crops/${cropId}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
            });
 
            if (res.ok) {
                this.showSuccess('Crop deleted successfully!');
                const container = document.querySelector('.crop-detail');
                if (container) {
                    container.style.display = 'none';
                }
                await this.fetchCrops();
            } else {
                try {
                    const error = await res.json();
                    console.error('API Error Response:', error);
                    const errorMsg = error.detail || error.message || `Failed to delete crop (HTTP ${res.status})`;
                    this.showError(String(errorMsg));
                } catch (parseError) {
                    console.error('Failed to parse error response:', parseError);
                    this.showError(`Failed to delete crop (HTTP ${res.status})`);
                }
            }
        } catch (err) {
            console.error('Network/Delete Error:', err);
            const errorMsg = err && err.message ? String(err.message) : 'Unknown error occurred';
            this.showError('Error: ' + errorMsg);
        }
    }
 
    async handlePlanSubmit(e) {
        e.preventDefault();
 
        // Get form values with fallbacks
        const varietySelect = document.querySelector('select[name="plant_variety_id"]');
        const bedInput = document.querySelector('input[name="bed_location"]');
        const seedDateInput = document.querySelector('input[name="seed_start_date"]');
        const quantityInput = document.querySelector('input[name="quantity_planted"]');
        const notesInput = document.querySelector('input[name="notes"]');
 
        // Validate inputs exist
        if (!varietySelect || !varietySelect.value) {
            this.showError('Please select a plant variety');
            return;
        }
        if (!bedInput || !bedInput.value) {
            this.showError('Please enter a bed location');
            return;
        }
        if (!seedDateInput || !seedDateInput.value) {
            this.showError('Please select a seed start date');
            return;
        }
 
        const formData = {
            site_id: this.selectedSite,
            plant_variety_id: parseInt(varietySelect.value),
            bed_location: bedInput.value,
            seed_start_date: seedDateInput.value,
            quantity_planted: quantityInput ? parseInt(quantityInput.value) || 1 : 1,
            notes: notesInput ? notesInput.value : '',
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
                this.showSuccess('Crop planted successfully!');
            } else {
                try {
                    const error = await res.json();
                    console.error('API Error Response:', error);
                    const errorMsg = error.detail || error.message || `Failed to plant crop (HTTP ${res.status})`;
                    this.showError(String(errorMsg));
                } catch (parseError) {
                    console.error('Failed to parse error response:', parseError);
                    this.showError(`Failed to plant crop (HTTP ${res.status})`);
                }
            }
        } catch (err) {
            console.error('Network/Form Error:', err);
            const errorMsg = err && err.message ? String(err.message) : 'Unknown error occurred';
            this.showError('Error: ' + errorMsg);
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
        // Safely convert message to string, handling any type
        let msg = 'An error occurred';
        try {
            if (message === null || message === undefined) {
                msg = 'An error occurred';
            } else if (typeof message === 'string') {
                msg = message;
            } else if (typeof message === 'object') {
                // If it's an object, try to extract error info
                if (message.message) {
                    msg = String(message.message);
                } else if (message.detail) {
                    msg = String(message.detail);
                } else {
                    msg = JSON.stringify(message);
                }
            } else {
                msg = String(message);
            }
        } catch (e) {
            msg = 'An error occurred';
        }
        
        console.error('Error:', msg);
        const container = document.querySelector('.error-message');
        if (container) {
            container.textContent = msg;
            container.style.display = 'block';
            container.style.background = '#ffebee';
            container.style.color = '#c62828';
            container.style.borderLeft = '4px solid #c62828';
            setTimeout(() => {
                container.style.display = 'none';
            }, 5000);
        } else {
            alert(msg);
        }
    }
 
    showSuccess(message) {
        const msg = String(message || 'Success!');
        console.log('Success:', msg);
        const container = document.querySelector('.error-message');
        if (container) {
            container.textContent = '✓ ' + msg;
            container.style.display = 'block';
            container.style.background = '#e8f5e9';
            container.style.color = '#2e7d32';
            container.style.borderLeft = '4px solid #2e7d32';
            setTimeout(() => {
                container.style.display = 'none';
            }, 3000);
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
    console.log('🌱 Garden Calendar initializing...');
    const calendar = new GardenCalendar();
 
    // Debug: Check if elements exist
    console.log('Checking form elements:');
    console.log('  - Plan button:', !!document.querySelector('button[data-action="open-plan"]'));
    console.log('  - Cancel button:', !!document.querySelector('button[data-action="cancel-plan"]'));
    console.log('  - Plant type select:', !!document.querySelector('select[name="plant_type_id"]'));
    console.log('  - Variety select:', !!document.querySelector('select[name="plant_variety_id"]'));
    console.log('  - Seed date input:', !!document.querySelector('input[name="seed_start_date"]'));
    console.log('  - Plan form:', !!document.querySelector('form[data-form="plan-crop"]'));
 
    // Wire up event listeners
    const planBtn = document.querySelector('button[data-action="open-plan"]');
    if (planBtn) {
        planBtn.addEventListener('click', () => calendar.openPlanForm());
    } else {
        console.warn('⚠️  Plan button not found');
    }
 
    const cancelBtn = document.querySelector('button[data-action="cancel-plan"]');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => calendar.closePlanForm());
    } else {
        console.warn('⚠️  Cancel button not found');
    }
 
    const plantTypeSelect = document.querySelector('select[name="plant_type_id"]');
    if (plantTypeSelect) {
        plantTypeSelect.addEventListener('change', (e) => {
            if (e.target.value) {
                calendar.fetchVarietiesForType(parseInt(e.target.value));
            }
        });
    } else {
        console.warn('⚠️  Plant type select not found');
    }
 
    const varietySelect = document.querySelector('select[name="plant_variety_id"]');
    if (varietySelect) {
        varietySelect.addEventListener('change', (e) => {
            if (e.target.value) {
                calendar.fetchCompanions(parseInt(e.target.value));
            }
        });
    } else {
        console.warn('⚠️  Variety select not found');
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
    } else {
        console.warn('⚠️  Seed date input not found');
    }
 
    const planForm = document.querySelector('form[data-form="plan-crop"]');
    if (planForm) {
        planForm.addEventListener('submit', (e) => calendar.handlePlanSubmit(e));
    } else {
        console.warn('⚠️  Plan form not found');
    }
 
    const prevBtn = document.querySelector('button[data-action="prev-month"]');
    if (prevBtn) {
        prevBtn.addEventListener('click', () => calendar.previousMonth());
    } else {
        console.warn('⚠️  Previous month button not found');
    }
 
    const nextBtn = document.querySelector('button[data-action="next-month"]');
    if (nextBtn) {
        nextBtn.addEventListener('click', () => calendar.nextMonth());
    } else {
        console.warn('⚠️  Next month button not found');
    }
 
    // Store calendar instance globally for debugging
    window.gardenCalendar = calendar;
    console.log('✅ Garden Calendar ready! (window.gardenCalendar available)');
});