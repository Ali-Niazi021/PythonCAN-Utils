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

  // Dynamic gradient for voltage: red (critical) -> orange (low) -> green (normal) -> yellow (high) -> pink (very high)
  // Range: 2.5V (red) -> 3.0V (orange) -> 3.3V (yellow-green) -> 3.7V (green/ideal) -> 4.2V (yellow) -> 4.3V+ (pink)
  const getVoltageColor = (voltage) => {
    if (voltage === null) return '#2d3748';
    
    // Clamp voltage to gradient range
    const minV = 2.5;
    const maxV = 4.35;
    const clampedV = Math.max(minV, Math.min(maxV, voltage));
    
    // Normalize to 0-1 range
    const t = (clampedV - minV) / (maxV - minV);
    
    // Color stops for Li-ion voltage range
    // 2.5V (0) -> 3.0V (0.27) -> 3.3V (0.43) -> 3.7V (0.65) -> 4.2V (0.92) -> 4.35V (1)
    const colors = [
      { pos: 0,    r: 239, g: 68,  b: 68  }, // Red (#ef4444) - critical low
      { pos: 0.27, r: 249, g: 115, b: 22  }, // Orange (#f97316) - very low
      { pos: 0.43, r: 250, g: 204, b: 21  }, // Yellow (#facc15) - low
      { pos: 0.65, r: 34,  g: 197, b: 94  }, // Green (#22c55e) - ideal/normal
      { pos: 0.92, r: 59,  g: 130, b: 246 }, // Blue (#3b82f6) - high
      { pos: 1,    r: 168, g: 85,  b: 247 }  // Purple (#a855f7) - very high
    ];
    
    // Find the two colors to interpolate between
    let lower = colors[0];
    let upper = colors[colors.length - 1];
    
    for (let i = 0; i < colors.length - 1; i++) {
      if (t >= colors[i].pos && t <= colors[i + 1].pos) {
        lower = colors[i];
        upper = colors[i + 1];
        break;
      }
    }
    
    // Interpolate between the two colors
    const range = upper.pos - lower.pos;
    const localT = range > 0 ? (t - lower.pos) / range : 0;
    
    const r = Math.round(lower.r + (upper.r - lower.r) * localT);
    const g = Math.round(lower.g + (upper.g - lower.g) * localT);
    const b = Math.round(lower.b + (upper.b - lower.b) * localT);
    
    return `rgb(${r}, ${g}, ${b})`;
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
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-label">Active:</span>
            <span className="stat-value">{stats.active}/108</span>
          </div>
          {cellData.stackVoltage !== null && (
            <div className="stat-item highlight">
              <Zap size={16} />
              <span className="stat-label">Stack:</span>
              <span className="stat-value">{cellData.stackVoltage.toFixed(2)} V</span>
            </div>
          )}
          {stats.min !== null && (
            <>
              <div className="stat-item">
                <TrendingDown size={16} />
                <span className="stat-label">Min:</span>
                <span className="stat-value">{stats.min.toFixed(3)} V</span>
              </div>
              <div className="stat-item">
                <TrendingUp size={16} />
                <span className="stat-label">Max:</span>
                <span className="stat-value">{stats.max.toFixed(3)} V</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Avg:</span>
                <span className="stat-value">{stats.avg.toFixed(3)} V</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Δ:</span>
                <span className="stat-value">{(stats.delta * 1000).toFixed(1)} mV</span>
              </div>
            </>
          )}
        </div>

        <div className="voltage-grid-container">
          <div className="voltage-grid">
            {cellData.modules.map((module, moduleId) => (
              <div key={moduleId} className="module-column">
                <div className="module-header">Module {moduleId}</div>
                <div className="cell-rows">
                  {module.map((voltage, cellIdx) => (
                    <div
                      key={cellIdx}
                      className="voltage-row"
                      style={{ borderLeftColor: getVoltageColor(voltage) }}
                    >
                      <span className="cell-label">C{cellIdx}</span>
                      <span
                        className="voltage-chip"
                        style={{ backgroundColor: getVoltageColor(voltage) }}
                        title={`Module ${moduleId}, Cell ${cellIdx}: ${voltage !== null ? voltage.toFixed(4) + ' V - ' + getCellStatus(voltage) : 'No data'}`}
                      >
                        {voltage !== null ? voltage.toFixed(3) : '--'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default CellVoltageMonitor;
