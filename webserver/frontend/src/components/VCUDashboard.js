import React, { useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, Gauge, HeartPulse, Settings, ShieldAlert, SlidersHorizontal, Zap,
} from 'lucide-react';
import { useNowTick, isTimestampStale } from '../hooks/useStaleness';
import './VCUDashboard.css';

const SET_VCU_CONFIG_ID = 0x800000CF;

const VCU_FRAME_SIGNALS = {
  VCU_Summary: ['VCU_State', 'VCU_Speed', 'VCU_Buzzer_State', 'VCU_RTD_Active', 'VCU_Red_Car'],
  VCU_APPS_Voltages: ['VCU_APPS1_Filt_mV', 'VCU_APPS1_Raw_mV', 'VCU_APPS2_Filt_mV', 'VCU_APPS2_Raw_mV', 'VCU_BSE_Filt_mV', 'VCU_BSE_Raw_mV'],
  VCU_APPS_Values: ['VCU_APPS1_Value', 'VCU_APPS2_Value', 'VCU_APPS_Value', 'VCU_APPS_Valid', 'VCU_APPS_Implausible'],
  VCU_BSE: ['VCU_BSE_PSI', 'VCU_BSE_Valid', 'VCU_BSE_Stale', 'VCU_BSE_ADC_Err', 'VCU_BSE_Out_of_Range'],
  VCU_Dead_Car: ['VCU_Dead_HVC_Msg_Valid', 'VCU_Dead_IMD_OK', 'VCU_Dead_BMS_OK', 'VCU_Dead_SDC_OK'],
  VCU_CAN_Health: ['VCU_Controls_Passive_Err', 'VCU_Controls_Bus_Off', 'VCU_DAQ_Passive_Err', 'VCU_DAQ_Bus_Off', 'VCU_Controls_Status', 'VCU_DAQ_Status'],
  VCU_Config: [
    'VCU_Max_Torque',
    'VCU_Motor_Direction',
    'VCU_Regen_Enabled',
    'VCU_ECHO_DAQ',
    'VCU_Ignore_RTD_Switch',
    'VCU_Ignore_RTD_Brakes',
    'VCU_Use_APPS1_Only',
    'VCU_Use_APPS2_Only',
    'VCU_Ignore_APPS_Errs',
    'VCU_Ignore_BSE_Errs',
    'VCU_Ignore_SDC',
    'VCU_Ignore_Brake_Plausibility',
    'VCU_Always_Green',
    'VCU_Wheel_Diameter',
    'VCU_TC_Enabled',
    'VCU_TC_Target_Slip',
    'VCU_TC_Kp',
    'VCU_TC_Ki',
    'VCU_TC_Kd',
    'VCU_TC_Min_Front_RPM',
  ],
};

const VCU_SIGNAL_NAMES = new Set(Object.values(VCU_FRAME_SIGNALS).flat());

const STATE_LABELS = {
  0: 'LOADING',
  1: 'NOT READY',
  2: 'PLAYING RTD SOUND',
  3: 'DRIVING',
  4: 'BAP FAULT',
  5: 'HARD FAULT',
};

const BUZZER_LABELS = { 0: 'INACTIVE', 1: 'PLAYING', 2: 'DONE' };
const STATUS_LABELS = {
  0: 'OK',
  1: 'BUSY',
  2: 'OLD DATA',
  3: 'OVERFLOW',
  4: 'FIFO FULL',
  5: 'INVALID DATA',
  6: 'ERROR PASSIVE',
  7: 'BUS OFF',
  8: 'WRONG HANDLE',
  9: 'CHANNEL NOT CONFIGURED',
  10: 'INVALID PARAMETER',
  11: 'NULL POINTER',
  12: 'INVALID CHANNEL ID',
  13: 'MAX MO REACHED',
  14: 'MAX HANDLES REACHED',
  15: 'UNKNOWN',
};

const BOOLEAN_LABELS = { 0: 'FALSE', 1: 'TRUE' };
const DIRECTION_LABELS = { 0: 'REVERSE', 1: 'FORWARD' };

