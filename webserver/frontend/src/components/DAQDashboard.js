import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, CheckCircle, Gauge, RefreshCw, RotateCcw, Send,
  Settings, ShieldAlert, Square, Wifi, WifiOff, Zap,
} from 'lucide-react';
import { isTimestampStale, messageFreshnessTimestamp, useNowTick } from '../hooks/useStaleness';
import './DAQDashboard.css';

const DAQ_DBC_FILENAME = 'DAQ-Firmware.dbc';
const STALE_DEFAULT_MS = 2500;
const OFFLINE_DEFAULT_MS = 5000;
const COMMAND_HISTORY_LIMIT = 80;
const ACCEL_DISTANCE_TARGET_FT = 246;

const COMMANDS = {
  setBoardIdBase: 0x0D0000C1,
  resetBase: 0x0D0000C2,
  accelTimer: 0x0DA000C3,
};

const BOARD_OPTIONS = [
  { label: 'Default', name: 'Default', id: 0x00 },
  { label: 'DBF', name: 'DBF', id: 0x0A },
  { label: 'DBL', name: 'DBL', id: 0x0B },
  { label: 'DBR', name: 'DBR', id: 0x0C },
];

const BOARDS = [
  {
    key: 'dbf',
    name: 'DBF',
    title: 'Front Board',
    id: 0x0A,
    statusMessage: 'DBF_Status',
    timestampSignal: 'DBF_Status_Timestamp',
    resetLabel: 'Reset DBF',
    metrics: [
      { label: 'FL wheel', signal: 'DBF_WSPD_FL_MPH', unit: 'MPH', fallbackSignal: 'DBF_WSPD_FL_RPM', fallbackUnit: 'RPM' },
      { label: 'FR wheel', signal: 'DBF_WSPD_FR_MPH', unit: 'MPH', fallbackSignal: 'DBF_WSPD_FR_RPM', fallbackUnit: 'RPM' },
      { label: 'Steering', signal: 'DBF_Steering_Angle_Deg', unit: 'deg' },
      { label: 'Pitot', signal: 'DBF_Pitot_MPH', unit: 'MPH' },
    ],
  },
  {
    key: 'dbl',
    name: 'DBL',
    title: 'Back Left Board',
    id: 0x0B,
    statusMessage: 'DBL_Status',
    timestampSignal: 'DBL_Status_Timestamp',
    resetLabel: 'Reset DBL',
    metrics: [
      { label: 'BL wheel', signal: 'DBL_WSPD_BL_MPH', unit: 'MPH', fallbackSignal: 'DBL_WSPD_BL_RPM', fallbackUnit: 'RPM' },
      { label: 'Shock', signal: 'DBL_Shock_BL_mm', unit: 'mm' },
      { label: 'Swirl CT', signal: 'DBL_CT_Swirl_Deg_C', unit: 'C' },
      { label: 'Tach L', signal: 'DBL_Tach_L_RPM', unit: 'RPM' },
    ],
  },
  {
    key: 'dbr',
    name: 'DBR',
    title: 'Back Right Board',
    id: 0x0C,
    statusMessage: 'DBR_Status',
    timestampSignal: 'DBR_Status_Timestamp',
    resetLabel: 'Reset DBR',
    metrics: [
      { label: 'BR wheel', signal: 'DBR_WSPD_BR_MPH', unit: 'MPH', fallbackSignal: 'DBR_WSPD_BR_RPM', fallbackUnit: 'RPM' },
      { label: 'Shock', signal: 'DBR_Shock_BR_mm', unit: 'mm' },
      { label: 'Motor CT', signal: 'DBR_CT_Motor_Deg_C', unit: 'C' },
      { label: 'Tach R', signal: 'DBR_Tach_R_RPM', unit: 'RPM' },
    ],
  },
];

