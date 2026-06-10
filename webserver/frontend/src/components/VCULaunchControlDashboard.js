import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, Gauge, SlidersHorizontal, Zap,
} from 'lucide-react';
import {
  useNowTick, isTimestampStale, messageFreshnessTimestamp,
} from '../hooks/useStaleness';
import {
  SET_VCU_CONFIG_ID,
  buildVcuConfigFrame,
  clampNumber,
  createDefaultVcuConfig,
  getVcuConfigFromSignals,
} from './vcuConfig';
import './VCUDashboard.css';
import './VCULaunchControlDashboard.css';

const LAUNCH_FRAME_SIGNALS = {
  VCU_Launch_State: [
    'VCU_Launch_State_Machine',
    'VCU_Launch_Armed',
    'VCU_Launch_Active',
    'VCU_Launch_Elapsed_ms',
    'VCU_Launch_Curve_Torque',
  ],
  VCU_Config: [
    'VCU_Launch_Torque_Offtheline',
    'VCU_Launch_Torque_Init',
    'VCU_Launch_Torque_Final',
  ],
  VCU_APPS_Values: [
    'VCU_APPS_Value',
    'VCU_APPS_Valid',
    'VCU_APPS_Implausible',
  ],
  VCU_BSE: [
    'VCU_BSE_PSI',
    'VCU_BSE_Valid',
  ],
  VCU_Summary: [
    'VCU_State',
  ],
};

const LAUNCH_SIGNAL_NAMES = new Set(Object.values(LAUNCH_FRAME_SIGNALS).flat());
const LAUNCH_STATE_LABELS = {
  0: 'DISARMED',
  1: 'ARMED',
  2: 'LAUNCHING',
};
const VCU_STATE_LABELS = {
  0: 'LOADING',
  1: 'NOT READY',
  2: 'PLAYING RTD SOUND',
  3: 'DRIVING',
  4: 'BAP FAULT',
  5: 'HARD FAULT',
};
const BOOLEAN_LABELS = { 0: 'FALSE', 1: 'TRUE' };
const LAUNCH_COMMANDS = {
  ARM: 1,
  DISARM: 2,
};
const BRAKE_RELEASED_THRESHOLD_PSI = 1;

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
  launchTorqueOfftheline: config.launchTorqueOfftheline,
  launchTorqueInit: config.launchTorqueInit,
  launchTorqueFinal: config.launchTorqueFinal,
});

const buildLaunchCurveSamples = (draft) => {
  const offtheline = clampNumber(draft.launchTorqueOfftheline, 0, 230, 100);
  const init = clampNumber(draft.launchTorqueInit, 0, 230, 150);
  const final = clampNumber(draft.launchTorqueFinal, 0, 230, 183);
  const samples = [];

  for (let step = 0; step <= 30; step += 1) {
    const time = step / 10;
    let torque = final;

    if (time < 0.2) {
      torque = offtheline;
    } else if (time <= 3) {
      torque = init + ((time * time) * (final - init)) / 9;
    }

    samples.push({ time, torque });
  }

  return { offtheline, init, final, samples };
};