const CONFIG_GROUP_OPTIONS = [
  { value: 0, label: 'MAX_TORQUE' },
  { value: 1, label: 'MOTOR_DIRECTION' },
  { value: 2, label: 'REGEN_ENABLED' },
  { value: 3, label: 'DEBUG_DEFINES' },
  { value: 4, label: 'WHEEL_DIAMETER' },
  { value: 5, label: 'TRACTION_CONTROL_ENABLED' },
  { value: 6, label: 'TRACTION_CONTROL_TARGET_SLIP' },
  { value: 7, label: 'TRACTION_CONTROL_KP' },
  { value: 8, label: 'TRACTION_CONTROL_KI' },
  { value: 9, label: 'TRACTION_CONTROL_KD' },
  { value: 10, label: 'TRACTION_CONTROL_MIN_FRONT_RPM' },
];

const DEBUG_FIELDS = [
  ['echoDaq', 'VCU_ECHO_DAQ', 'SET_VCU_ECHO_DAQ', 'Echo DAQ'],
  ['ignoreRtdSwitch', 'VCU_Ignore_RTD_Switch', 'SET_VCU_Ignore_RTD_Switch', 'Ignore RTD switch'],
  ['ignoreRtdBrakes', 'VCU_Ignore_RTD_Brakes', 'SET_VCU_Ignore_RTD_Brakes', 'Ignore RTD brakes'],
  ['useApps1Only', 'VCU_Use_APPS1_Only', 'SET_VCU_Use_APPS1_Only', 'Use APPS1 only'],
  ['useApps2Only', 'VCU_Use_APPS2_Only', 'SET_VCU_Use_APPS2_Only', 'Use APPS2 only'],
  ['ignoreAppsErrs', 'VCU_Ignore_APPS_Errs', 'SET_VCU_Ignore_APPS_Errs', 'Ignore APPS errors'],
  ['ignoreBseErrs', 'VCU_Ignore_BSE_Errs', 'SET_VCU_Ignore_BSE_Errs', 'Ignore BSE errors'],
  ['ignoreSdc', 'VCU_Ignore_SDC', 'SET_VCU_Ignore_SDC', 'Ignore SDC'],
  ['ignoreBrakePlausibility', 'VCU_Ignore_Brake_Plausibility', 'SET_VCU_Ignore_Brake_Plausibility', 'Ignore brake plausibility'],
  ['alwaysGreen', 'VCU_Always_Green', 'SET_VCU_Always_Green', 'Always green'],
];

const CONFIG_READBACK_FIELDS = [
  ['VCU_Max_Torque', 'Max torque'],
  ['VCU_Motor_Direction', 'Motor direction', DIRECTION_LABELS],
  ['VCU_Regen_Enabled', 'Regen enabled', BOOLEAN_LABELS],
  ['VCU_Wheel_Diameter', 'Wheel diameter'],
  ['VCU_TC_Enabled', 'Traction control enabled', BOOLEAN_LABELS],
  ['VCU_TC_Target_Slip', 'Target slip'],
  ['VCU_TC_Kp', 'Traction control Kp'],
  ['VCU_TC_Ki', 'Traction control Ki'],
  ['VCU_TC_Kd', 'Traction control Kd'],
  ['VCU_TC_Min_Front_RPM', 'Min front RPM'],
];

const getNumeric = (signal) => {
  if (signal === undefined || signal === null) return null;
  if (typeof signal === 'number') return Number.isFinite(signal) ? signal : null;
  if (typeof signal === 'object') {
    if (typeof signal.raw === 'number') return signal.raw;
    if (typeof signal.value === 'number') return signal.value;
  }
  const parsed = Number(signal);
  return Number.isFinite(parsed) ? parsed : null;
};

const getDisplay = (signal, fallback = '--', decimals = null) => {
  if (signal === undefined || signal === null) return fallback;
  if (typeof signal === 'object') {
    const { value, raw, unit } = signal;
    if (typeof value === 'string') return value;
    if (typeof value === 'number') {
      const precision = decimals !== null ? decimals : (Number.isInteger(value) ? 0 : 2);
      return `${value.toFixed(precision)}${unit ? ` ${unit}` : ''}`;
    }
    if (typeof raw === 'number') return String(raw);
    return fallback;
  }
  if (typeof signal === 'number') {
    const precision = decimals !== null ? decimals : (Number.isInteger(signal) ? 0 : 2);
    return signal.toFixed(precision);
  }
  return String(signal);
};