const DETAIL_GROUPS = {
  dbf: [
    { title: 'Wheel Speed FL', signals: ['DBF_WSPD_FL_MPH', 'DBF_WSPD_FL_RPM', 'DBF_WSPD_FL_Avg_Delta'], health: [{ signal: 'DBF_WSPD_FL_Valid', kind: 'valid' }, { signal: 'DBF_WSPD_FL_Timeout', kind: 'fault', label: 'Timeout' }] },
    { title: 'Wheel Speed FR', signals: ['DBF_WSPD_FR_MPH', 'DBF_WSPD_FR_RPM', 'DBF_WSPD_FR_Avg_Delta'], health: [{ signal: 'DBF_WSPD_FR_Valid', kind: 'valid' }, { signal: 'DBF_WSPD_FR_Timeout', kind: 'fault', label: 'Timeout' }] },
    { title: 'Shock FL', signals: ['DBF_Shock_FL_mm', 'DBF_Shock_FL_Raw_mV', 'DBF_Shock_FL_Filt_mV'], trend: 'DBF_Shock_FL_mm', health: [{ signal: 'DBF_Shock_FL_Valid', kind: 'valid' }, { signal: 'DBF_Shock_FL_ADC_Err', kind: 'fault', label: 'ADC error' }] },
    { title: 'Shock FR', signals: ['DBF_Shock_FR_mm', 'DBF_Shock_FR_Raw_mV', 'DBF_Shock_FR_Filt_mV'], trend: 'DBF_Shock_FR_mm', health: [{ signal: 'DBF_Shock_FR_Valid', kind: 'valid' }, { signal: 'DBF_Shock_FR_ADC_Err', kind: 'fault', label: 'ADC error' }] },
    { title: 'Steering Angle', signals: ['DBF_Steering_Angle_Deg', 'DBF_Steering_Angle_Raw_mV', 'DBF_Steering_Angle_Filt_mV'], trend: 'DBF_Steering_Angle_Deg', centered: true, health: [{ signal: 'DBF_Steering_Angle_Valid', kind: 'valid' }, { signal: 'DBF_Steering_Angle_ADC_Err', kind: 'fault', label: 'ADC error' }] },
    { title: 'Pitot Tube', signals: ['DBF_Pitot_MPH', 'DBF_Pitot_Raw_mV', 'DBF_Pitot_Filt_mV'], trend: 'DBF_Pitot_MPH', health: [{ signal: 'DBF_Pitot_Valid', kind: 'valid' }, { signal: 'DBF_Pitot_ADC_Err', kind: 'fault', label: 'ADC error' }] },
    { title: 'Odometer', signals: ['FL_Odo', 'FR_Odo'], derived: 'odoDiff' },
  ],
  dbl: [
    { title: 'Wheel Speed BL', signals: ['DBL_WSPD_BL_MPH', 'DBL_WSPD_BL_RPM', 'DBL_WSPD_BL_Avg_Delta'], health: [{ signal: 'DBL_WSPD_BL_Valid', kind: 'valid' }, { signal: 'DBL_WSPD_BL_Timeout', kind: 'fault', label: 'Timeout' }] },
    { title: 'Shock BL', signals: ['DBL_Shock_BL_mm', 'DBL_Shock_BL_Raw_mV', 'DBL_Shock_BL_Filt_mV'], trend: 'DBL_Shock_BL_mm', health: [{ signal: 'DBL_Shock_BL_Valid', kind: 'valid' }, { signal: 'DBL_Shock_BL_ADC_Err', kind: 'fault', label: 'ADC error' }] },
    { title: 'Coolant Swirl', signals: ['DBL_CT_Swirl_Deg_C', 'DBL_CT_Swirl_Raw_mV', 'DBL_CT_Swirl_Filt_mV'], trend: 'DBL_CT_Swirl_Deg_C', health: [{ signal: 'DBL_CT_Swirl_Valid', kind: 'valid' }, { signal: 'DBL_CT_Swirl_ADC_Err', kind: 'fault', label: 'ADC error' }, { signal: 'DBL_CT_Swirl_Out_of_Range', kind: 'warning', label: 'Out of range' }] },
    { title: 'Coolant Rad 1', signals: ['DBL_CT_Rad1_Deg_C', 'DBL_CT_Rad1_Raw_mV', 'DBL_CT_Rad1_Filt_mV'], trend: 'DBL_CT_Rad1_Deg_C', health: [{ signal: 'DBL_CT_Rad1_Valid', kind: 'valid' }, { signal: 'DBL_CT_Rad1_ADC_Err', kind: 'fault', label: 'ADC error' }, { signal: 'DBL_CT_Rad1_Out_of_Range', kind: 'warning', label: 'Out of range' }] },
    { title: 'Coolant Rad 2', signals: ['DBL_CT_Rad2_Deg_C', 'DBL_CT_Rad2_Raw_mV', 'DBL_CT_Rad2_Filt_mV'], trend: 'DBL_CT_Rad2_Deg_C', health: [{ signal: 'DBL_CT_Rad2_Valid', kind: 'valid' }, { signal: 'DBL_CT_Rad2_ADC_Err', kind: 'fault', label: 'ADC error' }, { signal: 'DBL_CT_Rad2_Out_of_Range', kind: 'warning', label: 'Out of range' }] },
    { title: 'Tach L', signals: ['DBL_Tach_L_RPM', 'DBL_Tach_L_Avg_Delta'], health: [{ signal: 'DBL_Tach_L_Valid', kind: 'valid' }, { signal: 'DBL_Tach_L_Timeout', kind: 'fault', label: 'Timeout' }] },
  ],
  dbr: [
    { title: 'Wheel Speed BR', signals: ['DBR_WSPD_BR_MPH', 'DBR_WSPD_BR_RPM', 'DBR_WSPD_BR_Avg_Delta'], health: [{ signal: 'DBR_WSPD_BR_Valid', kind: 'valid' }, { signal: 'DBR_WSPD_BR_Timeout', kind: 'fault', label: 'Timeout' }] },
    { title: 'Shock BR', signals: ['DBR_Shock_BR_mm', 'DBR_Shock_BR_Raw_mV', 'DBR_Shock_BR_Filt_mV'], trend: 'DBR_Shock_BR_mm', health: [{ signal: 'DBR_Shock_BR_Valid', kind: 'valid' }, { signal: 'DBR_Shock_BR_ADC_Err', kind: 'fault', label: 'ADC error' }] },
    { title: 'Motor Coolant', signals: ['DBR_CT_Motor_Deg_C', 'DBR_CT_Motor_Raw_mV', 'DBR_CT_Motor_Filt_mV'], trend: 'DBR_CT_Motor_Deg_C', health: [{ signal: 'DBL_CT_Motor_Valid', kind: 'valid', label: 'Valid' }, { signal: 'DBL_CT_Motor_ADC_Err', kind: 'fault', label: 'ADC error' }, { signal: 'DBL_CT_Motor_Out_of_Range', kind: 'warning', label: 'Out of range' }] },
    { title: 'Inverter Coolant', signals: ['DBR_CT_Inv_Deg_C', 'DBR_CT_Inv_Raw_mV', 'DBR_CT_Inv_Filt_mV'], trend: 'DBR_CT_Inv_Deg_C', health: [{ signal: 'DBL_CT_Inv_Valid', kind: 'valid', label: 'Valid' }, { signal: 'DBL_CT_Inv_ADC_Err', kind: 'fault', label: 'ADC error' }, { signal: 'DBL_CT_Inv_Out_of_Range', kind: 'warning', label: 'Out of range' }] },
    { title: 'Tach R', signals: ['DBR_Tach_R_RPM', 'DBR_Tach_R_Avg_Delta'], health: [{ signal: 'DBR_Tach_R_Valid', kind: 'valid' }, { signal: 'DBR_Tach_R_Timeout', kind: 'fault', label: 'Timeout' }] },
  ],
};

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'dbf', label: 'Front DBF' },
  { key: 'dbl', label: 'Left DBL' },
  { key: 'dbr', label: 'Right DBR' },
  { key: 'config', label: 'Config' },
];

