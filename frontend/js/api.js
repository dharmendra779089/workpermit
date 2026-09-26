/**
 * Opmaint CMMS — API Client (Vanilla JavaScript / Fetch API)
 * Handles JWT authentication, token headers, error formatting, and endpoints.
 */

const API_BASE = '/api';

class ApiClient {
  constructor() {
    this.token = localStorage.getItem('opmaint_jwt_access') || null;
    this.refreshToken = localStorage.getItem('opmaint_jwt_refresh') || null;
  }

  setTokens(access, refresh) {
    this.token = access;
    this.refreshToken = refresh;
    if (access) localStorage.setItem('opmaint_jwt_access', access);
    else localStorage.removeItem('opmaint_jwt_access');

    if (refresh) localStorage.setItem('opmaint_jwt_refresh', refresh);
    else localStorage.removeItem('opmaint_jwt_refresh');
  }

  clearTokens() {
    this.token = null;
    this.refreshToken = null;
    localStorage.removeItem('opmaint_jwt_access');
    localStorage.removeItem('opmaint_jwt_refresh');
    localStorage.removeItem('opmaint_current_user');
  }

  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      // Handle HTTP 401 Unauthorized
      if (response.status === 401) {
        // If not already on login, try refresh or log out
        this.clearTokens();
        if (!endpoint.includes('/auth/login/')) {
          console.warn('Session expired. Redirecting to login.');
        }
      }

      if (response.status === 204) {
        return null;
      }

      const data = await response.json();

      if (!response.ok) {
        // Format structured server error message
        let errorMsg = 'An unexpected server error occurred.';
        if (data.detail) {
          errorMsg = data.detail;
        } else if (data.reason) {
          errorMsg = Array.isArray(data.reason) ? data.reason.join(' ') : data.reason;
        } else if (data.type_data) {
          const typeErrors = Object.entries(data.type_data).map(([k, v]) => `${k}: ${v}`).join('; ');
          errorMsg = `Safety Specification Error: ${typeErrors}`;
        } else if (typeof data === 'object') {
          const errors = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`).join(' | ');
          errorMsg = errors;
        }
        const err = new Error(errorMsg);
        err.status = response.status;
        err.data = data;
        throw err;
      }

      return data;
    } catch (err) {
      throw err;
    }
  }

  // --- Auth Endpoints ---
  async login(username, password) {
    const res = await this.request('/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    });
    this.setTokens(res.access, res.refresh);
    if (res.user) {
      localStorage.setItem('opmaint_current_user', JSON.stringify(res.user));
    }
    return res;
  }

  async getMe() {
    return this.request('/auth/me/');
  }

  // --- Master Data Endpoints ---
  async getPlants() {
    return this.request('/plants/');
  }

  async getAreas(plantId = null) {
    const query = plantId ? `?plant=${plantId}` : '';
    return this.request(`/areas/${query}`);
  }

  async getEquipment(areaId = null, plantId = null) {
    let query = '';
    if (areaId) query = `?area=${areaId}`;
    else if (plantId) query = `?plant=${plantId}`;
    return this.request(`/equipment/${query}`);
  }

  async getPermitTypes() {
    return this.request('/permit-types/');
  }

  async getDashboardStats() {
    return this.request('/dashboard/stats/');
  }

  // --- Permits Endpoints ---
  async getPermits(params = {}) {
    const searchParams = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== '' && v !== null && v !== undefined) {
        searchParams.append(k, v);
      }
    }
    const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return this.request(`/permits/${query}`);
  }

  async getPermit(id) {
    return this.request(`/permits/${id}/`);
  }

  async createPermit(data) {
    return this.request('/permits/', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async updatePermit(id, data) {
    return this.request(`/permits/${id}/`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  // --- Lifecycle State Machine Transitions ---
  async submitPermit(id) {
    return this.request(`/permits/${id}/submit/`, { method: 'POST' });
  }

  async approvePermit(id, comment, signatureData) {
    return this.request(`/permits/${id}/approve/`, {
      method: 'POST',
      body: JSON.stringify({ comment, signature_data: signatureData })
    });
  }

  async rejectPermit(id, reason) {
    return this.request(`/permits/${id}/reject/`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    });
  }

  async activatePermit(id) {
    return this.request(`/permits/${id}/activate/`, { method: 'POST' });
  }

  async suspendPermit(id, reason) {
    return this.request(`/permits/${id}/suspend/`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    });
  }

  async resumePermit(id, notes) {
    return this.request(`/permits/${id}/resume/`, {
      method: 'POST',
      body: JSON.stringify({ notes })
    });
  }

  async closePermit(id, completionNotes) {
    return this.request(`/permits/${id}/close/`, {
      method: 'POST',
      body: JSON.stringify({ completion_notes: completionNotes })
    });
  }

  async verifyClosure(id, notes) {
    return this.request(`/permits/${id}/verify_closure/`, {
      method: 'POST',
      body: JSON.stringify({ notes })
    });
  }

  async cancelPermit(id, reason) {
    return this.request(`/permits/${id}/cancel/`, {
      method: 'POST',
      body: JSON.stringify({ reason })
    });
  }

  async requestExtension(id, hours, reason) {
    return this.request(`/permits/${id}/request_extension/`, {
      method: 'POST',
      body: JSON.stringify({ hours, reason })
    });
  }

  async approveExtension(id, approved, comment) {
    return this.request(`/permits/${id}/approve_extension/`, {
      method: 'POST',
      body: JSON.stringify({ approved, comment })
    });
  }

  async logWork(id, data) {
    return this.request(`/permits/${id}/log_work/`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async preCheckConflicts(data) {
    return this.request('/permits/pre_check_conflicts/', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }
}

// Export singleton instance
window.api = new ApiClient();
