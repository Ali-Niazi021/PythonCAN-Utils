import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, Gauge, Settings, SlidersHorizontal, Zap,
} from 'lucide-react';
import {
  useNowTick, isTimestampStale, messageFreshnessTimestamp,
} from '../hooks/useStaleness';
import {
  LAUNCH_CURVE_POINT_INDICES,
  SET_VCU_CONFIG_ID,
  buildVcuConfigFrame,
  createDefaultVcuConfig,
  getVcuConfigFromSignals,
} from './vcuConfig';
import './VCUDashboard.css';
import './VCULaunchControlDashboard.css';

const LAUNCH_FRAME_SIGNALS = {
  VCU_TRC_State: [
    'VCU_TRC_State_Machine',
    'VCU_TRC_Current_Run',
    'VCU_TRC_Selected_Curve',
    'VCU_TRC_Learning_Active',
    'VCU_TRC_Launch_Mode_Active',
    'VCU_TRC_Best_Curve',
    'VCU_TRC_Grip_Score_A',
    'VCU_TRC_Grip_Score_B',
    'VCU_TRC_Recommended_Slip',
  ],
  VCU_TRC_Run_Data: [
    'VCU_TRC_Run_Index',
    'VCU_TRC_Run_Valid',
    'VCU_TRC_Run_Avg_Slip',
    'VCU_TRC_Run_Peak_Slip',
    'VCU_TRC_Run_Grip_Score',
  ],
  VCU_Config: [
    'VCU_Launch_Enabled',
    'VCU_Launch_End_RPM',
    'VCU_Launch_Timeout_ms',
    'VCU_Launch_Max_Slip',
    'VCU_Launch_Best_Curve',
    'VCU_Launch_Active_Curve',
    'VCU_Launch_Recommended_Slip',
    'VCU_Launch_Actual_RPM_0',
    'VCU_Launch_Actual_RPM_1',
    'VCU_Launch_Actual_RPM_2',
    'VCU_Launch_Actual_RPM_3',
    'VCU_Launch_Actual_RPM_4',
    'VCU_Launch_Actual_Torque_0',
    'VCU_Launch_Actual_Torque_1',
    'VCU_Launch_Actual_Torque_2',
    'VCU_Launch_Actual_Torque_3',
    'VCU_Launch_Actual_Torque_4',
  ],
};

const LAUNCH_SIGNAL_NAMES = new Set(Object.values(LAUNCH_FRAME_SIGNALS).flat());
const RUN_INDICES = [1, 2, 3];

const TRC_STATE_LABELS = {
  0: 'OFF',
  1: 'ACTIVE',
  2: 'LAUNCH_IDLE',
  3: 'LAUNCH',
  4: 'LEARNING_IDLE',
  5: 'LEARNING_READY_RUN1',
  6: 'LEARNING_RUNNING_RUN1',
  7: 'LEARNING_COMPLETE_RUN1',
  8: 'LEARNING_READY_RUN2',
  9: 'LEARNING_RUNNING_RUN2',
  10: 'LEARNING_COMPLETE_RUN2',
  11: 'LEARNING_READY_RUN3',
  12: 'LEARNING_RUNNING_RUN3',
  13: 'LEARNING_PROCESSING',
  14: 'LEARNING_RESULTS_READY',
  15: 'LEARNING_ABORTED',
  16: 'FAULT',
};

const CURVE_LABELS = {
  0: 'CURVE_A',
  1: 'CURVE_B',
  2: 'CURVE_C',
  3: 'UPLOADED',
};

const BOOLEAN_LABELS = { 0: 'FALSE', 1: 'TRUE' };