const enumLabel = (signal, labels) => {
  const numeric = getNumeric(signal);
  return numeric !== null && labels[numeric] ? labels[numeric] : getDisplay(signal);
};

const bitValue = (signal) => {
  const numeric = getNumeric(signal);
  return numeric === null ? null : numeric !== 0;
};

const freshnessClass = (timestamp, nowMs, staleMs) => {
  if (!timestamp) return 'missing';
  return isTimestampStale(timestamp, nowMs, staleMs) ? 'stale' : 'fresh';
};

const freshnessLabel = (timestamp, nowMs) => {
  if (!timestamp) return 'No data';
  const ageS = Math.max(0, (nowMs - timestamp * 1000) / 1000);
  return ageS < 60 ? `${ageS.toFixed(1)}s ago` : `${Math.round(ageS)}s ago`;
};

const clampNumber = (value, min, max, fallback = min) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.min(max, Math.max(min, numeric));
};

const buildConfigFrame = (mux, config) => {
  const bytes = new Uint8Array(8);
  bytes[0] = mux;
  const view = new DataView(bytes.buffer);

  if (mux === 0) view.setInt16(1, Math.round(Number(config.maxTorqueNm || 0) * 10), true);
  if (mux === 1) bytes[1] = Number(config.motorDirection) ? 1 : 0;
  if (mux === 2) bytes[1] = config.regenEnabled ? 1 : 0;
  if (mux === 3) {
    let packed = 0;
    DEBUG_FIELDS.forEach(([key], idx) => {
      if (config[key]) packed |= (1 << idx);
    });
    bytes[1] = packed & 0xFF;
    bytes[2] = (packed >> 8) & 0xFF;
  }
  if (mux === 4) view.setUint16(1, Math.round(clampNumber(config.wheelDiameterIn, 8, 30, 18)), true);
  if (mux === 5) bytes[1] = config.tcEnabled ? 1 : 0;
  if (mux === 6) view.setUint16(1, Math.round(clampNumber(config.tcTargetSlip, 1, 5, 1) * 1000), true);
  if (mux === 7) view.setUint16(1, Math.round(clampNumber(config.tcKp, 0, 32.767, 0) * 1000), true);
  if (mux === 8) view.setUint16(1, Math.round(clampNumber(config.tcKi, 0, 32.767, 0) * 1000), true);
  if (mux === 9) view.setUint16(1, Math.round(clampNumber(config.tcKd, 0, 32.767, 0) * 1000), true);
  if (mux === 10) view.setUint16(1, Math.round(clampNumber(config.tcMinFrontRpm, 0, 32767, 0)), true);
  return Array.from(bytes);
};

const getCanonicalFrameName = (decoded) => {
  const messageName = decoded?.message_name;
  if (messageName && VCU_FRAME_SIGNALS[messageName]) return messageName;
  if (!decoded?.signals) return null;

  const signalNames = Object.keys(decoded.signals);
  let bestFrameName = null;
  let bestOverlap = 0;

  Object.entries(VCU_FRAME_SIGNALS).forEach(([frameName, expectedSignals]) => {
    const overlap = expectedSignals.reduce(
      (count, signalName) => count + (signalNames.includes(signalName) ? 1 : 0),
      0,
    );
    if (overlap > bestOverlap) {
      bestOverlap = overlap;
      bestFrameName = frameName;
    }
  });

  return bestOverlap > 0 ? bestFrameName : null;
};

function Freshness({ timestamp, nowMs, staleTimeoutMs }) {
  return (
    <span className={`freshness ${freshnessClass(timestamp, nowMs, staleTimeoutMs)}`}>
      {freshnessLabel(timestamp, nowMs)}
    </span>
  );
}

function LinearGauge({ label, value, max, unit, freshness, nowMs, staleTimeoutMs }) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="vcu-gauge-row">
      <div className="vcu-gauge-meta">
        <span>{label}</span>
        {freshness && <Freshness timestamp={freshness} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />}
      </div>
      <div className="vcu-gauge-track">
        <div className="vcu-gauge-fill" style={{ width: `${pct}%` }} />
      </div>
      <strong>{value === null ? '--' : `${value.toFixed(value >= 100 ? 0 : 1)} ${unit}`}</strong>
    </div>
  );
}