const buildCurvePreview = (draft) => {
  const width = 360;
  const height = 170;
  const padding = { top: 16, right: 18, bottom: 28, left: 28 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const { offtheline, init, final, samples } = buildLaunchCurveSamples(draft);
  const maxTorque = Math.max(120, offtheline, init, final);

  const polyline = samples.map(({ time, torque }) => {
    const x = padding.left + (time / 3) * plotWidth;
    const y = padding.top + plotHeight - (torque / maxTorque) * plotHeight;
    return `${x},${y}`;
  }).join(' ');

  const guideValues = Array.from(new Set([offtheline, init, final]))
    .sort((left, right) => right - left);

  return {
    width,
    height,
    padding,
    plotWidth,
    plotHeight,
    maxTorque,
    polyline,
    guideValues,
  };
};

const formatElapsed = (elapsedMs) => {
  if (elapsedMs === null) return '--';
  return `${(elapsedMs / 1000).toFixed(2)} s`;
};

const readinessClass = (value) => {
  if (value === null) return 'unknown';
  return value ? 'good' : 'bad';
};

const readinessText = (value, readyLabel, waitingLabel) => {
  if (value === null) return '--';
  return value ? readyLabel : waitingLabel;
};

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
  staleTimeoutMs = 30000,
}) {
  const nowMs = useNowTick(1000);
  const [commandStatus, setCommandStatus] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);
  const [busyAction, setBusyAction] = useState(null);
  const [launchDraft, setLaunchDraft] = useState(() => createLaunchDraft(createDefaultVcuConfig()));
  const [draftDirty, setDraftDirty] = useState(false);

  const enabledDbcCount = dbcFiles.filter((file) => file.enabled).length;

  const { frames, latestSignals, matchedSourceDbc } = useMemo(() => {
    const frameMap = {};
    const signalMap = new Map();
    let latestMatchedSourceDbc = null;
    let latestMatchedTimestamp = -1;

    messages.forEach((message) => {
      const decoded = message?.decoded;
      if (!decoded?.signals) return;

      const frameName = getCanonicalFrameName(decoded);
      const signalEntries = Object.entries(decoded.signals).filter(([signalName]) => LAUNCH_SIGNAL_NAMES.has(signalName));
      if (!frameName && signalEntries.length === 0) return;

      const timestamp = messageFreshnessTimestamp(message)
        ?? (typeof message.timestamp === 'number' ? message.timestamp : 0);

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

  const launchReadback = useMemo(
    () => getVcuConfigFromSignals((name) => latestSignals.get(name)?.signal),
    [latestSignals],
  );
  const draftSourceKey = useMemo(
    () => JSON.stringify(createLaunchDraft(launchReadback)),
    [launchReadback],
  );

  useEffect(() => {
    if (!draftDirty) {
      setLaunchDraft(createLaunchDraft(launchReadback));
    }
  }, [draftDirty, draftSourceKey, launchReadback]);

  const getSignal = (name) => latestSignals.get(name)?.signal;
  const stateMachine = getNumeric(getSignal('VCU_Launch_State_Machine'));
  const launchArmed = bitValue(getSignal('VCU_Launch_Armed'));
  const launchActive = bitValue(getSignal('VCU_Launch_Active'));
  const elapsedMs = getNumeric(getSignal('VCU_Launch_Elapsed_ms'));
  const curveTorque = getNumeric(getSignal('VCU_Launch_Curve_Torque'));
  const appsPct = getNumeric(getSignal('VCU_APPS_Value'));
  const appsValid = bitValue(getSignal('VCU_APPS_Valid'));
  const appsImplausible = bitValue(getSignal('VCU_APPS_Implausible'));
  const bsePsi = getNumeric(getSignal('VCU_BSE_PSI'));
  const bseValid = bitValue(getSignal('VCU_BSE_Valid'));
  const vcuState = getNumeric(getSignal('VCU_State'));
  const hasAnyData = latestSignals.size > 0;
  const launchStateTimestamp = frames.VCU_Launch_State?.timestamp;
  const launchTelemetryFresh = Boolean(launchStateTimestamp)
    && !isTimestampStale(launchStateTimestamp, nowMs, staleTimeoutMs);
  const brakesReleased = bsePsi === null ? null : bsePsi <= BRAKE_RELEASED_THRESHOLD_PSI;
  const throttleReady = appsPct === null ? null : appsPct >= 25;
  const drivingReady = vcuState === null ? null : vcuState === 3;
  const canArm = typeof onSendMessage === 'function'
    && busyAction === null
    && launchTelemetryFresh
    && stateMachine === 0;
  const canDisarm = typeof onSendMessage === 'function' && busyAction === null;

  const dbcStatusText = matchedSourceDbc
    ? `Matched ${matchedSourceDbc}`
    : enabledDbcCount > 0
      ? 'Waiting for launch-control signals'
      : 'No DBC enabled';

  const curvePreview = useMemo(() => buildCurvePreview(launchDraft), [launchDraft]);

  const patchDraft = (field, value) => {
    setDraftDirty(true);
    setLaunchDraft((previous) => ({ ...previous, [field]: value }));
  };

  const sendLaunchCommand = async (launchCommand, label) => {
    if (typeof onSendMessage !== 'function') {
      setCommandStatus({ type: 'error', text: 'Send unavailable' });
      return;
    }

    setBusyAction(label);
    setCommandStatus({ type: 'pending', text: `${label}...` });

    try {
      const ok = await onSendMessage(
        SET_VCU_CONFIG_ID,
        buildVcuConfigFrame(240, { launchCommand }),
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

  const applyTorqueSettings = async () => {
    if (typeof onSendMessage !== 'function') {
      setSaveStatus({ type: 'error', text: 'Send unavailable' });
      return;
    }

    const writes = [
      [42, 'launchTorqueOfftheline'],
      [43, 'launchTorqueInit'],
      [44, 'launchTorqueFinal'],
    ];

    setBusyAction('apply-torque');
    setSaveStatus({ type: 'pending', text: 'Applying launch torque settings...' });

    try {
      for (const [mux, field] of writes) {
        const ok = await onSendMessage(
          SET_VCU_CONFIG_ID,
          buildVcuConfigFrame(mux, { [field]: launchDraft[field] }),
          true,
          false,
        );
        if (!ok) {
          throw new Error(`VCU rejected mux ${mux}`);
        }
      }

      setDraftDirty(false);
      setSaveStatus({ type: 'success', text: 'Launch torque settings sent. Reload from VCU to confirm readback.' });
    } catch (error) {
      setSaveStatus({ type: 'error', text: `Apply failed: ${error?.message || error}` });
    } finally {
      setBusyAction(null);
    }
  };

  const reloadFromVcu = () => {
    setLaunchDraft(createLaunchDraft(launchReadback));
    setDraftDirty(false);
    setSaveStatus(null);
  };

  return (
    <div className="vcu-dashboard vcu-launch-dashboard">
      <div className="vcu-header">
        <div>
          <h2><Gauge size={22} /> Launch Control</h2>
          <p>Arm or abort the VCU launch system, monitor live trigger status, and tune the three torque set-points.</p>
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
        0.0-0.2 s uses off-the-line torque, then the VCU follows a quadratic ramp from init torque to final torque at 3.0 s. Output torque is still bounded by the driver pedal request.
      </div>

      {!matchedSourceDbc && (
        <div className="vcu-notice">
          {enabledDbcCount > 0
            ? 'Waiting for decoded VCU launch-control frames from an enabled DBC.'
            : 'Enable a DBC that exposes VCU launch-control messages to populate this page.'}
        </div>
      )}

      {!hasAnyData && (
        <div className="vcu-empty">
          <AlertTriangle size={28} />
          <div>
            <h3>No launch-control frames received yet</h3>
            <p>Connect to CAN and enable a DBC that contains the new VCU launch state and config signals.</p>
          </div>
        </div>
      )}

      <div className="vcu-kpi-grid vcu-launch-top-grid">
        <section className="vcu-card">
          <div className="vcu-card-header">
            <Activity size={18} />
            <h3>Live Status</h3>
            <Freshness timestamp={frames.VCU_Launch_State?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />
          </div>

          <div className={`vcu-launch-state-chip state-${stateMachine ?? 'unknown'}`}>
            {stateMachine !== null ? LAUNCH_STATE_LABELS[stateMachine] || stateMachine : '--'}
          </div>

          <div className="vcu-pill-row">
            <span className={`vcu-pill ${launchArmed ? 'good' : 'unknown'}`}>Armed: {readinessText(launchArmed, 'YES', 'NO')}</span>
            <span className={`vcu-pill ${launchActive ? 'good' : 'unknown'}`}>Active: {readinessText(launchActive, 'YES', 'NO')}</span>
            <span className={`vcu-pill ${launchTelemetryFresh ? 'good' : 'bad'}`}>Telemetry: {launchTelemetryFresh ? 'FRESH' : 'STALE'}</span>
          </div>

          <div className="vcu-gauge-row">
            <div className="vcu-gauge-meta">
              <span>Curve torque</span>
            </div>
            <div className="vcu-gauge-track">
              <div className="vcu-gauge-fill" style={{ width: `${clampNumber(curveTorque ?? 0, 0, 230, 0) / 230 * 100}%` }} />
            </div>
            <strong>{curveTorque !== null ? `${Math.round(curveTorque)} Nm` : '--'}</strong>
          </div>

          <div className="vcu-gauge-row">
            <div className="vcu-gauge-meta">
              <span>Pedal (APPS)</span>
            </div>
            <div className="vcu-gauge-track">
              <div className="vcu-gauge-fill" style={{ width: `${clampNumber(appsPct ?? 0, 0, 100, 0)}%` }} />
            </div>
            <strong>{appsPct !== null ? `${appsPct.toFixed(1)} %` : '--'}</strong>
          </div>

          <div className="vcu-launch-live-grid">
            <span>Elapsed <strong>{formatElapsed(elapsedMs)}</strong></span>
            <span>Brake pressure <strong>{bsePsi !== null ? `${bsePsi.toFixed(1)} PSI` : '--'}</strong></span>
            <span>VCU state <strong>{enumLabel(getSignal('VCU_State'), VCU_STATE_LABELS)}</strong></span>
            <span>APPS valid <strong>{enumLabel(getSignal('VCU_APPS_Valid'), BOOLEAN_LABELS)}</strong></span>
          </div>

          {stateMachine === 1 && (
            <div className="vcu-launch-armed-note">
              Waiting for trigger: brake pressure {'<='} 1 PSI, throttle {'>'} 25%, and VCU state = DRIVING.
            </div>
          )}
        </section>

        <section className="vcu-card">
          <div className="vcu-card-header">
            <Zap size={18} />
            <h3>Arm / Abort</h3>
          </div>

          <div className="vcu-launch-action-stack">
            <button
              type="button"
              className="vcu-launch-arm-button"
              onClick={() => sendLaunchCommand(LAUNCH_COMMANDS.ARM, 'Arm launch')}
              disabled={!canArm}
            >
              ARM LAUNCH
            </button>
            <button
              type="button"
              className="vcu-launch-disarm-button"
              onClick={() => sendLaunchCommand(LAUNCH_COMMANDS.DISARM, 'Disarm launch')}
              disabled={!canDisarm}
            >
              DISARM (ABORT)
            </button>
          </div>

          <div className="vcu-launch-guardrails">
            <span>ARM is only enabled when fresh `VCU_Launch_State` telemetry shows `DISARMED`.</span>
            <span>DISARM is always available as the software abort and forces the VCU back to `DISARMED`.</span>
            <span>After each run the VCU auto-returns to `DISARMED`, so the next launch requires a fresh ARM command.</span>
          </div>

          <div className="vcu-launch-trigger-grid">
            <div className={`vcu-launch-trigger-item ${readinessClass(brakesReleased)}`}>
              <span>Brake release</span>
              <strong>{readinessText(brakesReleased, 'READY', 'HOLDING')}</strong>
            </div>
            <div className={`vcu-launch-trigger-item ${readinessClass(throttleReady)}`}>
              <span>Throttle > 25%</span>
              <strong>{readinessText(throttleReady, 'READY', 'WAITING')}</strong>
            </div>
            <div className={`vcu-launch-trigger-item ${readinessClass(drivingReady)}`}>
              <span>VCU = DRIVING</span>
              <strong>{readinessText(drivingReady, 'READY', 'WAITING')}</strong>
            </div>
            <div className={`vcu-launch-trigger-item ${readinessClass(appsValid && !appsImplausible)}`}>
              <span>APPS plausibility</span>
              <strong>{readinessText(appsValid && !appsImplausible, 'VALID', 'CHECK')}</strong>
            </div>
            <div className={`vcu-launch-trigger-item ${readinessClass(bseValid)}`}>
              <span>BSE validity</span>
              <strong>{readinessText(bseValid, 'VALID', 'CHECK')}</strong>
            </div>
          </div>
        </section>
      </div>

      <section className="vcu-card">
        <div className="vcu-card-header">
          <SlidersHorizontal size={18} />
          <h3>Torque Curve</h3>
          <Freshness timestamp={frames.VCU_Config?.timestamp} nowMs={nowMs} staleTimeoutMs={staleTimeoutMs} />
        </div>

        <div className="vcu-launch-curve-grid">
          <div className="vcu-sender vcu-launch-editor-form">
            <div className="vcu-sender-header">
              <span>Stored Parameters</span>
              <strong>Writes persist via muxes 42, 43, and 44</strong>
            </div>

            <label>
              Off-the-line torque (0-0.2 s)
              <input
                type="number"
                min="0"
                max="230"
                step="1"
                value={launchDraft.launchTorqueOfftheline}
                onChange={(event) => patchDraft('launchTorqueOfftheline', event.target.value)}
              />
            </label>

            <label>
              Init torque (curve at t = 0)
              <input
                type="number"
                min="0"
                max="230"
                step="1"
                value={launchDraft.launchTorqueInit}
                onChange={(event) => patchDraft('launchTorqueInit', event.target.value)}
              />
            </label>

            <label>
              Final torque (curve at t = 3.0 s)
              <input
                type="number"
                min="0"
                max="230"
                step="1"
                value={launchDraft.launchTorqueFinal}
                onChange={(event) => patchDraft('launchTorqueFinal', event.target.value)}
              />
            </label>

            <div className="vcu-launch-button-row">
              <button type="button" onClick={applyTorqueSettings} disabled={busyAction !== null}>Apply</button>
              <button type="button" className="vcu-launch-secondary" onClick={reloadFromVcu} disabled={busyAction !== null || !draftDirty}>Reload from VCU</button>
            </div>

            {draftDirty && (
              <div className="vcu-launch-copy">Editor values differ from the most recent VCU config readback.</div>
            )}
          </div>

          <div className="vcu-launch-preview-panel">
            <div className="vcu-launch-chart-card">
              <svg viewBox={`0 0 ${curvePreview.width} ${curvePreview.height}`} className="vcu-launch-chart" role="img" aria-label="Launch torque preview curve">
                <rect x="0" y="0" width={curvePreview.width} height={curvePreview.height} rx="10" />
                {curvePreview.guideValues.map((value) => {
                  const y = curvePreview.padding.top + curvePreview.plotHeight - (value / curvePreview.maxTorque) * curvePreview.plotHeight;
                  return (
                    <g key={value}>
                      <line x1={curvePreview.padding.left} x2={curvePreview.width - curvePreview.padding.right} y1={y} y2={y} className="vcu-launch-guide-line" />
                      <text x="6" y={y + 4} className="vcu-launch-guide-label">{value}</text>
                    </g>
                  );
                })}
                {[0.2, 1.5, 3].map((time) => {
                  const x = curvePreview.padding.left + (time / 3) * curvePreview.plotWidth;
                  return <line key={time} x1={x} x2={x} y1={curvePreview.padding.top} y2={curvePreview.height - curvePreview.padding.bottom} className="vcu-launch-time-line" />;
                })}
                <polyline points={curvePreview.polyline} className="vcu-launch-curve-line" />
                <text x={curvePreview.padding.left} y={curvePreview.height - 6} className="vcu-launch-axis-label">0.0s</text>
                <text x={curvePreview.padding.left + (0.2 / 3) * curvePreview.plotWidth - 10} y={curvePreview.height - 6} className="vcu-launch-axis-label">0.2s</text>
                <text x={curvePreview.padding.left + (1.5 / 3) * curvePreview.plotWidth - 10} y={curvePreview.height - 6} className="vcu-launch-axis-label">1.5s</text>
                <text x={curvePreview.width - curvePreview.padding.right - 18} y={curvePreview.height - 6} className="vcu-launch-axis-label">3.0s</text>
              </svg>
              <div className="vcu-launch-chart-caption">
                Off-the-line torque overrides the first 0.2 s. The quadratic ramp then transitions from init torque to final torque over the next 2.8 s.
              </div>
            </div>

            <div className="vcu-config-group">
              <div className="vcu-config-group-header">VCU Readback</div>
              <div className="vcu-readback-grid">
                <span className="vcu-config-item">Off-the-line <strong>{getDisplay(getSignal('VCU_Launch_Torque_Offtheline'))}</strong></span>
                <span className="vcu-config-item">Init torque <strong>{getDisplay(getSignal('VCU_Launch_Torque_Init'))}</strong></span>
                <span className="vcu-config-item">Final torque <strong>{getDisplay(getSignal('VCU_Launch_Torque_Final'))}</strong></span>
                <span className="vcu-config-item">Launch state <strong>{enumLabel(getSignal('VCU_Launch_State_Machine'), LAUNCH_STATE_LABELS)}</strong></span>
                <span className="vcu-config-item">Launch armed <strong>{enumLabel(getSignal('VCU_Launch_Armed'), BOOLEAN_LABELS)}</strong></span>
                <span className="vcu-config-item">Launch active <strong>{enumLabel(getSignal('VCU_Launch_Active'), BOOLEAN_LABELS)}</strong></span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

export default VCULaunchControlDashboard;