const TRC_COMMANDS = {
  ENTER_LEARNING: 3,
  ARM: 4,
  ABORT: 5,
  EXIT_LEARNING: 6,
  ENTER_LAUNCH: 7,
  ARM_LAUNCH: 8,
  EXIT_LAUNCH: 9,
};

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
      const precision = decimals !== null ? decimals : (Number.isInteger(value) ? 0 : 3);
      return `${value.toFixed(precision)}${unit ? ` ${unit}` : ''}`;
    }
    if (typeof raw === 'number') return String(raw);
    return fallback;
  }
  if (typeof signal === 'number') {
    const precision = decimals !== null ? decimals : (Number.isInteger(signal) ? 0 : 3);
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

const getCanonicalFrameName = (decoded) => {
  const messageName = decoded?.message_name;
  if (messageName && LAUNCH_FRAME_SIGNALS[messageName]) return messageName;
  if (!decoded?.signals) return null;

  const signalNames = Object.keys(decoded.signals);
  let bestFrameName = null;
  let bestOverlap = 0;

  Object.entries(LAUNCH_FRAME_SIGNALS).forEach(([frameName, expectedSignals]) => {
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

const createLaunchDraft = (config) => ({
  launchEnabled: config.launchEnabled,
  launchEndRpm: config.launchEndRpm,
  launchTimeoutMs: config.launchTimeoutMs,
  launchMaxSlip: config.launchMaxSlip,
  launchActiveCurve: config.launchActiveCurve,
  launchActualRpm0: config.launchActualRpm0,
  launchActualRpm1: config.launchActualRpm1,
  launchActualRpm2: config.launchActualRpm2,
  launchActualRpm3: config.launchActualRpm3,
  launchActualRpm4: config.launchActualRpm4,
  launchActualTorque0: config.launchActualTorque0,
  launchActualTorque1: config.launchActualTorque1,
  launchActualTorque2: config.launchActualTorque2,
  launchActualTorque3: config.launchActualTorque3,
  launchActualTorque4: config.launchActualTorque4,
});

const formatRatio = (signalOrNumber) => {
  const numeric = getNumeric(signalOrNumber);
  return numeric === null ? '--' : numeric.toFixed(3);
};

const roundedInt = (value) => Math.round(Number(value) || 0);

function Freshness({ timestamp, nowMs, staleTimeoutMs }) {
  return (
    <span className={`freshness ${freshnessClass(timestamp, nowMs, staleTimeoutMs)}`}>
      {freshnessLabel(timestamp, nowMs)}
    </span>
  );
}

function VCULaunchControlDashboard({
  messages,
  dbcFiles = [],
  onSendMessage,
  onRegisterRawCallback,
  staleTimeoutMs = 30000,
}) {
  const nowMs = useNowTick(1000);
  const [commandStatus, setCommandStatus] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);
  const [busyAction, setBusyAction] = useState(null);
  const [launchDraft, setLaunchDraft] = useState(() => createLaunchDraft(createDefaultVcuConfig()));
  const [draftDirty, setDraftDirty] = useState(false);
  const [runData, setRunData] = useState({ 1: null, 2: null, 3: null });

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
      const signalEntries = Object.entries(decoded.signals).filter(([signalName]) => LAUNCH_SIGNAL_NAMES.has(signalName));
      if (!frameName && signalEntries.length === 0) return;

      const timestamp = messageFreshnessTimestamp(msg)
        ?? (typeof msg.timestamp === 'number' ? msg.timestamp : 0);

      if (frameName && (!frameMap[frameName] || timestamp >= frameMap[frameName].timestamp)) {
        frameMap[frameName] = { signals: decoded.signals, timestamp };
      }

      signalEntries.forEach(([signalName, signal]) => {
        const previous = signalMap.get(signalName);
        if (!previous || timestamp >= previous.timestamp) {
          signalMap.set(signalName, { signal, timestamp });
        }
      });

      if (decoded.source_dbc && timestamp >= latestMatchedTimestamp) {
        latestMatchedTimestamp = timestamp;
        latestMatchedSourceDbc = decoded.source_dbc;
      }
    });

    return { frames: frameMap, latestSignals: signalMap, matchedSourceDbc: latestMatchedSourceDbc };
  }, [messages]);

  const getSignal = useCallback((name) => latestSignals.get(name)?.signal, [latestSignals]);

  const launchReadback = useMemo(() => getVcuConfigFromSignals(getSignal), [getSignal]);
  const draftSourceKey = useMemo(() => JSON.stringify(createLaunchDraft(launchReadback)), [launchReadback]);

  useEffect(() => {
    if (!draftDirty) {
      setLaunchDraft(createLaunchDraft(launchReadback));
    }
  }, [draftDirty, draftSourceKey, launchReadback]);

  const processRawMessage = useCallback((message) => {
    const decoded = message?.decoded;
    if (!decoded?.signals) return;
    if (decoded.message_name !== 'VCU_TRC_Run_Data' && decoded.signals.VCU_TRC_Run_Index === undefined) return;

    const runIndex = getNumeric(decoded.signals.VCU_TRC_Run_Index);
    if (!RUN_INDICES.includes(runIndex)) return;

    const timestamp = messageFreshnessTimestamp(message)
      ?? (typeof message.timestamp === 'number' ? message.timestamp : 0);

    setRunData((previous) => ({
      ...previous,
      [runIndex]: {
        signals: decoded.signals,
        timestamp,
      },
    }));
  }, []);

  useEffect(() => {
    if (!onRegisterRawCallback) return undefined;
    return onRegisterRawCallback(processRawMessage);
  }, [onRegisterRawCallback, processRawMessage]);

  const trcState = getNumeric(getSignal('VCU_TRC_State_Machine'));
  const currentRun = getNumeric(getSignal('VCU_TRC_Current_Run'));
  const selectedCurve = getSignal('VCU_TRC_Selected_Curve');
  const bestCurve = getSignal('VCU_TRC_Best_Curve') || getSignal('VCU_Launch_Best_Curve');
  const recommendedSlip = getSignal('VCU_TRC_Recommended_Slip') || getSignal('VCU_Launch_Recommended_Slip');
  const learningActive = bitValue(getSignal('VCU_TRC_Learning_Active')) ?? false;
  const launchModeActive = bitValue(getSignal('VCU_TRC_Launch_Mode_Active')) ?? false;
  const usingUploadedCurve = Number(launchDraft.launchActiveCurve) === 3;
  const hasAnyData = latestSignals.size > 0;

  const rpmValues = LAUNCH_CURVE_POINT_INDICES.map((index) => Number(launchDraft[`launchActualRpm${index}`]));
  const rpmMonotonic = rpmValues.every((value, index) => index === 0 || value >= rpmValues[index - 1]);

  const uploadedCurveReadbackReady = LAUNCH_CURVE_POINT_INDICES.every((index) => (
    getSignal(`VCU_Launch_Actual_RPM_${index}`) !== undefined
    && getSignal(`VCU_Launch_Actual_Torque_${index}`) !== undefined
  ));

  const uploadedCurveMatches = uploadedCurveReadbackReady && LAUNCH_CURVE_POINT_INDICES.every((index) => (
    roundedInt(getNumeric(getSignal(`VCU_Launch_Actual_RPM_${index}`))) === roundedInt(launchDraft[`launchActualRpm${index}`])
    && roundedInt(getNumeric(getSignal(`VCU_Launch_Actual_Torque_${index}`))) === roundedInt(launchDraft[`launchActualTorque${index}`])
  ));

  const canEnterLearning = (trcState === 0 || trcState === 1 || trcState === null) && !learningActive && !launchModeActive;
  const canArmLearning = [4, 7, 10].includes(trcState);
  const canEnterLaunch = (trcState === 0 || trcState === 1 || trcState === null) && !learningActive && !launchModeActive && launchReadback.launchEnabled;
  const canArmLaunch = trcState === 2 && (!usingUploadedCurve || uploadedCurveMatches);
  const canAbort = launchModeActive || learningActive || [3, 6, 9, 12].includes(trcState);
  const canExitLearning = learningActive || (trcState !== null && trcState >= 4 && trcState <= 15);
  const canExitLaunch = launchModeActive || trcState === 2 || trcState === 3;

  const dbcStatusText = matchedSourceDbc
    ? `Matched ${matchedSourceDbc}`
    : enabledDbcCount > 0
      ? 'Waiting for launch-control signals'
      : 'No DBC enabled';

  const patchLaunchDraft = (patch) => {
    setDraftDirty(true);
    setLaunchDraft((previous) => ({ ...previous, ...patch }));
  };

  const sendCommand = async (commandValue, label) => {
    if (typeof onSendMessage !== 'function') {
      setCommandStatus({ type: 'error', text: 'Send unavailable' });
      return;
    }

    setBusyAction(label);
    setCommandStatus({ type: 'pending', text: `${label}...` });

    try {
      const ok = await onSendMessage(
        SET_VCU_CONFIG_ID,
        buildVcuConfigFrame(240, { trcCommand: commandValue }),
        true,
        false,
      );
      setCommandStatus(ok
        ? { type: 'success', text: `${label} sent` }
        : { type: 'error', text: `${label} rejected` });
    } catch (error) {
      setCommandStatus({ type: 'error', text: `Send failed: ${error?.message || error}` });
    } finally {
      setBusyAction(null);
    }
  };

  const saveLaunchConfig = async () => {
    if (typeof onSendMessage !== 'function') {
      setSaveStatus({ type: 'error', text: 'Send unavailable' });
      return;
    }
    if (!rpmMonotonic) {
      setSaveStatus({ type: 'error', text: 'RPM breakpoints must be monotonic.' });
      return;
    }

    const muxes = [22, 23, 24, 25, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38];
    setBusyAction('save-launch-config');
    setSaveStatus({ type: 'pending', text: 'Saving launch config...' });

    try {
      for (const mux of muxes) {
        const ok = await onSendMessage(SET_VCU_CONFIG_ID, buildVcuConfigFrame(mux, launchDraft), true, false);
        if (!ok) {
          throw new Error(`VCU rejected mux ${mux}`);
        }
      }
      setDraftDirty(false);
      setSaveStatus({ type: 'success', text: 'Launch config sent. Verify readback below.' });
    } catch (error) {
      setSaveStatus({ type: 'error', text: `Save failed: ${error?.message || error}` });
    } finally {
      setBusyAction(null);
    }
  };

  const resetDraftToReadback = () => {
    setLaunchDraft(createLaunchDraft(launchReadback));
    setDraftDirty(false);
  };

  return (
    <div className="vcu-dashboard vcu-launch-dashboard">
      <div className="vcu-header">
        <div>
          <h2><Gauge size={22} /> Launch Control</h2>
          <p>Learning mode, actual launch control, and uploaded launch-curve management for VCU TRC.</p>
        </div>
        <div className="vcu-header-actions">
          <span className={`vcu-dbc-pill ${matchedSourceDbc ? 'enabled' : 'disabled'}`}>
            {dbcStatusText}
          </span>
          {commandStatus && <span className={`vcu-status-pill ${commandStatus.type}`}>{commandStatus.text}</span>}
          {saveStatus && <span className={`vcu-status-pill ${saveStatus.type}`}>{saveStatus.text}</span>}
        </div>
      </div>

      <div className="vcu-notice">
        Launch control is independent from standard traction control enable. Use VCU TRC state and VCU Config readback as the source of truth.
      </div>

      {!matchedSourceDbc && (
        <div className="vcu-notice">
          {enabledDbcCount > 0
            ? 'Waiting for decoded VCU launch-control signals from an enabled DBC.'
            : 'Enable a DBC that exposes VCU launch-control signals to populate this page.'}
        </div>
      )}

      {!hasAnyData && (
        <div className="vcu-empty">
          <AlertTriangle size={28} />
          <div>
            <h3>No launch-control frames received yet</h3>
            <p>Connect to CAN and enable a DBC that contains the VCU launch-control messages.</p>
          </div>
        </div>
      )}

      <div className="vcu-kpi-grid">
        <section className="vcu-card">
          <div className="vcu-card-header"><Activity size={18} /><h3>TRC State</h3><Freshness timestamp={frames.VCU_TRC_State?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} /></div>
          <div className={`vcu-state state-${trcState ?? 'unknown'}`}>{trcState !== null ? TRC_STATE_LABELS[trcState] || trcState : '--'}</div>
          <div className="vcu-inline-values">
            <span>Current run <strong>{currentRun || '--'}</strong></span>
            <span>Selected curve <strong>{enumLabel(selectedCurve, CURVE_LABELS)}</strong></span>
            <span>Best curve <strong>{enumLabel(bestCurve, CURVE_LABELS)}</strong></span>
            <span>Recommended slip <strong>{formatRatio(recommendedSlip)}</strong></span>
          </div>
          <div className="vcu-pill-row">
            <span className={`vcu-pill ${learningActive ? 'good' : 'unknown'}`}>Learning: {learningActive ? 'ACTIVE' : 'INACTIVE'}</span>
            <span className={`vcu-pill ${launchModeActive ? 'good' : 'unknown'}`}>Launch mode: {launchModeActive ? 'ACTIVE' : 'INACTIVE'}</span>
            <span className={`vcu-pill ${trcState === 3 ? 'good' : 'unknown'}`}>Launch armed/live: {trcState === 3 ? 'YES' : 'NO'}</span>
          </div>
        </section>

        <section className="vcu-card">
          <div className="vcu-card-header"><Zap size={18} /><h3>Learning Summary</h3></div>
          <div className="vcu-launch-summary-grid">
            <span>Grip score A <strong>{formatRatio(getSignal('VCU_TRC_Grip_Score_A'))}</strong></span>
            <span>Grip score B <strong>{formatRatio(getSignal('VCU_TRC_Grip_Score_B'))}</strong></span>
            <span>Launch enabled <strong>{enumLabel(getSignal('VCU_Launch_Enabled'), BOOLEAN_LABELS)}</strong></span>
            <span>Active curve source <strong>{enumLabel(getSignal('VCU_Launch_Active_Curve'), CURVE_LABELS)}</strong></span>
          </div>
        </section>
      </div>

      <div className="vcu-section-grid vcu-launch-sections">
        <section className="vcu-card">
          <div className="vcu-card-header"><SlidersHorizontal size={18} /><h3>Learning Control</h3></div>
          <p className="vcu-launch-copy">Use `ENTER_LEARNING`, then arm each run after the VCU returns to the next compatible learning state.</p>
          <div className="vcu-launch-action-grid">
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.ENTER_LEARNING, 'Enter Learning')} disabled={busyAction !== null || !canEnterLearning}>Enter Learning</button>
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.ARM, 'Arm Next Learning Run')} disabled={busyAction !== null || !canArmLearning}>Arm Next Learning Run</button>
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.ABORT, 'Abort')} disabled={busyAction !== null || !canAbort}>Abort</button>
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.EXIT_LEARNING, 'Exit Learning')} disabled={busyAction !== null || !canExitLearning}>Exit Learning</button>
          </div>
          <div className="vcu-launch-guardrails">
            <span>Learning can be armed from `LEARNING_IDLE`, `LEARNING_COMPLETE_RUN1`, or `LEARNING_COMPLETE_RUN2`.</span>
            <span>The run starts only after throttle crosses the VCU start threshold.</span>
          </div>
        </section>

        <section className="vcu-card">
          <div className="vcu-card-header"><Gauge size={18} /><h3>Actual Launch Control</h3></div>
          <p className="vcu-launch-copy">Use `ENTER_LAUNCH`, verify the selected curve source and uploaded readback, then arm launch.</p>
          <div className="vcu-launch-action-grid">
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.ENTER_LAUNCH, 'Enter Launch')} disabled={busyAction !== null || !canEnterLaunch}>Enter Launch</button>
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.ARM_LAUNCH, 'Arm Launch')} disabled={busyAction !== null || !canArmLaunch}>Arm Launch</button>
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.ABORT, 'Abort')} disabled={busyAction !== null || !canAbort}>Abort</button>
            <button type="button" onClick={() => sendCommand(TRC_COMMANDS.EXIT_LAUNCH, 'Exit Launch')} disabled={busyAction !== null || !canExitLaunch}>Exit Launch</button>
          </div>
          <div className="vcu-launch-guardrails">
            <span>Launch arming requires `LAUNCH_IDLE`.</span>
            {usingUploadedCurve && (
              <span className={uploadedCurveMatches ? 'vcu-launch-ok' : 'vcu-launch-warning'}>
                Uploaded curve verification: {uploadedCurveMatches ? 'readback matches editor' : 'save and verify all 10 uploaded points before arming'}.
              </span>
            )}
          </div>
        </section>
      </div>

      <section className="vcu-card">
        <div className="vcu-card-header"><Activity size={18} /><h3>Learning Results</h3><Freshness timestamp={frames.VCU_TRC_State?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} /></div>
        <div className="vcu-launch-results-grid">
          {RUN_INDICES.map((runIndex) => {
            const run = runData[runIndex];
            const signals = run?.signals || {};
            return (
              <div key={runIndex} className="vcu-launch-result-card">
                <div className="vcu-launch-result-header">
                  <strong>Run {runIndex}</strong>
                  <Freshness timestamp={run?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />
                </div>
                <div className="vcu-launch-summary-grid">
                  <span>Valid <strong>{enumLabel(signals.VCU_TRC_Run_Valid, BOOLEAN_LABELS)}</strong></span>
                  <span>Avg slip <strong>{formatRatio(signals.VCU_TRC_Run_Avg_Slip)}</strong></span>
                  <span>Peak slip <strong>{formatRatio(signals.VCU_TRC_Run_Peak_Slip)}</strong></span>
                  <span>Grip score <strong>{formatRatio(signals.VCU_TRC_Run_Grip_Score)}</strong></span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="vcu-card">
        <div className="vcu-card-header"><Settings size={18} /><h3>Actual Launch Curve Editor</h3><Freshness timestamp={frames.VCU_Config?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} /></div>
        <div className="vcu-launch-editor-grid">
          <div className="vcu-sender vcu-launch-editor-form">
            <div className="vcu-sender-header">
              <span>Launch Config</span>
              <strong>Readback is authoritative</strong>
            </div>

            <label className="vcu-checkbox">
              <input type="checkbox" checked={Boolean(launchDraft.launchEnabled)} onChange={(event) => patchLaunchDraft({ launchEnabled: event.target.checked })} />
              Launch enabled
            </label>

            <label>
              Active curve source
              <select value={launchDraft.launchActiveCurve} onChange={(event) => patchLaunchDraft({ launchActiveCurve: Number(event.target.value) })}>
                <option value={0}>CURVE_A</option>
                <option value={1}>CURVE_B</option>
                <option value={2}>CURVE_C</option>
                <option value={3}>UPLOADED</option>
              </select>
            </label>

            <div className="vcu-launch-editor-meta">
              <label>
                End RPM
                <input type="number" min="0" max="32767" step="1" value={launchDraft.launchEndRpm} onChange={(event) => patchLaunchDraft({ launchEndRpm: event.target.value })} />
              </label>
              <label>
                Timeout (ms)
                <input type="number" min="0" max="60000" step="1" value={launchDraft.launchTimeoutMs} onChange={(event) => patchLaunchDraft({ launchTimeoutMs: event.target.value })} />
              </label>
              <label>
                Max slip
                <input type="number" min="1" max="5" step="0.001" value={launchDraft.launchMaxSlip} onChange={(event) => patchLaunchDraft({ launchMaxSlip: event.target.value })} />
              </label>
            </div>

            <div className="vcu-launch-curve-table">
              <div className="vcu-launch-curve-head">
                <span>Point</span>
                <span>RPM</span>
                <span>Torque (Nm)</span>
              </div>
              {LAUNCH_CURVE_POINT_INDICES.map((index) => (
                <div key={index} className="vcu-launch-curve-row">
                  <strong>{index}</strong>
                  <input type="number" min="0" max="32767" step="1" value={launchDraft[`launchActualRpm${index}`]} onChange={(event) => patchLaunchDraft({ [`launchActualRpm${index}`]: event.target.value })} />
                  <input type="number" min="0" max="230" step="1" value={launchDraft[`launchActualTorque${index}`]} onChange={(event) => patchLaunchDraft({ [`launchActualTorque${index}`]: event.target.value })} />
                </div>
              ))}
            </div>

            {!rpmMonotonic && (
              <div className="vcu-notice">RPM breakpoints must be monotonic non-decreasing before the curve can be written.</div>
            )}

            <div className="vcu-launch-button-row">
              <button type="button" onClick={saveLaunchConfig} disabled={busyAction !== null || !rpmMonotonic}>Save Launch Settings</button>
              <button type="button" className="vcu-launch-secondary" onClick={resetDraftToReadback} disabled={busyAction !== null || !draftDirty}>Load Readback</button>
            </div>
          </div>

          <div className="vcu-config-sections">
            <section className="vcu-config-group">
              <div className="vcu-config-group-header">Launch Readback</div>
              <div className="vcu-readback-grid">
                <span className="vcu-config-item">Launch enabled <strong>{enumLabel(getSignal('VCU_Launch_Enabled'), BOOLEAN_LABELS)}</strong></span>
                <span className="vcu-config-item">Active curve <strong>{enumLabel(getSignal('VCU_Launch_Active_Curve'), CURVE_LABELS)}</strong></span>
                <span className="vcu-config-item">Best curve <strong>{enumLabel(bestCurve, CURVE_LABELS)}</strong></span>
                <span className="vcu-config-item">Recommended slip <strong>{formatRatio(recommendedSlip)}</strong></span>
                <span className="vcu-config-item">End RPM <strong>{getDisplay(getSignal('VCU_Launch_End_RPM'))}</strong></span>
                <span className="vcu-config-item">Timeout <strong>{getDisplay(getSignal('VCU_Launch_Timeout_ms'))}</strong></span>
                <span className="vcu-config-item">Max slip <strong>{formatRatio(getSignal('VCU_Launch_Max_Slip'))}</strong></span>
              </div>
            </section>

            <section className="vcu-config-group">
              <div className="vcu-config-group-header">Uploaded Curve Readback</div>
              <div className="vcu-launch-readback-table">
                <div className="vcu-launch-curve-head">
                  <span>Point</span>
                  <span>RPM</span>
                  <span>Torque (Nm)</span>
                </div>
                {LAUNCH_CURVE_POINT_INDICES.map((index) => (
                  <div key={index} className="vcu-launch-curve-row readback">
                    <strong>{index}</strong>
                    <span>{getDisplay(getSignal(`VCU_Launch_Actual_RPM_${index}`))}</span>
                    <span>{getDisplay(getSignal(`VCU_Launch_Actual_Torque_${index}`))}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      </section>
    </div>
  );
}

export default VCULaunchControlDashboard;