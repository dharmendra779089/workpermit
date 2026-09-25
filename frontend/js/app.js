/**
 * Opmaint CMMS — Frontend Application Controller (Vanilla JS ES6+)
 * Manages views, dynamic wizard form generation from schemas, countdown timers,
 * digital canvas signatures, state transitions, and responsive plant floor mode.
 */

class AppController {
  constructor() {
    this.currentUser = null;
    this.permitTypes = [];
    this.plants = [];
    this.areas = [];
    this.equipment = [];
    this.currentPermit = null;
    this.activeFilters = {
      status: '',
      permit_type: '',
      plant: '',
      area: '',
      search: '',
      expiring_soon: '',
      my_approvals: ''
    };
    this.wizardData = {
      step: 1,
      permit_type: '',
      type_data: {},
      hazards: [],
      ppe_required: [],
      precautions: []
    };
    this.countdownInterval = null;
    this.searchDebounceTimer = null;
    this.canvasSignature = null;
    this.isDrawing = false;
  }

  async init() {
    console.log("Initializing Opmaint CMMS PTW Module...");
    this.initCanvasSignature();
    
    // Check if user is logged in
    const storedUser = localStorage.getItem('opmaint_current_user');
    if (storedUser && window.api.token) {
      try {
        this.currentUser = JSON.parse(storedUser);
        this.updateUserUI();
      } catch (e) {
        this.currentUser = null;
      }
    }

    // If no user, default login as Requester for seamless demo inspection
    if (!this.currentUser) {
      await this.quickLogin('requester@opmaint.com');
    }

    // Load master data
    await this.loadMasterData();

    // Start live countdown ticker
    this.startCountdownTicker();

    // Load dashboard
    await this.fetchDashboardStats();
    await this.fetchPermits();
  }

  // --- Auth & Role Switching ---
  async quickLogin(username) {
    try {
      this.showToast('Switching role...', 'info');
      const res = await window.api.login(username, 'SafetyFirst@2026');
      this.currentUser = res.user;
      this.updateUserUI();
      this.showToast(`Active Role: ${this.currentUser.full_name} (${this.currentUser.role_display})`, 'success');

      // Refresh permits and stats with new role context
      await this.fetchDashboardStats();
      await this.fetchPermits();

      // If viewing detail, refresh detail view for role action bar
      if (this.currentPermit) {
        await this.loadPermitDetail(this.currentPermit.id);
      }
    } catch (err) {
      this.showToast(`Login failed: ${err.message}`, 'error');
    }
  }

  updateUserUI() {
    if (!this.currentUser) return;
    const nameEl = document.getElementById('user-display-name');
    const roleEl = document.getElementById('user-display-role');
    const initialsEl = document.getElementById('user-avatar-initials');

    if (nameEl) nameEl.textContent = this.currentUser.full_name || this.currentUser.username;
    if (roleEl) roleEl.textContent = this.currentUser.role_display;
    if (initialsEl) {
      const parts = (this.currentUser.full_name || this.currentUser.username).split(' ');
      initialsEl.textContent = parts.map(p => p[0]).join('').substring(0, 2).toUpperCase();
    }

    // Highlight active role button in header
    document.querySelectorAll('.role-btn').forEach(btn => btn.classList.remove('active-role'));
    const roleMap = {
      'REQUESTER': '.role-req',
      'AREA_OWNER': '.role-ao',
      'SAFETY_OFFICER': '.role-so',
      'ADMIN': '.role-admin'
    };
    const selector = roleMap[this.currentUser.role];
    if (selector) {
      const target = document.querySelector(selector);
      if (target) target.classList.add('active-role');
    }
  }

  logout() {
    window.api.clearTokens();
    this.currentUser = null;
    this.showToast('Logged out. Re-authenticating...', 'info');
    this.quickLogin('requester@opmaint.com');
  }

  // --- Master Data ---
  async loadMasterData() {
    try {
      const [typesRes, plantsRes, areasRes, eqRes] = await Promise.all([
        window.api.getPermitTypes(),
        window.api.getPlants(),
        window.api.getAreas(),
        window.api.getEquipment()
      ]);

      this.permitTypes = typesRes || [];
      this.plants = plantsRes || [];
      this.areas = areasRes || [];
      this.equipment = eqRes || [];

      this.populateFilterDropdowns();
      this.populateWizardDropdowns();
    } catch (err) {
      console.error("Error loading master data:", err);
    }
  }

  populateFilterDropdowns() {
    const plantSelect = document.getElementById('filter-plant');
    if (plantSelect) {
      plantSelect.innerHTML = '<option value="">All Plants</option>';
      this.plants.forEach(p => {
        plantSelect.innerHTML += `<option value="${p.id}">${p.name} [${p.code}]</option>`;
      });
    }

    const areaSelect = document.getElementById('filter-area');
    if (areaSelect) {
      areaSelect.innerHTML = '<option value="">All Areas</option>';
      this.areas.forEach(a => {
        areaSelect.innerHTML += `<option value="${a.id}">${a.name}</option>`;
      });
    }
  }

  onPlantFilterChange() {
    const plantId = document.getElementById('filter-plant').value;
    const areaSelect = document.getElementById('filter-area');
    if (!areaSelect) return;

    areaSelect.innerHTML = '<option value="">All Areas</option>';
    const filteredAreas = plantId ? this.areas.filter(a => a.plant == plantId) : this.areas;
    filteredAreas.forEach(a => {
      areaSelect.innerHTML += `<option value="${a.id}">${a.name}</option>`;
    });

    this.fetchPermits();
  }

  // --- Dashboard & Permits Listing ---
  async fetchDashboardStats() {
    try {
      const stats = await window.api.getDashboardStats();
      document.getElementById('kpi-active').textContent = stats.active_count;
      document.getElementById('kpi-expiring').textContent = stats.expiring_soon_count;
      document.getElementById('kpi-pending-approval').textContent = stats.pending_my_approval_count;
      document.getElementById('kpi-suspended').textContent = stats.suspended_count;
      document.getElementById('kpi-total').textContent = stats.total_permits;

      // Pulse badge if approvals pending
      const pendingBadge = document.getElementById('kpi-pending-badge');
      if (pendingBadge) {
        if (stats.pending_my_approval_count > 0) {
          pendingBadge.classList.add('badge-warning');
          pendingBadge.textContent = `${stats.pending_my_approval_count} Actionable`;
        } else {
          pendingBadge.classList.remove('badge-warning');
          pendingBadge.textContent = 'None';
        }
      }
    } catch (err) {
      console.error("Failed to load KPI stats:", err);
    }
  }

