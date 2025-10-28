import React, { useState, useMemo, useRef, useEffect } from 'react';
import { Send, Trash2, FileText, Filter, Upload, ChevronDown, ChevronRight, Activity, Wifi, WifiOff, RefreshCw, Plus, List } from 'lucide-react';
import TransmitList from './TransmitList';
import './CANExplorer.css';

function CANExplorer({ 
  connected, 
  messages, 
  onClearMessages, 
  onSendMessage, 
  onLoadDBC, 
  dbcLoaded, 
  dbcFile,
  devices,
  onConnect,
  onDisconnect,
  onRefreshDevices,
  connectionStatus,
  stats,
  activeTab,
  onTabChange,
  children
}) {
  const [filterText, setFilterText] = useState('');
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [expandedReceivedMessages, setExpandedReceivedMessages] = useState(true);
  const [expandedTransmitList, setExpandedTransmitList] = useState(false);
  const fileInputRef = useRef(null);
  
  // Connection form state
  const [deviceType, setDeviceType] = useState('pcan');
  const [channel, setChannel] = useState('USB1');
  const [baudrate, setBaudrate] = useState('BAUD_500K');

  // Persistent count tracking - survives message array trimming
  const messageCountsRef = useRef(new Map());
  const lastProcessedTimestampRef = useRef(0);

  // Update counts when new messages arrive
  useEffect(() => {
    // Process messages with timestamps newer than the last processed one
    const newMessages = messages.filter(msg => msg.timestamp > lastProcessedTimestampRef.current);
    
    if (newMessages.length > 0) {
      newMessages.forEach(msg => {
        const key = msg.id;
        const currentCount = messageCountsRef.current.get(key) || 0;
        messageCountsRef.current.set(key, currentCount + 1);
      });
      
      // Update the last processed timestamp to the newest message
      const latestTimestamp = Math.max(...newMessages.map(m => m.timestamp));
      lastProcessedTimestampRef.current = latestTimestamp;
    }
  }, [messages]);

  // Clear counts when messages are cleared
  const handleClearMessages = () => {
    messageCountsRef.current.clear();
    lastProcessedTimestampRef.current = 0;
    onClearMessages();
  };

  // Aggregate messages by CAN ID and calculate cycle time
  const aggregatedMessages = useMemo(() => {
    const messageMap = new Map();
    
    messages.forEach(msg => {
      const key = msg.id;
      if (messageMap.has(key)) {
        const existing = messageMap.get(key);
        const timeDiff = msg.timestamp - existing.timestamp;
        existing.lastTimestamp = existing.timestamp;
        existing.data = msg.data;
        existing.timestamp = msg.timestamp;
        existing.decoded = msg.decoded;
        // Calculate cycle time (only if we have at least 2 messages)
        if (timeDiff > 0) {
          existing.cycleTime = timeDiff;
        }
      } else {
        messageMap.set(key, {
          id: msg.id,
          data: msg.data,
          timestamp: msg.timestamp,
          lastTimestamp: null,
          is_extended: msg.is_extended,
          dlc: msg.dlc,
          decoded: msg.decoded,
          cycleTime: null
        });
      }
    });

    // Add persistent counts to each message
    const messagesWithCounts = Array.from(messageMap.values()).map(msg => ({
      ...msg,
      count: messageCountsRef.current.get(msg.id) || 0
    }));

    return messagesWithCounts.sort((a, b) => a.id - b.id);
  }, [messages]);

  // Filter messages
  const filteredMessages = useMemo(() => {
    if (!filterText) return aggregatedMessages;
    
    const filter = filterText.toLowerCase();
    return aggregatedMessages.filter(msg => {
      const idHex = msg.id.toString(16).toLowerCase();
      const dataHex = msg.data.map(b => b.toString(16).padStart(2, '0')).join('').toLowerCase();
      const messageName = msg.decoded?.message_name?.toLowerCase() || '';
      
      return idHex.includes(filter) || dataHex.includes(filter) || messageName.includes(filter);
    });
  }, [aggregatedMessages, filterText]);

  const handleLoadDBC = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.name.endsWith('.dbc')) {
      alert('Please select a .dbc file');
      return;
    }

    try {
      await onLoadDBC(file);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error) {
      alert('Failed to upload DBC file: ' + error.message);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const toggleRowExpansion = (msgId) => {
    setExpandedRows(prev => {
      const newSet = new Set(prev);
      if (newSet.has(msgId)) {
        newSet.delete(msgId);
      } else {
        newSet.add(msgId);
      }
      return newSet;
    });
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleTimeString('en-US', { hour12: false });
  };

  const formatCycleTime = (cycleTime) => {
    if (!cycleTime) return '—';
    if (cycleTime < 1) {
      return `${(cycleTime * 1000).toFixed(0)} ms`;
    }
    return `${cycleTime.toFixed(3)} s`;
  };

  const formatData = (data) => {
    return data.map(b => b.toString(16).padStart(2, '0').toUpperCase()).join(' ');
  };

  const handleConnectClick = async () => {
    console.log('Connect button clicked!');
    console.log('Current state:', { connected, deviceType, channel, baudrate });
    
    try {
      if (connected) {
        console.log('Attempting to disconnect...');
        await onDisconnect();
      } else {
        console.log('Attempting to connect...');
        const result = await onConnect(deviceType, channel, baudrate);
        console.log('Connection result:', result);
      }
    } catch (error) {
      console.error('Connection error:', error);
      alert('Connection failed: ' + error.message);
    }
  };

  const formatUptime = (seconds) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="can-explorer-layout">
      {/* Sidebar for ALL controls */}
      <div className="can-sidebar">
        {/* App Header */}
        <div className="sidebar-section app-header">
          <div className="app-title">
            <img src="/logo.png" alt="TREV Logo" className="app-logo" />
            <div>
              <h1>TREV Explorer</h1>
              <span className="app-subtitle">TREV4 CAN Viewer</span>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="sidebar-section">
          <div className="sidebar-tabs">
            <button
              className={`sidebar-tab ${activeTab === 'explorer' ? 'active' : ''}`}
              onClick={() => onTabChange('explorer')}
            >
              CAN Explorer
            </button>
            <div className="sidebar-menu-group">
              <div className="sidebar-menu-header">BMS</div>
              <button
                className={`sidebar-tab submenu ${activeTab === 'bms-status' ? 'active' : ''}`}
                onClick={() => onTabChange('bms-status')}
              >
                Status Dashboard
              </button>
              <button
                className={`sidebar-tab submenu ${activeTab === 'thermistor' ? 'active' : ''}`}
                onClick={() => onTabChange('thermistor')}
              >
                Thermistors
              </button>
              <button
                className={`sidebar-tab submenu ${activeTab === 'voltage' ? 'active' : ''}`}
                onClick={() => onTabChange('voltage')}
              >
                Cell Voltages
              </button>
            </div>
          </div>
        </div>

        {/* Connection Panel */}
        <div className="sidebar-section">
          <div className="sidebar-header">
            {connected ? <Wifi size={18} /> : <WifiOff size={18} />}
            <span>Connection</span>
          </div>
          
          <div className="connection-form">
            <div className="form-group">
              <label>Device Type</label>
              <select 
                value={deviceType} 
                onChange={(e) => setDeviceType(e.target.value)}
                disabled={connected}
              >
                <option value="pcan">PCAN-USB</option>
                <option value="canable">CANable</option>
              </select>
            </div>

            <div className="form-group">
              <label>Channel</label>
              <input
                type="text"
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                disabled={connected}
                placeholder="USB1"
              />
            </div>

            <div className="form-group">
              <label>Baudrate</label>
              <select
                value={baudrate}
                onChange={(e) => setBaudrate(e.target.value)}
                disabled={connected}
              >
                <option value="BAUD_1M">1 Mbit/s</option>
                <option value="BAUD_500K">500 kbit/s</option>
                <option value="BAUD_250K">250 kbit/s</option>
                <option value="BAUD_125K">125 kbit/s</option>
              </select>
            </div>

            <button
              className={`btn btn-block ${connected ? 'btn-danger' : 'btn-primary'}`}
              onClick={handleConnectClick}
            >
              {connected ? 'Disconnect' : 'Connect'}
            </button>

            <button
              className="btn btn-secondary btn-block"
              onClick={onRefreshDevices}
              disabled={connected}
            >
              <RefreshCw size={16} />
              Refresh Devices
            </button>

            {connected && (
              <div className="connection-info">
                <div className="info-row">
                  <span className="info-label">Device:</span>
                  <span className="info-value">{connectionStatus.device_type?.toUpperCase()}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Channel:</span>
                  <span className="info-value">{connectionStatus.channel}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Messages:</span>
                  <span className="info-value">{stats.message_count}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Rate:</span>
                  <span className="info-value">{stats.message_rate} msg/s</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Uptime:</span>
                  <span className="info-value">{formatUptime(stats.uptime_seconds)}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* DBC Upload */}
        <div className="sidebar-section">
          <div className="sidebar-header">
            <FileText size={18} />
            <span>DBC File</span>
          </div>
          <button className="btn btn-secondary btn-block" onClick={handleUploadClick}>
            <Upload size={16} />
            Upload
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".dbc"
            onChange={handleLoadDBC}
            style={{ display: 'none' }}
          />
          {dbcLoaded ? (
            <div className="sidebar-status success">
              ✓ {dbcFile || 'Loaded'}
            </div>
          ) : (
            <div className="sidebar-status">
              No file loaded
            </div>
          )}
        </div>

        {/* Filter */}
        <div className="sidebar-section">
          <div className="sidebar-header">
            <Filter size={18} />
            <span>Filter</span>
          </div>
          <input
            type="text"
            placeholder="ID or data..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="filter-input-sidebar"
          />
        </div>
      </div>

      {/* Main content area - Message table or custom content */}
      <div className="can-main-content">
        {children ? (
          // Render custom content (like ThermistorMonitor or CellVoltageMonitor)
          children
        ) : (
          // Default: Render collapsible sections for Received Messages and Transmit List
          <>
            {/* Received Messages Section */}
            <div className="collapsible-section">
              <div 
                className="collapsible-header"
                onClick={() => setExpandedReceivedMessages(!expandedReceivedMessages)}
              >
                <div className="collapsible-title">
                  {expandedReceivedMessages ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                  <span>Received Messages ({filteredMessages.length})</span>
                </div>
                {expandedReceivedMessages && (
                  <button 
                    className="btn btn-danger btn-sm" 
                    onClick={(e) => { e.stopPropagation(); handleClearMessages(); }}
                  >
                    <Trash2 size={16} />
                    Clear All
                  </button>
                )}
              </div>

              {expandedReceivedMessages && (
                <div className="collapsible-content">
                  <div className="table-container-full">
              <table className="messages-table">
                <thead>
                  <tr>
                    <th style={{ width: '40px' }}></th>
                    <th style={{ width: '100px' }}>CAN ID</th>
                    <th>Message Name</th>
                    <th style={{ width: '150px' }}>Data (Hex)</th>
                    <th style={{ width: '80px' }}>Count</th>
                    <th style={{ width: '100px' }}>Cycle Time</th>
                    <th style={{ width: '100px' }}>Last RX</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMessages.length === 0 ? (
                    <tr>
                      <td colSpan="7" style={{ textAlign: 'center', padding: '40px', color: '#a0aec0' }}>
                        {messages.length === 0 ? 'No messages received yet' : 'No messages match filter'}
                      </td>
                    </tr>
                  ) : (
                    filteredMessages.map((msg, index) => {
                      const rowKey = `${msg.id}-${index}`;
                      const isExpanded = expandedRows.has(rowKey);
                      const hasSignals = msg.decoded && Object.keys(msg.decoded.signals).length > 0;
                      
                      return (
                        <React.Fragment key={rowKey}>
                          <tr className="message-row">
                            <td>
                              {hasSignals && (
                                <button
                                  className="expand-btn"
                                  onClick={() => toggleRowExpansion(rowKey)}
                                >
                                  {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                                </button>
                              )}
                            </td>
                            <td>
                              <span className="hex-data">
                                {msg.is_extended ? `0x${msg.id.toString(16).padStart(8, '0').toUpperCase()}` : `0x${msg.id.toString(16).padStart(3, '0').toUpperCase()}`}
                              </span>
                            </td>
                            <td>
                              {msg.decoded ? (
                                <span className="message-name">{msg.decoded.message_name}</span>
                              ) : (
                                <span style={{ color: '#a0aec0' }}>No DBC</span>
                              )}
                            </td>
                            <td><span className="hex-data-small">{formatData(msg.data)}</span></td>
                            <td>
                              <span className="badge badge-info">{msg.count}</span>
                            </td>
                            <td>{formatCycleTime(msg.cycleTime)}</td>
                            <td>{formatTimestamp(msg.timestamp)}</td>
                          </tr>
                          
                          {/* Expanded row showing all signals */}
                          {isExpanded && hasSignals && (
                            <tr className="expanded-row">
                              <td></td>
                              <td colSpan="6">
                                <div className="signals-container">
                                  <table className="signals-table">
                                    <thead>
                                      <tr>
                                        <th>Signal Name</th>
                                        <th>Value</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {Object.entries(msg.decoded.signals).map(([key, signalData]) => {
                                        // Handle both old format (plain value) and new format (object with metadata)
                                        const isObject = typeof signalData === 'object' && signalData !== null && !Array.isArray(signalData);
                                        const value = isObject ? signalData.value : signalData;
                                        const unit = isObject ? signalData.unit : null;
                                        const raw = isObject ? signalData.raw : null;
                                        
                                        // Format the display value
                                        let displayValue;
                                        if (typeof value === 'number') {
                                          displayValue = value.toFixed(3);
                                        } else {
                                          displayValue = value;
                                        }
                                        
                                        // Add unit if available
                                        if (unit) {
                                          displayValue = `${displayValue} ${unit}`;
                                        }
                                        
                                        // For enums, show both name and raw value
                                        if (typeof value === 'string' && raw !== null && raw !== undefined) {
                                          displayValue = `${value} (${raw})`;
                                        }
                                        
                                        return (
                                          <tr key={key}>
                                            <td className="signal-name">{key}</td>
                                            <td className="signal-value">{displayValue}</td>
                                          </tr>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
                  </div>
                </div>
              )}
            </div>

            {/* Transmit List Section */}
            <div className="collapsible-section">
              <div 
                className="collapsible-header"
                onClick={() => setExpandedTransmitList(!expandedTransmitList)}
              >
                <div className="collapsible-title">
                  {expandedTransmitList ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                  <span>Transmit List</span>
                </div>
              </div>

              {expandedTransmitList && (
                <div className="collapsible-content transmit-list-container">
                  <TransmitList 
                    dbcFile={dbcFile}
                    onSendMessage={onSendMessage}
                  />
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default CANExplorer;
