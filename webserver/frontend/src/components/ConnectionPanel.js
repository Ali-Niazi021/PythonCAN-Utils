import React, { useState } from 'react';
import { Wifi, WifiOff, RefreshCw, Zap } from 'lucide-react';
import './ConnectionPanel.css';

function ConnectionPanel({ connected, devices, onConnect, onDisconnect, onRefreshDevices }) {
  const [deviceType, setDeviceType] = useState('pcan');
  const [channel, setChannel] = useState('USB1');
  const [baudrate, setBaudrate] = useState('BAUD_500K');
  const [connecting, setConnecting] = useState(false);

  const baudrates = [
    'BAUD_1M', 'BAUD_800K', 'BAUD_500K', 'BAUD_250K',
    'BAUD_125K', 'BAUD_100K', 'BAUD_50K', 'BAUD_20K', 'BAUD_10K'
  ];

  const handleConnect = async () => {
    setConnecting(true);
    const success = await onConnect(deviceType, channel, baudrate);
    setConnecting(false);
    if (!success) {
      alert('Failed to connect. Check device and settings.');
    }
  };

  const handleDisconnect = async () => {
    setConnecting(true);
    await onDisconnect();
    setConnecting(false);
  };

  const pcanDevices = devices.filter(d => d.device_type === 'pcan');
  const canableDevices = devices.filter(d => d.device_type === 'canable');

  return (
    <div className="connection-panel">
      <div className="connection-content">
        <div className="connection-controls">
          <div className="form-group">
            <label>Device Type</label>
            <select
              value={deviceType}
              onChange={(e) => {
                setDeviceType(e.target.value);
                if (e.target.value === 'pcan' && pcanDevices.length > 0) {
                  setChannel(pcanDevices[0].name);
                } else if (e.target.value === 'canable' && canableDevices.length > 0) {
                  setChannel(String(canableDevices[0].index));
                }
              }}
              disabled={connected}
            >
              <option value="pcan">PCAN</option>
              <option value="canable">CANable</option>
            </select>
          </div>

          <div className="form-group">
            <label>Channel</label>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              disabled={connected}
            >
              {deviceType === 'pcan' ? (
                pcanDevices.length > 0 ? (
                  pcanDevices.map(device => (
                    <option key={device.name} value={device.name}>
                      {device.name} {device.occupied && '(Occupied)'}
                    </option>
                  ))
                ) : (
                  <option value="USB1">USB1</option>
                )
              ) : (
                canableDevices.length > 0 ? (
                  canableDevices.map(device => (
                    <option key={device.index} value={String(device.index)}>
                      Device {device.index}: {device.description}
                    </option>
                  ))
                ) : (
                  <option value="0">Device 0</option>
                )
              )}
            </select>
          </div>

          <div className="form-group">
            <label>Baudrate</label>
            <select
              value={baudrate}
              onChange={(e) => setBaudrate(e.target.value)}
              disabled={connected}
            >
              {baudrates.map(br => (
                <option key={br} value={br}>{br}</option>
              ))}
            </select>
          </div>

          <button
            className="btn-refresh"
            onClick={onRefreshDevices}
            disabled={connected || connecting}
            title="Refresh Devices"
          >
            <RefreshCw size={18} />
          </button>

          {!connected ? (
            <button
              className="btn btn-success btn-connect"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? (
                <>
                  <div className="spinner-small"></div>
                  Connecting...
                </>
              ) : (
                <>
                  <Wifi size={18} />
                  Connect
                </>
              )}
            </button>
          ) : (
            <button
              className="btn btn-danger btn-connect"
              onClick={handleDisconnect}
              disabled={connecting}
            >
              <WifiOff size={18} />
              Disconnect
            </button>
          )}
        </div>

        <div className="connection-status">
          <div className={`status-indicator ${connected ? 'connected' : 'disconnected'}`}>
            <Zap size={16} />
            <span>{connected ? 'Connected' : 'Disconnected'}</span>
          </div>
          {devices.length > 0 && (
            <div className="devices-found">
              {devices.length} device(s) available
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ConnectionPanel;