  async fetchPermits() {
    try {
      this.activeFilters.search = document.getElementById('filter-search').value.trim();
      this.activeFilters.status = document.getElementById('filter-status').value;
      this.activeFilters.permit_type = document.getElementById('filter-type').value;
      this.activeFilters.plant = document.getElementById('filter-plant').value;
      this.activeFilters.area = document.getElementById('filter-area').value;

      const permits = await window.api.getPermits(this.activeFilters);
      this.renderPermitsTable(permits);
    } catch (err) {
      console.error("Failed to fetch permits:", err);
      this.showToast(`Error fetching permits: ${err.message}`, 'error');
    }
  }

  debouncedFetchPermits() {
    clearTimeout(this.searchDebounceTimer);
    this.searchDebounceTimer = setTimeout(() => {
      this.fetchPermits();
    }, 300);
  }

  renderPermitsTable(permits) {
    const tbody = document.getElementById('permits-table-body');
    const emptyState = document.getElementById('permits-empty-state');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!permits || permits.length === 0) {
      emptyState.style.display = 'block';
      return;
    }
    emptyState.style.display = 'none';

    permits.forEach(p => {
      const row = document.createElement('tr');
      row.className = 'permit-row';
      row.onclick = (e) => {
        // Prevent trigger if clicking an action button directly
        if (!e.target.closest('button')) {
          this.loadPermitDetail(p.id);
        }
      };

      // Type Badge styling
      const typeColor = p.type_meta?.color || '#3b82f6';
      const statusClass = `status-${p.status.toLowerCase()}`;

      // Validity & Countdown Cell
      let countdownHtml = '';
      if (p.status === 'ACTIVE' || p.status === 'APPROVED') {
        const isUrgent = p.is_expiring_soon;
        const formattedTime = this.formatSeconds(p.seconds_remaining);
        countdownHtml = `
          <div class="countdown-cell ${isUrgent ? 'countdown-urgent' : 'countdown-live'}" data-permit-id="${p.id}" data-seconds="${p.seconds_remaining}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <span class="timer-display">${formattedTime}</span>
            ${isUrgent ? '<span class="kpi-badge badge-warning" style="margin-left:4px;">&lt; 2h</span>' : ''}
          </div>
        `;
      } else {
        countdownHtml = `<span class="countdown-ended">&mdash;</span>`;
      }

      // Quick action button
      let actionBtnHtml = '';
      if (p.needs_my_approval) {
        actionBtnHtml = `<button class="btn-table-action btn-action-primary" onclick="app.openApproveModal(${p.id})">Approve</button>`;
      } else {
        actionBtnHtml = `<button class="btn-table-action" onclick="app.loadPermitDetail(${p.id})">View</button>`;
      }

      row.innerHTML = `
        <td>
          <div class="permit-code-cell">
            <span class="permit-number-badge">${p.permit_number}</span>
            <span class="type-pill" style="background:${typeColor}22; color:${typeColor}; border:1px solid ${typeColor}44;">
              ${p.permit_type_display}
            </span>
          </div>
        </td>
        <td>
          <div class="permit-title-cell">
            <div class="permit-title-text" title="${p.title}">${p.title}</div>
            <span class="permit-eq-tag">${p.equipment_tag} &bull; ${p.equipment_name}</span>
          </div>
        </td>
        <td>
          <div class="location-stack">
            <span class="loc-plant">${p.plant_name}</span>
            <span class="loc-area">${p.area_name}</span>
          </div>
        </td>
        <td>
          <span class="status-pill ${statusClass}">
            <span class="status-dot"></span>
            ${p.status_display}
          </span>
        </td>
        <td>
          ${countdownHtml}
        </td>
        <td>
          <div class="party-stack">
            <span class="party-requester">${p.requester_name}</span>
            <span class="party-contractor">${p.contractor_name} (${p.team_size} pax)</span>
          </div>
        </td>
        <td class="text-right">
          <div class="action-buttons-cell">
            ${actionBtnHtml}
          </div>
        </td>
      `;

      tbody.appendChild(row);
    });
  }

  // --- Live Countdown Ticker ---
  startCountdownTicker() {
    if (this.countdownInterval) clearInterval(this.countdownInterval);
    this.countdownInterval = setInterval(() => {
      // 1. Update table countdown cells
      document.querySelectorAll('.countdown-cell[data-seconds]').forEach(el => {
        let sec = parseInt(el.getAttribute('data-seconds'), 10);
        if (sec > 0) {
          sec--;
          el.setAttribute('data-seconds', sec);
          const display = el.querySelector('.timer-display');
          if (display) display.textContent = this.formatSeconds(sec);
          if (sec <= 7200 && !el.classList.contains('countdown-urgent')) {
            el.classList.add('countdown-urgent');
          }
        } else {
          const display = el.querySelector('.timer-display');
          if (display) display.textContent = 'Expired';
          el.classList.remove('countdown-live', 'countdown-urgent');
          el.classList.add('countdown-ended');
        }
      });

      // 2. Update detail view countdown
      if (this.currentPermit && this.currentPermit.seconds_remaining !== undefined) {
        if (this.currentPermit.seconds_remaining > 0) {
          this.currentPermit.seconds_remaining--;
          const timerEl = document.getElementById('detail-countdown-timer');
          if (timerEl) {
            timerEl.textContent = this.formatSeconds(this.currentPermit.seconds_remaining);
            if (this.currentPermit.seconds_remaining <= 7200) {
              timerEl.classList.add('warning');
            }
          }
        } else {
          const timerEl = document.getElementById('detail-countdown-timer');
          if (timerEl) {
            timerEl.textContent = 'EXPIRED';
            timerEl.classList.add('expired');
          }
        }
      }
    }, 1000);
  }

  formatSeconds(seconds) {
    if (seconds <= 0) return '00:00:00';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  // Quick Filter Toggles
  setQuickFilter(key, val) {
    if (key === 'status') {
      document.getElementById('filter-status').value = val;
    } else if (key === 'expiring_soon') {
      this.activeFilters.expiring_soon = 'true';
    }
    this.fetchPermits();
  }

  toggleMyApprovals() {
    const btn = document.getElementById('btn-toggle-my-approvals');
    if (this.activeFilters.my_approvals === 'true') {
      this.activeFilters.my_approvals = '';
      btn.classList.remove('active');
    } else {
      this.activeFilters.my_approvals = 'true';
      btn.classList.add('active');
    }
    this.fetchPermits();
  }

  clearFilters() {
    document.getElementById('filter-search').value = '';
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-plant').value = '';
    document.getElementById('filter-area').value = '';
    document.getElementById('btn-toggle-my-approvals').classList.remove('active');
    this.activeFilters = {
      status: '', permit_type: '', plant: '', area: '', search: '', expiring_soon: '', my_approvals: ''
    };
    this.fetchPermits();
  }

  // --- Navigation & View Switching ---
  showDashboard() {
    this.hideAllViews();
    document.getElementById('view-dashboard').classList.add('active');
    document.getElementById('nav-dashboard-btn').classList.add('active');
    this.fetchDashboardStats();
    this.fetchPermits();
  }

  showCreatePermit() {
    this.hideAllViews();
    document.getElementById('view-create').classList.add('active');
    document.getElementById('nav-create-btn').classList.add('active');
    this.resetWizardForm();
  }

  hideAllViews() {
    document.querySelectorAll('.view-section').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-link').forEach(n => n.classList.remove('active'));
  }

  // --- SCREEN 2: WIZARD & DYNAMIC EXTENSIBLE FORM CREATION ---
  resetWizardForm() {
    this.wizardData = {
      step: 1,
      permit_type: this.permitTypes[0]?.code || 'HOT_WORK',
      type_data: {},
      hazards: [],
      ppe_required: [],
      precautions: []
    };

    // Render Type Selection Cards
    const container = document.getElementById('type-selector-buttons');
    if (container) {
      container.innerHTML = '';
      this.permitTypes.forEach(t => {
        const card = document.createElement('div');
        card.className = `type-select-card ${t.code === this.wizardData.permit_type ? 'selected' : ''}`;
        card.onclick = () => this.selectPermitType(t.code);
        card.innerHTML = `
          <div class="type-card-name" style="color: ${t.color};">${t.name}</div>
          <div class="type-card-desc">${t.description}</div>
        `;
        container.appendChild(card);
      });
    }

    // Set defaults in form
    document.getElementById('form-permit-type-input').value = this.wizardData.permit_type;
    document.getElementById('form-title').value = '';
    document.getElementById('form-description').value = '';
    document.getElementById('form-contractor').value = '';
    document.getElementById('form-team-size').value = 2;

    // Set default datetimes (Start: now + 30 mins, End: now + 8 hrs)
    const now = new Date();
    now.setMinutes(now.getMinutes() + 30);
    const endTime = new Date(now);
    endTime.setHours(endTime.getHours() + 8);

    document.getElementById('form-start-time').value = this.toLocalISO(now);
    document.getElementById('form-end-time').value = this.toLocalISO(endTime);

    this.goToStep(1);
  }

  toLocalISO(d) {
    const pad = (n) => n.toString().padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  selectPermitType(typeCode) {
    this.wizardData.permit_type = typeCode;
    document.getElementById('form-permit-type-input').value = typeCode;

    document.querySelectorAll('.type-select-card').forEach(c => {
      c.classList.remove('selected');
    });
    event.currentTarget.classList.add('selected');
  }

  populateWizardDropdowns() {
    const plantSelect = document.getElementById('form-plant');
    if (plantSelect) {
      plantSelect.innerHTML = '<option value="">Select Plant...</option>';
      this.plants.forEach(p => {
        plantSelect.innerHTML += `<option value="${p.id}">${p.name} [${p.code}]</option>`;
      });
    }
  }

  onWizardPlantChange() {
    const plantId = document.getElementById('form-plant').value;
    const areaSelect = document.getElementById('form-area');
    const eqSelect = document.getElementById('form-equipment');

    areaSelect.innerHTML = '<option value="">Select Area...</option>';
    eqSelect.innerHTML = '<option value="">Select Equipment...</option>';
    eqSelect.disabled = true;

    if (!plantId) {
      areaSelect.disabled = true;
      return;
    }

    areaSelect.disabled = false;
    const areas = this.areas.filter(a => a.plant == plantId);
    areas.forEach(a => {
      areaSelect.innerHTML += `<option value="${a.id}">${a.name} (${a.code})</option>`;
    });
  }

  onWizardAreaChange() {
    const areaId = document.getElementById('form-area').value;
    const eqSelect = document.getElementById('form-equipment');

    eqSelect.innerHTML = '<option value="">Select Equipment...</option>';
    if (!areaId) {
      eqSelect.disabled = true;
      return;
    }

    eqSelect.disabled = false;
    const eqs = this.equipment.filter(e => e.area == areaId);
    eqs.forEach(e => {
      eqSelect.innerHTML += `<option value="${e.id}">${e.tag_number} - ${e.name} [${e.criticality}]</option>`;
    });
  }

  goToStep(stepNumber) {
    this.wizardData.step = stepNumber;

    // Update wizard nav indicators
    document.querySelectorAll('.wizard-step').forEach((s, idx) => {
      s.classList.toggle('active', idx + 1 === stepNumber);
    });

    document.querySelectorAll('.step-indicator').forEach((ind, idx) => {
      const num = idx + 1;
      ind.classList.toggle('active', num === stepNumber);
      ind.classList.toggle('completed', num < stepNumber);
    });

    // Step-specific initializations
    if (stepNumber === 2) {
      this.renderDynamicSchemaFields();
    } else if (stepNumber === 3) {
      this.renderSafetyChecklists();
    } else if (stepNumber === 4) {
      this.renderReviewAndConflictCheck();
    }
  }

  validateAndNextStep(currentStep) {
    if (currentStep === 1) {
      const type = document.getElementById('form-permit-type-input').value;
      const title = document.getElementById('form-title').value.trim();
      const desc = document.getElementById('form-description').value.trim();
      const eq = document.getElementById('form-equipment').value;
      const contractor = document.getElementById('form-contractor').value.trim();
      const start = document.getElementById('form-start-time').value;
      const end = document.getElementById('form-end-time').value;

      if (!type || !title || !desc || !eq || !contractor || !start || !end) {
        this.showToast('Please fill all mandatory general and location fields.', 'warning');
        return;
      }

      if (new Date(end) <= new Date(start)) {
        this.showToast('Planned end time must be after planned start time.', 'error');
        return;
      }

      this.goToStep(2);
    } else if (currentStep === 2) {
      // Validate dynamic fields
      const typeSchema = this.permitTypes.find(t => t.code === this.wizardData.permit_type);
      if (typeSchema && typeSchema.fields) {
        const typeData = {};
        for (const f of typeSchema.fields) {
          const inputEl = document.getElementById(`dyn-field-${f.name}`);
          if (!inputEl) continue;

          let val = null;
          if (f.type === 'boolean') {
            val = inputEl.checked;
          } else {
            val = inputEl.value.trim();
          }

          if (f.required && (val === '' || val === null)) {
            this.showToast(`Field '${f.label}' is mandatory for ${typeSchema.name}.`, 'warning');
            inputEl.focus();
            return;
          }

          // Specific gas validations
          if (f.name === 'gas_test_lel_pct' && parseFloat(val) >= 10.0) {
            this.showToast('SAFETY ALERT: Combustible gas LEL is >= 10%. Hot work strictly prohibited!', 'error');
            inputEl.focus();
            return;
          }

          typeData[f.name] = val;
        }
        this.wizardData.type_data = typeData;
      }
      this.goToStep(3);
    } else if (currentStep === 3) {
      // Gather checked hazards, PPE, and precautions
      this.wizardData.hazards = Array.from(document.querySelectorAll('#checklist-hazards input:checked')).map(el => el.value);
      this.wizardData.ppe_required = Array.from(document.querySelectorAll('#checklist-ppe input:checked')).map(el => el.value);
      this.wizardData.precautions = Array.from(document.querySelectorAll('#checklist-precautions input:checked')).map(el => el.value);

      if (this.wizardData.precautions.length === 0) {
        this.showToast('You must verify at least one safety precaution checkbox.', 'warning');
        return;
      }

      this.goToStep(4);
    }
  }

  // --- Dynamic Schema Field Renderer ---
  renderDynamicSchemaFields() {
    const typeSchema = this.permitTypes.find(t => t.code === this.wizardData.permit_type);
    const container = document.getElementById('dynamic-schema-fields-container');
    const badgeEl = document.getElementById('step-2-type-badge');
    const descEl = document.getElementById('step-2-type-description');

    if (!typeSchema || !container) return;

    badgeEl.textContent = typeSchema.name;
    badgeEl.style.backgroundColor = `${typeSchema.color}22`;
    badgeEl.style.color = typeSchema.color;
    badgeEl.style.border = `1px solid ${typeSchema.color}55`;
    descEl.textContent = typeSchema.description;

    container.innerHTML = '';

    typeSchema.fields.forEach(f => {
      const fieldDiv = document.createElement('div');
      fieldDiv.className = `form-group ${f.type === 'textarea' ? 'full-width' : ''}`;

      const requiredMarker = f.required ? '<span class="required">*</span>' : '';
      const unitLabel = f.unit ? `<span class="unit-tag">(${f.unit})</span>` : '';
      const labelHtml = `<label for="dyn-field-${f.name}">${f.label} ${unitLabel} ${requiredMarker}</label>`;

      let inputHtml = '';
      const existingVal = this.wizardData.type_data[f.name] !== undefined ? this.wizardData.type_data[f.name] : (f.placeholder || '');

      if (f.type === 'select') {
        const optionsHtml = f.options.map(opt => `<option value="${opt}" ${existingVal === opt ? 'selected' : ''}>${opt}</option>`).join('');
        inputHtml = `<select id="dyn-field-${f.name}">${optionsHtml}</select>`;
      } else if (f.type === 'textarea') {
        inputHtml = `<textarea id="dyn-field-${f.name}" rows="3" placeholder="${f.placeholder || ''}">${existingVal}</textarea>`;
      } else if (f.type === 'boolean') {
        inputHtml = `
          <label class="custom-checkbox-tag" style="margin-top:6px;">
            <input type="checkbox" id="dyn-field-${f.name}" ${existingVal ? 'checked' : ''}>
            <span>Confirm: ${f.label}</span>
          </label>
        `;
      } else if (f.type === 'number') {
        inputHtml = `<input type="number" id="dyn-field-${f.name}" step="${f.step || 'any'}" min="${f.min || ''}" max="${f.max || ''}" value="${existingVal}" placeholder="${f.placeholder || ''}">`;
      } else if (f.type === 'datetime-local') {
        const defaultTime = existingVal || this.toLocalISO(new Date());
        inputHtml = `<input type="datetime-local" id="dyn-field-${f.name}" value="${defaultTime}">`;
      } else {
        inputHtml = `<input type="text" id="dyn-field-${f.name}" value="${existingVal}" placeholder="${f.placeholder || ''}">`;
      }

      const helpHtml = f.help_text ? `<span class="input-hint">${f.help_text}</span>` : '';
      fieldDiv.innerHTML = `${labelHtml}${inputHtml}${helpHtml}`;
      container.appendChild(fieldDiv);
    });
  }

  // --- Step 3: Safety Checklists ---
  renderSafetyChecklists() {
    const typeSchema = this.permitTypes.find(t => t.code === this.wizardData.permit_type);
    if (!typeSchema) return;

    // Hazards
    const hazardsContainer = document.getElementById('checklist-hazards');
    hazardsContainer.innerHTML = '';
    (typeSchema.default_hazards || []).forEach((h, idx) => {
      const isChecked = this.wizardData.hazards.includes(h) || this.wizardData.hazards.length === 0;
      hazardsContainer.innerHTML += `
        <label class="custom-checkbox-tag">
          <input type="checkbox" value="${h}" ${isChecked ? 'checked' : ''}>
          <span>${h}</span>
        </label>
      `;
    });

    // PPE
    const ppeContainer = document.getElementById('checklist-ppe');
    ppeContainer.innerHTML = '';
    (typeSchema.default_ppe || []).forEach((p, idx) => {
      const isChecked = this.wizardData.ppe_required.includes(p) || this.wizardData.ppe_required.length === 0;
      ppeContainer.innerHTML += `
        <label class="custom-checkbox-tag">
          <input type="checkbox" value="${p}" ${isChecked ? 'checked' : ''}>
          <span>${p}</span>
        </label>
      `;
    });

    // Precautions
    const precContainer = document.getElementById('checklist-precautions');
    precContainer.innerHTML = '';
    (typeSchema.default_precautions || []).forEach((item, idx) => {
      const isChecked = this.wizardData.precautions.includes(item) || this.wizardData.precautions.length === 0;
      precContainer.innerHTML += `
        <label class="checkbox-list-item">
          <input type="checkbox" value="${item}" ${isChecked ? 'checked' : ''}>
          <span>${item}</span>
        </label>
      `;
    });
  }

  // --- Step 4: Spatial Conflict Check & Review ---
  async renderReviewAndConflictCheck() {
    const eqId = document.getElementById('form-equipment').value;
    const start = document.getElementById('form-start-time').value;
    const end = document.getElementById('form-end-time').value;
    const type = this.wizardData.permit_type;

    const conflictBox = document.getElementById('conflict-detection-result');
    conflictBox.className = 'conflict-check-box';
    conflictBox.innerHTML = '<span class="spinner-small"></span> Scanning for spatial safety conflicts with other active permits...';

    // Call Pre-Check Conflicts API
    try {
      const res = await window.api.preCheckConflicts({
        equipment_id: eqId,
        planned_start: new Date(start).toISOString(),
        planned_end: new Date(end).toISOString(),
        permit_type: type
      });

      if (res.conflicts && res.conflicts.length > 0) {
        conflictBox.className = 'conflict-check-box has-conflict';
        let conflictHtml = '<strong>SAFETY CONFLICT DETECTED:</strong><ul style="margin-top:6px; margin-left:18px;">';
        res.conflicts.forEach(c => {
          conflictHtml += `<li>${c.message}</li>`;
        });
        conflictHtml += '</ul><p style="margin-top:8px; font-size:0.8rem;">Proceeding will flag this permit for heightened safety review.</p>';
        conflictBox.innerHTML = conflictHtml;
      } else {
        conflictBox.className = 'conflict-check-box no-conflict';
        conflictBox.innerHTML = '<strong>✔ No Spatial or Temporal Clashes:</strong> Equipment area is clear of conflicting hot work or confined space permits.';
      }
    } catch (err) {
      conflictBox.className = 'conflict-check-box no-conflict';
      conflictBox.innerHTML = 'Conflict scanner ready.';
    }

    // Populate review summary
    const summaryContainer = document.getElementById('wizard-review-summary');
    const eq = this.equipment.find(e => e.id == eqId);
    const typeSchema = this.permitTypes.find(t => t.code === type);

    summaryContainer.innerHTML = `
      <div class="info-item">
        <span class="info-label">Permit Type</span>
        <span class="info-val" style="color:${typeSchema?.color}">${typeSchema?.name}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Title</span>
        <span class="info-val">${document.getElementById('form-title').value}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Equipment</span>
        <span class="info-val">${eq ? `${eq.tag_number} (${eq.name})` : ''}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Contractor</span>
        <span class="info-val">${document.getElementById('form-contractor').value} (${document.getElementById('form-team-size').value} pax)</span>
      </div>
      <div class="info-item">
        <span class="info-label">Planned Window</span>
        <span class="info-val">${start.replace('T', ' ')} to ${end.replace('T', ' ')}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Hazards & PPE</span>
        <span class="info-val">${this.wizardData.hazards.length} Hazards, ${this.wizardData.ppe_required.length} PPE items</span>
      </div>
    `;
  }

  async submitPermitForm(submitImmediately = false) {
    try {
      const payload = {
        permit_type: this.wizardData.permit_type,
        title: document.getElementById('form-title').value.trim(),
        description: document.getElementById('form-description').value.trim(),
        contractor_name: document.getElementById('form-contractor').value.trim(),
        team_size: parseInt(document.getElementById('form-team-size').value, 10),
        equipment: parseInt(document.getElementById('form-equipment').value, 10),
        planned_start: new Date(document.getElementById('form-start-time').value).toISOString(),
        planned_end: new Date(document.getElementById('form-end-time').value).toISOString(),
        hazards: this.wizardData.hazards,
        ppe_required: this.wizardData.ppe_required,
        precautions: this.wizardData.precautions,
        type_data: this.wizardData.type_data,
        submit_immediately: submitImmediately
      };

      this.showToast('Saving permit...', 'info');
      const newPermit = await window.api.createPermit(payload);

      this.showToast(
        submitImmediately ? `Permit ${newPermit.permit_number} submitted for approval!` : `Draft ${newPermit.permit_number} saved!`,
        'success'
      );

      this.loadPermitDetail(newPermit.id);
    } catch (err) {
      console.error("Submit permit failed:", err);
      this.showToast(`Error: ${err.message}`, 'error');
    }
  }

  // --- SCREEN 3: PERMIT DETAIL & ACTION HUB ---
  async loadPermitDetail(permitId) {
    try {
      const permit = await window.api.getPermit(permitId);
      this.currentPermit = permit;
      this.renderPermitDetail(permit);
      this.hideAllViews();
      document.getElementById('view-detail').classList.add('active');
    } catch (err) {
      console.error("Failed to load permit detail:", err);
      this.showToast(`Error loading permit: ${err.message}`, 'error');
    }
  }

  renderPermitDetail(p) {
    document.getElementById('detail-number').textContent = p.permit_number;
    document.getElementById('detail-title').textContent = p.title;

    // Type badge
    const typeBadge = document.getElementById('detail-type-badge');
    const typeColor = p.type_meta?.color || '#3b82f6';
    typeBadge.textContent = p.permit_type_display;
    typeBadge.style.backgroundColor = `${typeColor}22`;
    typeBadge.style.color = typeColor;
    typeBadge.style.border = `1px solid ${typeColor}55`;

    // Status pill
    const statusPill = document.getElementById('detail-status-pill');
    statusPill.className = `status-pill status-${p.status.toLowerCase()}`;
    statusPill.textContent = p.status_display;

    // Location Breadcrumbs
    document.getElementById('detail-location-breadcrumbs').textContent = `${p.plant_name} > ${p.area_name} > ${p.equipment_tag} (${p.equipment_name})`;

    // Conflict Banner
    const conflictBanner = document.getElementById('detail-conflict-banner');
    if (p.conflicts && p.conflicts.length > 0) {
      conflictBanner.style.display = 'flex';
      conflictBanner.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <div>
          <strong>SAFETY WARNING:</strong> ${p.conflicts[0].message}
        </div>
      `;
    } else {
      conflictBanner.style.display = 'none';
    }

    // Live Countdown
    const countdownTimer = document.getElementById('detail-countdown-timer');
    const countdownSub = document.getElementById('detail-countdown-sub');
    if (p.status === 'ACTIVE' || p.status === 'APPROVED') {
      countdownTimer.textContent = this.formatSeconds(p.seconds_remaining);
      countdownTimer.className = 'countdown-digits' + (p.is_expiring_soon ? ' warning' : '');
      countdownSub.textContent = p.status === 'ACTIVE' ? 'Active Work Window' : 'Pre-start Window';
    } else {
      countdownTimer.textContent = p.status_display.toUpperCase();
      countdownTimer.className = 'countdown-digits expired';
      countdownSub.textContent = 'Status State';
    }

    // General Info Grid
    document.getElementById('detail-requester').textContent = p.requester_name;
    document.getElementById('detail-contractor').textContent = p.contractor_name;
    document.getElementById('detail-team-size').textContent = `${p.team_size} Personnel`;
    document.getElementById('detail-window').textContent = `${this.formatDateTime(p.planned_start)} — ${this.formatDateTime(p.planned_end)}`;
    document.getElementById('detail-actual-start').textContent = p.actual_start ? this.formatDateTime(p.actual_start) : '—';
    document.getElementById('detail-actual-end').textContent = p.actual_end ? this.formatDateTime(p.actual_end) : '—';
    document.getElementById('detail-description').textContent = p.description;

    // Dynamic Type Data Grid
    this.renderDetailTypeData(p);

    // Risk Assessment: Hazards & PPE
    const hazardsEl = document.getElementById('detail-hazards-list');
    hazardsEl.innerHTML = '';
    (p.hazards || []).forEach(h => {
      hazardsEl.innerHTML += `<span class="hazard-chip">${h}</span>`;
    });

    const ppeEl = document.getElementById('detail-ppe-list');
    ppeEl.innerHTML = '';
    (p.ppe_required || []).forEach(ppe => {
      ppeEl.innerHTML += `<span class="ppe-chip">${ppe}</span>`;
    });

    const precEl = document.getElementById('detail-precautions-list');
    precEl.innerHTML = '';
    (p.precautions || []).forEach(pr => {
      precEl.innerHTML += `<li>${pr}</li>`;
    });

    // Closure block if closed
    const closureCard = document.getElementById('detail-closure-card');
    const closureContent = document.getElementById('detail-closure-content');
    if (p.status === 'CLOSED' || p.status === 'CLOSED_VERIFIED') {
      closureCard.style.display = 'block';
      closureContent.innerHTML = `
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Work Completed At</span>
            <span class="info-val">${this.formatDateTime(p.closed_at)}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Safety Officer Verification</span>
            <span class="info-val">${p.closure_verified_by_name ? `Verified by ${p.closure_verified_by_name} (${this.formatDateTime(p.closure_verified_at)})` : '<span style="color:#f59e0b">Pending Safety Officer Walk-around</span>'}</span>
          </div>
        </div>
        <p><strong>Requester Notes:</strong> ${p.completion_notes || 'None'}</p>
        ${p.closure_verification_notes ? `<p style="margin-top:8px;"><strong>Safety Verification Notes:</strong> ${p.closure_verification_notes}</p>` : ''}
      `;
    } else {
      closureCard.style.display = 'none';
    }

    // Approvals Trail
    this.renderDetailApprovals(p);

    // Audit Trail Timeline
    this.renderDetailAuditTimeline(p);

    // Role-gated Dynamic Action Bar
    this.renderDetailActionBar(p);
  }

  renderDetailTypeData(p) {
    const grid = document.getElementById('detail-type-data-grid');
    grid.innerHTML = '';

    const typeSchema = this.permitTypes.find(t => t.code === p.permit_type);
    const fieldMap = {};
    if (typeSchema && typeSchema.fields) {
      typeSchema.fields.forEach(f => fieldMap[f.name] = f);
    }

    const typeData = p.type_data || {};
    if (Object.keys(typeData).length === 0) {
      grid.innerHTML = '<span style="color:var(--text-muted)">No specialized type parameters logged.</span>';
      return;
    }

    for (const [key, val] of Object.entries(typeData)) {
      const fDef = fieldMap[key];
      const label = fDef ? fDef.label : key.replace(/_/g, ' ').toUpperCase();
      const unit = fDef?.unit ? ` ${fDef.unit}` : '';
      let displayVal = val;

      if (typeof val === 'boolean') {
        displayVal = val ? '✔ YES (Verified)' : '✖ NO';
      }

      grid.innerHTML += `
        <div class="type-data-item">
          <span class="info-label">${label}</span>
          <div class="type-data-val">${displayVal}${unit}</div>
        </div>
      `;
    }
  }

  renderDetailApprovals(p) {
    const container = document.getElementById('detail-approvals-list');
    container.innerHTML = '';

    if (!p.approvals || p.approvals.length === 0) {
      container.innerHTML = '<span style="color:var(--text-muted)">No sign-offs required or submitted yet.</span>';
      return;
    }

    p.approvals.forEach(app => {
      const card = document.createElement('div');
      card.className = `approval-card ${app.status.toLowerCase()}`;
      card.innerHTML = `
        <div class="approval-header">
          <span class="approval-role">${app.role_type_display}</span>
          <span class="status-pill status-${app.status.toLowerCase()}">${app.status_display}</span>
        </div>
        <div class="approver-name">${app.approver_name}</div>
        ${app.acted_at ? `<div style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono); margin-top:2px;">Acted: ${this.formatDateTime(app.acted_at)}</div>` : ''}
        ${app.comment ? `<div class="approval-comment">"${app.comment}"</div>` : ''}
        ${app.signature_data ? `<div class="signature-preview"><img src="${app.signature_data}" alt="Digital Signature" height="36"></div>` : ''}
      `;
      container.appendChild(card);
    });
  }

  renderDetailAuditTimeline(p) {
    const container = document.getElementById('detail-audit-timeline');
    container.innerHTML = '';

    if (!p.audit_logs || p.audit_logs.length === 0) {
      container.innerHTML = '<span style="color:var(--text-muted)">Audit log is empty.</span>';
      return;
    }

    // Chronological order
    p.audit_logs.forEach(log => {
      const item = document.createElement('div');
      item.className = 'audit-item';
      item.innerHTML = `
        <div class="audit-meta">
          <span class="audit-action">${log.action}</span>
          <span class="audit-time">${this.formatDateTime(log.timestamp)}</span>
        </div>
        <div class="audit-actor">${log.actor_name} &bull; <span style="color:var(--text-muted); font-size:0.75rem;">${log.actor_role}</span></div>
        ${log.from_status !== 'NONE' ? `<div style="font-size:0.72rem; color:var(--text-muted); font-family:var(--font-mono);">Transition: ${log.from_status} &rarr; ${log.to_status}</div>` : ''}
        ${log.comment ? `<div class="audit-comment">${log.comment}</div>` : ''}
      `;
      container.appendChild(item);
    });
  }

  // --- Dynamic Role-Gated Action Bar ---
  renderDetailActionBar(p) {
    const container = document.getElementById('detail-actions-container');
    container.innerHTML = '';

    const actions = p.available_actions || [];

    // QR Code button (Always available for site walk-around)
    container.innerHTML += `
      <button class="btn-secondary" onclick="app.openQrModal('${p.permit_number}')" title="Scan QR Code for site inspection">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
        Site QR Code
      </button>
    `;

    // SUBMIT (Draft)
    if (actions.includes('SUBMIT')) {
      container.innerHTML += `
        <button class="btn-primary" onclick="app.submitCurrentDraft()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          Submit for Approval
        </button>
      `;
    }

    // APPROVE
    if (actions.includes('APPROVE')) {
      container.innerHTML += `
        <button class="btn-success" onclick="app.openApproveModal(${p.id})">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          Sign & Approve
        </button>
      `;
    }

    // REJECT
    if (actions.includes('REJECT')) {
      container.innerHTML += `
        <button class="btn-danger" onclick="app.openRejectModal(${p.id})">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          Reject Permit
        </button>
      `;
    }

    // ACTIVATE
    if (actions.includes('ACTIVATE')) {
      container.innerHTML += `
        <button class="btn-success" onclick="app.activateCurrentPermit()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Activate on Site
        </button>
      `;
    }

    // SUSPEND
    if (actions.includes('SUSPEND')) {
      container.innerHTML += `
        <button class="btn-danger" onclick="app.openSuspendModal(${p.id})">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
          Emergency Suspend
        </button>
      `;
    }

    // RESUME
    if (actions.includes('RESUME')) {
      container.innerHTML += `
        <button class="btn-primary" onclick="app.openResumeModal(${p.id})">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Authorize Resumption
        </button>
      `;
    }

    // CLOSE (Requester)
    if (actions.includes('CLOSE')) {
      container.innerHTML += `
        <button class="btn-primary" onclick="app.openCloseModal(${p.id})">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          Mark Work Complete
        </button>
      `;
    }

    // VERIFY CLOSURE (Safety Officer)
    if (actions.includes('VERIFY_CLOSURE')) {
      container.innerHTML += `
        <button class="btn-success" onclick="app.openVerifyClosureModal(${p.id})">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          Verify Closure & Archive
        </button>
      `;
    }

    // REQUEST EXTENSION
    if (actions.includes('REQUEST_EXTENSION')) {
      container.innerHTML += `
        <button class="btn-secondary" onclick="app.openExtensionModal(${p.id})">
          + Request Extension
        </button>
      `;
    }

    // REVIEW EXTENSION
    if (actions.includes('REVIEW_EXTENSION')) {
      container.innerHTML += `
        <button class="btn-primary" onclick="app.openReviewExtensionModal(${p.id})">
          Review Extension (${p.extension_hours}h)
        </button>
      `;
    }

    // CANCEL
    if (actions.includes('CANCEL')) {
      container.innerHTML += `
        <button class="btn-outline" onclick="app.cancelCurrentPermit()">
          Cancel Permit
        </button>
      `;
    }
  }

  // --- State Machine Action Handlers ---
  async submitCurrentDraft() {
    if (!this.currentPermit) return;
    try {
      this.showToast('Submitting permit for approvals...', 'info');
      await window.api.submitPermit(this.currentPermit.id);
      this.showToast('Permit submitted successfully!', 'success');
      await this.loadPermitDetail(this.currentPermit.id);
    } catch (err) {
      this.showToast(`Submission failed: ${err.message}`, 'error');
    }
  }

  async activateCurrentPermit() {
    if (!this.currentPermit) return;
    try {
      this.showToast('Activating permit on site...', 'info');
      await window.api.activatePermit(this.currentPermit.id);
      this.showToast('Permit ACTIVE! Work is authorized inside window.', 'success');
      await this.loadPermitDetail(this.currentPermit.id);
    } catch (err) {
      this.showToast(`Activation failed: ${err.message}`, 'error');
    }
  }

  async cancelCurrentPermit() {
    if (!this.currentPermit) return;
    const reason = prompt("Enter cancellation reason:");
    if (reason === null) return;
    try {
      this.showToast('Cancelling permit...', 'info');
      await window.api.cancelPermit(this.currentPermit.id, reason);
      this.showToast('Permit has been cancelled.', 'info');
      await this.loadPermitDetail(this.currentPermit.id);
    } catch (err) {
      this.showToast(`Cancellation failed: ${err.message}`, 'error');
    }
  }

  // --- Modals & Actions ---
  openApproveModal(permitId) {
    const id = permitId || (this.currentPermit ? this.currentPermit.id : null);
    if (!id) return;
    this.pendingActionPermitId = id;
    document.getElementById('approve-comment').value = '';
    this.clearSignature();
    this.openModal('modal-approve');
  }

  async confirmApprove() {
    const comment = document.getElementById('approve-comment').value.trim();
    const sigData = this.getSignatureData();

    if (!sigData) {
      this.showToast('Please provide your digital signature on the pad.', 'warning');
      return;
    }

    try {
      this.showToast('Submitting approval sign-off...', 'info');
      await window.api.approvePermit(this.pendingActionPermitId, comment, sigData);
      this.closeModal('modal-approve');
      this.showToast('Approval recorded successfully!', 'success');
      await this.fetchDashboardStats();
      if (this.currentPermit && this.currentPermit.id === this.pendingActionPermitId) {
        await this.loadPermitDetail(this.pendingActionPermitId);
      } else {
        await this.fetchPermits();
      }
    } catch (err) {
      this.showToast(`Approval failed: ${err.message}`, 'error');
    }
  }

  openRejectModal(permitId) {
    this.pendingActionPermitId = permitId || this.currentPermit.id;
    document.getElementById('reject-reason').value = '';
    this.openModal('modal-reject');
  }

  async confirmReject() {
    const reason = document.getElementById('reject-reason').value.trim();
    if (!reason) {
      this.showToast('A mandatory rejection reason is required.', 'warning');
      return;
    }

    try {
      this.showToast('Submitting rejection...', 'info');
      await window.api.rejectPermit(this.pendingActionPermitId, reason);
      this.closeModal('modal-reject');
      this.showToast('Permit rejected.', 'info');
      await this.loadPermitDetail(this.pendingActionPermitId);
    } catch (err) {
      this.showToast(`Rejection failed: ${err.message}`, 'error');
    }
  }

  openSuspendModal(permitId) {
    this.pendingActionPermitId = permitId || this.currentPermit.id;
    document.getElementById('suspend-reason').value = '';
    this.openModal('modal-suspend');
  }

  async confirmSuspend() {
    const reason = document.getElementById('suspend-reason').value.trim();
    if (!reason) {
      this.showToast('A mandatory suspension reason is required.', 'warning');
      return;
    }

    try {
      this.showToast('Haulting permit work...', 'info');
      await window.api.suspendPermit(this.pendingActionPermitId, reason);
      this.closeModal('modal-suspend');
      this.showToast('Permit SUSPENDED. Site alerted.', 'error');
      await this.loadPermitDetail(this.pendingActionPermitId);
    } catch (err) {
      this.showToast(`Suspension failed: ${err.message}`, 'error');
    }
  }

  openResumeModal(permitId) {
    this.pendingActionPermitId = permitId || this.currentPermit.id;
    document.getElementById('resume-notes').value = '';
    this.openModal('modal-resume');
  }

  async confirmResume() {
    const notes = document.getElementById('resume-notes').value.trim();
    try {
      this.showToast('Resuming permit...', 'info');
      await window.api.resumePermit(this.pendingActionPermitId, notes);
      this.closeModal('modal-resume');
      this.showToast('Permit resumed to ACTIVE status.', 'success');
      await this.loadPermitDetail(this.pendingActionPermitId);
    } catch (err) {
      this.showToast(`Resume failed: ${err.message}`, 'error');
    }
  }

  openCloseModal(permitId) {
    this.pendingActionPermitId = permitId || this.currentPermit.id;
    document.getElementById('close-notes').value = '';
    this.openModal('modal-close');
  }

  async confirmClose() {
    const notes = document.getElementById('close-notes').value.trim();
    if (!notes) {
      this.showToast('Please provide completion and housekeeping notes.', 'warning');
      return;
    }

    try {
      this.showToast('Marking work complete...', 'info');
      await window.api.closePermit(this.pendingActionPermitId, notes);
      this.closeModal('modal-close');
      this.showToast('Permit closed! Awaiting Safety Officer walk-around.', 'success');
      await this.loadPermitDetail(this.pendingActionPermitId);
    } catch (err) {
      this.showToast(`Closure failed: ${err.message}`, 'error');
    }
  }

  openVerifyClosureModal(permitId) {
    this.pendingActionPermitId = permitId || this.currentPermit.id;
    document.getElementById('verify-notes').value = '';
    this.openModal('modal-verify-closure');
  }

  async confirmVerifyClosure() {
    const notes = document.getElementById('verify-notes').value.trim();
    try {
      this.showToast('Archiving verified permit...', 'info');
      await window.api.verifyClosure(this.pendingActionPermitId, notes);
      this.closeModal('modal-verify-closure');
      this.showToast('Permit CLOSED & VERIFIED! Handover archived.', 'success');
      await this.loadPermitDetail(this.pendingActionPermitId);
    } catch (err) {
      this.showToast(`Verification failed: ${err.message}`, 'error');
    }
  }

  openExtensionModal(permitId) {
    this.pendingActionPermitId = permitId || this.currentPermit.id;
    document.getElementById('ext-hours').value = 2;
    document.getElementById('ext-reason').value = '';
    this.openModal('modal-extension');
  }

  async confirmRequestExtension() {
    const hours = parseInt(document.getElementById('ext-hours').value, 10);
    const reason = document.getElementById('ext-reason').value.trim();

    if (!reason) {
      this.showToast('Extension justification is mandatory.', 'warning');
      return;
    }

    try {
      this.showToast('Submitting extension request...', 'info');
      await window.api.requestExtension(this.pendingActionPermitId, hours, reason);
      this.closeModal('modal-extension');
      this.showToast(`Requested +${hours} hours extension. Awaiting Safety Officer review.`, 'success');
      await this.loadPermitDetail(this.pendingActionPermitId);
    } catch (err) {
      this.showToast(`Extension request failed: ${err.message}`, 'error');
    }
  }

  openReviewExtensionModal(permitId) {
    this.pendingActionPermitId = permitId || this.currentPermit.id;
    const p = this.currentPermit;
    const detailsBox = document.getElementById('ext-request-details');
    detailsBox.innerHTML = `
      <p><strong>Requested Hours:</strong> +${p.extension_hours} Hours</p>
      <p><strong>Justification:</strong> ${p.extension_reason}</p>
      <p><strong>New Planned End:</strong> Shift extended</p>
    `;
    document.getElementById('ext-review-comment').value = '';
    this.openModal('modal-review-ext');
  }

  async confirmReviewExtension(approved) {
    const comment = document.getElementById('ext-review-comment').value.trim();
    try {
      this.showToast(approved ? 'Approving extension...' : 'Rejecting extension...', 'info');
      await window.api.approveExtension(this.pendingActionPermitId, approved, comment);
      this.closeModal('modal-review-ext');
      this.showToast(approved ? 'Extension APPROVED! Validity window extended.' : 'Extension rejected.', 'info');
      await this.loadPermitDetail(this.pendingActionPermitId);
    } catch (err) {
      this.showToast(`Action failed: ${err.message}`, 'error');
    }
  }

  openQrModal(permitNumber) {
    document.getElementById('qr-permit-label').textContent = permitNumber;
    const qrContainer = document.getElementById('qrcode-container');
    qrContainer.innerHTML = '';
    if (window.QRCode) {
      new QRCode(qrContainer, {
        text: `${window.location.origin}/#permit-${permitNumber}`,
        width: 160,
        height: 160,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.H
      });
    }
    this.openModal('modal-qr');
  }

  // Modal helpers
  openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('active');
  }

  closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('active');
  }

  // --- HTML5 Canvas Digital Signature Pad ---
  initCanvasSignature() {
    const canvas = document.getElementById('signature-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#0284c7';

    const getPos = (e) => {
      const rect = canvas.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      return {
        x: clientX - rect.left,
        y: clientY - rect.top
      };
    };

    const startDraw = (e) => {
      e.preventDefault();
      this.isDrawing = true;
      const pos = getPos(e);
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
    };

    const draw = (e) => {
      if (!this.isDrawing) return;
      e.preventDefault();
      const pos = getPos(e);
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
    };

    const stopDraw = () => {
      this.isDrawing = false;
    };

    canvas.addEventListener('mousedown', startDraw);
    canvas.addEventListener('mousemove', draw);
    window.addEventListener('mouseup', stopDraw);

    canvas.addEventListener('touchstart', startDraw, { passive: false });
    canvas.addEventListener('touchmove', draw, { passive: false });
    window.addEventListener('touchend', stopDraw);
  }

  clearSignature() {
    const canvas = document.getElementById('signature-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  getSignatureData() {
    const canvas = document.getElementById('signature-canvas');
    if (!canvas) return '';

    // Check if canvas is blank
    const ctx = canvas.getContext('2d');
    const pixelBuffer = new Uint32Array(
      ctx.getImageData(0, 0, canvas.width, canvas.height).data.buffer
    );
    const hasDrawn = pixelBuffer.some(color => color !== 0);
    if (!hasDrawn) return '';

    return canvas.toDataURL('image/png');
  }

  // --- Mobile-First Field Mode Toggle ---
  toggleFieldMode() {
    document.body.classList.toggle('mode-field');
    const isField = document.body.classList.contains('mode-field');
    const textEl = document.getElementById('field-mode-text');
    if (textEl) {
      textEl.textContent = isField ? 'Exit Field Mode' : 'Field Mode';
    }
    this.showToast(isField ? 'High-Contrast Plant Floor Mode ON' : 'Standard CMMS Mode ON', 'info');
  }

  // --- Utilities ---
  formatDateTime(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  }

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 250);
    }, 4000);
  }
}

// Instantiate and initialize on DOM load
window.app = new AppController();
document.addEventListener('DOMContentLoaded', () => {
  window.app.init();
});