function HealthPill({ label, signal, goodWhenTrue = true, text = null }) {
  const active = bitValue(signal);
  if (active === null) return <span className="vcu-pill unknown">{label}: ?</span>;
  const good = active === goodWhenTrue;
  return <span className={`vcu-pill ${good ? 'good' : 'bad'}`}>{label}: {text || (good ? 'OK' : 'FAULT')}</span>;
}

function VCUDashboard({ messages, dbcFiles = [], onSendMessage, staleTimeoutMs = 30000 }) {
  const nowMs = useNowTick(1000);
  const [mux, setMux] = useState(0);
  const [config, setConfig] = useState({
    maxTorqueNm: 0,
    motorDirection: 1,
    regenEnabled: false,
    echoDaq: false,
    ignoreRtdSwitch: false,
    ignoreRtdBrakes: false,
    useApps1Only: false,
    useApps2Only: false,
    ignoreAppsErrs: false,
    ignoreBseErrs: false,
    ignoreSdc: false,
    ignoreBrakePlausibility: false,
    alwaysGreen: false,
    wheelDiameterIn: 18,
    tcEnabled: false,
    tcTargetSlip: 1,
    tcKp: 0,
    tcKi: 0,
    tcKd: 0,
    tcMinFrontRpm: 0,
  });
  const [sendStatus, setSendStatus] = useState(null);
  const [sendBusy, setSendBusy] = useState(false);
  const enabledDbcCount = dbcFiles.filter((file) => file.enabled).length;

  const { frames, latestSignals, matchedSourceDbc } = useMemo(() => {
    const frameMap = {};
    const signalMap = new Map();
    let latestMatchedSourceDbc = null;
    let latestMatchedTimestamp = -1;

    messages.forEach((msg) => {
      const decoded = msg?.decoded;
      if (!decoded?.signals) return;

      const frameName = getCanonicalFrameName(decoded);
      const signalEntries = Object.entries(decoded.signals).filter(([signalName]) => VCU_SIGNAL_NAMES.has(signalName));
      if (!frameName && signalEntries.length === 0) return;

      const timestamp = typeof msg.timestamp === 'number' ? msg.timestamp : 0;
      if (frameName && (!frameMap[frameName] || timestamp >= frameMap[frameName].timestamp)) {
        frameMap[frameName] = { signals: decoded.signals, timestamp };
      }

      signalEntries.forEach(([signalName, signal]) => {
        const previous = signalMap.get(signalName);
        if (!previous || timestamp >= previous.timestamp) signalMap.set(signalName, { signal, timestamp });
      });

      if (decoded.source_dbc && timestamp >= latestMatchedTimestamp) {
        latestMatchedTimestamp = timestamp;
        latestMatchedSourceDbc = decoded.source_dbc;
      }
    });

    return { frames: frameMap, latestSignals: signalMap, matchedSourceDbc: latestMatchedSourceDbc };
  }, [messages]);

  const getSignal = (name) => latestSignals.get(name)?.signal;
  const hasAnyData = latestSignals.size > 0;
  const dbcStatusText = matchedSourceDbc
    ? `Matched ${matchedSourceDbc}`
    : enabledDbcCount > 0
      ? 'Waiting for VCU signals'
      : 'No DBC enabled';

  const apps1 = getNumeric(getSignal('VCU_APPS1_Value'));
  const apps2 = getNumeric(getSignal('VCU_APPS2_Value'));
  const apps = getNumeric(getSignal('VCU_APPS_Value'));
  const bsePsi = getNumeric(getSignal('VCU_BSE_PSI'));

  const handleSendConfig = async () => {
    if (typeof onSendMessage !== 'function') {
      setSendStatus({ type: 'error', text: 'Send unavailable' });
      return;
    }
    setSendBusy(true);
    setSendStatus({ type: 'pending', text: 'Sending...' });
    try {
      const ok = await onSendMessage(SET_VCU_CONFIG_ID, buildConfigFrame(mux, config), true, false);
      setSendStatus(ok
        ? { type: 'success', text: 'Config frame sent' }
        : { type: 'error', text: 'Frame rejected by backend' });
    } catch (err) {
      setSendStatus({ type: 'error', text: `Send failed: ${err?.message || err}` });
    } finally {
      setSendBusy(false);
    }
  };

  const renderVoltagePair = (label, filtered, raw) => (
    <div className="vcu-voltage-row">
      <span>{label}</span>
      <strong>{getDisplay(filtered, '--', 3)}</strong>
      <em>{getDisplay(raw, '--', 3)}</em>
    </div>
  );

  return (
    <div className="vcu-dashboard">
      <div className="vcu-header">
        <div>
          <h2><Gauge size={22} /> VCU Dashboard</h2>
          <p>Real-time VCU telemetry matched by signal name from any decoded DBC.</p>
        </div>
        <div className="vcu-header-actions">
          <span className={`vcu-dbc-pill ${matchedSourceDbc ? 'enabled' : 'disabled'}`}>
            {dbcStatusText}
          </span>
          {sendStatus && <span className={`vcu-status-pill ${sendStatus.type}`}>{sendStatus.text}</span>}
        </div>
      </div>

      {!matchedSourceDbc && (
        <div className="vcu-notice">
          {enabledDbcCount > 0
            ? 'Waiting for decoded VCU signals from an enabled DBC.'
            : 'Enable a DBC that contains the expected VCU signals to populate this dashboard.'}
        </div>
      )}
      {!hasAnyData && (
        <div className="vcu-empty">
          <AlertTriangle size={28} />
          <div>
            <h3>No VCU frames received yet</h3>
            <p>Connect to CAN with a DBC that exposes the expected VCU signal names.</p>
          </div>
        </div>
      )}

      <div className="vcu-kpi-grid">
        <section className="vcu-card">
          <div className="vcu-card-header"><HeartPulse size={18} /><h3>State</h3><Freshness timestamp={frames.VCU_Summary?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} /></div>
          <div className={`vcu-state state-${getNumeric(getSignal('VCU_State')) ?? 'unknown'}`}>{enumLabel(getSignal('VCU_State'), STATE_LABELS)}</div>
          <div className="vcu-inline-values">
            <span>Speed <strong>{getDisplay(getSignal('VCU_Speed'))}</strong></span>
            <span>Buzzer <strong>{enumLabel(getSignal('VCU_Buzzer_State'), BUZZER_LABELS)}</strong></span>
          </div>
        </section>
        <section className="vcu-card">
          <div className="vcu-card-header"><Activity size={18} /><h3>Readiness</h3></div>
          <div className="vcu-pill-row">
            <HealthPill label="RTD" signal={getSignal('VCU_RTD_Active')} />
            <HealthPill label="Red car" signal={getSignal('VCU_Red_Car')} goodWhenTrue={false} />
            <HealthPill label="HVC msg" signal={getSignal('VCU_Dead_HVC_Msg_Valid')} />
            <HealthPill label="SDC" signal={getSignal('VCU_Dead_SDC_OK')} />
          </div>
        </section>
      </div>

      <div className="vcu-section-grid">
        <section className="vcu-card">
          <div className="vcu-card-header"><SlidersHorizontal size={18} /><h3>Pedals</h3></div>
          <LinearGauge label="APPS 1" value={apps1} max={100} unit="%" freshness={frames.VCU_APPS_Values?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />
          <LinearGauge label="APPS 2" value={apps2} max={100} unit="%" freshness={frames.VCU_APPS_Values?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />
          <LinearGauge label="APPS combined" value={apps} max={100} unit="%" freshness={frames.VCU_APPS_Values?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />
          <LinearGauge label="BSE" value={bsePsi} max={10000} unit="PSI" freshness={frames.VCU_BSE?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />
        </section>
        <section className="vcu-card">
          <div className="vcu-card-header"><Zap size={18} /><h3>Sensor Voltages</h3></div>
          <div className="vcu-voltage-head"><span>Signal</span><strong>Filtered</strong><em>Raw</em></div>
          {renderVoltagePair('APPS 1', getSignal('VCU_APPS1_Filt_mV'), getSignal('VCU_APPS1_Raw_mV'))}
          {renderVoltagePair('APPS 2', getSignal('VCU_APPS2_Filt_mV'), getSignal('VCU_APPS2_Raw_mV'))}
          {renderVoltagePair('BSE', getSignal('VCU_BSE_Filt_mV'), getSignal('VCU_BSE_Raw_mV'))}
        </section>
      </div>

      <section className="vcu-card">
        <div className="vcu-card-header"><ShieldAlert size={18} /><h3>Health and Faults</h3></div>
        <div className="vcu-health-grid">
          <div>
            <h4>APPS</h4>
            <div className="vcu-pill-row">
              <HealthPill label="APPS valid" signal={getSignal('VCU_APPS_Valid')} />
              <HealthPill label="Implausible" signal={getSignal('VCU_APPS_Implausible')} goodWhenTrue={false} />
              <HealthPill label="APPS1 stale" signal={getSignal('VCU_APPS1_Stale')} goodWhenTrue={false} />
              <HealthPill label="APPS2 stale" signal={getSignal('VCU_APPS2_Stale')} goodWhenTrue={false} />
              <HealthPill label="APPS1 ADC" signal={getSignal('VCU_APPS1_ADC_Err')} goodWhenTrue={false} />
              <HealthPill label="APPS2 ADC" signal={getSignal('VCU_APPS2_ADC_Err')} goodWhenTrue={false} />
              <HealthPill label="APPS1 range" signal={getSignal('VCU_APPS1_Out_of_Range')} goodWhenTrue={false} />
              <HealthPill label="APPS2 range" signal={getSignal('VCU_APPS2_Out_of_Range')} goodWhenTrue={false} />
            </div>
          </div>
          <div>
            <h4>BSE</h4>
            <div className="vcu-pill-row">
              <HealthPill label="Valid" signal={getSignal('VCU_BSE_Valid')} />
              <HealthPill label="Stale" signal={getSignal('VCU_BSE_Stale')} goodWhenTrue={false} />
              <HealthPill label="ADC" signal={getSignal('VCU_BSE_ADC_Err')} goodWhenTrue={false} />
              <HealthPill label="Range" signal={getSignal('VCU_BSE_Out_of_Range')} goodWhenTrue={false} />
            </div>
          </div>
          <div>
            <h4>Dead Car Inputs</h4>
            <div className="vcu-pill-row">
              <HealthPill label="HVC msg" signal={getSignal('VCU_Dead_HVC_Msg_Valid')} />
              <HealthPill label="IMD" signal={getSignal('VCU_Dead_IMD_OK')} />
              <HealthPill label="BMS" signal={getSignal('VCU_Dead_BMS_OK')} />
              <HealthPill label="SDC" signal={getSignal('VCU_Dead_SDC_OK')} />
            </div>
          </div>
          <div>
            <h4>CAN Health</h4>
            <div className="vcu-pill-row">
              <HealthPill label="Controls passive" signal={getSignal('VCU_Controls_Passive_Err')} goodWhenTrue={false} />
              <HealthPill label="Controls bus off" signal={getSignal('VCU_Controls_Bus_Off')} goodWhenTrue={false} />
              <HealthPill label="DAQ passive" signal={getSignal('VCU_DAQ_Passive_Err')} goodWhenTrue={false} />
              <HealthPill label="DAQ bus off" signal={getSignal('VCU_DAQ_Bus_Off')} goodWhenTrue={false} />
              <HealthPill label="Controls TX seen" signal={getSignal('VCU_Controls_TX_Fault_Seen')} goodWhenTrue={false} />
              <HealthPill label="Controls RX seen" signal={getSignal('VCU_Controls_RX_Fault_Seen')} goodWhenTrue={false} />
              <HealthPill label="DAQ TX seen" signal={getSignal('VCU_DAQ_TX_Fault_Seen')} goodWhenTrue={false} />
              <HealthPill label="DAQ RX seen" signal={getSignal('VCU_DAQ_RX_Fault_Seen')} goodWhenTrue={false} />
            </div>
            <div className="vcu-status-grid">
              <span>Controls status <strong>{enumLabel(getSignal('VCU_Controls_Status'), STATUS_LABELS)}</strong></span>
              <span>DAQ status <strong>{enumLabel(getSignal('VCU_DAQ_Status'), STATUS_LABELS)}</strong></span>
              <span>TX errs <strong>{getDisplay(getSignal('VCU_Controls_TX_Errs'))}</strong></span>
              <span>RX errs <strong>{getDisplay(getSignal('VCU_Controls_RX_Errs'))}</strong></span>
            </div>
          </div>
        </div>
      </section>

      <section className="vcu-card">
        <div className="vcu-card-header"><Settings size={18} /><h3>Config</h3><Freshness timestamp={frames.VCU_Config?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} /></div>
        <div className="vcu-config-grid">
          <div className="vcu-readback-grid">
            {CONFIG_READBACK_FIELDS.map(([signalName, label, labels]) => (
              <span key={signalName}>{label} <strong>{labels ? enumLabel(getSignal(signalName), labels) : getDisplay(getSignal(signalName))}</strong></span>
            ))}
            {DEBUG_FIELDS.map(([, readSignal, , label]) => (
              <span key={readSignal}>{label} <strong>{enumLabel(getSignal(readSignal), BOOLEAN_LABELS)}</strong></span>
            ))}
          </div>
          <div className="vcu-sender">
            <label>
              Config group
              <select value={mux} onChange={(event) => setMux(Number(event.target.value))}>
                {CONFIG_GROUP_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            {mux === 0 && (
              <label>
                Max torque (Nm)
                <input type="number" min="-230" max="230" step="0.1" value={config.maxTorqueNm} onChange={(event) => setConfig((prev) => ({ ...prev, maxTorqueNm: event.target.value }))} />
              </label>
            )}
            {mux === 1 && (
              <label>
                Motor direction
                <select value={config.motorDirection} onChange={(event) => setConfig((prev) => ({ ...prev, motorDirection: Number(event.target.value) }))}>
                  <option value={0}>REVERSE</option>
                  <option value={1}>FORWARD</option>
                </select>
              </label>
            )}
            {mux === 2 && (
              <label className="vcu-checkbox">
                <input type="checkbox" checked={config.regenEnabled} onChange={(event) => setConfig((prev) => ({ ...prev, regenEnabled: event.target.checked }))} />
                Regen enabled
              </label>
            )}
            {mux === 3 && (
              <div className="vcu-debug-grid">
                {DEBUG_FIELDS.map(([key, , , label]) => (
                  <label className="vcu-checkbox" key={key}>
                    <input type="checkbox" checked={config[key]} onChange={(event) => setConfig((prev) => ({ ...prev, [key]: event.target.checked }))} />
                    {label}
                  </label>
                ))}
              </div>
            )}
            {mux === 4 && (
              <label>
                Wheel diameter (in)
                <input type="number" min="8" max="30" step="1" value={config.wheelDiameterIn} onChange={(event) => setConfig((prev) => ({ ...prev, wheelDiameterIn: event.target.value }))} />
              </label>
            )}
            {mux === 5 && (
              <label className="vcu-checkbox">
                <input type="checkbox" checked={config.tcEnabled} onChange={(event) => setConfig((prev) => ({ ...prev, tcEnabled: event.target.checked }))} />
                Traction control enabled
              </label>
            )}
            {mux === 6 && (
              <label>
                Target slip
                <input type="number" min="1" max="5" step="0.001" value={config.tcTargetSlip} onChange={(event) => setConfig((prev) => ({ ...prev, tcTargetSlip: event.target.value }))} />
              </label>
            )}
            {mux === 7 && (
              <label>
                Traction control Kp
                <input type="number" min="0" max="32.767" step="0.001" value={config.tcKp} onChange={(event) => setConfig((prev) => ({ ...prev, tcKp: event.target.value }))} />
              </label>
            )}
            {mux === 8 && (
              <label>
                Traction control Ki
                <input type="number" min="0" max="32.767" step="0.001" value={config.tcKi} onChange={(event) => setConfig((prev) => ({ ...prev, tcKi: event.target.value }))} />
              </label>
            )}
            {mux === 9 && (
              <label>
                Traction control Kd
                <input type="number" min="0" max="32.767" step="0.001" value={config.tcKd} onChange={(event) => setConfig((prev) => ({ ...prev, tcKd: event.target.value }))} />
              </label>
            )}
            {mux === 10 && (
              <label>
                Min front RPM
                <input type="number" min="0" max="32767" step="1" value={config.tcMinFrontRpm} onChange={(event) => setConfig((prev) => ({ ...prev, tcMinFrontRpm: event.target.value }))} />
              </label>
            )}
            <button type="button" onClick={handleSendConfig} disabled={sendBusy}>
              {sendBusy ? 'Sending...' : 'Send Config'}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export { buildConfigFrame };
export default VCUDashboard;
