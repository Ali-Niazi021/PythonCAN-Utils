import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown, ChevronUp, Gauge, GripVertical, Layers, Pencil, Plus,
  Search, Settings, Trash2, X,
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

function readLocalConfig() {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) return { widgets: [], clusters: [] };
    const data = JSON.parse(raw);
    return {
      widgets: Array.isArray(data?.widgets) ? data.widgets : [],
      clusters: Array.isArray(data?.clusters) ? data.clusters : [],
    };
  } catch (err) {
    console.warn('Failed to read local driving dashboard config:', err);
    return { widgets: [], clusters: [] };
  }
}

function writeLocalConfig(widgets, clusters) {
  localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify({ widgets, clusters }));
}

function makeId(prefix) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

// Pull the numeric component out of a decoded signal payload.
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

/* ──────────────────────────────────────────────────────
   Cluster header bar (rename, collapse, delete)
   ────────────────────────────────────────────────────── */
function ClusterHeader({ cluster, editMode, onRename, onToggleCollapse, onDelete }) {
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(cluster.name);
  const inputRef = useRef(null);

  useEffect(() => {
    if (renaming && inputRef.current) inputRef.current.focus();
  }, [renaming]);

  const commitRename = () => {
    const trimmed = nameDraft.trim();
    if (trimmed && trimmed !== cluster.name) onRename(cluster.id, trimmed);
    setRenaming(false);
  };

  return (
    <div className="cluster-header" onDragOver={(e) => e.preventDefault()}>
      <button
        type="button"
        className="cluster-collapse-btn"
        onClick={() => onToggleCollapse(cluster.id)}
        title={cluster.collapsed ? 'Expand' : 'Collapse'}
      >
        {cluster.collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {renaming ? (
        <input
          ref={inputRef}
          className="cluster-rename-input"
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitRename();
            if (e.key === 'Escape') { setRenaming(false); setNameDraft(cluster.name); }
          }}
        />
      ) : (
        <span className="cluster-name">
          <Layers size={14} />
          {cluster.name}
        </span>
      )}

      {editMode && (
        <div className="cluster-tools">
          {!renaming && (
            <button
              type="button"
              className="cluster-tool-btn"
              onClick={() => { setNameDraft(cluster.name); setRenaming(true); }}
              title="Rename cluster"
            >
              <Pencil size={13} />
            </button>
          )}
          <button
            type="button"
            className="cluster-tool-btn danger"
            onClick={() => onDelete(cluster.id)}
            title="Delete cluster (widgets move to ungrouped)"
          >
            <Trash2 size={13} />
          </button>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────
   Draggable widget card
   ────────────────────────────────────────────────────── */
function DraggableWidgetCard({
  widget, index, clusterId, editMode, catalog, latestSignals, nowMs, staleTimeoutMs,
  onRemove, onPatch, onDragStart, onDragOver, onDragEnd, onDrop,
}) {
  const metaEntry = useMemo(() => {
    const entries = catalog.get(widget.signal_name);
    if (!entries || entries.length === 0) return null;
    if (widget.source_dbc) {
      const match = entries.find((e) => e.sourceDbc === widget.source_dbc);
      if (match) return match;
    }
    return entries[0];
  }, [catalog, widget.signal_name, widget.source_dbc]);

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
      className={`driving-card size-${widget.size || 'medium'} ${stale ? 'stale' : ''} ${!hasData ? 'no-data' : ''} ${editMode ? 'draggable' : ''}`}
      draggable={editMode}
      onDragStart={(e) => onDragStart(e, widget.id, clusterId, index)}
      onDragOver={(e) => onDragOver(e, clusterId, index)}
      onDragEnd={onDragEnd}
      onDrop={(e) => onDrop(e, clusterId, index)}
    >
      <div className="driving-card-head">
        {editMode && (
          <GripVertical size={14} className="driving-drag-handle" />
        )}
        <span className="driving-card-label" title={widget.signal_name}>{label}</span>
        {editMode && (
          <div className="driving-card-tools">
            <button type="button" className="danger" onClick={() => onRemove(widget.id)} title="Remove">
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
        <WidgetConfigPanel
          widget={widget}
          type={type}
          catalog={catalog}
          onPatch={onPatch}
        />
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────
   Widget configuration panel (shown in edit mode)
   ────────────────────────────────────────────────────── */
function WidgetConfigPanel({ widget, type, catalog, onPatch }) {
  return (
    <div className="driving-card-config">
      <label>
        Label
        <input
          type="text"
          value={widget.label || ''}
          placeholder={widget.signal_name}
          onChange={(e) => onPatch(widget.id, { label: e.target.value || null })}
        />
      </label>
      <div className="driving-config-row">
        <label>
          Display
          <select
            value={widget.display_type || 'auto'}
            onChange={(e) => onPatch(widget.id, { display_type: e.target.value })}
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
            onChange={(e) => onPatch(widget.id, { size: e.target.value })}
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
              onPatch(widget.id, { decimals: v === '' ? null : Math.max(0, Math.min(6, parseInt(v, 10) || 0)) });
            }}
          />
        </label>
      )}
      {catalog.get(widget.signal_name)?.length > 1 && (
        <label>
          DBC source
          <select
            value={widget.source_dbc || ''}
            onChange={(e) => onPatch(widget.id, { source_dbc: e.target.value || null })}
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
  );
}

/* ──────────────────────────────────────────────────────
   Main DrivingDashboard component
   ────────────────────────────────────────────────────── */
function DrivingDashboard({ messages = [], dbcFiles = [], staleTimeoutMs = 30000 }) {
  const [widgets, setWidgets] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [catalog, setCatalog] = useState(new Map());
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [pickerQuery, setPickerQuery] = useState('');
  const [saveStatus, setSaveStatus] = useState('idle');
  const [newClusterName, setNewClusterName] = useState('');
  const [assignTarget, setAssignTarget] = useState(null); // widgetId → clusterId being chosen

  const nowMs = useNowTick(1000);
  const saveTimerRef = useRef(null);
  const initialisedRef = useRef(false);
  const dragRef = useRef(null); // { widgetId, fromClusterId, fromIndex }

  const enabledDbcCount = dbcFiles.filter((f) => f.enabled).length;

  /* ── Load persisted layout and signal catalog ── */
  useEffect(() => {
    let cancelled = false;

    async function loadConfig() {
      const local = readLocalConfig();
      try {
        const data = await apiService.getDrivingDashboardConfig();
        if (!cancelled) {
          const w = Array.isArray(data?.widgets) ? data.widgets : [];
          const c = Array.isArray(data?.clusters) ? data.clusters : [];
          setWidgets(w.length > 0 ? w : local.widgets);
          setClusters(c.length > 0 || w.length > 0 ? c : local.clusters);
        }
      } catch (err) {
        if (!cancelled) {
          setWidgets(local.widgets);
          setClusters(local.clusters);
        }
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

  /* ── Persist layout (debounced) ── */
  const persist = useCallback((nextWidgets, nextClusters) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setSaveStatus('saving');
    let savedLocally = false;
    try {
      writeLocalConfig(nextWidgets, nextClusters);
      savedLocally = true;
    } catch (err) {
      console.error('Failed to save local driving dashboard config:', err);
    }

    saveTimerRef.current = setTimeout(async () => {
      try {
        await apiService.saveDrivingDashboardConfig(nextWidgets, nextClusters);
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
      if (initialisedRef.current) persist(next, clusters);
      return next;
    });
  }, [persist, clusters]);

  const updateClusters = useCallback((updater) => {
    setClusters((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      if (initialisedRef.current) persist(widgets, next);
      return next;
    });
  }, [persist, widgets]);

  useEffect(() => () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
  }, []);

  /* ── Latest decoded signals ── */
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

  /* ── Cluster helpers ── */
  const ungroupedWidgets = useMemo(
    () => widgets.filter((w) => !w.cluster_id),
    [widgets],
  );

  const widgetsByCluster = useMemo(() => {
    const map = {};
    clusters.forEach((c) => { map[c.id] = []; });
    widgets.forEach((w) => {
      if (w.cluster_id && map[w.cluster_id]) {
        map[w.cluster_id].push(w);
      }
    });
    return map;
  }, [widgets, clusters]);

  const addCluster = useCallback(() => {
    const name = newClusterName.trim();
    if (!name) return;
    const cluster = { id: makeId('cl'), name, collapsed: false };
    updateClusters((prev) => [...prev, cluster]);
    setNewClusterName('');
  }, [newClusterName, updateClusters]);

  const renameCluster = useCallback((clusterId, newName) => {
    updateClusters((prev) => prev.map((c) => (c.id === clusterId ? { ...c, name: newName } : c)));
  }, [updateClusters]);

  const toggleClusterCollapse = useCallback((clusterId) => {
    updateClusters((prev) => prev.map((c) => (c.id === clusterId ? { ...c, collapsed: !c.collapsed } : c)));
  }, [updateClusters]);

  const deleteCluster = useCallback((clusterId) => {
    // Move all widgets in this cluster to ungrouped
    updateWidgets((prev) => prev.map((w) => (w.cluster_id === clusterId ? { ...w, cluster_id: null } : w)));
    updateClusters((prev) => prev.filter((c) => c.id !== clusterId));
  }, [updateWidgets, updateClusters]);

  const assignWidgetToCluster = useCallback((widgetId, clusterId) => {
    updateWidgets((prev) => prev.map((w) => (w.id === widgetId ? { ...w, cluster_id: clusterId || null } : w)));
    setAssignTarget(null);
  }, [updateWidgets]);

  /* ── Widget CRUD ── */
  const addWidget = useCallback((signalName, sourceDbc) => {
    updateWidgets((prev) => [
      ...prev,
      {
        id: makeId('w'),
        signal_name: signalName,
        source_dbc: sourceDbc || null,
        label: null,
        display_type: 'auto',
        decimals: null,
        size: 'medium',
        cluster_id: null,
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

  /* ── Drag and drop ── */
  const handleDragStart = useCallback((e, widgetId, fromClusterId, fromIndex) => {
    dragRef.current = { widgetId, fromClusterId, fromIndex };
    e.dataTransfer.effectAllowed = 'move';
    // Make the drag image slightly translucent
    if (e.currentTarget) {
      e.currentTarget.classList.add('dragging');
    }
  }, []);

  const handleDragOver = useCallback((e, toClusterId, toIndex) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const handleDragEnd = useCallback((e) => {
    if (e.currentTarget) {
      e.currentTarget.classList.remove('dragging');
    }
    dragRef.current = null;
  }, []);

  const handleDrop = useCallback((e, toClusterId, toIndex) => {
    e.preventDefault();
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;

    const { widgetId, fromClusterId } = drag;
    // Don't drop on self
    if (fromClusterId === toClusterId && drag.fromIndex === toIndex) return;

    setWidgets((prevWidgets) => {
      const widget = prevWidgets.find((w) => w.id === widgetId);
      if (!widget) return prevWidgets;

      // Build ordered list of widgets grouped the same way the render shows them:
      // clusters in order, then ungrouped at the bottom.
      // We'll work with the flat array but track which cluster each belongs to.

      // Remove the widget from its current position
      const without = prevWidgets.filter((w) => w.id !== widgetId);

      // Update the cluster assignment if moving between clusters
      const movedWidget = {
        ...widget,
        cluster_id: toClusterId || null,
      };

      // Rebuild the full ordered list maintaining the render order:
      // cluster 0 widgets, cluster 1 widgets, ..., ungrouped widgets
      const clusterOrder = clusters.map((c) => c.id);
      // null at end = ungrouped
      const getOrder = (w) => {
        const cid = w.cluster_id || null;
        if (cid === null) return clusterOrder.length; // ungrouped last
        const idx = clusterOrder.indexOf(cid);
        return idx >= 0 ? idx : clusterOrder.length;
      };

      // Partition remaining widgets by cluster
      const byCluster = {};
      without.forEach((w) => {
        const key = w.cluster_id || '__ungrouped__';
        if (!byCluster[key]) byCluster[key] = [];
        byCluster[key].push(w);
      });

      // Insert moved widget at the target position in the target cluster
      const targetKey = toClusterId || '__ungrouped__';
      if (!byCluster[targetKey]) byCluster[targetKey] = [];
      const insertIdx = Math.min(toIndex, byCluster[targetKey].length);
      byCluster[targetKey].splice(insertIdx, 0, movedWidget);

      // Reassemble in render order
      const result = [];
      clusterOrder.forEach((cid) => {
        if (byCluster[cid]) result.push(...byCluster[cid]);
      });
      if (byCluster['__ungrouped__']) result.push(...byCluster['__ungrouped__']);

      return result;
    });
  }, [clusters]);

  // Drop handler for dropping onto a cluster header (appends to end of cluster)
  const handleClusterHeaderDrop = useCallback((e, clusterId) => {
    e.preventDefault();
    const drag = dragRef.current;
    if (!drag) return;

    const { widgetId } = drag;
    dragRef.current = null;

    setWidgets((prevWidgets) => {
      const widget = prevWidgets.find((w) => w.id === widgetId);
      if (!widget) return prevWidgets;
      if (widget.cluster_id === clusterId) return prevWidgets; // already in this cluster

      return prevWidgets.map((w) => (w.id === widgetId ? { ...w, cluster_id: clusterId } : w));
    });
  }, []);

  // Drop handler for dropping into ungrouped area
  const handleUngroupedDrop = useCallback((e) => {
    e.preventDefault();
    const drag = dragRef.current;
    if (!drag) return;

    const { widgetId, fromClusterId, fromIndex } = drag;
    dragRef.current = null;

    if (!fromClusterId) return; // already ungrouped

    setWidgets((prevWidgets) => {
      const widget = prevWidgets.find((w) => w.id === widgetId);
      if (!widget) return prevWidgets;
      return prevWidgets.map((w) => (w.id === widgetId ? { ...w, cluster_id: null } : w));
    });
  }, []);

  /* ── Signal picker ── */
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

  /* ── Render a single cluster section ── */
  const renderClusterSection = (cluster) => {
    const clusterWidgets = widgetsByCluster[cluster.id] || [];
    return (
      <div
        key={cluster.id}
        className={`cluster-section ${cluster.collapsed ? 'collapsed' : ''}`}
        onDragOver={editMode ? (e) => e.preventDefault() : undefined}
        onDrop={editMode ? (e) => handleClusterHeaderDrop(e, cluster.id) : undefined}
      >
        <ClusterHeader
          cluster={cluster}
          editMode={editMode}
          onRename={renameCluster}
          onToggleCollapse={toggleClusterCollapse}
          onDelete={deleteCluster}
        />
        {!cluster.collapsed && (
          <div className="cluster-widgets driving-grid">
            {clusterWidgets.length === 0 && editMode && (
              <div className="cluster-drop-hint">Drag widgets here</div>
            )}
            {clusterWidgets.map((widget, index) => (
              <DraggableWidgetCard
                key={widget.id}
                widget={widget}
                index={index}
                clusterId={cluster.id}
                editMode={editMode}
                catalog={catalog}
                latestSignals={latestSignals}
                nowMs={nowMs}
                staleTimeoutMs={staleTimeoutMs}
                onRemove={removeWidget}
                onPatch={patchWidget}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragEnd={handleDragEnd}
                onDrop={handleDrop}
              />
            ))}
          </div>
        )}
      </div>
    );
  };

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

      {/* ── Signal picker (edit mode) ── */}
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

      {/* ── Create cluster UI (edit mode) ── */}
      {editMode && (
        <div className="cluster-create-bar">
          <Layers size={16} />
          <input
            type="text"
            placeholder="New cluster name (e.g. Battery, Inverter, Suspension)…"
            value={newClusterName}
            onChange={(e) => setNewClusterName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') addCluster(); }}
          />
          <button
            type="button"
            className="cluster-create-btn"
            onClick={addCluster}
            disabled={!newClusterName.trim()}
          >
            <Plus size={14} /> Create Cluster
          </button>
        </div>
      )}

      {/* ── Assign widget dropdown ── */}
      {assignTarget && editMode && (
        <div className="assign-overlay" onClick={() => setAssignTarget(null)}>
          <div className="assign-panel" onClick={(e) => e.stopPropagation()}>
            <h4>Move to cluster</h4>
            <button
              type="button"
              className="assign-option"
              onClick={() => assignWidgetToCluster(assignTarget, null)}
            >
              Ungrouped
            </button>
            {clusters.map((c) => (
              <button
                key={c.id}
                type="button"
                className="assign-option"
                onClick={() => assignWidgetToCluster(assignTarget, c.id)}
              >
                <Layers size={13} /> {c.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Dashboard content ── */}
      {widgets.length === 0 ? (
        <div className="driving-empty">
          <Gauge size={40} />
          <p>No values configured yet.</p>
          <p className="driving-empty-hint">
            Click <strong>Configure</strong> and add signals to build your dashboard.
          </p>
        </div>
      ) : (
        <>
          {/* Cluster sections */}
          {clusters.map((cluster) => renderClusterSection(cluster))}

          {/* Ungrouped widgets */}
          {ungroupedWidgets.length > 0 && (
            <div
              className="ungrouped-section"
              onDragOver={editMode ? (e) => e.preventDefault() : undefined}
              onDrop={editMode ? handleUngroupedDrop : undefined}
            >
              {clusters.length > 0 && (
                <div className="ungrouped-label">
                  {clusters.length > 0 ? 'Ungrouped' : ''}
                </div>
              )}
              <div className="driving-grid">
                {ungroupedWidgets.map((widget, index) => (
                  <DraggableWidgetCard
                    key={widget.id}
                    widget={widget}
                    index={index}
                    clusterId={null}
                    editMode={editMode}
                    catalog={catalog}
                    latestSignals={latestSignals}
                    nowMs={nowMs}
                    staleTimeoutMs={staleTimeoutMs}
                    onRemove={removeWidget}
                    onPatch={patchWidget}
                    onDragStart={handleDragStart}
                    onDragOver={handleDragOver}
                    onDragEnd={handleDragEnd}
                    onDrop={handleDrop}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────
   Value renderers (unchanged from original)
   ────────────────────────────────────────────────────── */
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
