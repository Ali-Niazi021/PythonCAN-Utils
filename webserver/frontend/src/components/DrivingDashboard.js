import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown, ChevronUp, Gauge, Plus, Search, Settings, Trash2, X,
} from 'lucide-react';
import { apiService } from '../services/api';
import {
  useNowTick, isTimestampStale, messageFreshnessTimestamp,
} from '../hooks/useStaleness';
import './DrivingDashboard.css';

const DISPLAY_TYPES = [
  { value: 'auto', label: 'Auto' },
  { value: 'number', label: 'Number' },
  { value: 'gauge', label: 'Gauge' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'enum', label: 'Enum' },
];

const SIZE_OPTIONS = [
  { value: 'small', label: 'Small' },
  { value: 'medium', label: 'Medium' },
  { value: 'large', label: 'Large' },
];

const MAX_PICKER_RESULTS = 40;
const LOCAL_STORAGE_KEY = 'drivingDashboardConfig';

function readLocalWidgets() {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    return Array.isArray(data?.widgets) ? data.widgets : [];
  } catch (err) {
    console.warn('Failed to read local driving dashboard config:', err);
    return [];
  }
}

function writeLocalWidgets(widgets) {
  localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify({ widgets }));
}

function makeWidgetId() {
  return `w_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

// Pull the numeric component out of a decoded signal payload. Signals may be a
// bare number/string or a { value, raw, unit } object. Enum signals expose the
// numeric code under `raw` while `value` holds the label string.
function getNumericValue(sig) {
  if (sig == null) return null;
  if (typeof sig === 'number') return sig;
  if (typeof sig === 'object') {
    if (typeof sig.raw === 'number') return sig.raw;
    if (typeof sig.value === 'number') return sig.value;
    const parsed = Number(sig.value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  const parsed = Number(sig);
  return Number.isFinite(parsed) ? parsed : null;
}

function getDisplayValue(sig) {
  if (sig == null) return null;
  if (typeof sig === 'object') return sig.value;
  return sig;
}

function getUnit(sig, meta) {
  if (sig && typeof sig === 'object' && sig.unit) return sig.unit;
  if (meta && meta.unit) return meta.unit;
  return '';
}

// Decide how to render a widget when its display type is left on "auto".
function resolveDisplayType(widget, meta) {
  if (widget.display_type && widget.display_type !== 'auto') return widget.display_type;
  if (meta) {
    if (meta.choices && Object.keys(meta.choices).length > 0) return 'enum';
    if (meta.length === 1) return 'boolean';
    if (Number(meta.minimum) === 0 && Number(meta.maximum) === 1 && Number(meta.scale) === 1) {
      return 'boolean';
    }
  }
  return 'number';
}

function formatNumber(value, decimals) {
  if (value == null || !Number.isFinite(value)) return '--';
  if (decimals == null) {
    if (Number.isInteger(value)) return String(value);
    return value.toFixed(2);
  }
  return value.toFixed(decimals);
}

function DrivingDashboard({ messages = [], dbcFiles = [], staleTimeoutMs = 30000 }) {
  const [widgets, setWidgets] = useState([]);
  const [catalog, setCatalog] = useState(new Map());
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [pickerQuery, setPickerQuery] = useState('');
  const [saveStatus, setSaveStatus] = useState('idle'); // idle | saving | saved | saved-local | error

  const nowMs = useNowTick(1000);
  const saveTimerRef = useRef(null);
  const initialisedRef = useRef(false);

  const enabledDbcCount = dbcFiles.filter((f) => f.enabled).length;

  // Load persisted layout and the signal catalog on mount.
  useEffect(() => {
    let cancelled = false;

    async function loadConfig() {
      const localWidgets = readLocalWidgets();
      try {
        const data = await apiService.getDrivingDashboardConfig();
        if (!cancelled && Array.isArray(data?.widgets)) {
          setWidgets(data.widgets.length > 0 ? data.widgets : localWidgets);
        }
      } catch (err) {
        if (!cancelled) setWidgets(localWidgets);
        console.warn('Failed to load driving dashboard config:', err);
      } finally {
        if (!cancelled) initialisedRef.current = true;
      }
    }

    loadConfig();
    return () => { cancelled = true; };
  }, []);

  const loadCatalog = useCallback(async () => {
    setLoadingCatalog(true);
    setLoadError(null);
    try {
      const data = await apiService.getDBCMessages();
      const map = new Map();
      (data?.messages || []).forEach((msg) => {
        (msg.signals || []).forEach((signal) => {
          if (!map.has(signal.name)) map.set(signal.name, []);
          map.get(signal.name).push({
            sourceDbc: msg.source_dbc || null,
            messageName: msg.name,
            meta: signal,
          });
        });
      });
      setCatalog(map);
    } catch (err) {
      setLoadError(err?.response?.data?.detail || 'No DBC file loaded');
      setCatalog(new Map());
    } finally {
      setLoadingCatalog(false);
    }
  }, []);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog, enabledDbcCount]);

  // Persist layout changes (debounced) once the initial config has loaded.
  const persist = useCallback((nextWidgets) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setSaveStatus('saving');
    let savedLocally = false;
    try {
      writeLocalWidgets(nextWidgets);
      savedLocally = true;
    } catch (err) {
      console.error('Failed to save local driving dashboard config:', err);
    }

    saveTimerRef.current = setTimeout(async () => {
      try {
        await apiService.saveDrivingDashboardConfig(nextWidgets);
        setSaveStatus('saved');
      } catch (err) {
        if (savedLocally) {
          console.warn('Saved driving dashboard config locally; backend sync failed:', err);
          setSaveStatus('saved-local');
        } else {
          console.error('Failed to save driving dashboard config:', err);
          setSaveStatus('error');
        }
      }
    }, 500);
  }, []);

  const updateWidgets = useCallback((updater) => {
    setWidgets((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      if (initialisedRef.current) persist(next);
      return next;
    });
  }, [persist]);

  useEffect(() => () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
  }, []);

  // Latest decoded value per signal name across all buses/DBCs.
  const latestSignals = useMemo(() => {
    const map = new Map();
    messages.forEach((msg) => {
      const decoded = msg?.decoded;
      if (!decoded?.signals) return;
      const ts = messageFreshnessTimestamp(msg)
        ?? (typeof msg.timestamp === 'number' ? msg.timestamp : 0);
      Object.entries(decoded.signals).forEach(([name, sig]) => {
        const prev = map.get(name);
        if (!prev || ts >= prev.ts) {
          map.set(name, {
            sig,
            ts,
            sourceDbc: decoded.source_dbc || null,
            messageName: decoded.message_name || null,
          });
        }
      });
    });
    return map;
  }, [messages]);

  const getMetaFor = useCallback((signalName, sourceDbc) => {
    const entries = catalog.get(signalName);
    if (!entries || entries.length === 0) return null;
    if (sourceDbc) {
      const match = entries.find((e) => e.sourceDbc === sourceDbc);
      if (match) return match;
    }
    return entries[0];
  }, [catalog]);

  const addWidget = useCallback((signalName, sourceDbc) => {
    updateWidgets((prev) => [
      ...prev,
      {
        id: makeWidgetId(),
        signal_name: signalName,
        source_dbc: sourceDbc || null,
        label: null,
        display_type: 'auto',
        decimals: null,
        size: 'medium',
      },
    ]);
    setPickerQuery('');
  }, [updateWidgets]);

  const removeWidget = useCallback((id) => {
    updateWidgets((prev) => prev.filter((w) => w.id !== id));
  }, [updateWidgets]);

  const patchWidget = useCallback((id, patch) => {
    updateWidgets((prev) => prev.map((w) => (w.id === id ? { ...w, ...patch } : w)));
  }, [updateWidgets]);

  const moveWidget = useCallback((id, direction) => {
    updateWidgets((prev) => {
      const index = prev.findIndex((w) => w.id === id);
      if (index < 0) return prev;
      const target = index + direction;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }, [updateWidgets]);

  // Signal-name picker results (bus independent).
  const pickerResults = useMemo(() => {
    const query = pickerQuery.trim().toLowerCase();
    const names = Array.from(catalog.keys()).sort((a, b) => a.localeCompare(b));
    const filtered = query
      ? names.filter((name) => name.toLowerCase().includes(query))
      : names;
    return filtered.slice(0, MAX_PICKER_RESULTS).map((name) => ({
      name,
      entries: catalog.get(name),
    }));
  }, [catalog, pickerQuery]);

  const saveStatusText = {
    idle: '',
    saving: 'Saving…',
    saved: 'Saved',
    'saved-local': 'Saved locally',
    error: 'Save failed',
  }[saveStatus];

  return (
    <div className="driving-dashboard">
      <div className="driving-header">
        <div className="driving-title">
          <Gauge size={22} />
          <h2>Driving Dashboard</h2>
        </div>
        <div className="driving-header-actions">
          {saveStatusText && (
            <span className={`driving-save-status ${saveStatus}`}>{saveStatusText}</span>
          )}
          <button
            type="button"
            className={`driving-config-toggle ${editMode ? 'active' : ''}`}
            onClick={() => setEditMode((v) => !v)}
          >
            <Settings size={16} />
            {editMode ? 'Done' : 'Configure'}
          </button>
        </div>
      </div>

      {enabledDbcCount === 0 && (
        <div className="driving-banner warning">
          No DBC file is enabled. Enable a DBC to decode and select signals.
        </div>
      )}
      {loadError && enabledDbcCount > 0 && (
        <div className="driving-banner warning">{loadError}</div>
      )}

      {editMode && (
        <div className="driving-picker">
          <div className="driving-picker-header">
            <Search size={16} />
            <input
              type="text"
              placeholder="Search signals by name…"
              value={pickerQuery}
              onChange={(e) => setPickerQuery(e.target.value)}
            />
            {pickerQuery && (
              <button type="button" className="driving-picker-clear" onClick={() => setPickerQuery('')}>
                <X size={14} />
              </button>
            )}
          </div>
          <div className="driving-picker-results">
            {loadingCatalog && <div className="driving-picker-empty">Loading signals…</div>}
            {!loadingCatalog && pickerResults.length === 0 && (
              <div className="driving-picker-empty">No matching signals.</div>
            )}
            {!loadingCatalog && pickerResults.map(({ name, entries }) => (
              <div key={name} className="driving-picker-row">
                <div className="driving-picker-signal">
                  <span className="driving-picker-name">{name}</span>
                  <span className="driving-picker-meta">
                    {entries[0]?.messageName}
                    {entries.length > 1 ? ` (+${entries.length - 1} more)` : ''}
                    {entries[0]?.meta?.unit ? ` · ${entries[0].meta.unit}` : ''}
                  </span>
                </div>
                <button
                  type="button"
                  className="driving-picker-add"
                  onClick={() => addWidget(name, entries[0]?.sourceDbc)}
                >
                  <Plus size={14} /> Add
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {widgets.length === 0 ? (
        <div className="driving-empty">
          <Gauge size={40} />
          <p>No values configured yet.</p>
          <p className="driving-empty-hint">
            Click <strong>Configure</strong> and add signals to build your dashboard.
          </p>
        </div>
      ) : (
        <div className="driving-grid">
          {widgets.map((widget, index) => {
            const metaEntry = getMetaFor(widget.signal_name, widget.source_dbc);
            const meta = metaEntry?.meta || null;
            const live = latestSignals.get(widget.signal_name);
            const sig = live?.sig;
            const stale = live ? isTimestampStale(live.ts, nowMs, staleTimeoutMs) : false;
            const hasData = !!live;
            const type = resolveDisplayType(widget, meta);
            const label = widget.label || widget.signal_name;
            const numeric = getNumericValue(sig);

            return (
              <div
                key={widget.id}
                className={`driving-card size-${widget.size || 'medium'} ${stale ? 'stale' : ''} ${!hasData ? 'no-data' : ''}`}
              >
                <div className="driving-card-head">
                  <span className="driving-card-label" title={widget.signal_name}>{label}</span>
                  {editMode && (
                    <div className="driving-card-tools">
                      <button type="button" onClick={() => moveWidget(widget.id, -1)} disabled={index === 0} title="Move up">
                        <ChevronUp size={14} />
                      </button>
                      <button type="button" onClick={() => moveWidget(widget.id, 1)} disabled={index === widgets.length - 1} title="Move down">
                        <ChevronDown size={14} />
                      </button>
                      <button type="button" className="danger" onClick={() => removeWidget(widget.id)} title="Remove">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>

                <WidgetValue
                  type={type}
                  sig={sig}
                  meta={meta}
                  numeric={numeric}
                  decimals={widget.decimals}
                  hasData={hasData}
                />

                {!editMode && (
                  <div className="driving-card-foot">
                    <span className="driving-card-source">
                      {live?.messageName || metaEntry?.messageName || '—'}
                    </span>
                    {stale && <span className="driving-card-stale">stale</span>}
                  </div>
                )}

                {editMode && (
                  <div className="driving-card-config">
                    <label>
                      Label
                      <input
                        type="text"
                        value={widget.label || ''}
                        placeholder={widget.signal_name}
                        onChange={(e) => patchWidget(widget.id, { label: e.target.value || null })}
                      />
                    </label>
                    <div className="driving-config-row">
                      <label>
                        Display
                        <select
                          value={widget.display_type || 'auto'}
                          onChange={(e) => patchWidget(widget.id, { display_type: e.target.value })}
                        >
                          {DISPLAY_TYPES.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Size
                        <select
                          value={widget.size || 'medium'}
                          onChange={(e) => patchWidget(widget.id, { size: e.target.value })}
                        >
                          {SIZE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {(type === 'number' || type === 'gauge') && (
                      <label>
                        Decimals
                        <input
                          type="number"
                          min="0"
                          max="6"
                          value={widget.decimals == null ? '' : widget.decimals}
                          placeholder="auto"
                          onChange={(e) => {
                            const v = e.target.value;
                            patchWidget(widget.id, { decimals: v === '' ? null : Math.max(0, Math.min(6, parseInt(v, 10) || 0)) });
                          }}
                        />
                      </label>
                    )}
                    {catalog.get(widget.signal_name)?.length > 1 && (
                      <label>
                        DBC source
                        <select
                          value={widget.source_dbc || ''}
                          onChange={(e) => patchWidget(widget.id, { source_dbc: e.target.value || null })}
                        >
                          {catalog.get(widget.signal_name).map((entry) => (
                            <option key={`${entry.sourceDbc}_${entry.messageName}`} value={entry.sourceDbc || ''}>
                              {entry.sourceDbc || 'unknown'} · {entry.messageName}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WidgetValue({ type, sig, meta, numeric, decimals, hasData }) {
  if (!hasData) {
    return (
      <div className="driving-value">
        <span className="driving-value-main muted">--</span>
      </div>
    );
  }

  if (type === 'boolean') {
    const on = numeric != null && numeric !== 0;
    const display = getDisplayValue(sig);
    const text = typeof display === 'string' && Number.isNaN(Number(display))
      ? display
      : (on ? 'ON' : 'OFF');
    return (
      <div className="driving-value">
        <span className={`driving-bool ${on ? 'on' : 'off'}`}>{text}</span>
      </div>
    );
  }

  if (type === 'enum') {
    const display = getDisplayValue(sig);
    let text = display;
    if ((display == null || typeof display === 'number') && meta?.choices && numeric != null) {
      text = meta.choices[numeric] ?? numeric;
    }
    return (
      <div className="driving-value">
        <span className="driving-enum">{text == null ? '--' : String(text)}</span>
        {numeric != null && <span className="driving-enum-code">#{numeric}</span>}
      </div>
    );
  }

  const unit = getUnit(sig, meta);
  const valueText = formatNumber(numeric, decimals);
  const min = meta && Number.isFinite(Number(meta.minimum)) ? Number(meta.minimum) : null;
  const max = meta && Number.isFinite(Number(meta.maximum)) ? Number(meta.maximum) : null;
  const showGauge = (type === 'gauge' || (min != null && max != null && max > min));
  let pct = null;
  if (showGauge && min != null && max != null && max > min && numeric != null) {
    pct = Math.max(0, Math.min(100, ((numeric - min) / (max - min)) * 100));
  }

  return (
    <div className="driving-value">
      <div className="driving-value-line">
        <span className="driving-value-main">{valueText}</span>
        {unit && <span className="driving-value-unit">{unit}</span>}
      </div>
      {showGauge && pct != null && (
        <div className="driving-gauge">
          <div className="driving-gauge-fill" style={{ width: `${pct}%` }} />
          <div className="driving-gauge-scale">
            <span>{formatNumber(min, decimals)}</span>
            <span>{formatNumber(max, decimals)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default DrivingDashboard;
