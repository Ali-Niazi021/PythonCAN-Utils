import React, { useMemo } from 'react';
import { Battery, TrendingUp, TrendingDown, Zap } from 'lucide-react';
import './CellVoltageMonitor.css';

function CellVoltageMonitor({ messages }) {
  // Extract cell voltage data from CAN messages
  const cellData = useMemo(() => {
    const modules = Array(6).fill(null).map(() => Array(18).fill(null));
    let stackVoltage = null;
    
    messages.forEach(msg => {
      if (msg.decoded && msg.decoded.signals) {
        const signals = msg.decoded.signals;
        
        // Look for Cell_X_Voltage signals
        Object.entries(signals).forEach(([key, signalData]) => {
          // Extract numeric value from signal metadata object
          const value = typeof signalData === 'object' && signalData !== null 
            ? signalData.value 
            : signalData;
          
          // Match Cell_X_Voltage pattern
          const cellMatch = key.match(/Cell_(\d+)_Voltage/);
          if (cellMatch) {
            const cellNum = parseInt(cellMatch[1]) - 1; // 0-indexed
            const moduleId = Math.floor(cellNum / 18);
            const cellIdx = cellNum % 18;
            
            if (moduleId >= 0 && moduleId < 6 && cellIdx >= 0 && cellIdx < 18 && typeof value === 'number') {
              // Convert to volts if needed (assume mV if > 100)
              const voltage = value > 100 ? value / 1000 : value;
              modules[moduleId][cellIdx] = voltage;
            }
          }
          
          // Look for stack voltage
          if (key.toLowerCase().includes('stack') && key.toLowerCase().includes('voltage') && typeof value === 'number') {
            stackVoltage = value > 1000 ? value / 1000 : value;
          }
        });
      }
    });
    
    return { modules, stackVoltage };
  }, [messages]);

  // Calculate statistics
  const stats = useMemo(() => {
    const allVoltages = cellData.modules.flat().filter(v => v !== null);
    
    if (allVoltages.length === 0) {
      return { active: 0, min: null, max: null, avg: null, delta: null };
    }
    
    const min = Math.min(...allVoltages);
    const max = Math.max(...allVoltages);
    const avg = allVoltages.reduce((a, b) => a + b, 0) / allVoltages.length;
    const delta = max - min;
    
    return { active: allVoltages.length, min, max, avg, delta };
  }, [cellData]);

  const getVoltageColor = (voltage) => {
    if (voltage === null) return '#2d3748';
    if (voltage < 2.5) return '#f56565'; // Critical low
    if (voltage < 3.0) return '#fc8181'; // Very low
    if (voltage < 3.3) return '#ed8936'; // Low
    if (voltage < 4.2) return '#48bb78'; // Normal
    if (voltage < 4.3) return '#ecc94b'; // High
    return '#f687b3'; // Very high
  };

  const getCellStatus = (voltage) => {
    if (voltage === null) return 'No Data';
    if (voltage < 2.5) return 'Critical';
    if (voltage < 3.0) return 'Very Low';
    if (voltage < 3.3) return 'Low';
    if (voltage < 4.2) return 'Normal';
    if (voltage < 4.3) return 'High';
    return 'Very High';
  };

  return (
    <div className="cell-voltage-monitor">
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <Battery size={20} />
            108-Cell Multi-Module Battery Voltage Monitor
          </div>
        </div>
        
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-label">Active:</span>
            <span className="stat-value">{stats.active}/108</span>
          </div>
          {cellData.stackVoltage !== null && (
            <div className="stat-item highlight">
              <Zap size={16} />
              <span className="stat-label">Stack:</span>
              <span className="stat-value">{cellData.stackVoltage.toFixed(3)} V</span>
            </div>
          )}
          {stats.min !== null && (
            <>
              <div className="stat-item">
                <TrendingDown size={16} />
                <span className="stat-label">Min:</span>
                <span className="stat-value">{stats.min.toFixed(4)} V</span>
              </div>
              <div className="stat-item">
                <TrendingUp size={16} />
                <span className="stat-label">Max:</span>
                <span className="stat-value">{stats.max.toFixed(4)} V</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Avg:</span>
                <span className="stat-value">{stats.avg.toFixed(4)} V</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Delta:</span>
                <span className="stat-value">{stats.delta.toFixed(4)} V</span>
              </div>
            </>
          )}
        </div>

        <div className="voltage-grid-container">
          <div className="voltage-grid">
            {cellData.modules.map((module, moduleId) => (
              <div key={moduleId} className="module-column">
                <div className="module-header">Module {moduleId}</div>
                <div className="cell-list">
                  {module.map((voltage, cellIdx) => (
                    <div
                      key={cellIdx}
                      className="voltage-cell"
                      style={{ backgroundColor: getVoltageColor(voltage) }}
                      title={`Module ${moduleId}, Cell ${cellIdx}: ${voltage !== null ? voltage.toFixed(4) + ' V - ' + getCellStatus(voltage) : 'No data'}`}
                    >
                      <div className="cell-num">C{cellIdx}</div>
                      {voltage !== null && (
                        <div className="voltage-value">{voltage.toFixed(3)}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="legend">
          <div className="legend-title">Voltage Scale:</div>
          <div className="legend-items">
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#f56565' }}></div>
              <span>&lt; 2.5V (Critical)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#fc8181' }}></div>
              <span>2.5-3.0V (Very Low)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#ed8936' }}></div>
              <span>3.0-3.3V (Low)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#48bb78' }}></div>
              <span>3.3-4.2V (Normal)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#ecc94b' }}></div>
              <span>4.2-4.3V (High)</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#f687b3' }}></div>
              <span>&gt; 4.3V (Very High)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CellVoltageMonitor;
