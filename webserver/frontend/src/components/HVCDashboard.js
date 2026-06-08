import React, { useEffect, useMemo, useState } from 'react';
import {
  Battery, Activity, Gauge, Thermometer, AlertTriangle, Zap, RotateCcw, Radio,
} from 'lucide-react';
import { useNowTick, isTimestampStale, messageFreshnessTimestamp } from '../hooks/useStaleness';
import './HVCDashboard.css';

// HVC firmware reset trigger (extended ID, not currently in hvc.dbc).
const HVC_RESET_CAN_ID = 0x004001F6;
const HVC_RESET_DATA = [0, 0, 0, 0, 0, 0, 0, 0];

// BMB CAN passthrough enable/disable command (extended ID, defined in hvc.dbc
// as BMB_Passthrough_Control). DLC = 1, byte 0 bit 0 carries the request.
const HVC_BMB_PASSTHROUGH_CAN_ID = 0x004001FB;

// Map DBC message names → state key on this component.
const HVC_MESSAGE_MAP = {
  HVC_IO_Summary: 'ioSummary',
  IO_Summary: 'ioSummary',
  HVC_IO_Current: 'ioCurrent',
  IO_Current: 'ioCurrent',
  HVC_IO_VSense: 'ioVSense',
  IO_VSense: 'ioVSense',
  HVC_BMS_State: 'bmsState',
  BMS_State: 'bmsState',
  HVC_SOC: 'soc',
  SOC: 'soc',
  HVC_ACC_Summary: 'accSummary',
  ACC_Summary: 'accSummary',
  HVC_Current_Limit: 'currentLimit',
  Current_Limit: 'currentLimit',
  HVC_PL_Signal: 'plSignal',
  PL_Signal: 'plSignal',
  HVC_EMeter_Therms: 'emeterTherms',
  EMeter_Therms: 'emeterTherms',
};

const EMETER_THERM_SIGNALS = [
  ['HVC_EMeter_Therm_0_C', 'EMeter_Therm_0_C'],
  ['HVC_EMeter_Therm_1_C', 'EMeter_Therm_1_C'],
  ['HVC_EMeter_Therm_2_C', 'EMeter_Therm_2_C'],
  ['HVC_EMeter_Therm_3_C', 'EMeter_Therm_3_C'],
  ['HVC_EMeter_Therm_4_C', 'EMeter_Therm_4_C'],
  ['HVC_EMeter_Therm_5_C', 'EMeter_Therm_5_C'],
];

// Known BMS_State enum names from hvc.dbc.
const HVC_BMS_STATES = ['PRE_INIT', 'RUNNING', 'CHARGING', 'BALANCING', 'ERRORED'];

// Known BMB_Fault_State enum names from hvc.dbc.
const HVC_BMB_FAULT_STATES = ['INIT', 'IDLE', 'CHARGING', 'DISCHARGING', 'BALANCING', 'FAULT', 'RESERVED'];

// Extract numeric value from server-decoded signal payload (object {value, raw, unit}).
const getNumeric = (signal) => {
  if (signal === undefined || signal === null) return null;
  if (typeof signal === 'number') return Number.isFinite(signal) ? signal : null;
  if (typeof signal === 'object') {
    if (typeof signal.raw === 'number') return signal.raw;
    if (typeof signal.value === 'number') return signal.value;
  }
  const num = Number(signal);
  return Number.isFinite(num) ? num : null;
};

// Extract display string (enum label etc.) from a decoded signal.
const getDisplay = (signal, fallback = '--') => {
  if (signal === undefined || signal === null) return fallback;
  if (typeof signal === 'object') {
    if (typeof signal.value === 'string') return signal.value;
    if (signal.value !== undefined && signal.value !== null) return String(signal.value);
    if (signal.raw !== undefined && signal.raw !== null) return String(signal.raw);
    return fallback;
  }
  return String(signal);
};

