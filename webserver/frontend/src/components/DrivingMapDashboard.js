import React, { useEffect, useMemo, useState } from 'react';
import { Crosshair, LocateFixed, MapPinned, Navigation, Trash2 } from 'lucide-react';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import {
  useNowTick, isTimestampStale, messageFreshnessTimestamp,
} from '../hooks/useStaleness';
import './DrivingMapDashboard.css';

const DEFAULT_CENTER = [39.8283, -98.5795];
const DEFAULT_ZOOM = 4;
const FOLLOW_ZOOM = 17;
const MAX_TRAIL_POINTS = 1000;
const DUPLICATE_COORD_EPSILON = 0.000005;

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

function isMeaningfullyDifferent(left, right) {
  if (!left || !right) return true;
  return (
    Math.abs(left.lat - right.lat) > DUPLICATE_COORD_EPSILON
    || Math.abs(left.lon - right.lon) > DUPLICATE_COORD_EPSILON
  );
}

function formatCoordinate(value) {
  return Number.isFinite(value) ? value.toFixed(6) : '--';
}

function formatAge(timestampSeconds, nowMs) {
  if (!timestampSeconds) return '--';
  const ageSeconds = Math.max(0, Math.round((nowMs - timestampSeconds * 1000) / 1000));
  if (ageSeconds < 60) return `${ageSeconds}s ago`;
  const minutes = Math.floor(ageSeconds / 60);
  const seconds = ageSeconds % 60;
  return `${minutes}m ${seconds}s ago`;
}

function FollowPosition({ point, follow }) {
  const map = useMap();

  useEffect(() => {
    if (!point || !follow) return;
    const zoom = Math.max(map.getZoom(), FOLLOW_ZOOM);
    map.setView([point.lat, point.lon], zoom, { animate: true });
  }, [follow, map, point]);

  useEffect(() => {
    const id = setTimeout(() => map.invalidateSize(), 0);
    return () => clearTimeout(id);
  }, [map]);

  return null;
}

