import React, { useMemo } from 'react';
import { Thermometer, TrendingUp, TrendingDown } from 'lucide-react';
import './ThermistorMonitor.css';

function ThermistorMonitor({ messages }) {
  // Extract thermistor data from CAN messages
  const thermistorData = useMemo(() => {
    const modules = Array(6).fill(null).map(() => Array(56).fill(null));
    
    messages.forEach(msg => {
      if (msg.decoded && msg.decoded.signals) {
        const signals = msg.decoded.signals;
        
        // Look for Temp_XXX signals
        Object.entries(signals).forEach(([key, signalData]) => {
          if (key.startsWith('Temp_')) {
            const tempNum = parseInt(key.split('_')[1]);
            const moduleId = Math.floor(tempNum / 56);
            const channel = tempNum % 56;
            
            if (moduleId >= 0 && moduleId < 6 && channel >= 0 && channel < 56) {
              // Extract numeric value from signal metadata object
              const value = typeof signalData === 'object' && signalData !== null 
                ? signalData.value 
                : signalData;
              modules[moduleId][channel] = typeof value === 'number' ? value : null;
            }
          }
        });
      }
    });
    
    return modules;
  }, [messages]);

  // Calculate statistics
  const stats = useMemo(() => {
    const allTemps = thermistorData.flat().filter(t => t !== null);
    
    if (allTemps.length === 0) {
      return { active: 0, min: null, max: null, avg: null };
    }
    
    return {
      active: allTemps.length,
      min: Math.min(...allTemps),
      max: Math.max(...allTemps),
      avg: allTemps.reduce((a, b) => a + b, 0) / allTemps.length
    };
  }, [thermistorData]);

  const getTempColor = (temp) => {
    if (temp === null) return '#2d3748';
    if (temp < 30) return '#8b5cf6';  // Purple
    if (temp < 40) return '#3b82f6';  // Blue
    if (temp < 50) return '#22c55e';  // Green
    if (temp < 60) return '#f59e0b';  // Orange
    return '#ef4444';  // Red
  };

  return (
    <div className="thermistor-monitor">
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <Thermometer size={20} />
            336-Channel Multi-Module Thermistor Monitor
          </div>
        </div>
        
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-label">Active:</span>
            <span className="stat-value">{stats.active}/336</span>
          </div>
          {stats.min !== null && (
            <>
              <div className="stat-item">
                <TrendingDown size={16} />
                <span className="stat-label">Min:</span>
                <span className="stat-value">{stats.min.toFixed(1)}°C</span>
              </div>
              <div className="stat-item">
                <TrendingUp size={16} />
                <span className="stat-label">Max:</span>
                <span className="stat-value">{stats.max.toFixed(1)}°C</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Avg:</span>
                <span className="stat-value">{stats.avg.toFixed(1)}°C</span>
              </div>
            </>
          )}
        </div>

        <div className="thermistor-grid-container">
          <div className="thermistor-grid">
            {thermistorData.map((module, moduleId) => (
              <div key={moduleId} className="module-column">
                <div className="module-header">Module {moduleId}</div>
                <div className="channel-list">
                  {module.map((temp, channel) => (
                    <div
                      key={channel}
                      className="thermistor-cell"
                      style={{ backgroundColor: getTempColor(temp) }}
                      title={`Module ${moduleId}, Channel ${channel}: ${temp !== null ? temp.toFixed(1) + '°C' : 'No data'}`}
                    >
                      <div className="channel-num">{channel}</div>
                      {temp !== null && (
                        <div className="temp-value">{temp.toFixed(1)}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="legend">
          <div className="legend-title">Temperature Scale:</div>
          <div className="legend-items">
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#8b5cf6' }}></div>
              <span>&lt; 30°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#3b82f6' }}></div>
              <span>30-40°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#22c55e' }}></div>
              <span>40-50°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#f59e0b' }}></div>
              <span>50-60°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{ backgroundColor: '#ef4444' }}></div>
              <span>&gt; 60°C</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ThermistorMonitor;
