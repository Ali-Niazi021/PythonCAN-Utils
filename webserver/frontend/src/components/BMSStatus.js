import React, { useState, useEffect } from 'react';
import { Activity, AlertTriangle, Thermometer, Zap, TrendingUp, TrendingDown, Info, Send, CheckCircle, XCircle } from 'lucide-react';
import { apiService } from '../services/api';
import FirmwareFlasher from './FirmwareFlasher';
import './BMSStatus.css';

function BMSStatus({ messages, onSendMessage, dbcFile }) {
  const [moduleData, setModuleData] = useState({});
  const [selectedModule, setSelectedModule] = useState('all'); // 'all' or 0-5
  const [commandStatus, setCommandStatus] = useState({}); // Track command responses
  const [faultHistory, setFaultHistory] = useState({}); // Track all faults with timestamps

  useEffect(() => {
    if (!messages || messages.length === 0) return;

    const newModuleData = {};
    const now = Date.now();

    // Process messages for all 6 modules
    messages.forEach(msg => {
      if (!msg.decoded) return;

      const msgName = msg.decoded.message_name;
      
      // Extract module number from message name
      // Handle different patterns: "BMS_Heartbeat_0", "Cell_Temp_0_3", "Cell_Voltage_1_3"
      let moduleId = null;
      
      // For messages with module suffix (e.g., "BMS_Heartbeat_0")
      const moduleSuffixMatch = msgName.match(/_(\d)$/);
      if (moduleSuffixMatch) {
        moduleId = parseInt(moduleSuffixMatch[1]);
      } else {
        // For Cell_Temp and Cell_Voltage messages, extract module from thermistor/cell number
        const tempMatch = msgName.match(/Cell_Temp_(\d+)_/);
        if (tempMatch) {
          const thermNum = parseInt(tempMatch[1]);
          moduleId = Math.floor(thermNum / 56); // 56 thermistors per module
        } else {
          const voltMatch = msgName.match(/Cell_Voltage_(\d+)_/);
          if (voltMatch) {
            const cellNum = parseInt(voltMatch[1]);
            moduleId = Math.floor((cellNum - 1) / 18); // 18 cells per module, cells start at 1
          }
        }
      }
      
      if (moduleId === null) return;
      
      if (!newModuleData[moduleId]) {
        newModuleData[moduleId] = {
          heartbeat: null,
          canStats: null,
          bms1Status: null,
          bms2Status: null,
          temperatures: [],
          voltages: [],
          i2cDiag: null,
          debugInfo: null
        };
      }

      // Parse different message types
      if (msgName.startsWith('BMS_Heartbeat_')) {
        newModuleData[moduleId].heartbeat = msg.decoded.signals;
        
        // Update fault history when we see a heartbeat
        const byte0 = msg.decoded.signals.Error_Flags_Byte0?.raw ?? msg.decoded.signals.Error_Flags_Byte0?.value ?? 0;
        const byte1 = msg.decoded.signals.Error_Flags_Byte1?.raw ?? msg.decoded.signals.Error_Flags_Byte1?.value ?? 0;
        const byte2 = msg.decoded.signals.Error_Flags_Byte2?.raw ?? msg.decoded.signals.Error_Flags_Byte2?.value ?? 0;
        const byte3 = msg.decoded.signals.Error_Flags_Byte3?.raw ?? msg.decoded.signals.Error_Flags_Byte3?.value ?? 0;

        const activeFaults = [];
        
        // Temperature errors (Byte 0)
        if (byte0 & 1) activeFaults.push({ type: 'temp', msg: 'Over Temperature', id: 'temp_over' });
        if (byte0 & 2) activeFaults.push({ type: 'temp', msg: 'Under Temperature', id: 'temp_under' });
        if (byte0 & 4) activeFaults.push({ type: 'temp', msg: 'Temp Sensor Fault', id: 'temp_sensor' });
        if (byte0 & 8) activeFaults.push({ type: 'temp', msg: 'Temperature Gradient', id: 'temp_gradient' });

        // Voltage errors (Byte 1)
        if (byte1 & 1) activeFaults.push({ type: 'voltage', msg: 'Over Voltage', id: 'volt_over' });
        if (byte1 & 2) activeFaults.push({ type: 'voltage', msg: 'Under Voltage', id: 'volt_under' });
        if (byte1 & 4) activeFaults.push({ type: 'voltage', msg: 'Voltage Imbalance', id: 'volt_imbalance' });
        if (byte1 & 8) activeFaults.push({ type: 'voltage', msg: 'Voltage Sensor Fault', id: 'volt_sensor' });

        // Current errors (Byte 2)
        if (byte2 & 1) activeFaults.push({ type: 'current', msg: 'Over Current Charge', id: 'curr_over_charge' });
        if (byte2 & 2) activeFaults.push({ type: 'current', msg: 'Over Current Discharge', id: 'curr_over_discharge' });
        if (byte2 & 4) activeFaults.push({ type: 'current', msg: 'Current Sensor Fault', id: 'curr_sensor' });
        if (byte2 & 8) activeFaults.push({ type: 'current', msg: 'Short Circuit', id: 'curr_short' });

        // Communication errors (Byte 3)
        if (byte3 & 1) activeFaults.push({ type: 'comm', msg: 'CAN Bus Off', id: 'can_bus_off' });
        if (byte3 & 2) activeFaults.push({ type: 'comm', msg: 'CAN TX Timeout', id: 'can_tx_timeout' });
        if (byte3 & 4) activeFaults.push({ type: 'comm', msg: 'CAN RX Overflow', id: 'can_rx_overflow' });
        if (byte3 & 8) activeFaults.push({ type: 'comm', msg: 'I2C1 BMS1 Error', id: 'i2c1_bms1' });
        if (byte3 & 16) activeFaults.push({ type: 'comm', msg: 'I2C3 BMS2 Error', id: 'i2c3_bms2' });
        if (byte3 & 32) activeFaults.push({ type: 'comm', msg: 'I2C Timeout', id: 'i2c_timeout' });
        if (byte3 & 64) activeFaults.push({ type: 'comm', msg: 'I2C Fault', id: 'i2c_fault' });
        if (byte3 & 128) activeFaults.push({ type: 'comm', msg: 'Watchdog Reset', id: 'watchdog' });

        // Update fault history
        setFaultHistory(prev => {
          const newHistory = { ...prev };
          const moduleKey = `module_${moduleId}`;
          
          if (!newHistory[moduleKey]) {
            newHistory[moduleKey] = {};
          }
          
          // Update timestamps for currently active faults
          activeFaults.forEach(fault => {
            newHistory[moduleKey][fault.id] = {
              ...fault,
              lastSeen: now
            };
          });
          
          return newHistory;
        });
      } else if (msgName.startsWith('BMS_CAN_Stats_')) {
        newModuleData[moduleId].canStats = msg.decoded.signals;
      } else if (msgName.startsWith('BMS1_Chip_Status_')) {
        newModuleData[moduleId].bms1Status = msg.decoded.signals;
      } else if (msgName.startsWith('BMS2_Chip_Status_')) {
        newModuleData[moduleId].bms2Status = msg.decoded.signals;
      } else if (msgName.startsWith('Cell_Temp_')) {
        // Extract temperature values
        Object.entries(msg.decoded.signals).forEach(([name, signal]) => {
          if (name.startsWith('Temp_')) {
            newModuleData[moduleId].temperatures.push({
              name,
              value: signal.value,
              unit: signal.unit
            });
          }
        });
      } else if (msgName.startsWith('Cell_Voltage_')) {
        // Extract voltage values
        Object.entries(msg.decoded.signals).forEach(([name, signal]) => {
          if (name.includes('Voltage')) {
            newModuleData[moduleId].voltages.push({
              name,
              value: signal.value,
              unit: signal.unit
            });
          }
        });
      } else if (msgName.startsWith('BMS_I2C_Diagnostics_')) {
        newModuleData[moduleId].i2cDiag = msg.decoded.signals;
      } else if (msgName.startsWith('BMS_Debug_Response_')) {
        newModuleData[moduleId].debugInfo = msg.decoded.signals;
      }
    });

    setModuleData(newModuleData);
  }, [messages]);

  // Calculate combined data for all modules
  const getCombinedData = () => {
    const combined = {
      temperatures: [],
      voltages: [],
      totalErrors: 0,
      activeModules: 0
    };

    Object.values(moduleData).forEach(module => {
      if (module.temperatures.length > 0) combined.temperatures.push(...module.temperatures);
      if (module.voltages.length > 0) combined.voltages.push(...module.voltages);
      if (module.heartbeat) {
        combined.activeModules++;
        const faultCount = module.heartbeat.Fault_Count?.value || 0;
        combined.totalErrors += faultCount;
      }
    });

    return combined;
  };

  const combinedData = getCombinedData();
  const isAllModulesView = selectedModule === 'all';
  const module = isAllModulesView ? {} : (moduleData[selectedModule] || {});

  // Monitor for command ACK/response messages
  useEffect(() => {
    if (!messages || messages.length === 0) return;

    // Check for ACK messages in recent messages
    const recentMessages = messages.slice(-10); // Check last 10 messages
    
    recentMessages.forEach(msg => {
      if (!msg.decoded) return;
      
      const msgName = msg.decoded.message_name;
      
      // Track Chip Reset ACKs
      if (msgName.startsWith('BMS_Chip_Reset_ACK_')) {
        const moduleMatch = msgName.match(/_(\d)$/);
        if (moduleMatch) {
          const modId = parseInt(moduleMatch[1]);
          const status = msg.decoded.signals.Status?.value || 'Unknown';
          setCommandStatus(prev => ({
            ...prev,
            [`chip_reset_${modId}`]: {
              status: status === 'Success' ? 'success' : 'error',
              message: `Status: ${status}`,
              timestamp: Date.now()
            }
          }));
        }
      }
      
      // Track Debug Responses
      if (msgName.startsWith('BMS_Debug_Response_')) {
        const moduleMatch = msgName.match(/_(\d)$/);
        if (moduleMatch) {
          const modId = parseInt(moduleMatch[1]);
          setCommandStatus(prev => ({
            ...prev,
            [`debug_${modId}`]: {
              status: 'success',
              message: 'Debug response received',
              timestamp: Date.now(),
              data: msg.decoded.signals
            }
          }));
        }
      }
    });
  }, [messages]);

  // Clear old command statuses after 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setCommandStatus(prev => {
        const updated = { ...prev };
        Object.keys(updated).forEach(key => {
          if (now - updated[key].timestamp > 5000) {
            delete updated[key];
          }
        });
        return updated;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Clear old faults from history after 5 seconds of not being seen
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setFaultHistory(prev => {
        const updated = { ...prev };
        let hasChanges = false;
        
        Object.keys(updated).forEach(moduleKey => {
          Object.keys(updated[moduleKey]).forEach(faultId => {
            if (now - updated[moduleKey][faultId].lastSeen > 5000) {
              delete updated[moduleKey][faultId];
              hasChanges = true;
            }
          });
          
          // Clean up empty module entries
          if (Object.keys(updated[moduleKey]).length === 0) {
            delete updated[moduleKey];
            hasChanges = true;
          }
        });
        
        return hasChanges ? updated : prev;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Send command functions
  const sendCommand = async (messageName, signals = {}) => {
    if (!dbcFile) {
      alert('No DBC file loaded');
      return false;
    }

    try {
      // Encode the message using the DBC
      const encoded = await apiService.encodeMessage(messageName, signals);
      
      // Send the message
      const success = await onSendMessage(
        encoded.can_id,
        encoded.data,
        encoded.is_extended,
        false
      );

      if (success) {
        console.log(`Sent ${messageName}`);
        return true;
      }
      return false;
    } catch (error) {
      console.error(`Failed to send ${messageName}:`, error);
      alert(`Failed to send command: ${error.message}`);
      return false;
    }
  };

  const handleResetCommand = async (moduleId) => {
    // BMS_Reset_Command requires Reset_Magic signal (typically 0xAA or similar)
    const success = await sendCommand(`BMS_Reset_Command_${moduleId}`, { Reset_Magic: 0xAA });
    if (success !== false) {
      setCommandStatus(prev => ({
        ...prev,
        [`reset_${moduleId}`]: { 
          status: 'success', 
          message: 'Reset command sent (no ACK expected)', 
          timestamp: Date.now() 
        }
      }));
    }
  };

  const handleChipResetCommand = async (moduleId) => {
    // BMS_Chip_Reset_Command requires Reset_Request signal (typically 1 to request reset)
    await sendCommand(`BMS_Chip_Reset_Command_${moduleId}`, { Reset_Request: 1 });
    setCommandStatus(prev => ({
      ...prev,
      [`chip_reset_${moduleId}`]: { status: 'pending', message: 'Waiting for ACK...', timestamp: Date.now() }
    }));
  };

  const handleDebugRequest = async () => {
    // BMS_Debug_Request requires Request_Type signal (0 for general debug info)
    await sendCommand('BMS_Debug_Request', { Request_Type: 0 });
    // Mark all modules as pending since it's a broadcast
    const newStatus = {};
    for (let i = 0; i < 6; i++) {
      newStatus[`debug_${i}`] = { status: 'pending', message: 'Waiting for response...', timestamp: Date.now() };
    }
    setCommandStatus(prev => ({ ...prev, ...newStatus }));
  };

  const { 
    heartbeat, 
    canStats, 
    bms1Status, 
    bms2Status, 
    temperatures = [], 
    voltages = [], 
    i2cDiag, 
    debugInfo 
  } = module;

  // Use combined data if "All Modules" is selected
  const displayTemps = isAllModulesView ? combinedData.temperatures : temperatures;
  const displayVolts = isAllModulesView ? combinedData.voltages : voltages;

  // Calculate min/max temps and voltages
  const tempValues = displayTemps.map(t => t.value).filter(v => v != null);
  const minTemp = tempValues.length > 0 ? Math.min(...tempValues) : null;
  const maxTemp = tempValues.length > 0 ? Math.max(...tempValues) : null;
  const avgTemp = tempValues.length > 0 ? (tempValues.reduce((a, b) => a + b, 0) / tempValues.length).toFixed(1) : null;

  const voltValues = displayVolts.map(v => v.value).filter(v => v != null);
  const minVolt = voltValues.length > 0 ? Math.min(...voltValues) : null;
  const maxVolt = voltValues.length > 0 ? Math.max(...voltValues) : null;
  const avgVolt = voltValues.length > 0 ? Math.round(voltValues.reduce((a, b) => a + b, 0) / voltValues.length) : null;

  const getBMSStateClass = (state) => {
    const stateMap = {
      'INIT': 'state-init',
      'IDLE': 'state-idle',
      'CHARGING': 'state-charging',
      'DISCHARGING': 'state-discharging',
      'BALANCING': 'state-balancing',
      'FAULT': 'state-fault',
      'SHUTDOWN': 'state-shutdown'
    };
    return stateMap[state] || 'state-unknown';
  };

  const getErrorFlags = (moduleId) => {
    if (moduleId === null || moduleId === undefined) return [];
    
    // Return all faults from history for this module
    const moduleKey = `module_${moduleId}`;
    const moduleFaults = faultHistory[moduleKey] || {};
    
    return Object.values(moduleFaults);
  };

  const errorFlags = getErrorFlags(isAllModulesView ? null : selectedModule);

  return (
    <div className="bms-status">
      <div className="bms-header">
        <h2><Activity size={24} /> BMS Status Dashboard</h2>
        <div className="module-selector">
          <button
            className={`module-btn ${selectedModule === 'all' ? 'active' : ''} has-data`}
            onClick={() => setSelectedModule('all')}
          >
            All Modules
          </button>
          {[0, 1, 2, 3, 4, 5].map(id => (
            <button
              key={id}
              className={`module-btn ${selectedModule === id ? 'active' : ''} ${moduleData[id] ? 'has-data' : ''}`}
              onClick={() => setSelectedModule(id)}
            >
              Module {id}
            </button>
          ))}
        </div>
      </div>

      {!isAllModulesView && !moduleData[selectedModule] && (
        <div className="no-data">
          <Info size={48} />
          <p>No data received from Module {selectedModule}</p>
          <p className="hint">Connect to CAN bus and ensure module is transmitting</p>
        </div>
      )}

      {(isAllModulesView || moduleData[selectedModule]) && (
        <div className="bms-dashboard">
          {/* Overview Cards */}
          <div className="overview-grid">
            {/* BMS State Card - Only for single module view */}
            {!isAllModulesView && heartbeat && (
              <div className="status-card">
                <div className="card-header">
                  <Activity size={20} />
                  <h3>System State</h3>
                </div>
                <div className="card-content">
                  {heartbeat.BMS_State && (
                    <div className={`bms-state ${getBMSStateClass(heartbeat.BMS_State.value)}`}>
                      {heartbeat.BMS_State.value || 'UNKNOWN'}
                    </div>
                  )}
                  {heartbeat.Fault_Count && (
                    <div className="stat-row">
                      <span>Fault Count:</span>
                      <span className="stat-value">{heartbeat.Fault_Count.value}</span>
                    </div>
                  )}
                  
                  {/* Fault Flags */}
                  {errorFlags.length > 0 && (
                    <div className="fault-flags-section">
                      <div className="fault-flags-header">
                        <AlertTriangle size={16} />
                        <span>Active Fault Flags</span>
                      </div>
                      <div className="fault-flags-list">
                        {errorFlags.map((flag, index) => (
                          <div key={index} className={`fault-flag fault-flag-${flag.type}`}>
                            <AlertTriangle size={12} />
                            <span>{flag.msg}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {errorFlags.length === 0 && heartbeat.Fault_Count?.value === 0 && (
                    <div className="no-faults">
                      <CheckCircle size={16} />
                      <span>No Active Faults</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* System Overview - Only for all modules view */}
            {isAllModulesView && (
              <div className="status-card">
                <div className="card-header">
                  <Activity size={20} />
                  <h3>System Overview</h3>
                </div>
                <div className="card-content">
                  <div className="stat-row">
                    <span>Active Modules:</span>
                    <span className="stat-value">{combinedData.activeModules} / 6</span>
                  </div>
                  <div className="stat-row">
                    <span>Total Errors:</span>
                    <span className="stat-value">{combinedData.totalErrors}</span>
                  </div>
                  <div className="stat-row">
                    <span>Total Cells:</span>
                    <span className="stat-value">{displayVolts.length}</span>
                  </div>
                  <div className="stat-row">
                    <span>Total Thermistors:</span>
                    <span className="stat-value">{displayTemps.length}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Temperature Card */}
            <div className="status-card">
              <div className="card-header">
                <Thermometer size={20} />
                <h3>Temperature</h3>
              </div>
              <div className="card-content">
                <div className="stat-row">
                  <TrendingDown size={16} className="stat-icon cold" />
                  <span>Min:</span>
                  <span className="stat-value">{minTemp !== null ? `${minTemp.toFixed(1)}°C` : '--'}</span>
                </div>
                <div className="stat-row">
                  <TrendingUp size={16} className="stat-icon hot" />
                  <span>Max:</span>
                  <span className="stat-value">{maxTemp !== null ? `${maxTemp.toFixed(1)}°C` : '--'}</span>
                </div>
                <div className="stat-row">
                  <span>Avg:</span>
                  <span className="stat-value">{avgTemp !== null ? `${avgTemp}°C` : '--'}</span>
                </div>
              </div>
            </div>

            {/* Voltage Card */}
            <div className="status-card">
              <div className="card-header">
                <Zap size={20} />
                <h3>Cell Voltage</h3>
              </div>
              <div className="card-content">
                <div className="stat-row">
                  <TrendingDown size={16} className="stat-icon" />
                  <span>Min:</span>
                  <span className="stat-value">{minVolt !== null ? `${minVolt} mV` : '--'}</span>
                </div>
                <div className="stat-row">
                  <TrendingUp size={16} className="stat-icon" />
                  <span>Max:</span>
                  <span className="stat-value">{maxVolt !== null ? `${maxVolt} mV` : '--'}</span>
                </div>
                <div className="stat-row">
                  <span>Avg:</span>
                  <span className="stat-value">{avgVolt !== null ? `${avgVolt} mV` : '--'}</span>
                </div>
                <div className="stat-row">
                  <span>Delta:</span>
                  <span className="stat-value">
                    {minVolt !== null && maxVolt !== null ? `${maxVolt - minVolt} mV` : '--'}
                  </span>
                </div>
              </div>
            </div>

            {/* BMS1 Chip Status - Only for single module view */}
            {!isAllModulesView && bms1Status && (
              <div className="status-card">
                <div className="card-header">
                  <Info size={20} />
                  <h3>BMS Chip 1</h3>
                </div>
                <div className="card-content">
                  <div className="stat-row">
                    <span>Stack Voltage:</span>
                    <span className="stat-value">{bms1Status.BMS1_Stack_Voltage?.value || '--'} mV</span>
                  </div>
                  <div className="stat-row">
                    <span>Temperature:</span>
                    <span className="stat-value">{bms1Status.BMS1_TS2_Temperature?.value?.toFixed(1) || '--'}°C</span>
                  </div>
                  <div className="stat-row">
                    <span>Alarm Status:</span>
                    <span className="stat-value">0x{(bms1Status.BMS1_Alarm_Status?.value || 0).toString(16).toUpperCase().padStart(4, '0')}</span>
                  </div>
                </div>
              </div>
            )}

            {/* BMS2 Chip Status - Only for single module view */}
            {!isAllModulesView && bms2Status && (
              <div className="status-card">
                <div className="card-header">
                  <Info size={20} />
                  <h3>BMS Chip 2</h3>
                </div>
                <div className="card-content">
                  <div className="stat-row">
                    <span>Stack Voltage:</span>
                    <span className="stat-value">{bms2Status.BMS2_Stack_Voltage?.value || '--'} mV</span>
                  </div>
                  <div className="stat-row">
                    <span>Temperature:</span>
                    <span className="stat-value">{bms2Status.BMS2_TS2_Temperature?.value?.toFixed(1) || '--'}°C</span>
                  </div>
                  <div className="stat-row">
                    <span>Alarm Status:</span>
                    <span className="stat-value">0x{(bms2Status.BMS2_Alarm_Status?.value || 0).toString(16).toUpperCase().padStart(4, '0')}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Command Buttons Section */}
          {!isAllModulesView && (
            <div className="commands-section">
              <div className="card-header">
                <Send size={20} />
                <h3>Module Commands</h3>
              </div>
              <div className="commands-grid">
                <div className="command-item">
                  <button 
                    className="btn-command"
                    onClick={() => handleResetCommand(selectedModule)}
                    disabled={!dbcFile}
                  >
                    <Send size={16} />
                    BMS Reset
                  </button>
                  {commandStatus[`reset_${selectedModule}`] && (
                    <div className={`command-status ${commandStatus[`reset_${selectedModule}`].status}`}>
                      {commandStatus[`reset_${selectedModule}`].status === 'success' ? (
                        <><CheckCircle size={14} /> {commandStatus[`reset_${selectedModule}`].message}</>
                      ) : commandStatus[`reset_${selectedModule}`].status === 'pending' ? (
                        <><Activity size={14} className="spinning" /> {commandStatus[`reset_${selectedModule}`].message}</>
                      ) : (
                        <><XCircle size={14} /> {commandStatus[`reset_${selectedModule}`].message}</>
                      )}
                    </div>
                  )}
                </div>

                <div className="command-item">
                  <button 
                    className="btn-command"
                    onClick={() => handleChipResetCommand(selectedModule)}
                    disabled={!dbcFile}
                  >
                    <Send size={16} />
                    Chip Reset
                  </button>
                  {commandStatus[`chip_reset_${selectedModule}`] && (
                    <div className={`command-status ${commandStatus[`chip_reset_${selectedModule}`].status}`}>
                      {commandStatus[`chip_reset_${selectedModule}`].status === 'success' ? (
                        <><CheckCircle size={14} /> {commandStatus[`chip_reset_${selectedModule}`].message}</>
                      ) : commandStatus[`chip_reset_${selectedModule}`].status === 'pending' ? (
                        <><Activity size={14} className="spinning" /> {commandStatus[`chip_reset_${selectedModule}`].message}</>
                      ) : (
                        <><XCircle size={14} /> {commandStatus[`chip_reset_${selectedModule}`].message}</>
                      )}
                    </div>
                  )}
                </div>

                <div className="command-item">
                  <button 
                    className="btn-command"
                    onClick={handleDebugRequest}
                    disabled={!dbcFile}
                  >
                    <Send size={16} />
                    Debug Request (All Modules)
                  </button>
                  {commandStatus[`debug_${selectedModule}`] && (
                    <div className={`command-status ${commandStatus[`debug_${selectedModule}`].status}`}>
                      {commandStatus[`debug_${selectedModule}`].status === 'success' ? (
                        <><CheckCircle size={14} /> {commandStatus[`debug_${selectedModule}`].message}</>
                      ) : commandStatus[`debug_${selectedModule}`].status === 'pending' ? (
                        <><Activity size={14} className="spinning" /> {commandStatus[`debug_${selectedModule}`].message}</>
                      ) : (
                        <><XCircle size={14} /> {commandStatus[`debug_${selectedModule}`].message}</>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Individual Module Status Cards - Only for all modules view */}
          {isAllModulesView && (
            <div className="module-cards-section">
              <h3 className="section-title">Individual Module Status</h3>
              <div className="module-cards-grid">
                {[0, 1, 2, 3, 4, 5].map(moduleId => {
                  const modData = moduleData[moduleId];
                  if (!modData) {
                    return (
                      <div key={moduleId} className="module-card inactive">
                        <div className="module-card-header">
                          <span className="module-id">Module {moduleId}</span>
                          <span className="module-status offline">OFFLINE</span>
                        </div>
                        <div className="module-card-content">
                          <p className="no-data-text">No data received</p>
                        </div>
                      </div>
                    );
                  }

                  // Calculate module-specific stats
                  const modTempValues = modData.temperatures.map(t => t.value).filter(v => v != null);
                  const modMinTemp = modTempValues.length > 0 ? Math.min(...modTempValues) : null;
                  const modMaxTemp = modTempValues.length > 0 ? Math.max(...modTempValues) : null;

                  const modVoltValues = modData.voltages.map(v => v.value).filter(v => v != null);
                  const modMinVolt = modVoltValues.length > 0 ? Math.min(...modVoltValues) : null;
                  const modMaxVolt = modVoltValues.length > 0 ? Math.max(...modVoltValues) : null;
                  const modAvgVolt = modVoltValues.length > 0 ? Math.round(modVoltValues.reduce((a, b) => a + b, 0) / modVoltValues.length) : null;

                  const modState = modData.heartbeat?.BMS_State?.value || 'UNKNOWN';
                  const modFaultCount = modData.heartbeat?.Fault_Count?.value || 0;
                  const hasFault = modFaultCount > 0 || modState === 'FAULT';
                  
                  // Get error flags for this module from history
                  const modErrorFlags = getErrorFlags(moduleId);

                  return (
                    <div key={moduleId} className={`module-card ${hasFault ? 'has-fault' : 'active'}`}>
                      <div className="module-card-header">
                        <span className="module-id">Module {moduleId}</span>
                        <span className={`module-status ${modState.toLowerCase()}`}>{modState}</span>
                      </div>
                      <div className="module-card-content">
                        <div className="module-stat">
                          <Thermometer size={14} />
                          <span className="stat-label">Temp:</span>
                          <span className="stat-values">
                            {modMinTemp !== null && modMaxTemp !== null 
                              ? `${modMinTemp.toFixed(1)}°C - ${modMaxTemp.toFixed(1)}°C`
                              : '--'}
                          </span>
                        </div>
                        <div className="module-stat">
                          <Zap size={14} />
                          <span className="stat-label">Voltage:</span>
                          <span className="stat-values">
                            {modMinVolt !== null && modMaxVolt !== null 
                              ? `${modMinVolt} / ${modAvgVolt} / ${modMaxVolt} mV`
                              : '--'}
                          </span>
                        </div>
                        {hasFault && (
                          <div className="module-stat fault">
                            <AlertTriangle size={14} />
                            <span className="stat-label">Faults:</span>
                            <span className="stat-values error">{modFaultCount}</span>
                          </div>
                        )}
                        
                        {/* Fault Flags List */}
                        {modErrorFlags.length > 0 && (
                          <div className="module-fault-flags">
                            {modErrorFlags.map((flag, idx) => (
                              <div key={idx} className={`mini-fault-flag flag-${flag.type}`}>
                                {flag.msg}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* CAN Statistics - Only for single module view */}
          {!isAllModulesView && canStats && (
            <div className="stats-section">
              <h3>CAN Bus Statistics</h3>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">RX Messages:</span>
                  <span className="stat-value">{canStats.RX_Message_Count?.value || 0}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">TX Success:</span>
                  <span className="stat-value">{canStats.TX_Success_Count?.value || 0}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">TX Errors:</span>
                  <span className="stat-value">{canStats.TX_Error_Count?.value || 0}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">RX Queue Full:</span>
                  <span className="stat-value">{canStats.RX_Queue_Full_Count?.value || 0}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Bus Off:</span>
                  <span className="stat-value">{canStats.Bus_Off_Count?.value || 0}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">TX Queue Full:</span>
                  <span className="stat-value">{canStats.TX_Queue_Full_Count?.value || 0}</span>
                </div>
              </div>
            </div>
          )}

          {/* I2C Diagnostics - Only for single module view */}
          {!isAllModulesView && i2cDiag && (
            <div className="stats-section">
              <h3>I2C Diagnostics</h3>
              <div className="i2c-grid">
                <div className="i2c-bus">
                  <h4>I2C1 (BMS1)</h4>
                  <div className="stat-row">
                    <span>Error:</span>
                    <span className="stat-value">{i2cDiag.I2C1_Error_Code?.value || 'NONE'}</span>
                  </div>
                  <div className="stat-row">
                    <span>State:</span>
                    <span className="stat-value">{i2cDiag.I2C1_State?.value || 'UNKNOWN'}</span>
                  </div>
                </div>
                <div className="i2c-bus">
                  <h4>I2C3 (BMS2)</h4>
                  <div className="stat-row">
                    <span>Error:</span>
                    <span className="stat-value">{i2cDiag.I2C3_Error_Code?.value || 'NONE'}</span>
                  </div>
                  <div className="stat-row">
                    <span>State:</span>
                    <span className="stat-value">{i2cDiag.I2C3_State?.value || 'UNKNOWN'}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Debug Info - Only for single module view */}
          {!isAllModulesView && debugInfo && (
            <div className="stats-section">
              <h3>System Debug</h3>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Free Heap:</span>
                  <span className="stat-value">{debugInfo.Free_Heap_KB?.value?.toFixed(2) || '--'} KB</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Min Free Heap:</span>
                  <span className="stat-value">{debugInfo.Min_Free_Heap_KB?.value?.toFixed(2) || '--'} KB</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">CPU Usage:</span>
                  <span className="stat-value">{debugInfo.CPU_Usage_Percent?.value || '--'}%</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Uptime:</span>
                  <span className="stat-value">{debugInfo.Uptime_Seconds?.value || '--'} s</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Firmware Flasher - Always show for individual module view */}
      {!isAllModulesView && (
        <FirmwareFlasher 
          moduleId={selectedModule} 
          disabled={!dbcFile}
        />
      )}
    </div>
  );
}

export default BMSStatus;