const formatVoltsFromMv = (signal) => {
  const v = getNumeric(signal);
  return v === null ? '--' : `${(v / 1000).toFixed(2)} V`;
};

const formatAmpsFromMa = (signal) => {
  const v = getNumeric(signal);
  return v === null ? '--' : `${(v / 1000).toFixed(2)} A`;
};

const formatTempC = (signal) => {
  const v = getNumeric(signal);
  return v === null ? '--' : `${v.toFixed(1)} °C`;
};

const formatPercent = (signal) => {
  const v = getNumeric(signal);
  return v === null ? '--' : `${v.toFixed(2)} %`;
};

const formatCapacityAh = (signal) => {
  const v = getNumeric(signal);
  return v === null ? '--' : `${(v / 3600).toFixed(2)} Ah`;
};

const getSignal = (signals, ...names) => {
  if (!signals) return undefined;
  for (const name of names) {
    if (signals[name] !== undefined) return signals[name];
  }
  return undefined;
};

const getSignalEntry = (signals, ...names) => {
  if (!signals) return { name: null, signal: undefined };
  for (const name of names) {
    if (signals[name] !== undefined) return { name, signal: signals[name] };
  }
  return { name: null, signal: undefined };
};

const normalizeStateName = (raw) => {
  const upper = String(raw || '').toUpperCase();
  return HVC_BMS_STATES.find((s) => upper.includes(s)) || null;
};

