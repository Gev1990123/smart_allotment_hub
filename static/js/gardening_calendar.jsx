import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Plus, Leaf, AlertCircle } from 'lucide-react';

export default function GardeningCalendar() {
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedSite, setSelectedSite] = useState(1);
  const [crops, setCrops] = useState([]);
  const [sites, setSites] = useState([]);
  const [plantTypes, setPlantTypes] = useState([]);
  const [varieties, setVarieties] = useState([]);
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [selectedCrop, setSelectedCrop] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [companions, setCompanions] = useState([]);

  const [formData, setFormData] = useState({
    plant_variety_id: '',
    seed_start_date: '',
    bed_location: '',
    quantity_planted: 1,
    notes: '',
  });

  // Fetch initial data
  useEffect(() => {
    fetchSites();
    fetchPlantTypes();
    fetchCrops();
  }, [selectedSite, currentMonth]);

  const fetchSites = async () => {
    try {
      const res = await fetch('/api/sites');
      const data = await res.json();
      setSites(data.sites || []);
      if (data.sites?.length > 0) setSelectedSite(data.sites[0].id);
    } catch (error) {
      console.error('Failed to fetch sites:', error);
    }
  };

  const fetchPlantTypes = async () => {
    try {
      const res = await fetch('/api/plant-profiles/types');
      const data = await res.json();
      setPlantTypes(data.plant_types || []);
    } catch (error) {
      console.error('Failed to fetch plant types:', error);
    }
  };

  const fetchCrops = async () => {
    try {
      const res = await fetch(`/api/calendar/crops/site/${selectedSite}`);
      const data = await res.json();
      setCrops(data.crops || []);
    } catch (error) {
      console.error('Failed to fetch crops:', error);
    }
  };

  const fetchVarietiesForType = async (typeId) => {
    try {
      const res = await fetch(`/api/plant-profiles/types/${typeId}/varieties`);
      const data = await res.json();
      setVarieties(data.varieties || []);
    } catch (error) {
      console.error('Failed to fetch varieties:', error);
    }
  };

  const fetchTimeline = async (varietyId, seedDate) => {
    try {
      const res = await fetch(
        `/api/calendar/timeline/${varietyId}?seed_start_date=${seedDate}`
      );
      const data = await res.json();
      setTimeline(data);
    } catch (error) {
      console.error('Failed to fetch timeline:', error);
    }
  };

  const fetchCompanions = async (varietyId) => {
    try {
      const res = await fetch(`/api/calendar/companions/${varietyId}`);
      const data = await res.json();
      setCompanions(data.companions || []);
    } catch (error) {
      console.error('Failed to fetch companions:', error);
    }
  };

  const handlePlantTypeChange = (e) => {
    const typeId = parseInt(e.target.value);
    fetchVarietiesForType(typeId);
  };

  const handleVarietyChange = (e) => {
    const varietyId = parseInt(e.target.value);
    setFormData({ ...formData, plant_variety_id: varietyId });
    fetchCompanions(varietyId);
  };

  const handleSeedDateChange = (e) => {
    const date = e.target.value;
    setFormData({ ...formData, seed_start_date: date });
    if (formData.plant_variety_id && date) {
      fetchTimeline(formData.plant_variety_id, date);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('/api/calendar/crops/plant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          site_id: selectedSite,
          plant_variety_id: parseInt(formData.plant_variety_id),
          quantity_planted: parseInt(formData.quantity_planted),
        }),
      });
      if (res.ok) {
        setShowPlanForm(false);
        setFormData({
          plant_variety_id: '',
          seed_start_date: '',
          bed_location: '',
          quantity_planted: 1,
          notes: '',
        });
        fetchCrops();
      }
    } catch (error) {
      console.error('Failed to plant crop:', error);
    }
  };

  const daysInMonth = (date) => new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  const firstDayOfMonth = (date) => new Date(date.getFullYear(), date.getMonth(), 1).getDay();
  const monthName = currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  const getCropsForDate = (day) => {
    const dateStr = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), day)
      .toISOString()
      .split('T')[0];
    return crops.filter(
      (crop) =>
        crop.seed_start_date === dateStr ||
        crop.expected_harvest_date === dateStr ||
        crop.transplant_date === dateStr
    );
  };

  const CalendarDay = ({ day }) => {
    const dayCrops = getCropsForDate(day);
    return (
      <div
        style={{
          minHeight: '120px',
          padding: '8px',
          borderRadius: 'var(--border-radius-md)',
          backgroundColor: 'var(--color-background-secondary)',
          border: '0.5px solid var(--color-border-tertiary)',
          fontSize: '13px',
        }}
      >
        <div style={{ fontWeight: '500', marginBottom: '8px', color: 'var(--color-text-primary)' }}>
          {day}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {dayCrops.map((crop) => (
            <div
              key={crop.id}
              onClick={() => setSelectedCrop(crop)}
              style={{
                padding: '4px 6px',
                backgroundColor: 'var(--color-background-info)',
                color: 'var(--color-text-info)',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '11px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {crop.emoji} {crop.crop_name.split(' - ')[1]}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1200px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '24px', fontWeight: '500' }}>🌱 Garden Calendar</h1>
        <button
          onClick={() => setShowPlanForm(!showPlanForm)}
          style={{
            padding: '8px 16px',
            backgroundColor: 'var(--color-background-info)',
            color: 'var(--color-text-info)',
            border: '0.5px solid var(--color-border-info)',
            borderRadius: 'var(--border-radius-md)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontWeight: '500',
          }}
        >
          <Plus size={16} /> Plan Crop
        </button>
      </div>

      {/* Site selector */}
      <div style={{ marginBottom: '2rem' }}>
        <label style={{ display: 'block', marginBottom: '8px', color: 'var(--color-text-secondary)', fontSize: '13px' }}>
          Select Site
        </label>
        <select
          value={selectedSite}
          onChange={(e) => setSelectedSite(parseInt(e.target.value))}
          style={{
            width: '100%',
            maxWidth: '300px',
            padding: '8px 12px',
            borderRadius: 'var(--border-radius-md)',
            border: '0.5px solid var(--color-border-tertiary)',
            backgroundColor: 'var(--color-background-primary)',
            color: 'var(--color-text-primary)',
          }}
        >
          {sites.map((site) => (
            <option key={site.id} value={site.id}>
              {site.friendly_name || site.site_code}
            </option>
          ))}
        </select>
      </div>

      {/* Plan form */}
      {showPlanForm && (
        <div
          style={{
            padding: '1.5rem',
            backgroundColor: 'var(--color-background-secondary)',
            borderRadius: 'var(--border-radius-lg)',
            border: '0.5px solid var(--color-border-tertiary)',
            marginBottom: '2rem',
          }}
        >
          <h2 style={{ fontSize: '18px', fontWeight: '500', marginBottom: '1rem' }}>Plan New Crop</h2>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                  Plant Type
                </label>
                <select
                  onChange={handlePlantTypeChange}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: 'var(--border-radius-md)',
                    border: '0.5px solid var(--color-border-tertiary)',
                    backgroundColor: 'var(--color-background-primary)',
                  }}
                >
                  <option value="">Select type...</option>
                  {plantTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.emoji} {type.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                  Variety
                </label>
                <select
                  value={formData.plant_variety_id}
                  onChange={handleVarietyChange}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: 'var(--border-radius-md)',
                    border: '0.5px solid var(--color-border-tertiary)',
                    backgroundColor: 'var(--color-background-primary)',
                  }}
                >
                  <option value="">Select variety...</option>
                  {varieties.map((variety) => (
                    <option key={variety.id} value={variety.id}>
                      {variety.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                  Seed Start Date
                </label>
                <input
                  type="date"
                  value={formData.seed_start_date}
                  onChange={handleSeedDateChange}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: 'var(--border-radius-md)',
                    border: '0.5px solid var(--color-border-tertiary)',
                    backgroundColor: 'var(--color-background-primary)',
                  }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                  Bed Location
                </label>
                <input
                  type="text"
                  value={formData.bed_location}
                  onChange={(e) => setFormData({ ...formData, bed_location: e.target.value })}
                  placeholder="e.g. Bed A, Pot 1"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: 'var(--border-radius-md)',
                    border: '0.5px solid var(--color-border-tertiary)',
                    backgroundColor: 'var(--color-background-primary)',
                  }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                Quantity
              </label>
              <input
                type="number"
                value={formData.quantity_planted}
                onChange={(e) => setFormData({ ...formData, quantity_planted: parseInt(e.target.value) })}
                min="1"
                style={{
                  width: '100%',
                  maxWidth: '120px',
                  padding: '8px 12px',
                  borderRadius: 'var(--border-radius-md)',
                  border: '0.5px solid var(--color-border-tertiary)',
                  backgroundColor: 'var(--color-background-primary)',
                }}
              />
            </div>

            {timeline && (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: 'var(--color-background-primary)',
                  borderRadius: 'var(--border-radius-md)',
                  border: '0.5px solid var(--color-border-info)',
                }}
              >
                <div style={{ fontSize: '13px', marginBottom: '8px' }}>
                  <strong>Timeline:</strong>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', fontSize: '12px' }}>
                  <div>
                    <div style={{ color: 'var(--color-text-secondary)' }}>Germination</div>
                    <div style={{ fontWeight: '500' }}>{timeline.germination_days} days</div>
                  </div>
                  {timeline.transplant_ready_date && (
                    <div>
                      <div style={{ color: 'var(--color-text-secondary)' }}>Transplant Ready</div>
                      <div style={{ fontWeight: '500' }}>{timeline.transplant_ready_days} days</div>
                    </div>
                  )}
                  <div>
                    <div style={{ color: 'var(--color-text-secondary)' }}>Harvest</div>
                    <div style={{ fontWeight: '500' }}>~{timeline.harvest_days_from_seed} days</div>
                  </div>
                </div>
              </div>
            )}

            {companions.length > 0 && (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: 'var(--color-background-primary)',
                  borderRadius: 'var(--border-radius-md)',
                  border: '0.5px solid var(--color-border-success)',
                }}
              >
                <div style={{ fontSize: '13px', marginBottom: '8px' }}>
                  <strong>Companion Plants:</strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {companions.map((comp) => (
                    <div key={comp.id} style={{ fontSize: '12px' }}>
                      <span style={{ fontWeight: '500' }}>{comp.companion_name}</span>
                      {comp.relationship === 'companion' ? ' ✓' : ' ✗'} — {comp.benefit || comp.notes}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                type="submit"
                style={{
                  padding: '10px 16px',
                  backgroundColor: 'var(--color-background-success)',
                  color: 'var(--color-text-success)',
                  border: '0.5px solid var(--color-border-success)',
                  borderRadius: 'var(--border-radius-md)',
                  cursor: 'pointer',
                  fontWeight: '500',
                }}
              >
                Plant Crop
              </button>
              <button
                type="button"
                onClick={() => setShowPlanForm(false)}
                style={{
                  padding: '10px 16px',
                  backgroundColor: 'transparent',
                  color: 'var(--color-text-secondary)',
                  border: '0.5px solid var(--color-border-tertiary)',
                  borderRadius: 'var(--border-radius-md)',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Calendar header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <button
          onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))}
          style={{
            padding: '8px 12px',
            backgroundColor: 'transparent',
            border: '0.5px solid var(--color-border-tertiary)',
            borderRadius: 'var(--border-radius-md)',
            cursor: 'pointer',
          }}
        >
          <ChevronLeft size={18} />
        </button>
        <h2 style={{ fontSize: '18px', fontWeight: '500' }}>{monthName}</h2>
        <button
          onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))}
          style={{
            padding: '8px 12px',
            backgroundColor: 'transparent',
            border: '0.5px solid var(--color-border-tertiary)',
            borderRadius: 'var(--border-radius-md)',
            cursor: 'pointer',
          }}
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {/* Calendar grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(7, 1fr)',
          gap: '12px',
          marginBottom: '2rem',
        }}
      >
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
          <div key={day} style={{ textAlign: 'center', fontWeight: '500', marginBottom: '8px', fontSize: '13px' }}>
            {day}
          </div>
        ))}
        {Array.from({ length: firstDayOfMonth(currentMonth) }).map((_, i) => (
          <div key={`empty-${i}`} />
        ))}
        {Array.from({ length: daysInMonth(currentMonth) }).map((_, i) => (
          <CalendarDay key={i + 1} day={i + 1} />
        ))}
      </div>

      {/* Crop detail view */}
      {selectedCrop && (
        <div
          style={{
            padding: '1.5rem',
            backgroundColor: 'var(--color-background-secondary)',
            borderRadius: 'var(--border-radius-lg)',
            border: '0.5px solid var(--color-border-tertiary)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '18px', fontWeight: '500' }}>
              {selectedCrop.emoji} {selectedCrop.crop_name}
            </h3>
            <button
              onClick={() => setSelectedCrop(null)}
              style={{
                padding: '4px 8px',
                backgroundColor: 'transparent',
                border: '0.5px solid var(--color-border-tertiary)',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '12px',
              }}
            >
              ✕
            </button>
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: '1rem',
              fontSize: '13px',
            }}
          >
            <div>
              <div style={{ color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Location</div>
              <div style={{ fontWeight: '500' }}>{selectedCrop.bed_location}</div>
            </div>
            <div>
              <div style={{ color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Quantity</div>
              <div style={{ fontWeight: '500' }}>{selectedCrop.quantity_planted}</div>
            </div>
            <div>
              <div style={{ color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Sown</div>
              <div style={{ fontWeight: '500' }}>{selectedCrop.seed_start_date}</div>
            </div>
            <div>
              <div style={{ color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Expected Harvest</div>
              <div style={{ fontWeight: '500' }}>{selectedCrop.expected_harvest_date}</div>
            </div>
            {selectedCrop.transplant_date && (
              <div>
                <div style={{ color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Transplant</div>
                <div style={{ fontWeight: '500' }}>{selectedCrop.transplant_date}</div>
              </div>
            )}
            <div>
              <div style={{ color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Status</div>
              <div style={{ fontWeight: '500' }}>{selectedCrop.status}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}