import React, { useState, useEffect, useRef } from 'react';
import { 
  BarChart3, 
  UploadCloud, 
  CheckSquare, 
  History, 
  Settings as SettingsIcon, 
  Sparkles, 
  User as UserIcon, 
  ChevronRight, 
  X, 
  AlertTriangle, 
  Search, 
  Filter, 
  Lock, 
  Unlock, 
  RefreshCw, 
  FileSpreadsheet, 
  Check, 
  Building2, 
  Calendar, 
  Coins, 
  Plane, 
  Hotel, 
  Car,
  FolderOpen
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [user, setUser] = useState(null);
  const [organizations, setOrganizations] = useState([]);
  const [currentOrg, setCurrentOrg] = useState(null);
  
  // Login credentials state
  const [usernameInput, setUsernameInput] = useState('acme_analyst');
  const [passwordInput, setPasswordInput] = useState('password123');
  const [authError, setAuthError] = useState('');

  // App global statuses
  const [stats, setStats] = useState(null);
  const [rawRecords, setRawRecords] = useState([]);
  const [facilities, setFacilities] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  
  // UI filters
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [searchFilter, setSearchFilter] = useState('');
  
  // Selected row for Detail Drawer
  const [selectedRecord, setSelectedRecord] = useState(null);
  
  // Admin role bypass for demonstration convenience
  const [bypassAdmin, setBypassAdmin] = useState(false);

  // Edit fields
  const [editQty, setEditQty] = useState('');
  const [editUnit, setEditUnit] = useState('');
  const [editReason, setEditReason] = useState('');
  const [editError, setEditError] = useState('');

  // Toast State
  const [toastMessage, setToastMessage] = useState('');
  const [showToast, setShowToast] = useState(false);

  const fileInputRef = useRef(null);
  const [uploadSource, setUploadSource] = useState('SAP');
  const [isUploading, setIsUploading] = useState(false);

  // New facility form
  const [facName, setFacName] = useState('');
  const [facCode, setFacCode] = useState('');
  const [facRegion, setFacRegion] = useState('US-CA');

  const triggerToast = (msg) => {
    setToastMessage(msg);
    setShowToast(true);
    setTimeout(() => setShowToast(false), 4000);
  };

  // 1. Initial Load checks
  useEffect(() => {
    fetchSession();
  }, []);

  // Fetch stats and lists whenever organization or tab changes
  useEffect(() => {
    if (user) {
      refreshData();
    }
  }, [user, currentOrg, activeTab]);

  const fetchSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/me/`);
      if (res.ok) {
        const data = await res.json();
        setUser(data.user);
        setOrganizations(data.organizations);
        if (data.organizations.length > 0) {
          setCurrentOrg(data.organizations[0]);
        }
      }
    } catch (e) {
      console.log("No active session found:", e);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');
    try {
      const res = await fetch(`${API_BASE}/api/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: usernameInput, password: passwordInput })
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data.user);
        setOrganizations(data.organizations);
        
        // Match user organization
        const matchedOrg = data.organizations.find(o => o.id === data.user.organization_id);
        setCurrentOrg(matchedOrg || data.organizations[0]);
        triggerToast(`Welcome back, ${data.user.username}!`);
      } else {
        const err = await res.json();
        setAuthError(err.error || 'Login failed.');
      }
    } catch (err) {
      setAuthError('Could not connect to backend server. Ensure it is running.');
    }
  };

  const handleLogout = () => {
    setUser(null);
    setCurrentOrg(null);
    setActiveTab('dashboard');
  };

  // Helper for requests supplying multi-tenant headers
  const getHeaders = () => {
    const headers = { 'Content-Type': 'application/json' };
    if (currentOrg) {
      headers['X-Tenant-ID'] = currentOrg.id;
    }
    if (bypassAdmin) {
      headers['X-Bypass-Admin'] = 'true';
    }
    return headers;
  };

  const refreshData = async () => {
    if (!currentOrg) return;
    try {
      const headers = getHeaders();
      
      // Fetch Dashboard Stats
      const statsRes = await fetch(`${API_BASE}/api/dashboard/stats/`, { headers });
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }

      // Fetch Facilities
      const facRes = await fetch(`${API_BASE}/api/facilities/`, { headers });
      if (facRes.ok) {
        const facData = await facRes.json();
        setFacilities(facData);
      }

      // Fetch Raw Records
      let rawUrl = `${API_BASE}/api/records/raw/?`;
      if (statusFilter) rawUrl += `status=${statusFilter}&`;
      if (sourceFilter) rawUrl += `source_type=${sourceFilter}&`;
      if (searchFilter) rawUrl += `search=${searchFilter}&`;
      const rawRes = await fetch(rawUrl, { headers });
      if (rawRes.ok) {
        const rawData = await rawRes.json();
        setRawRecords(rawData);
        
        // Refresh selected record detail if open
        if (selectedRecord) {
          const updatedSelected = rawData.find(r => r.id === selectedRecord.id);
          if (updatedSelected) {
            setSelectedRecord(updatedSelected);
          }
        }
      }

      // Fetch Audit Logs
      const auditRes = await fetch(`${API_BASE}/api/audit-logs/`, { headers });
      if (auditRes.ok) {
        const auditData = await auditRes.json();
        setAuditLogs(auditData);
      }

    } catch (e) {
      console.error("Error refreshing data:", e);
    }
  };

  // Seed DB trigger
  const handleTriggerSeed = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/seed/`, { method: 'POST' });
      if (res.ok) {
        triggerToast("Database seeded successfully!");
        fetchSession();
        refreshData();
      } else {
        triggerToast("Seeding failed.");
      }
    } catch (e) {
      triggerToast("Error triggering seed.");
    }
  };

  // API Ingest triggers
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setIsUploading(true);
    
    const formData = new FormData();
    formData.append('source_type', uploadSource);
    formData.append('file', file);

    try {
      const headers = {};
      if (currentOrg) {
        headers['X-Tenant-ID'] = currentOrg.id;
      }

      const res = await fetch(`${API_BASE}/api/ingest/upload/`, {
        method: 'POST',
        headers,
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        triggerToast(`Uploaded job completed! Success: ${data.summary.success}, Suspicious: ${data.summary.suspicious}`);
        refreshData();
      } else {
        const err = await res.json();
        triggerToast(`Upload failed: ${err.error || 'Unknown error'}`);
      }
    } catch (err) {
      triggerToast("Failed to upload. Ensure server is online.");
    } finally {
      setIsUploading(false);
      fileInputRef.current.value = "";
    }
  };

  const handleConcurSync = async () => {
    setIsUploading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ingest/sync/`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        triggerToast(`Concur Sync job completed! Success: ${data.summary.success}, Suspicious: ${data.summary.suspicious}`);
        refreshData();
      } else {
        triggerToast("Sync failed.");
      }
    } catch (e) {
      triggerToast("Network error syncing API.");
    } finally {
      setIsUploading(false);
    }
  };

  // Review sheet action handlers
  const handleApprove = async (id, reason) => {
    try {
      const res = await fetch(`${API_BASE}/api/records/raw/${id}/approve/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ reason: reason || 'Analyst signed off' })
      });
      if (res.ok) {
        triggerToast("Record approved and locked for auditing!");
        refreshData();
      } else {
        const err = await res.json();
        triggerToast(`Error: ${err.error}`);
      }
    } catch (e) {
      triggerToast("Failed to approve.");
    }
  };

  const handleReject = async (id, reason) => {
    try {
      const res = await fetch(`${API_BASE}/api/records/raw/${id}/reject/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ reason: reason || 'Record rejected' })
      });
      if (res.ok) {
        triggerToast("Record rejected and removed from carbon totals.");
        refreshData();
      } else {
        triggerToast("Failed to reject.");
      }
    } catch (e) {
      triggerToast("Network error.");
    }
  };

  const handleUnlock = async (id, reason) => {
    try {
      const res = await fetch(`${API_BASE}/api/records/raw/${id}/unlock/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ reason: reason || 'Unlocked for correction' })
      });
      if (res.ok) {
        triggerToast("Record unlocked successfully.");
        refreshData();
      } else {
        const err = await res.json();
        triggerToast(`Access Denied: ${err.error}`);
      }
    } catch (e) {
      triggerToast("Error unlocking record.");
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    setEditError('');
    if (!editQty || !editReason) {
      setEditError('Quantity and Justification Reason are required.');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/records/raw/${selectedRecord.id}/edit/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          quantity: editQty,
          unit: editUnit,
          reason: editReason
        })
      });
      if (res.ok) {
        triggerToast("Quantity adjusted. Emissions re-calculated!");
        setEditReason('');
        refreshData();
      } else {
        const err = await res.json();
        setEditError(err.error || 'Failed to edit record.');
      }
    } catch (e) {
      setEditError('Server network error.');
    }
  };

  // Facility creation
  const handleCreateFacility = async (e) => {
    e.preventDefault();
    if (!facName || !facCode) return;
    try {
      const res = await fetch(`${API_BASE}/api/facilities/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ name: facName, facility_code: facCode, region: facRegion })
      });
      if (res.ok) {
        triggerToast(`Facility ${facName} mapped!`);
        setFacName('');
        setFacCode('');
        refreshData();
      } else {
        triggerToast("Failed to map facility. Code must be unique.");
      }
    } catch (e) {
      triggerToast("Network error.");
    }
  };

  // Generate and download sample files to facilitate review
  const downloadSampleFile = (type) => {
    let content = "";
    let filename = "";
    if (type === 'sap') {
      content = "Materialbeleg,Buchungsdatum,Materialnummer,Materialkurztext,Menge,Einheit,Werk,Einkaufsbeleg\n" +
                "50001001,12.04.2026,DIESEL_01,Industrial Diesel,\"12.500,50\",LTR,1000,45000921\n" +
                "50001002,18.04.2026,NAT_GAS_02,Natural Gas Pipeline,4500,M3,1100,45000922\n" +
                "50001003,24.04.2026,DIESEL_01,Industrial Diesel,90000,LTR,1000,45000923\n" + // Anomaly: very high
                "50001004,30.04.2026,UNMAPPED_OIL,Heavy Industrial Oil,1000,L,1200,45000924\n" + // Unknown material
                "50001005,01.05.2026,DIESEL_01,Industrial Diesel,2500,LTR,1300,45000925\n"; // Plant code 1300 not mapped
      filename = "SAP_Fuel_Export_Sample.csv";
    } else if (type === 'utility') {
      content = "Account Number,Meter Number,Bill Period Start,Bill Period End,Usage,Unit,Tariff,Total Cost\n" +
                "98765432,E-MTR-8899,2026-04-12,2026-05-11,12450.00,kWh,E-19,2450.75\n" + // Crosses April-May
                "98765432,E-MTR-1234,2026-04-15,2026-05-14,22.40,MWh,E-19,4500.20\n" + // MWh unit conversion
                "98765432,E-MTR-8899,2026-05-12,2026-06-11,280000.00,kWh,E-19,42000.00\n" + // Anomaly: high usage
                "98765432,E-MTR-8899,2026-06-12,2026-08-11,15000.00,kWh,E-19,3000.00\n" + // Anomaly: > 45 days billing gap
                "98765432,E-MTR-UNKNOWN,2026-05-15,2026-06-14,500.00,kWh,E-19,100.00\n"; // Unknown meter
      filename = "Utility_Electricity_Sample.csv";
    }

    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Open Edit drawer setup
  const setupEditForm = (rec) => {
    setSelectedRecord(rec);
    if (rec.normalized_record) {
      setEditQty(rec.normalized_record.raw_quantity);
      setEditUnit(rec.normalized_record.raw_unit);
    } else {
      // Fallback extract
      setEditQty(rec.raw_data.Menge || rec.raw_data.usage || rec.raw_data.distance_value || '');
      setEditUnit(rec.raw_data.Einheit || rec.raw_data.unit || rec.raw_data.distance_unit || '');
    }
    setEditReason('');
    setEditError('');
  };

  // Log in form render
  if (!user) {
    return (
      <div className="login-container">
        <div className="card login-card">
          <div className="login-header">
            <div className="logo-icon">B</div>
            <h2 style={{ fontSize: '24px', fontWeight: '800' }}>Breathe ESG</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '4px' }}>
              Relational Emissions Ingest & Analyst Review Portal
            </p>
          </div>
          
          <form className="login-form" onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <select 
                className="tenant-select" 
                value={usernameInput} 
                onChange={(e) => setUsernameInput(e.target.value)}
              >
                <option value="acme_analyst">acme_analyst (Acme Analyst)</option>
                <option value="acme_auditor">acme_auditor (Acme Auditor)</option>
                <option value="acme_admin">acme_admin (Acme Admin)</option>
                <option value="beta_analyst">beta_analyst (Beta Services Analyst)</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input 
                type="password" 
                className="form-input" 
                value={passwordInput} 
                onChange={(e) => setPasswordInput(e.target.value)} 
                required 
              />
            </div>

            {authError && (
              <div className="anomaly-alert" style={{ padding: '12px' }}>
                <AlertTriangle size={16} />
                <span>{authError}</span>
              </div>
            )}

            <button type="submit" className="btn btn-primary" style={{ marginTop: '12px' }}>
              Sign In
            </button>
          </form>

          <div style={{ marginTop: '24px', textAlign: 'center' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Database empty? Trigger seed mapping configuration:
            </span>
            <button 
              onClick={handleTriggerSeed} 
              className="btn btn-secondary" 
              style={{ fontSize: '11px', padding: '6px 12px', marginTop: '8px', width: 'auto' }}
            >
              Seed Standard Settings
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Toast */}
      <div className={`toast ${showToast ? 'show' : ''}`}>
        <div className="toast-content">
          <Sparkles size={18} color="var(--color-secondary)" />
          <span>{toastMessage}</span>
        </div>
      </div>

      {/* Sidebar navigation */}
      <aside className="sidebar">
        <div className="logo-container">
          <div className="logo-icon">B</div>
          <span className="logo-text">Breathe ESG</span>
        </div>

        <nav className="nav-links">
          <li 
            className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            <BarChart3 size={18} />
            <span>Dashboard</span>
          </li>
          <li 
            className={`nav-item ${activeTab === 'ingest' ? 'active' : ''}`}
            onClick={() => setActiveTab('ingest')}
          >
            <UploadCloud size={18} />
            <span>Ingest Portal</span>
          </li>
          <li 
            className={`nav-item ${activeTab === 'review' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('review');
              refreshData();
            }}
          >
            <CheckSquare size={18} />
            <span>Review Grid</span>
            {rawRecords.filter(r => r.status === 'PENDING' || r.status === 'SUSPICIOUS').length > 0 && (
              <span style={{
                marginLeft: 'auto',
                backgroundColor: 'var(--color-primary-glow)',
                color: 'var(--color-primary)',
                padding: '2px 8px',
                borderRadius: '50px',
                fontSize: '11px',
                fontWeight: '700'
              }}>
                {rawRecords.filter(r => r.status === 'PENDING' || r.status === 'SUSPICIOUS').length}
              </span>
            )}
          </li>
          <li 
            className={`nav-item ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            <History size={18} />
            <span>Audit Trail</span>
          </li>
          <li 
            className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            <SettingsIcon size={18} />
            <span>Settings</span>
          </li>
        </nav>

        {/* Multi-tenancy Demo selector */}
        <div className="tenant-selector-card">
          <h4>Client Tenant (Scope)</h4>
          <select 
            className="tenant-select"
            value={currentOrg ? currentOrg.id : ''}
            onChange={(e) => {
              const matched = organizations.find(o => o.id === e.target.value);
              setCurrentOrg(matched);
              triggerToast(`Switched workspace to ${matched.name}`);
            }}
          >
            {organizations.map(org => (
              <option key={org.id} value={org.id}>{org.name}</option>
            ))}
          </select>
          
          <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input 
              type="checkbox" 
              id="bypass" 
              checked={bypassAdmin} 
              onChange={(e) => setBypassAdmin(e.target.checked)} 
            />
            <label htmlFor="bypass" style={{ fontSize: '11px', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              Bypass Admin Locks
            </label>
          </div>
        </div>

        {/* Current logged user metadata */}
        <div style={{ marginTop: '20px', borderTop: '1px solid var(--border-light)', paddingTop: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '36px', height: '36px', borderRadius: '50%', backgroundColor: 'rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyCenter: 'center' }}>
            <UserIcon size={16} style={{ margin: 'auto' }} />
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: '600' }}>{user.username}</div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'capitalize' }}>Role: {user.role}</div>
          </div>
          <button 
            onClick={handleLogout} 
            className="btn-close" 
            style={{ marginLeft: 'auto', width: '24px', height: '24px' }}
            title="Logout"
          >
            <X size={14} />
          </button>
        </div>
      </aside>

      {/* Main Panel views */}
      <main className="main-content">
        <header className="page-header">
          <div className="page-title">
            <h1 style={{ textTransform: 'capitalize' }}>{activeTab}</h1>
            <p>Active Workspace: <strong style={{ color: 'var(--color-primary)' }}>{currentOrg?.name}</strong></p>
          </div>
          <div className="header-actions">
            <button className="btn btn-secondary" style={{ width: 'auto' }} onClick={refreshData}>
              <RefreshCw size={14} />
              <span>Sync Dashboard</span>
            </button>
          </div>
        </header>

        {/* TAB 1: DASHBOARD OVERVIEW */}
        {activeTab === 'dashboard' && stats && (
          <div>
            {/* KPI Cards */}
            <div className="dashboard-grid">
              <div className="card widget-card">
                <div className="widget-icon" style={{ backgroundColor: 'var(--color-secondary-glow)', color: 'var(--color-secondary)' }}>
                  <Coins size={22} />
                </div>
                <div className="widget-details">
                  <h3>Approved Emissions</h3>
                  <div className="number">{stats.approved_emissions_mt.toFixed(2)} <span style={{ fontSize: '14px', fontWeight: '500', color: 'var(--text-secondary)' }}>MT CO2e</span></div>
                </div>
              </div>

              <div className="card widget-card">
                <div className="widget-icon" style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: 'var(--status-pending-text)' }}>
                  <AlertTriangle size={22} />
                </div>
                <div className="widget-details">
                  <h3>Pending Review</h3>
                  <div className="number">{stats.status_counts.PENDING}</div>
                </div>
              </div>

              <div className="card widget-card">
                <div className="widget-icon" style={{ backgroundColor: 'rgba(236, 72, 153, 0.1)', color: 'var(--status-suspicious-text)' }}>
                  <AlertTriangle size={22} />
                </div>
                <div className="widget-details">
                  <h3>Suspicious Anomalies</h3>
                  <div className="number" style={{ color: 'var(--status-suspicious-text)' }}>{stats.status_counts.SUSPICIOUS}</div>
                </div>
              </div>

              <div className="card widget-card">
                <div className="widget-icon" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: 'var(--status-rejected-text)' }}>
                  <X size={22} />
                </div>
                <div className="widget-details">
                  <h3>Validation Failures</h3>
                  <div className="number" style={{ color: 'var(--status-rejected-text)' }}>{stats.status_counts.REJECTED}</div>
                </div>
              </div>
            </div>

            {/* Graphics Grid */}
            <div className="analytics-grid">
              {/* Monthly Trend stacked bar chart */}
              <div className="card chart-container">
                <div className="chart-header">
                  <span className="chart-title">Emissions Over Time (Monthly Splitting)</span>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Metric Tons CO2e</span>
                </div>
                {stats.monthly_trend.length === 0 ? (
                  <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-muted)' }}>
                    <FolderOpen size={48} style={{ margin: '0 auto 12px auto', opacity: '0.4' }} />
                    <p>No approved activity records available for trending.</p>
                  </div>
                ) : (
                  <div className="monthly-chart">
                    {stats.monthly_trend.map((item, idx) => {
                      // Find max to scale height
                      const maxVal = Math.max(...stats.monthly_trend.map(m => m.co2e_mt), 1);
                      const heightPercent = `${(item.co2e_mt / maxVal) * 100}%`;
                      return (
                        <div key={idx} className="chart-bar-wrapper">
                          <div 
                            className="chart-bar-fill" 
                            style={{ height: heightPercent }}
                          >
                            <div className="chart-bar-tooltip">
                              {item.co2e_mt.toFixed(3)} MT CO2e
                            </div>
                          </div>
                          <span className="chart-bar-label">{item.month}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Scope Breakdown progress cards */}
              <div className="card">
                <div className="chart-header">
                  <span className="chart-title">Emissions by Scope Boundary</span>
                </div>
                <div className="scope-breakdown-container">
                  {/* Scope 1 */}
                  <div className="scope-bar-item">
                    <div className="scope-bar-header">
                      <span>Scope 1 (Direct Fuel)</span>
                      <strong>{(stats.scope_breakdown[1] / 1000).toFixed(2)} MT</strong>
                    </div>
                    <div className="scope-bar-track">
                      <div 
                        className="scope-bar-fill" 
                        style={{ 
                          width: `${(stats.scope_breakdown[1] / Math.max(stats.approved_emissions_mt * 1000, 1)) * 100}%`,
                          backgroundColor: '#f59e0b'
                        }} 
                      />
                    </div>
                  </div>

                  {/* Scope 2 */}
                  <div className="scope-bar-item">
                    <div className="scope-bar-header">
                      <span>Scope 2 (Electricity)</span>
                      <strong>{(stats.scope_breakdown[2] / 1000).toFixed(2)} MT</strong>
                    </div>
                    <div className="scope-bar-track">
                      <div 
                        className="scope-bar-fill" 
                        style={{ 
                          width: `${(stats.scope_breakdown[2] / Math.max(stats.approved_emissions_mt * 1000, 1)) * 100}%`,
                          backgroundColor: '#06b6d4'
                        }} 
                      />
                    </div>
                  </div>

                  {/* Scope 3 */}
                  <div className="scope-bar-item">
                    <div className="scope-bar-header">
                      <span>Scope 3 (Business Travel)</span>
                      <strong>{(stats.scope_breakdown[3] / 1000).toFixed(2)} MT</strong>
                    </div>
                    <div className="scope-bar-track">
                      <div 
                        className="scope-bar-fill" 
                        style={{ 
                          width: `${(stats.scope_breakdown[3] / Math.max(stats.approved_emissions_mt * 1000, 1)) * 100}%`,
                          backgroundColor: '#10b981'
                        }} 
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Ingestion audit log list */}
            <div className="card">
              <div className="chart-header" style={{ marginBottom: '16px' }}>
                <span className="chart-title">Recent Ingestion Pipelines</span>
              </div>
              {stats.recent_jobs.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No ingestion history found.</p>
              ) : (
                <div className="table-container">
                  <table className="custom-table">
                    <thead>
                      <tr>
                        <th>Created At</th>
                        <th>Source Platform</th>
                        <th>Status</th>
                        <th>Total Rows</th>
                        <th>Passed</th>
                        <th>Suspicious</th>
                        <th>Failed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.recent_jobs.map((j, idx) => (
                        <tr key={idx}>
                          <td>{new Date(j.created_at).toLocaleString()}</td>
                          <td style={{ fontWeight: '600' }}>{j.source_type}</td>
                          <td>
                            <span className={`badge ${j.status === 'COMPLETED' ? 'badge-approved' : 'badge-rejected'}`}>
                              {j.status}
                            </span>
                          </td>
                          <td>{j.summary.total || 0}</td>
                          <td>{j.summary.success || 0}</td>
                          <td>{j.summary.suspicious || 0}</td>
                          <td>{j.summary.failed || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: INGESTION PORTAL */}
        {activeTab === 'ingest' && (
          <div>
            <div className="ingest-grid">
              {/* SAP ERP Ingestion Card */}
              <div className="card uploader-card">
                <div className="uploader-icon-container">
                  <FileSpreadsheet size={32} />
                </div>
                <h3>SAP Fuel & Procurement</h3>
                <p>Ingests SAP material movements. Reads BUDAT date, WERKS plant mapping lookup, and German number formats.</p>
                <span className="sample-link" onClick={() => downloadSampleFile('sap')}>
                  Download Sample SAP Export Template
                </span>
                
                <button 
                  className="btn btn-primary" 
                  style={{ marginTop: 'auto' }}
                  onClick={() => {
                    setUploadSource('SAP');
                    fileInputRef.current.click();
                  }}
                  disabled={isUploading}
                >
                  Upload SAP ALV File
                </button>
              </div>

              {/* Utility Portal Electricity Ingestion Card */}
              <div className="card uploader-card">
                <div className="uploader-icon-container" style={{ color: 'var(--color-primary)' }}>
                  <Building2 size={32} />
                </div>
                <h3>Utility Portal (Electricity)</h3>
                <p>Ingests electricity bills. Calendarizes consumption proportionally across months based on billing duration.</p>
                <span className="sample-link" onClick={() => downloadSampleFile('utility')}>
                  Download Sample Utility Ledger
                </span>
                
                <button 
                  className="btn btn-primary" 
                  style={{ marginTop: 'auto' }}
                  onClick={() => {
                    setUploadSource('UTILITY');
                    fileInputRef.current.click();
                  }}
                  disabled={isUploading}
                >
                  Upload Billing CSV
                </button>
              </div>

              {/* Travel Booking Sync API Simulator */}
              <div className="card uploader-card">
                <div className="uploader-icon-container" style={{ color: 'var(--color-secondary)' }}>
                  <RefreshCw size={32} />
                </div>
                <h3>Corporate Travel Sync</h3>
                <p>Simulates Concur/Navan API sync. Computes distances via airport coordinates and applies cabin multipliers.</p>
                
                <button 
                  className="btn btn-success" 
                  style={{ marginTop: 'auto' }}
                  onClick={handleConcurSync}
                  disabled={isUploading}
                >
                  Sync Concur Travel API
                </button>
              </div>
            </div>

            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={handleFileUpload} 
              className="btn-upload-input" 
              accept=".csv" 
            />

            {/* Ingestion runs ledger */}
            {stats && (
              <div className="card">
                <div className="chart-header">
                  <span className="chart-title">Historical Import Runs</span>
                </div>
                <div className="table-container">
                  <table className="custom-table">
                    <thead>
                      <tr>
                        <th>Job ID</th>
                        <th>Run Timestamp</th>
                        <th>Source API</th>
                        <th>Status</th>
                        <th>Success Rows</th>
                        <th>Anomalies</th>
                        <th>Hard Fails</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.recent_jobs.map((j, idx) => (
                        <tr key={idx}>
                          <td>#{j.id}</td>
                          <td>{new Date(j.created_at).toLocaleString()}</td>
                          <td>{j.source_type}</td>
                          <td>
                            <span className={`badge ${j.status === 'COMPLETED' ? 'badge-approved' : 'badge-rejected'}`}>
                              {j.status}
                            </span>
                          </td>
                          <td>{j.summary.success || 0}</td>
                          <td>{j.summary.suspicious || 0}</td>
                          <td>{j.summary.failed || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: REVIEW AND APPROVAL GRID */}
        {activeTab === 'review' && (
          <div>
            {/* Filter controls */}
            <div className="filter-row">
              <div className="search-input-wrapper">
                <Search className="search-icon" size={16} />
                <input 
                  type="text" 
                  className="search-input" 
                  placeholder="Search raw values, text descriptions, error messages..." 
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                />
              </div>

              <select 
                className="filter-select" 
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All Review Statuses</option>
                <option value="PENDING">Pending Review</option>
                <option value="SUSPICIOUS">Suspicious Anomalies</option>
                <option value="APPROVED">Approved & Locked</option>
                <option value="REJECTED">Rejected</option>
              </select>

              <select 
                className="filter-select" 
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
              >
                <option value="">All Sources</option>
                <option value="SAP">SAP Fuel & Procurement</option>
                <option value="UTILITY">Utility Portal (Electricity)</option>
                <option value="CONCUR">Corporate Travel</option>
              </select>

              <button className="btn btn-secondary" style={{ width: 'auto' }} onClick={refreshData}>
                Filter
              </button>
            </div>

            {/* Main review ledger */}
            <div className="table-container">
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Row #</th>
                    <th>Source</th>
                    <th>Date</th>
                    <th>Activity Data Summary</th>
                    <th>Footprint Calculation</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rawRecords.length === 0 ? (
                    <tr>
                      <td colSpan="7" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px' }}>
                        No records match the active filters. Go to <strong>Ingest Portal</strong> to upload files or sync travel data first.
                      </td>
                    </tr>
                  ) : (
                    rawRecords.map((r, idx) => {
                      const dateVal = r.normalized_record?.activity_date || r.raw_data.Buchungsdatum || r.raw_data.start_date || 'N/A';
                      
                      // Format activity summary
                      let summary = "";
                      if (r.job_source === 'SAP') {
                        summary = `${r.raw_data.Menge || r.raw_data.MENGE || '0'} ${r.raw_data.Einheit || r.raw_data.MEINS || ''} of ${r.raw_data.Materialkurztext || r.raw_data.MAKTX || 'Fuel'}`;
                      } else if (r.job_source === 'UTILITY') {
                        summary = `${r.raw_data.Usage || r.raw_data.usage || '0'} ${r.raw_data.Unit || r.raw_data.unit || 'kWh'} (Meter: ${r.raw_data['Meter Number'] || r.raw_data.meter || ''})`;
                      } else if (r.job_source === 'CONCUR') {
                        summary = `${r.raw_data.type?.toUpperCase()}: ${r.raw_data.origin || ''} to ${r.raw_data.destination || r.raw_data.hotel_city || ''}`;
                      }

                      return (
                        <tr key={r.id} onClick={() => setupEditForm(r)}>
                          <td>#{r.row_index}</td>
                          <td style={{ fontWeight: '600' }}>{r.job_source}</td>
                          <td>{dateVal}</td>
                          <td>
                            <div style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {summary}
                            </div>
                          </td>
                          <td>
                            {r.normalized_record ? (
                              <strong style={{ color: 'var(--color-primary)' }}>
                                {(r.normalized_record.co2e_kg / 1000).toFixed(3)} MT CO2e
                              </strong>
                            ) : (
                              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                                Calculation failed
                              </span>
                            )}
                          </td>
                          <td>
                            <span className={`badge badge-${r.status.toLowerCase()}`}>
                              {r.status === 'SUSPICIOUS' && <AlertTriangle size={12} />}
                              {r.status === 'APPROVED' && <Lock size={12} />}
                              {r.status}
                            </span>
                          </td>
                          <td>
                            <span className="sample-link" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                              <span>Review Detail</span>
                              <ChevronRight size={14} />
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* SIDE DETAIL DRAWER (REVIEW SHEET) */}
            {selectedRecord && (
              <>
                <div className="drawer-overlay" onClick={() => setSelectedRecord(null)}></div>
                <div className="drawer">
                  <div className="drawer-header">
                    <div className="drawer-title">
                      <h2>Review Record #{selectedRecord.row_index}</h2>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        Source: {selectedRecord.job_source} | Ingested Job #{selectedRecord.job}
                      </span>
                    </div>
                    <button className="btn-close" onClick={() => setSelectedRecord(null)}>
                      <X size={18} />
                    </button>
                  </div>

                  <div className="drawer-body">
                    {/* Anomaly banner if suspicious */}
                    {selectedRecord.status === 'SUSPICIOUS' && (
                      <div className="anomaly-alert">
                        <AlertTriangle size={24} style={{ flexShrink: 0 }} />
                        <div>
                          <strong>Suspicious Anomaly Flagged:</strong>
                          <ul style={{ marginTop: '8px', paddingLeft: '16px' }}>
                            {selectedRecord.validation_errors.map((err, i) => (
                              <li key={i}>{err}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}

                    {/* Hard error banner if rejected */}
                    {selectedRecord.status === 'REJECTED' && (
                      <div className="anomaly-alert" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                        <AlertTriangle size={24} style={{ flexShrink: 0 }} />
                        <div>
                          <strong>Ingestion Parser Failure:</strong>
                          <p style={{ marginTop: '4px' }}>{selectedRecord.validation_errors.join(', ')}</p>
                        </div>
                      </div>
                    )}

                    {/* Section 1: Raw Ingested Data */}
                    <div className="drawer-section">
                      <h3>Raw Ingested Payload</h3>
                      <pre className="json-view">
                        {JSON.stringify(selectedRecord.raw_data, null, 2)}
                      </pre>
                    </div>

                    {/* Section 2: Calculation Breakdown (if computed) */}
                    {selectedRecord.normalized_record && (
                      <div className="drawer-section">
                        <h3>Emissions Normalization</h3>
                        <div className="data-grid">
                          <div className="data-item">
                            <span className="data-label">Scope Boundary</span>
                            <span className="data-value" style={{ fontWeight: '700' }}>
                              Scope {selectedRecord.normalized_record.scope}
                            </span>
                          </div>
                          <div className="data-item">
                            <span className="data-label">Category Classifier</span>
                            <span className="data-value">
                              {selectedRecord.normalized_record.category}
                            </span>
                          </div>
                          <div className="data-item">
                            <span className="data-label">Facility Plant / Site</span>
                            <span className="data-value" style={{ color: 'var(--color-secondary)', fontWeight: '600' }}>
                              {selectedRecord.normalized_record.facility_name || 'Corporate Wide (Travel)'}
                            </span>
                          </div>
                          <div className="data-item">
                            <span className="data-label">Activity Date</span>
                            <span className="data-value">
                              {selectedRecord.normalized_record.activity_date}
                            </span>
                          </div>
                          <div className="data-item">
                            <span className="data-label">Raw quantity input</span>
                            <span className="data-value">
                              {selectedRecord.normalized_record.raw_quantity} {selectedRecord.normalized_record.raw_unit}
                            </span>
                          </div>
                          <div className="data-item">
                            <span className="data-label">Normalized Base Unit</span>
                            <span className="data-value">
                              {parseFloat(selectedRecord.normalized_record.normalized_quantity).toFixed(2)} {selectedRecord.normalized_record.normalized_unit}
                            </span>
                          </div>
                          <div className="data-item" style={{ gridColumn: 'span 2', borderTop: '1px solid var(--border-light)', paddingTop: '12px', marginTop: '4px' }}>
                            <span className="data-label">Normalized Carbon Footprint</span>
                            <span className="data-value" style={{ fontSize: '18px', fontWeight: '800', color: 'var(--color-primary)' }}>
                              {(selectedRecord.normalized_record.co2e_kg / 1000).toFixed(4)} MT CO2e
                              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 'normal', marginLeft: '6px' }}>
                                ({parseFloat(selectedRecord.normalized_record.co2e_kg).toFixed(2)} kg CO2e)
                              </span>
                            </span>
                          </div>
                        </div>

                        {/* Calculation Formula detail */}
                        <div style={{ backgroundColor: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-light)', padding: '12px 16px', borderRadius: '8px', fontSize: '11px' }}>
                          <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>CALCULATION AUDIT TRAIL:</span>
                          <code style={{ color: 'var(--color-primary)' }}>
                            {selectedRecord.normalized_record.calculation_metadata.formula}
                          </code>
                          <div style={{ marginTop: '8px', color: 'var(--text-secondary)', display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
                            <span>Multiplier: {selectedRecord.normalized_record.calculation_metadata.conversion_multiplier}</span>
                            <span>Factor: {selectedRecord.normalized_record.calculation_metadata.factor_kg_co2e || selectedRecord.normalized_record.calculation_metadata.factor_kg_co2e_per_pkm || selectedRecord.normalized_record.calculation_metadata.factor_kg_co2e_per_room_night || selectedRecord.normalized_record.calculation_metadata.factor_kg_co2e_per_km} kg/unit</span>
                          </div>
                          
                          {/* Display billing calendarization splits if utility */}
                          {selectedRecord.normalized_record.calculation_metadata.calendar_splits && (
                            <div style={{ marginTop: '12px', borderTop: '1px dashed var(--border-light)', paddingTop: '10px' }}>
                              <span style={{ color: 'var(--text-muted)', fontWeight: '600', display: 'block', marginBottom: '6px' }}>
                                Calendar Pro-Rating Split Breakdown:
                              </span>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                {selectedRecord.normalized_record.calculation_metadata.calendar_splits.map((s, i) => (
                                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
                                    <span>Month: <strong>{s.month_start.substring(0, 7)}</strong> ({s.days_in_month} days)</span>
                                    <span>Usage: {parseFloat(s.usage_kwh).toFixed(1)} kWh | <strong>{parseFloat(s.co2e_kg).toFixed(1)} kg CO2e</strong></span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Section 3: Analyst Adjustment overrides (if not locked) */}
                    {(!selectedRecord.normalized_record?.is_locked || bypassAdmin) ? (
                      <form className="drawer-section" onSubmit={handleEditSubmit}>
                        <h3>Override Quantity & Recalculate</h3>
                        
                        <div className="form-input-row">
                          <div className="form-group" style={{ flexGrow: 2 }}>
                            <label className="form-label">Activity Quantity</label>
                            <input 
                              type="number" 
                              step="any"
                              className="form-input" 
                              value={editQty}
                              onChange={(e) => setEditQty(e.target.value)}
                              placeholder="Quantity"
                            />
                          </div>
                          <div className="form-group" style={{ flexGrow: 1 }}>
                            <label className="form-label">Unit</label>
                            <input 
                              type="text" 
                              className="form-input" 
                              value={editUnit}
                              onChange={(e) => setEditUnit(e.target.value)}
                              placeholder="e.g. L, kWh, MWh"
                            />
                          </div>
                        </div>

                        <div className="form-group">
                          <label className="form-label">Justification / Audit Reason</label>
                          <textarea 
                            className="form-input" 
                            style={{ height: '80px', resize: 'vertical' }}
                            placeholder="State the reason for overriding (e.g. 'Corrected typo in SAP report', 'Adjusted billing period gap')"
                            value={editReason}
                            onChange={(e) => setEditReason(e.target.value)}
                          />
                        </div>

                        {editError && (
                          <div className="anomaly-alert" style={{ padding: '8px 12px' }}>
                            <AlertTriangle size={14} />
                            <span>{editError}</span>
                          </div>
                        )}

                        <button type="submit" className="btn btn-secondary">
                          Apply Adjustments & Recalculate
                        </button>
                      </form>
                    ) : (
                      <div className="anomaly-alert" style={{ backgroundColor: 'rgba(16, 185, 129, 0.05)', color: 'var(--status-approved-text)', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                        <Lock size={18} style={{ flexShrink: 0 }} />
                        <div>
                          <strong>Locked for Audit:</strong>
                          <p style={{ marginTop: '4px' }}>
                            This record has been signed off and is locked. To modify values, an Admin must first unlock it.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="drawer-footer">
                    {/* Approve / Lock */}
                    {(!selectedRecord.normalized_record?.is_locked || bypassAdmin) ? (
                      <>
                        <button 
                          className="btn btn-success" 
                          style={{ flex: 1 }}
                          onClick={() => {
                            const reason = prompt("Enter approval notes (optional):");
                            handleApprove(selectedRecord.id, reason);
                          }}
                          disabled={!selectedRecord.normalized_record}
                        >
                          <Lock size={16} />
                          <span>Approve & Lock</span>
                        </button>
                        <button 
                          className="btn btn-danger" 
                          style={{ flex: 1 }}
                          onClick={() => {
                            const reason = prompt("Enter rejection reason:");
                            if (reason) handleReject(selectedRecord.id, reason);
                          }}
                        >
                          <X size={16} />
                          <span>Reject Row</span>
                        </button>
                      </>
                    ) : (
                      <button 
                        className="btn btn-secondary" 
                        style={{ flex: 1 }}
                        onClick={() => {
                          const reason = prompt("State why you are unlocking this approved record:");
                          if (reason) handleUnlock(selectedRecord.id, reason);
                        }}
                      >
                        <Unlock size={16} />
                        <span>Unlock Record (Admin)</span>
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* TAB 4: AUDIT HISTORY */}
        {activeTab === 'audit' && (
          <div className="card">
            <div className="chart-header">
              <span className="chart-title">Data Correction Audit Logs</span>
            </div>
            {auditLogs.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>No audit correction logs found.</p>
            ) : (
              <div className="audit-history-list">
                {auditLogs.map((log) => (
                  <div key={log.id} className="audit-log-item">
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: '600' }}>
                      <span style={{ color: 'var(--color-primary)' }}>
                        ACTION: {log.action}
                      </span>
                      <span>Record ID: #{log.record_id} ({log.record_type})</span>
                    </div>
                    {log.field_name && (
                      <div style={{ marginTop: '6px', fontSize: '12px' }}>
                        Field: <strong>{log.field_name}</strong> |
                        Previous: <del style={{ color: '#f87171' }}>{log.old_value}</del> |
                        New: <ins style={{ color: '#34d399', textDecoration: 'none', fontWeight: '600' }}>{log.new_value}</ins>
                      </div>
                    )}
                    <div style={{ marginTop: '8px', padding: '6px 12px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '4px', fontStyle: 'italic', color: 'var(--text-secondary)' }}>
                      &ldquo;{log.reason}&rdquo;
                    </div>
                    <div className="audit-log-meta">
                      Logged by <strong>{log.username || 'System'}</strong> on {new Date(log.timestamp).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 5: SETTINGS */}
        {activeTab === 'settings' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            {/* Facility code mapping configuration */}
            <div className="card">
              <div className="chart-header">
                <span className="chart-title">Map Plant / Meter Codes to Facilities</span>
              </div>
              
              <form onSubmit={handleCreateFacility} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '16px', marginBottom: '32px', alignItems: 'flex-end' }}>
                <div className="form-group">
                  <label className="form-label">Facility Name</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    placeholder="e.g. Heidelberg Logistics Center" 
                    value={facName}
                    onChange={(e) => setFacName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Source Plant / Meter Code</label>
                  <input 
                    type="text" 
                    className="form-input" 
                    placeholder="e.g. 1300, E-MTR-5544" 
                    value={facCode}
                    onChange={(e) => setFacCode(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Grid Emission Region</label>
                  <select 
                    className="tenant-select" 
                    value={facRegion}
                    onChange={(e) => setFacRegion(e.target.value)}
                  >
                    <option value="US-CA">US California Grid (CAMX)</option>
                    <option value="US-NY">US Upstate NY Grid (NYUP)</option>
                    <option value="US-TX">US Texas Grid (ERCOT)</option>
                    <option value="DE">German Grid (DE)</option>
                    <option value="UK">United Kingdom Grid (UK)</option>
                    <option value="GLOBAL">Global Average Grid (GLOBAL)</option>
                  </select>
                </div>
                <button type="submit" className="btn btn-primary" style={{ width: 'auto', padding: '10px 24px' }}>
                  Add Mapped Site
                </button>
              </form>

              <h4 style={{ fontSize: '13px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '12px' }}>Mapped Facilities Configuration</h4>
              <div className="table-container">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Facility Name</th>
                      <th>Lookup Code mapping</th>
                      <th>Applied Grid Factor Region</th>
                    </tr>
                  </thead>
                  <tbody>
                    {facilities.map((fac) => (
                      <tr key={fac.id}>
                        <td style={{ fontWeight: '600' }}>{fac.name}</td>
                        <td><code>{fac.facility_code}</code></td>
                        <td>
                          <span className="badge badge-pending" style={{ backgroundColor: 'rgba(6, 182, 212, 0.08)', color: 'var(--color-primary)' }}>
                            {fac.region}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Test info */}
            <div className="card">
              <div className="chart-header">
                <span className="chart-title">System Information & Seed Configurations</span>
              </div>
              <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                Breathe ESG prototype system uses local DB instance storage. You can seed additional emission factors or reset mappings using the triggers below. Standard factors use EPA/DEFRA methodologies for diesel fuel, pipeline natural gas, and regional grid electricity.
              </p>
              
              <div style={{ marginTop: '20px', display: 'flex', gap: '16px' }}>
                <button className="btn btn-secondary" style={{ width: 'auto' }} onClick={handleTriggerSeed}>
                  Trigger Re-Seeding Configuration
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