function DrivingMapDashboard({ messages = [], dbcFiles = [], staleTimeoutMs = 30000 }) {
  const [trail, setTrail] = useState([]);
  const [follow, setFollow] = useState(true);
  const nowMs = useNowTick(1000);

  const hasGnssDbcEnabled = useMemo(
    () => dbcFiles.some((file) => file?.enabled && file.filename === 'can9-database-01.09.dbc'),
    [dbcFiles],
  );

  const gnss = useMemo(() => {
    let best = null;

    messages.forEach((msg) => {
      const signals = msg?.decoded?.signals;
      if (!signals || !('Latitude' in signals) || !('Longitude' in signals)) return;

      const ts = messageFreshnessTimestamp(msg)
        ?? (typeof msg.timestamp === 'number' ? msg.timestamp : 0);
      if (best && ts < best.timestamp) return;

      const lat = getNumericValue(signals.Latitude);
      const lon = getNumericValue(signals.Longitude);
      const validRaw = getNumericValue(signals.PositionValid);
      const accuracy = getNumericValue(signals.PositionAccuracy);
      const positionValid = validRaw == null ? true : validRaw !== 0;
      const coordsValid = (
        Number.isFinite(lat)
        && Number.isFinite(lon)
        && lat >= -90
        && lat <= 90
        && lon >= -180
        && lon <= 180
      );

      best = {
        lat,
        lon,
        accuracy,
        timestamp: ts,
        messageName: msg.decoded?.message_name || 'GnssPos',
        sourceDbc: msg.decoded?.source_dbc || null,
        positionValid,
        coordsValid,
        accepted: positionValid && coordsValid,
      };
    });

    return best;
  }, [messages]);

  const currentPoint = useMemo(() => (gnss?.accepted ? {
    lat: gnss.lat,
    lon: gnss.lon,
    timestamp: gnss.timestamp,
    accuracy: gnss.accuracy,
  } : null), [gnss]);

  const stale = gnss ? isTimestampStale(gnss.timestamp, nowMs, staleTimeoutMs) : false;
  const mapCenter = currentPoint ? [currentPoint.lat, currentPoint.lon] : DEFAULT_CENTER;
  const mapZoom = currentPoint ? FOLLOW_ZOOM : DEFAULT_ZOOM;
  const trailPositions = trail.map((point) => [point.lat, point.lon]);

  useEffect(() => {
    if (!currentPoint || stale) return;

    setTrail((prev) => {
      const last = prev[prev.length - 1];
      if (!isMeaningfullyDifferent(last, currentPoint)) return prev;
      return [...prev, currentPoint].slice(-MAX_TRAIL_POINTS);
    });
  }, [currentPoint, stale]);

  let statusText = 'Waiting for GNSS';
  let statusClass = 'waiting';
  if (currentPoint && stale) {
    statusText = 'GNSS stale';
    statusClass = 'warning';
  } else if (currentPoint) {
    statusText = 'Live position';
    statusClass = 'live';
  } else if (gnss && !gnss.positionValid) {
    statusText = 'Position invalid';
    statusClass = 'warning';
  } else if (gnss && !gnss.coordsValid) {
    statusText = 'Coordinates out of range';
    statusClass = 'warning';
  } else if (!hasGnssDbcEnabled) {
    statusText = 'GNSS DBC not enabled';
    statusClass = 'warning';
  }

  return (
    <div className="driving-map-dashboard">
      <div className="driving-map-header">
        <div className="driving-map-title">
          <MapPinned size={22} />
          <h2>Driving Map Dashboard</h2>
        </div>
        <div className="driving-map-actions">
          <button
            type="button"
            className={`driving-map-action ${follow ? 'active' : ''}`}
            onClick={() => setFollow((value) => !value)}
          >
            {follow ? <LocateFixed size={16} /> : <Crosshair size={16} />}
            {follow ? 'Following' : 'Follow Off'}
          </button>
          <button
            type="button"
            className="driving-map-action"
            onClick={() => setTrail([])}
            disabled={trail.length === 0}
          >
            <Trash2 size={16} />
            Clear Trail
          </button>
        </div>
      </div>

      <div className="driving-map-layout">
        <div className="driving-map-shell">
          <MapContainer
            className="driving-leaflet-map"
            center={mapCenter}
            zoom={mapZoom}
            scrollWheelZoom
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <FollowPosition point={currentPoint} follow={follow} />
            {trailPositions.length > 1 && (
              <Polyline
                positions={trailPositions}
                pathOptions={{ color: '#22c55e', weight: 4, opacity: 0.82 }}
              />
            )}
            {currentPoint && (
              <CircleMarker
                center={[currentPoint.lat, currentPoint.lon]}
                radius={9}
                pathOptions={{
                  color: '#dcfce7',
                  fillColor: stale ? '#f59e0b' : '#22c55e',
                  fillOpacity: 0.95,
                  weight: 3,
                }}
              >
                <Popup>
                  <strong>Car location</strong>
                  <br />
                  {formatCoordinate(currentPoint.lat)}, {formatCoordinate(currentPoint.lon)}
                </Popup>
              </CircleMarker>
            )}
          </MapContainer>

          {!currentPoint && (
            <div className="driving-map-empty">
              <Navigation size={34} />
              <p>{hasGnssDbcEnabled ? 'Waiting for valid Latitude and Longitude data.' : 'Enable can9-database-01.09.dbc to decode GNSS position.'}</p>
            </div>
          )}
        </div>

        <aside className="driving-map-status">
          <div className={`driving-map-status-pill ${statusClass}`}>{statusText}</div>
          <div className="driving-map-stat">
            <span>Latitude</span>
            <strong>{formatCoordinate(gnss?.lat)}</strong>
          </div>
          <div className="driving-map-stat">
            <span>Longitude</span>
            <strong>{formatCoordinate(gnss?.lon)}</strong>
          </div>
          <div className="driving-map-stat">
            <span>Accuracy</span>
            <strong>{Number.isFinite(gnss?.accuracy) ? `${gnss.accuracy.toFixed(0)} m` : '--'}</strong>
          </div>
          <div className="driving-map-stat">
            <span>Last Update</span>
            <strong>{formatAge(gnss?.timestamp, nowMs)}</strong>
          </div>
          <div className="driving-map-stat">
            <span>Trail Points</span>
            <strong>{trail.length}</strong>
          </div>
          <div className="driving-map-source">
            <span>{gnss?.messageName || 'GnssPos'}</span>
            <span>{gnss?.sourceDbc || 'can9-database-01.09.dbc'}</span>
          </div>
        </aside>
      </div>
    </div>
  );
}

export default DrivingMapDashboard;