const formatFlagLabel = (name) => name
  .replace(/^HVC_Err_/, '')
  .replace(/^Err_/, '')
  .replace(/^HVC_/, '')
  .replace(/([A-Z])/g, ' $1')
  .replace(/_/g, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const freshnessClass = (timestampSec, nowMs, staleMs) => {
  if (!timestampSec) return 'missing';
  return isTimestampStale(timestampSec, nowMs, staleMs) ? 'stale' : 'fresh';
};

const freshnessLabel = (timestampSec, nowMs) => {
  if (!timestampSec) return 'No data';
  const ageS = Math.max(0, (nowMs - timestampSec * 1000) / 1000);
  if (ageS < 60) return `${ageS.toFixed(1)}s ago`;
  return `${Math.round(ageS)}s ago`;
};

function HVCDashboard({ messages, onSendMessage, staleTimeoutMs = 30000 }) {
  const nowMs = useNowTick(1000);
  const [resetBusy, setResetBusy] = useState(false);
  const [resetStatus, setResetStatus] = useState(null);
  const [passthroughEnabled, setPassthroughEnabled] = useState(false);
  const [passthroughBusy, setPassthroughBusy] = useState(false);
  const [passthroughStatus, setPassthroughStatus] = useState(null);

  // ---- Aggregate latest HVC frames ----------------------------------------
  const frames = useMemo(() => {
    const acc = {
      ioSummary: null, ioCurrent: null, ioVSense: null,
      bmsState: null, soc: null, accSummary: null,
      currentLimit: null, plSignal: null, emeterTherms: null,
    };
    if (!messages || messages.length === 0) return acc;

    messages.forEach((msg) => {
      const decoded = msg?.decoded;
      if (!decoded || !decoded.signals) return;
      const key = HVC_MESSAGE_MAP[decoded.message_name];
      if (!key) return;
      const ts = typeof msg.timestamp === 'number' ? msg.timestamp : null;
      const freshnessTs = messageFreshnessTimestamp(msg);
      const existing = acc[key];
      if (!existing || (ts !== null && ts > existing.timestamp)) {
        acc[key] = { signals: decoded.signals, timestamp: ts, freshnessTimestamp: freshnessTs };
      }
    });
    return acc;
  }, [messages]);

  const hasAnyFrame = Object.values(frames).some((f) => f !== null);

  // ---- Handlers ------------------------------------------------------------
  const handleResetHVC = async () => {
    if (typeof onSendMessage !== 'function') {
      setResetStatus({ type: 'error', text: 'Reset unavailable: send handler missing' });
      return;
    }
    if (!window.confirm('Send HVC reset command now?')) return;

    setResetBusy(true);
    setResetStatus({ type: 'pending', text: 'Sending reset command...' });
    try {
      const ok = await onSendMessage(HVC_RESET_CAN_ID, HVC_RESET_DATA, true, false);
      setResetStatus(ok
        ? { type: 'success', text: `Reset sent: 0x${HVC_RESET_CAN_ID.toString(16).toUpperCase()}` }
        : { type: 'error', text: 'Failed to send reset command' });
    } catch (err) {
      setResetStatus({ type: 'error', text: `Failed to send reset: ${err?.message || err}` });
    } finally {
      setResetBusy(false);
    }
  };

  const handleTogglePassthrough = async () => {
    if (typeof onSendMessage !== 'function') {
      setPassthroughStatus({ type: 'error', text: 'Send handler unavailable' });
      return;
    }
    const next = !passthroughEnabled;
    setPassthroughBusy(true);
    setPassthroughStatus({
      type: 'pending',
      text: next ? 'Enabling BMB passthrough...' : 'Disabling BMB passthrough...',
    });
    try {
      const ok = await onSendMessage(HVC_BMB_PASSTHROUGH_CAN_ID, [next ? 1 : 0], true, false);
      if (ok) {
        setPassthroughEnabled(next);
        setPassthroughStatus({
          type: 'success',
          text: next ? 'BMB passthrough enabled' : 'BMB passthrough disabled',
        });
      } else {
        setPassthroughStatus({ type: 'error', text: 'Frame rejected by backend' });
      }
    } catch (err) {
      setPassthroughStatus({
        type: 'error',
        text: `Failed to toggle passthrough: ${err?.message || err}`,
      });
    } finally {
      setPassthroughBusy(false);
    }
  };

  // ---- Derived signals -----------------------------------------------------
  const soc = frames.soc?.signals || {};
  const acc = frames.accSummary?.signals || {};
  const ioSummary = frames.ioSummary?.signals || {};
  const ioVSense = frames.ioVSense?.signals || {};
  const ioCurrent = frames.ioCurrent?.signals || {};
  const bmsState = frames.bmsState?.signals || {};
  const currentLimit = frames.currentLimit?.signals || {};
  const plSignal = frames.plSignal?.signals || {};
  const emeterTherms = frames.emeterTherms?.signals || {};

  const sdcStatus = getSignalEntry(ioSummary, 'HVC_SDC_Open', 'SDC_Open', 'SDC_Closed');
  const imdStatus = getSignalEntry(ioSummary, 'HVC_IMD_Fault', 'IMD_Fault', 'IMD_Ok');
  const bmsFaultStatus = getSignalEntry(ioSummary, 'HVC_BMS_Fault', 'BMS_Fault', 'BMS_Fault_Ok');

  const stateText = getDisplay(getSignal(bmsState, 'HVC_BMS_State', 'BMS_State'), '--');
  const normalizedState = normalizeStateName(stateText);
  const stateFlags = Object.entries(bmsState)
    .filter(([name]) => name.startsWith('HVC_Err_') || name.startsWith('Err_'))
    .sort(([a], [b]) => a.localeCompare(b));

  const renderFreshness = (frame) => (
    <span className={`freshness ${freshnessClass(frame?.freshnessTimestamp, nowMs, staleTimeoutMs)}`}>
      {freshnessLabel(frame?.freshnessTimestamp, nowMs)}
    </span>
  );

  const renderFaultBadge = (label, signal, invert = false) => {
    const num = getNumeric(signal);
    if (num === null) return <span className="hvc-badge unknown">{label}: ?</span>;
    const faulted = invert ? num === 0 : num !== 0;
    return <span className={`hvc-badge ${faulted ? 'bad' : 'good'}`}>{label}: {faulted ? 'FAULT' : 'OK'}</span>;
  };

  return (
    <div className="hvc-dashboard">
      <div className="hvc-header">
        <div className="hvc-header-left">
          <h2><Gauge size={22} /> HVC Dashboard</h2>
          <p>Real-time high-voltage controller telemetry decoded from hvc.dbc.</p>
        </div>
        <div className="hvc-header-actions">
          <button
            type="button"
            className={`hvc-passthrough-btn ${passthroughEnabled ? 'on' : 'off'}`}
            onClick={handleTogglePassthrough}
            disabled={passthroughBusy}
            title="Toggle BMB CAN passthrough on the LV CAN bus"
          >
            <Radio size={15} />
            {passthroughBusy
              ? 'Sending...'
              : `BMB Passthrough: ${passthroughEnabled ? 'ON' : 'OFF'}`}
          </button>
          {passthroughStatus && (
            <span className={`hvc-status-pill ${passthroughStatus.type}`}>{passthroughStatus.text}</span>
          )}
          <button
            type="button"
            className="hvc-reset-btn"
            onClick={handleResetHVC}
            disabled={resetBusy}
            title="Send HVC firmware reset frame"
          >
            <RotateCcw size={15} />
            {resetBusy ? 'Sending...' : 'Reset HVC'}
          </button>
          {resetStatus && (
            <span className={`hvc-status-pill ${resetStatus.type}`}>{resetStatus.text}</span>
          )}
        </div>
      </div>

      {!hasAnyFrame && (
        <div className="hvc-empty">
          <AlertTriangle size={28} />
          <div>
            <h3>No HVC frames received yet</h3>
            <p>Connect to CAN with hvc.dbc enabled to populate this dashboard.</p>
          </div>
        </div>
      )}

      <div className="hvc-kpi-grid">
        <div className="hvc-kpi-card">
          <div className="hvc-card-header">
            <Battery size={18} /><span>State of Charge</span>{renderFreshness(frames.soc)}
          </div>
          <div className="hvc-kpi-value">{formatPercent(getSignal(soc, 'HVC_SOC_Percent', 'SOC_Percent'))}</div>
          <div className="hvc-kpi-sub">Capacity: <strong>{formatCapacityAh(getSignal(soc, 'HVC_SOC_Capacity_As', 'SOC_Capacity_As'))}</strong></div>
          <div className="hvc-kpi-sub">Delta: <strong>{formatCapacityAh(getSignal(soc, 'HVC_SOC_Delta_As', 'SOC_Delta_As'))}</strong></div>
        </div>

        <div className="hvc-kpi-card">
          <div className="hvc-card-header">
            <Zap size={18} /><span>Voltage Sense</span>{renderFreshness(frames.ioVSense)}
          </div>
          <div className="hvc-split-grid">
            <div><span>Battery</span><strong>{formatVoltsFromMv(getSignal(ioVSense, 'HVC_Batt_Voltage_mV', 'Batt_Voltage_mV'))}</strong></div>
            <div><span>Inverter</span><strong>{formatVoltsFromMv(getSignal(ioVSense, 'HVC_Inv_Voltage_mV', 'Inv_Voltage_mV'))}</strong></div>
          </div>
        </div>

        <div className="hvc-kpi-card">
          <div className="hvc-card-header">
            <Activity size={18} /><span>Bus Current</span>{renderFreshness(frames.ioCurrent)}
          </div>
          <div className="hvc-split-grid">
            <div><span>Low Channel</span><strong>{formatAmpsFromMa(getSignal(ioCurrent, 'HVC_Current_Low_mA', 'Current_Low_mA'))}</strong></div>
            <div><span>High Channel</span><strong>{formatAmpsFromMa(getSignal(ioCurrent, 'HVC_Current_High_mA', 'Current_High_mA'))}</strong></div>
          </div>
        </div>
      </div>

      <div className="hvc-section-grid">
        <section className="hvc-card">
          <div className="hvc-card-header">
            <Thermometer size={17} /><h3>Pack Extremes</h3>{renderFreshness(frames.accSummary)}
          </div>
          <div className="hvc-metric-grid">
            <div className="hvc-metric"><span>V Min</span><strong>{formatVoltsFromMv(getSignal(acc, 'HVC_Acc_Volt_Min_mV', 'Acc_Volt_Min_mV'))}</strong></div>
            <div className="hvc-metric"><span>V Max</span><strong>{formatVoltsFromMv(getSignal(acc, 'HVC_Acc_Volt_Max_mV', 'Acc_Volt_Max_mV'))}</strong></div>
            <div className="hvc-metric"><span>T Min</span><strong>{formatTempC(getSignal(acc, 'HVC_Acc_Temp_Min_C', 'Acc_Temp_Min_C'))}</strong></div>
            <div className="hvc-metric"><span>T Max</span><strong>{formatTempC(getSignal(acc, 'HVC_Acc_Temp_Max_C', 'Acc_Temp_Max_C'))}</strong></div>
          </div>
        </section>

        <section className="hvc-card">
          <div className="hvc-card-header">
            <Gauge size={17} /><h3>IO Summary</h3>{renderFreshness(frames.ioSummary)}
          </div>
          <div className="hvc-badge-row">
            {renderFaultBadge('SDC', sdcStatus.signal, sdcStatus.name === 'SDC_Closed')}
            {renderFaultBadge('IMD', imdStatus.signal, imdStatus.name === 'IMD_Ok')}
            {renderFaultBadge('BMS', bmsFaultStatus.signal, bmsFaultStatus.name === 'BMS_Fault_Ok')}
          </div>
          <div className="hvc-metric single">
            <span>Reference Temp</span>
            <strong>{formatTempC(getSignal(ioSummary, 'HVC_Ref_Temp_C', 'Ref_Temp_C'))}</strong>
          </div>
        </section>

        <section className="hvc-card">
          <div className="hvc-card-header">
            <AlertTriangle size={17} /><h3>BMS State</h3>{renderFreshness(frames.bmsState)}
          </div>
          <div className={`hvc-state-banner state-${(normalizedState || 'unknown').toLowerCase()}`}>
            {stateText}
          </div>
          <div className="hvc-state-chip-row">
            {HVC_BMS_STATES.map((s) => (
              <span
                key={s}
                className={`hvc-state-chip state-${s.toLowerCase()} ${normalizedState === s ? 'active' : ''}`}
              >
                {s}
              </span>
            ))}
          </div>
          {(() => {
            const bmbFaultModule = getSignal(bmsState, 'HVC_BMB_Fault_Module', 'BMB_Fault_Module');
            const bmbFaultState = getSignal(bmsState, 'HVC_BMB_Fault_State', 'BMB_Fault_State');
            const bmbModNum = getNumeric(bmbFaultModule);
            const bmbStateText = getDisplay(bmbFaultState, null);
            const bmbStateNum = getNumeric(bmbFaultState);
            if (bmbModNum === null && bmbStateNum === null) return null;
            // Only FAULT (5) is red; INIT (0) is blue; BALANCING (4) is purple; all others green.
            const stateKey = bmbStateNum != null ? HVC_BMB_FAULT_STATES[bmbStateNum] : null;
            const colorClass = stateKey === 'FAULT' ? 'faulted'
              : stateKey === 'INIT' ? 'init'
              : stateKey === 'BALANCING' ? 'balancing'
              : 'ok';
            return (
              <div className={`hvc-bmb-fault ${colorClass}`}>
                <div className="hvc-bmb-fault-header">
                  <span className="hvc-bmb-fault-title">BMB Fault</span>
                  {colorClass === 'faulted' ? (
                    <span className="hvc-badge bad">FAULTED</span>
                  ) : colorClass === 'init' ? (
                    <span className="hvc-badge" style={{ background: 'rgba(59,130,246,0.2)', color: '#93c5fd', borderColor: 'rgba(59,130,246,0.5)' }}>INIT</span>
                  ) : colorClass === 'balancing' ? (
                    <span className="hvc-badge" style={{ background: 'rgba(139,92,246,0.2)', color: '#c4b5fd', borderColor: 'rgba(139,92,246,0.5)' }}>BALANCING</span>
                  ) : (
                    <span className="hvc-badge good">OK</span>
                  )}
                </div>
                <div className="hvc-bmb-fault-details">
                  <div className="hvc-metric">
                    <span>Fault Module</span>
                    <strong>{bmbModNum === 255 ? 'None' : (bmbModNum != null ? `Module ${bmbModNum}` : '--')}</strong>
                  </div>
                  <div className="hvc-metric">
                    <span>Fault State</span>
                    <strong>{bmbStateText != null ? bmbStateText : '--'}</strong>
                  </div>
                </div>
                {bmbStateNum != null && (
                  <div className="hvc-state-chip-row" style={{ marginTop: 6 }}>
                    {HVC_BMB_FAULT_STATES.map((s) => (
                      <span
                        key={s}
                        className={`hvc-state-chip state-${s.toLowerCase()} ${HVC_BMB_FAULT_STATES[bmbStateNum] === s ? 'active' : ''}`}
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}
          {stateFlags.length > 0 ? (
            <div className="hvc-flag-grid">
              {stateFlags.map(([name, value]) => {
                const num = getNumeric(value);
                const cls = num === null ? 'unknown' : num !== 0 ? 'active' : 'clear';
                return (
                  <div key={name} className={`hvc-flag ${cls}`}>
                    <span className="hvc-flag-label">{formatFlagLabel(name)}</span>
                    <span className="hvc-flag-value">{getDisplay(value)}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="hvc-flag-empty">No BMS state flags decoded yet.</div>
          )}
        </section>

        <section className="hvc-card">
          <div className="hvc-card-header">
            <Activity size={17} /><h3>Current Limits</h3>{renderFreshness(frames.currentLimit)}
          </div>
          <div className="hvc-metric-grid">
            <div className="hvc-metric"><span>Charge Limit</span><strong>{formatAmpsFromMa(getSignal(currentLimit, 'HVC_Positive_Current_Limit_mA', 'Positive_Current_Limit_mA'))}</strong></div>
            <div className="hvc-metric"><span>Discharge Limit</span><strong>{formatAmpsFromMa(getSignal(currentLimit, 'HVC_Negative_Current_Limit_mA', 'Negative_Current_Limit_mA'))}</strong></div>
          </div>
        </section>

        <section className="hvc-card">
          <div className="hvc-card-header">
            <AlertTriangle size={17} /><h3>Precharge / PL Signal</h3>{renderFreshness(frames.plSignal)}
          </div>
          <div className="hvc-metric single">
            <span>Reason</span>
            <strong>{getDisplay(getSignal(plSignal, 'HVC_PL_Signal_Reason', 'PL_Signal_Reason'))}</strong>
          </div>
        </section>

        <section className="hvc-card hvc-emeter-card">
          <div className="hvc-card-header">
            <Thermometer size={17} /><h3>E-Meter Thermistors</h3>{renderFreshness(frames.emeterTherms)}
          </div>
          <div className="hvc-emeter-grid">
            {EMETER_THERM_SIGNALS.map((names, idx) => {
              const raw = getNumeric(getSignal(emeterTherms, ...names));
              const invalid = raw === null || raw === 0;
              return (
                <div key={names[0]} className={`hvc-emeter-cell ${invalid ? 'invalid' : ''}`}>
                  <span className="hvc-emeter-label">T{idx}</span>
                  <span className="hvc-emeter-value">
                    {invalid ? '--' : `${raw} °C`}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}

export default HVCDashboard;