function hex(value, width = 0) {
  if (value == null || Number.isNaN(Number(value))) return '--';
  return `0x${Number(value).toString(16).toUpperCase().padStart(width, '0')}`;
}

function byteString(data = []) {
  return data.map((b) => Number(b).toString(16).toUpperCase().padStart(2, '0')).join(' ');
}

function signalValue(payload) {
  if (payload == null) return null;
  if (typeof payload === 'object') {
    if (typeof payload.raw === 'number') return payload.raw;
    return payload.value ?? null;
  }
  return payload;
}

function numericValue(payload) {
  const value = signalValue(payload);
  if (typeof value === 'number') return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function boolValue(payload) {
  const value = signalValue(payload);
  if (value == null) return false;
  if (typeof value === 'string') {
    const normalized = value.trim().toUpperCase();
    return normalized === 'TRUE' || normalized === '1' || normalized === 'ON';
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric !== 0 : Boolean(value);
}

function unitFor(payload, fallback = '') {
  return payload && typeof payload === 'object' && payload.unit ? payload.unit : fallback;
}

function formatValue(payload, fallbackUnit = '', decimals = 1) {
  const value = signalValue(payload);
  if (value == null) return '--';
  if (typeof value === 'number') {
    const text = Number.isInteger(value) ? String(value) : value.toFixed(decimals);
    const unit = unitFor(payload, fallbackUnit);
    return unit ? `${text} ${unit}` : text;
  }
  return String(value);
}

function formatAge(timestampSeconds, nowMs) {
  if (!timestampSeconds) return 'No data';
  const ageMs = Math.max(0, nowMs - timestampSeconds * 1000);
  if (ageMs < 1000) return `${Math.round(ageMs)} ms`;
  return `${(ageMs / 1000).toFixed(1)} s`;
}

function boardCommandId(base, boardId) {
  return base | (boardId << 20);
}

function DAQDashboard({
  messages = [],
  connected = false,
  connectionStatus = {},
  stats = {},
  dbcFiles = [],
  onSendMessage,
  onUpdateDBCConfig,
}) {
  const nowMs = useNowTick(500);
  const [activeSection, setActiveSection] = useState('overview');
  const [staleMs, setStaleMs] = useState(() => Number(localStorage.getItem('daqStaleMs')) || STALE_DEFAULT_MS);
  const [offlineMs, setOfflineMs] = useState(() => Number(localStorage.getItem('daqOfflineMs')) || OFFLINE_DEFAULT_MS);
  const [selectedBusId, setSelectedBusId] = useState('');
  const [commandHistory, setCommandHistory] = useState([]);
  const [setIdTarget, setSetIdTarget] = useState(0x00);
  const [setIdNew, setSetIdNew] = useState(0x0A);
  const [minMax, setMinMax] = useState({});

  const connectedBuses = (connectionStatus.buses || []).filter((bus) => bus.connected);

  useEffect(() => {
    if (!selectedBusId && connectedBuses.length === 1) {
      setSelectedBusId(connectedBuses[0].bus_id);
    }
  }, [connectedBuses, selectedBusId]);

  useEffect(() => {
    localStorage.setItem('daqStaleMs', String(staleMs));
  }, [staleMs]);

  useEffect(() => {
    localStorage.setItem('daqOfflineMs', String(offlineMs));
  }, [offlineMs]);

  const daqDbcEntry = dbcFiles.find((file) => file.filename === DAQ_DBC_FILENAME);
  const daqDbcEnabled = !!daqDbcEntry?.enabled;

  const latestByMessage = useMemo(() => {
    const map = new Map();
    messages.forEach((msg) => {
      const decoded = msg?.decoded;
      const name = decoded?.message_name;
      if (!name || !decoded?.signals) return;
      const isDaq = decoded.source_dbc === DAQ_DBC_FILENAME || /^DB[FLR]_/.test(name);
      if (!isDaq) return;
      const ts = messageFreshnessTimestamp(msg) || msg.timestamp || 0;
      const prev = map.get(name);
      if (!prev || ts >= prev.ts) {
        map.set(name, { ...msg, ts, signals: decoded.signals, messageName: name });
      }
    });
    return map;
  }, [messages]);

  const latestBySignal = useMemo(() => {
    const map = new Map();
    latestByMessage.forEach((entry) => {
      Object.entries(entry.signals).forEach(([signal, payload]) => {
        const prev = map.get(signal);
        if (!prev || entry.ts >= prev.ts) {
          map.set(signal, { payload, ts: entry.ts, messageName: entry.messageName });
        }
      });
    });
    return map;
  }, [latestByMessage]);

  const sampleSignal = useCallback((name) => latestBySignal.get(name), [latestBySignal]);
  const samplePayload = useCallback((name) => sampleSignal(name)?.payload, [sampleSignal]);

  useEffect(() => {
    if (latestBySignal.size === 0) return;
    setMinMax((prev) => {
      let changed = false;
      const next = { ...prev };
      latestBySignal.forEach((entry, signal) => {
        const value = numericValue(entry.payload);
        if (value == null || !Number.isFinite(value)) return;
        const old = next[signal];
        if (!old || value < old.min || value > old.max) {
          next[signal] = {
            min: old ? Math.min(old.min, value) : value,
            max: old ? Math.max(old.max, value) : value,
          };
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [latestBySignal]);

  const boardStates = useMemo(() => BOARDS.map((board) => {
    const status = latestByMessage.get(board.statusMessage);
    const ageMs = status?.ts ? nowMs - status.ts * 1000 : Infinity;
    const state = !status ? 'offline' : ageMs > offlineMs ? 'offline' : ageMs > staleMs ? 'stale' : 'online';
    const faults = countBoardFaults(board.key, latestBySignal);
    return {
      ...board,
      statusFrame: status,
      ageMs,
      state,
      faults,
      timestamp: samplePayload(board.timestampSignal),
    };
  }), [latestByMessage, latestBySignal, nowMs, offlineMs, staleMs, samplePayload]);

  const overviewStats = useMemo(() => {
    const online = boardStates.filter((board) => board.state === 'online').length;
    const faultCount = boardStates.reduce((sum, board) => sum + board.faults, 0);
    const coolantSignals = ['DBL_CT_Swirl_Deg_C', 'DBL_CT_Rad1_Deg_C', 'DBL_CT_Rad2_Deg_C', 'DBR_CT_Motor_Deg_C', 'DBR_CT_Inv_Deg_C'];
    const highestCoolant = coolantSignals
      .map((signal) => numericValue(samplePayload(signal)))
      .filter((value) => value != null)
      .reduce((max, value) => Math.max(max, value), null);
    return { online, faultCount, highestCoolant };
  }, [boardStates, samplePayload]);

  const sendCommand = useCallback(async (canId, data, meaning, confirmText = null) => {
    if (confirmText && !window.confirm(confirmText)) return false;
    const payload = data.slice(0, 8);
    while (payload.length < 8) payload.push(0);
    const ok = await onSendMessage?.(canId, payload, true, false, selectedBusId || null);
    const entry = {
      ts: Date.now() / 1000,
      ok: !!ok,
      id: canId,
      data: payload,
      busId: selectedBusId || 'auto',
      meaning,
    };
    setCommandHistory((prev) => [entry, ...prev].slice(0, COMMAND_HISTORY_LIMIT));
    return ok;
  }, [onSendMessage, selectedBusId]);

  const enableDaqDbc = useCallback(async () => {
    if (!daqDbcEntry || !onUpdateDBCConfig) return;
    const rest = dbcFiles.filter((file) => file.filename !== DAQ_DBC_FILENAME);
    await onUpdateDBCConfig([{ ...daqDbcEntry, enabled: true }, ...rest]);
  }, [daqDbcEntry, dbcFiles, onUpdateDBCConfig]);

  const sendReset = useCallback((board) => sendCommand(
    boardCommandId(COMMANDS.resetBase, board.id),
    [0, 0, 0, 0, 0, 0, 0, 0],
    `Reset ${board.name}`,
    `Reset ${board.name} (${hex(board.id, 2)})? The board will reboot briefly.`
  ), [sendCommand]);

  const sendSetId = useCallback(() => {
    const canId = boardCommandId(COMMANDS.setBoardIdBase, Number(setIdTarget));
    return sendCommand(
      canId,
      [Number(setIdNew), 0, 0, 0, 0, 0, 0, 0],
      `Set board ID ${hex(setIdTarget, 2)} -> ${hex(setIdNew, 2)}`,
      `Send set-board-ID command ${hex(canId, 8)} with payload ${hex(setIdNew, 2)}? The target board will write flash and reset.`
    );
  }, [sendCommand, setIdTarget, setIdNew]);

  const sendAccelCommand = useCallback((command, label, confirmText = null) => sendCommand(
    COMMANDS.accelTimer,
    [command, 0, 0, 0, 0, 0, 0, 0],
    `Acceleration timer: ${label}`,
    confirmText
  ), [sendCommand]);

  const rxRate = stats.message_rate || connectionStatus.message_rate || 0;
  const latestFrameTs = Math.max(0, ...Array.from(latestByMessage.values()).map((entry) => entry.ts || 0));

  return (
    <div className="daq-dashboard">
      <header className="daq-header">
        <div className="daq-title">
          <Activity size={22} />
          <div>
            <h2>DAQ Dashboard</h2>
            <span>DBF / DBL / DBR telemetry and controls</span>
          </div>
        </div>
        <div className="daq-header-metrics">
          <StatusChip tone={connected ? 'ok' : 'fault'} icon={connected ? <Wifi size={14} /> : <WifiOff size={14} />} label={connected ? 'Connected' : 'Disconnected'} />
          <StatusChip tone={daqDbcEnabled ? 'ok' : 'warn'} label={daqDbcEnabled ? 'DAQ DBC enabled' : 'DAQ DBC inactive'} />
          <MetricPill label="RX" value={`${Number(rxRate).toFixed(1)} fps`} />
          <MetricPill label="Decoded" value={latestBySignal.size} />
        </div>
      </header>

      {!daqDbcEnabled && (
        <div className="daq-banner warn">
          <AlertTriangle size={16} />
          <span>{daqDbcEntry ? 'DAQ-Firmware.dbc is present but disabled.' : 'DAQ-Firmware.dbc is not listed by the backend yet.'}</span>
          {daqDbcEntry && onUpdateDBCConfig && (
            <button type="button" onClick={enableDaqDbc}>Enable DAQ DBC</button>
          )}
        </div>
      )}

      <section className="daq-toolbar">
        <div className="daq-toolbar-group">
          <label>
            Command bus
            <select value={selectedBusId} onChange={(e) => setSelectedBusId(e.target.value)}>
              <option value="">Auto</option>
              {connectedBuses.map((bus) => (
                <option key={bus.bus_id} value={bus.bus_id}>{bus.bus_id}</option>
              ))}
            </select>
          </label>
          <MetricPill label="Last frame" value={formatAge(latestFrameTs, nowMs)} />
        </div>
      </section>

      <nav className="daq-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={activeSection === tab.key ? 'active' : ''}
            onClick={() => setActiveSection(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeSection === 'overview' && (
        <OverviewSection
          boardStates={boardStates}
          overviewStats={overviewStats}
          samplePayload={samplePayload}
          sampleSignal={sampleSignal}
          nowMs={nowMs}
          staleMs={staleMs}
          minMax={minMax}
          sendReset={sendReset}
          sendAccelCommand={sendAccelCommand}
          commandHistory={commandHistory}
        />
      )}
      {['dbf', 'dbl', 'dbr'].includes(activeSection) && (
        <BoardDetailSection
          board={BOARDS.find((b) => b.key === activeSection)}
          groups={DETAIL_GROUPS[activeSection]}
          latestByMessage={latestByMessage}
          sampleSignal={sampleSignal}
          samplePayload={samplePayload}
          nowMs={nowMs}
          staleMs={staleMs}
          minMax={minMax}
          sendReset={sendReset}
        />
      )}
      {activeSection === 'config' && (
        <ConfigSection
          staleMs={staleMs}
          offlineMs={offlineMs}
          setStaleMs={setStaleMs}
          setOfflineMs={setOfflineMs}
          setIdTarget={setIdTarget}
          setSetIdTarget={setSetIdTarget}
          setIdNew={setIdNew}
          setSetIdNew={setSetIdNew}
          sendSetId={sendSetId}
          sendReset={sendReset}
          sendAccelCommand={sendAccelCommand}
          commandHistory={commandHistory}
        />
      )}
    </div>
  );
}

function countBoardFaults(boardKey, latestBySignal) {
  const groups = DETAIL_GROUPS[boardKey] || [];
  return groups.reduce((count, group) => count + (group.health || []).reduce((sum, health) => {
    const entry = latestBySignal.get(health.signal);
    if (!entry) return sum;
    const value = boolValue(entry.payload);
    if (health.kind === 'valid') return sum + (value ? 0 : 1);
    return sum + (value ? 1 : 0);
  }, 0), 0);
}

function StatusChip({ tone = 'neutral', icon = null, label }) {
  return <span className={`daq-chip ${tone}`}>{icon}{label}</span>;
}

function MetricPill({ label, value }) {
  return (
    <span className="daq-metric-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </span>
  );
}

function OverviewSection({ boardStates, overviewStats, samplePayload, sampleSignal, nowMs, staleMs, minMax, sendReset, sendAccelCommand, commandHistory }) {
  const accelState = getAccelState(samplePayload);
  return (
    <section className="daq-section">
      <div className="daq-summary-grid">
        <SummaryCard icon={<CheckCircle size={18} />} label="Boards online" value={`${overviewStats.online}/3`} tone={overviewStats.online === 3 ? 'ok' : 'warn'} />
        <SummaryCard icon={<ShieldAlert size={18} />} label="Active faults" value={overviewStats.faultCount} tone={overviewStats.faultCount === 0 ? 'ok' : 'fault'} />
        <SummaryCard icon={<Gauge size={18} />} label="Highest coolant" value={overviewStats.highestCoolant == null ? '--' : `${overviewStats.highestCoolant.toFixed(0)} C`} tone={overviewStats.highestCoolant > 90 ? 'fault' : overviewStats.highestCoolant > 75 ? 'warn' : 'ok'} />
        <SummaryCard icon={<Zap size={18} />} label="Accel timer" value={accelState} tone={accelState === 'Complete' ? 'ok' : accelState === 'Running' ? 'warn' : 'neutral'} />
      </div>

      <div className="daq-board-grid">
        {boardStates.map((board) => (
          <div key={board.key} className={`daq-board-card ${board.state}`}>
            <div className="daq-card-head">
              <div>
                <h3>{board.name}</h3>
                <span>{board.title} - {hex(board.id, 2)}</span>
              </div>
              <StatusChip tone={board.state === 'online' ? 'ok' : board.state === 'stale' ? 'warn' : 'fault'} label={board.state.toUpperCase()} />
            </div>
            <div className="daq-board-meta">
              <span>Heartbeat: {formatValue(board.timestamp, 'ms', 0)}</span>
              <span>Age: {formatAge(board.statusFrame?.ts, nowMs)}</span>
              <span>Faults: {board.faults}</span>
            </div>
            <div className="daq-mini-grid">
              {board.metrics.map((metric) => (
                <SignalMini
                  key={metric.signal}
                  label={metric.label}
                  payload={samplePayload(metric.signal)}
                  unit={metric.unit}
                  fallbackPayload={metric.fallbackSignal ? samplePayload(metric.fallbackSignal) : null}
                  fallbackUnit={metric.fallbackUnit}
                  minMax={minMax[metric.signal] || (metric.fallbackSignal ? minMax[metric.fallbackSignal] : null)}
                />
              ))}
            </div>
            <button type="button" className="daq-button danger" onClick={() => sendReset(board)}>
              <RotateCcw size={14} /> {board.resetLabel}
            </button>
          </div>
        ))}
      </div>

      <AccelTimerSection
        samplePayload={samplePayload}
        sampleSignal={sampleSignal}
        nowMs={nowMs}
        staleMs={staleMs}
        sendAccelCommand={sendAccelCommand}
        commandHistory={commandHistory}
      />
    </section>
  );
}

function SummaryCard({ icon, label, value, tone }) {
  return (
    <div className={`daq-summary-card ${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SignalMini({ label, payload, unit, fallbackPayload = null, fallbackUnit = '', minMax }) {
  const hasPrimary = signalValue(payload) != null;
  const displayPayload = hasPrimary ? payload : fallbackPayload;
  return (
    <div className="daq-signal-mini">
      <span>{label}</span>
      <strong>{formatValue(displayPayload, hasPrimary ? unit : fallbackUnit)}</strong>
      {hasPrimary && fallbackPayload && <small>{formatValue(fallbackPayload, fallbackUnit)}</small>}
      {!hasPrimary && fallbackPayload && <small>MPH unavailable</small>}
      {minMax && !fallbackPayload && <small>{minMax.min.toFixed(1)} / {minMax.max.toFixed(1)}</small>}
    </div>
  );
}

function BoardDetailSection({ board, groups, latestByMessage, sampleSignal, samplePayload, nowMs, staleMs, minMax, sendReset }) {
  return (
    <section className="daq-section">
      <div className="daq-section-header">
        <div>
          <h3>{board.title}</h3>
          <span>{board.name} {hex(board.id, 2)} decoded telemetry</span>
        </div>
        <button type="button" className="daq-button danger" onClick={() => sendReset(board)}>
          <RotateCcw size={14} /> {board.resetLabel}
        </button>
      </div>
      <div className="daq-detail-grid">
        {groups.map((group) => {
          const messageEntry = findGroupMessage(group, latestByMessage);
          const stale = messageEntry ? isTimestampStale(messageEntry.ts, nowMs, staleMs) : false;
          return (
            <div key={group.title} className={`daq-detail-card ${stale ? 'stale' : ''} ${!messageEntry ? 'missing' : ''}`}>
              <div className="daq-card-head">
                <h4>{group.title}</h4>
                <span>{!messageEntry ? 'No data' : stale ? 'Stale' : formatAge(messageEntry.ts, nowMs)}</span>
              </div>
              <div className="daq-health-row">
                {(group.health || []).map((health) => (
                  <HealthChip key={health.signal} health={health} payload={samplePayload(health.signal)} />
                ))}
              </div>
              <div className="daq-signal-table">
                {group.signals.map((signal) => (
                  <SignalRow key={signal} signal={signal} entry={sampleSignal(signal)} minMax={minMax[signal]} />
                ))}
                {group.derived === 'odoDiff' && (
                  <div className="daq-signal-row">
                    <span>Front odo diff</span>
                    <strong>{formatOdoDiff(samplePayload('FL_Odo'), samplePayload('FR_Odo'))}</strong>
                    <small>FL - FR</small>
                  </div>
                )}
              </div>
              {group.trend && <Sparkline value={numericValue(samplePayload(group.trend))} centered={group.centered} />}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function findGroupMessage(group, latestByMessage) {
  for (const entry of latestByMessage.values()) {
    if (group.signals.some((signal) => Object.prototype.hasOwnProperty.call(entry.signals, signal))) return entry;
  }
  return null;
}

function HealthChip({ health, payload }) {
  if (payload == null) return <StatusChip tone="neutral" label={`${health.label || labelFromSignal(health.signal)}: --`} />;
  const value = boolValue(payload);
  let tone = 'ok';
  let text = 'OK';
  if (health.kind === 'valid') {
    tone = value ? 'ok' : 'fault';
    text = value ? 'Valid' : 'Invalid';
  } else if (health.kind === 'warning') {
    tone = value ? 'warn' : 'ok';
    text = value ? (health.label || 'Warning') : 'OK';
  } else {
    tone = value ? 'fault' : 'ok';
    text = value ? (health.label || 'Fault') : 'OK';
  }
  return <StatusChip tone={tone} label={`${health.label || labelFromSignal(health.signal)}: ${text}`} />;
}

function SignalRow({ signal, entry, minMax }) {
  const missingMph = !entry && signal.endsWith('_MPH');
  return (
    <div className="daq-signal-row">
      <span title={signal}>{labelFromSignal(signal)}</span>
      <strong>{missingMph ? 'unavailable' : formatValue(entry?.payload)}</strong>
      <small>{missingMph ? 'older DBC' : (minMax ? `${minMax.min.toFixed(2)} / ${minMax.max.toFixed(2)}` : '-- / --')}</small>
    </div>
  );
}

function Sparkline({ value, centered = false }) {
  const pct = value == null ? 0 : centered ? Math.max(0, Math.min(100, 50 + value / 7.2)) : Math.max(0, Math.min(100, value));
  return (
    <div className="daq-bar">
      {centered && <span className="daq-bar-center" />}
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

function AccelTimerSection({ samplePayload, sampleSignal, nowMs, staleMs, sendAccelCommand, commandHistory }) {
  const enabledPayload = samplePayload('DBF_Accel_Timer_Enabled') ?? samplePayload('DBF_Accel_Timer_Dist_Enabled');
  const runningPayload = samplePayload('DBF_Accel_Timer_Running') ?? samplePayload('DBF_Accel_Timer_Dist_Running');
  const completePayload = samplePayload('DBF_Accel_Timer_Complete') ?? samplePayload('DBF_Accel_Timer_Dist_Complete');
  const enabled = boolValue(enabledPayload);
  const running = boolValue(runningPayload);
  const complete = boolValue(completePayload);
  const flComplete = boolValue(samplePayload('DBF_Accel_Timer_FL_Complete'));
  const frComplete = boolValue(samplePayload('DBF_Accel_Timer_FR_Complete'));
  const avgComplete = boolValue(samplePayload('DBF_Accel_Timer_Avg_Complete'));
  const fl = numericValue(samplePayload('DBF_Accel_Timer_FL_Time'));
  const fr = numericValue(samplePayload('DBF_Accel_Timer_FR_Time'));
  const avg = numericValue(samplePayload('DBF_Accel_Timer_Avg_Time'));
  const flDistanceEntry = sampleSignal('DBF_Accel_Timer_FL_Distance');
  const frDistanceEntry = sampleSignal('DBF_Accel_Timer_FR_Distance');
  const avgDistanceEntry = sampleSignal('DBF_Accel_Timer_Avg_Distance');
  const flDistance = numericValue(flDistanceEntry?.payload);
  const frDistance = numericValue(frDistanceEntry?.payload);
  const avgDistance = numericValue(avgDistanceEntry?.payload);
  const distanceTimestamp = Math.max(
    flDistanceEntry?.ts || 0,
    frDistanceEntry?.ts || 0,
    avgDistanceEntry?.ts || 0
  );
  const hasDistanceData = flDistance != null || frDistance != null || avgDistance != null;
  const distanceStale = distanceTimestamp > 0 && isTimestampStale(distanceTimestamp, nowMs, staleMs);
  const spread = fl != null && fr != null ? Math.abs(fl - fr) : null;
  const distanceSpread = flDistance != null && frDistance != null ? Math.abs(flDistance - frDistance) : null;
  const state = getAccelState(samplePayload);

  return (
    <section className="daq-section daq-accel-layout">
      <div className="daq-accel-card">
        <div className="daq-card-head">
          <div>
            <h3>Acceleration Timer</h3>
            <span>246 ft DBF timer</span>
          </div>
          <StatusChip tone={complete ? 'ok' : running ? 'warn' : enabled ? 'ok' : 'neutral'} label={state} />
        </div>
        <div className="daq-accel-actions">
          <button type="button" className="daq-button primary big" onClick={() => sendAccelCommand(1, 'Arm / Enable')}>
            <Zap size={18} /> Arm / Enable
          </button>
          <button type="button" className="daq-button" onClick={() => sendAccelCommand(2, 'Reset Results')}>
            <RefreshCw size={16} /> Reset Results
          </button>
          <button type="button" className="daq-button danger" onClick={() => sendAccelCommand(0, 'Disable', running ? 'Disable the acceleration timer while it is running?' : null)}>
            <Square size={16} /> Disable
          </button>
        </div>
        <div className="daq-health-row">
          <StatusChip tone={enabled ? 'ok' : 'neutral'} label={`Enabled: ${enabled ? 'YES' : 'NO'}`} />
          <StatusChip tone={running ? 'warn' : 'neutral'} label={`Running: ${running ? 'YES' : 'NO'}`} />
          <StatusChip tone={complete ? 'ok' : 'neutral'} label={`Complete: ${complete ? 'YES' : 'NO'}`} />
        </div>
        {spread != null && spread > 150 && (
          <div className="daq-banner warn inline"><AlertTriangle size={15} /> FL/FR differ by {spread.toFixed(0)} ms.</div>
        )}
        {distanceSpread != null && distanceSpread > 5 && running && (
          <div className="daq-banner warn inline"><AlertTriangle size={15} /> FL/FR distance differ by {distanceSpread.toFixed(1)} ft.</div>
        )}
      </div>
      <div className="daq-distance-card">
        <div className="daq-card-head">
          <div>
            <h3>Live Distance</h3>
            <span>{hasDistanceData ? `${formatAge(distanceTimestamp, nowMs)}${distanceStale ? ' stale' : ''}` : 'No distance data'}</span>
          </div>
          <StatusChip tone={hasDistanceData ? (distanceStale ? 'warn' : 'ok') : 'neutral'} label={hasDistanceData ? (distanceStale ? 'Stale' : 'Live') : 'Waiting'} />
        </div>
        {hasDistanceData ? (
          <div className="daq-distance-grid">
            <DistanceProgress label="Average" value={avgDistance} primary />
            <DistanceProgress label="FL" value={flDistance} />
            <DistanceProgress label="FR" value={frDistance} />
          </div>
        ) : (
          <div className="daq-no-distance">No decoded `DBF_Accel_Timer_Distance` frame has arrived yet.</div>
        )}
      </div>
      <div className="daq-result-grid">
        <TimerResult label="FL" ms={fl} complete={flComplete} />
        <TimerResult label="FR" ms={fr} complete={frComplete} />
        <TimerResult label="Average" ms={avg} complete={avgComplete} highlight />
      </div>
      <CommandHistory history={commandHistory.slice(0, 8)} />
    </section>
  );
}

function DistanceProgress({ label, value, primary = false }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, (value / ACCEL_DISTANCE_TARGET_FT) * 100));
  return (
    <div className={`daq-distance-progress ${primary ? 'primary' : ''}`}>
      <div className="daq-distance-label">
        <span>{label}</span>
        <strong>{value == null ? '--' : `${value.toFixed(2)} ft`}</strong>
      </div>
      <div className="daq-distance-bar">
        <span style={{ width: `${pct}%` }} />
      </div>
      <small>{pct.toFixed(0)}% of {ACCEL_DISTANCE_TARGET_FT} ft</small>
    </div>
  );
}

function TimerResult({ label, ms, complete, highlight = false }) {
  return (
    <div className={`daq-timer-result ${complete ? 'complete' : ''} ${highlight ? 'highlight' : ''}`} title={ms == null ? 'No raw ms value' : `${ms} ms`}>
      <span>{label}</span>
      <strong>{ms == null ? '--' : `${(ms / 1000).toFixed(3)} s`}</strong>
      <small>{complete ? 'locked' : 'waiting'}</small>
    </div>
  );
}

function getAccelState(samplePayload) {
  const enabled = boolValue(samplePayload('DBF_Accel_Timer_Enabled') ?? samplePayload('DBF_Accel_Timer_Dist_Enabled'));
  const running = boolValue(samplePayload('DBF_Accel_Timer_Running') ?? samplePayload('DBF_Accel_Timer_Dist_Running'));
  const complete = boolValue(samplePayload('DBF_Accel_Timer_Complete') ?? samplePayload('DBF_Accel_Timer_Dist_Complete'));
  if (complete) return 'Complete';
  if (running) return 'Running';
  if (enabled) return 'Armed';
  return 'Disabled';
}

function ConfigSection({ staleMs, offlineMs, setStaleMs, setOfflineMs, setIdTarget, setSetIdTarget, setIdNew, setSetIdNew, sendSetId, sendReset, sendAccelCommand, commandHistory }) {
  const setCanId = boardCommandId(COMMANDS.setBoardIdBase, Number(setIdTarget));
  return (
    <section className="daq-section daq-config-layout">
      <div className="daq-config-card protected">
        <div className="daq-card-head"><h3>Set Board ID</h3><Settings size={18} /></div>
        <div className="daq-form-grid">
          <label>Target current ID
            <select value={setIdTarget} onChange={(e) => setSetIdTarget(Number(e.target.value))}>
              {BOARD_OPTIONS.map((board) => <option key={board.id} value={board.id}>{board.label} ({hex(board.id, 2)})</option>)}
            </select>
          </label>
          <label>New board ID
            <select value={setIdNew} onChange={(e) => setSetIdNew(Number(e.target.value))}>
              {BOARD_OPTIONS.filter((board) => board.id !== 0).map((board) => <option key={board.id} value={board.id}>{board.label} ({hex(board.id, 2)})</option>)}
            </select>
          </label>
        </div>
        <div className="daq-command-preview">
          ID {hex(setCanId, 8)} - payload {hex(setIdNew, 2)} 00 00 00 00 00 00 00
        </div>
        <button type="button" className="daq-button danger" onClick={sendSetId}><Send size={14} /> Send Set ID</button>
      </div>

      <div className="daq-config-card">
        <div className="daq-card-head"><h3>Board Resets</h3><RotateCcw size={18} /></div>
        <div className="daq-reset-row">
          {BOARDS.map((board) => (
            <button key={board.key} type="button" className="daq-button danger" onClick={() => sendReset(board)}>{board.resetLabel}</button>
          ))}
        </div>
      </div>

      <div className="daq-config-card">
        <div className="daq-card-head"><h3>Heartbeat Thresholds</h3><Activity size={18} /></div>
        <div className="daq-form-grid">
          <label>Stale after ms
            <input type="number" min="500" max="60000" value={staleMs} onChange={(e) => setStaleMs(Math.max(500, Number(e.target.value) || STALE_DEFAULT_MS))} />
          </label>
          <label>Offline after ms
            <input type="number" min="1000" max="120000" value={offlineMs} onChange={(e) => setOfflineMs(Math.max(1000, Number(e.target.value) || OFFLINE_DEFAULT_MS))} />
          </label>
        </div>
      </div>

      <div className="daq-config-card">
        <div className="daq-card-head"><h3>Acceleration Command</h3><Zap size={18} /></div>
        <div className="daq-reset-row">
          <button type="button" className="daq-button primary" onClick={() => sendAccelCommand(1, 'Arm / Enable')}>Arm</button>
          <button type="button" className="daq-button" onClick={() => sendAccelCommand(2, 'Reset Results')}>Reset Results</button>
          <button type="button" className="daq-button danger" onClick={() => sendAccelCommand(0, 'Disable')}>Disable</button>
        </div>
      </div>

      <CommandHistory history={commandHistory} />
    </section>
  );
}

function CommandHistory({ history }) {
  return (
    <div className="daq-command-history">
      <div className="daq-card-head"><h3>Command History</h3><span>{history.length}</span></div>
      <div className="daq-table-wrap compact">
        <table className="daq-table">
          <thead><tr><th>Time</th><th>Bus</th><th>ID</th><th>Data</th><th>Meaning</th><th>Status</th></tr></thead>
          <tbody>
            {history.map((cmd, index) => (
              <tr key={`${cmd.ts}-${index}`}>
                <td>{new Date(cmd.ts * 1000).toLocaleTimeString()}</td>
                <td>{cmd.busId}</td>
                <td>{hex(cmd.id, 8)}</td>
                <td className="mono">{byteString(cmd.data)}</td>
                <td>{cmd.meaning}</td>
                <td>{cmd.ok ? 'sent' : 'failed'}</td>
              </tr>
            ))}
            {history.length === 0 && <tr><td colSpan="6" className="daq-empty-row">No commands sent this session.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function labelFromSignal(signal) {
  return signal.replace(/^DB[FLR]_/, '').replace(/_/g, ' ');
}

function formatOdoDiff(flPayload, frPayload) {
  const fl = numericValue(flPayload);
  const fr = numericValue(frPayload);
  if (fl == null || fr == null) return '--';
  return String(fl - fr);
}

export default DAQDashboard;
