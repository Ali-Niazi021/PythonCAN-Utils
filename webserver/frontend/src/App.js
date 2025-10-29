import React, { useState, useEffect, useCallback } from 'react';
import './App.css';
import Header from './components/Header';
import ConnectionPanel from './components/ConnectionPanel';
import CANExplorer from './components/CANExplorer';
import ThermistorMonitor from './components/ThermistorMonitor';
import CellVoltageMonitor from './components/CellVoltageMonitor';
import BMSStatus from './components/BMSStatus';
import StatusBar from './components/StatusBar';
import { apiService } from './services/api';
import { websocketService } from './services/websocket';

function App() {
  const [activeTab, setActiveTab] = useState('explorer');
  const [connected, setConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState({
    device_type: null,
    channel: null,
    baudrate: null,
    status: 'Disconnected'
  });
  const [devices, setDevices] = useState([]);
  const [messages, setMessages] = useState([]);
  const [stats, setStats] = useState({
    message_count: 0,
    uptime_seconds: 0,
    message_rate: 0
  });
  const [dbcLoaded, setDbcLoaded] = useState(false);
  const [dbcFile, setDbcFile] = useState(null);

  // Fetch available devices on mount
  useEffect(() => {
    fetchDevices();
    checkConnectionStatus();
    checkDBCStatus();
  }, []);

  const fetchDevices = async () => {
    try {
      const data = await apiService.getDevices();
      setDevices(data.devices || []);
    } catch (error) {
      console.error('Failed to fetch devices:', error);
    }
  };

  const checkConnectionStatus = async () => {
    try {
      const status = await apiService.getStatus();
      setConnected(status.connected);
      setConnectionStatus(status);
      
      if (status.connected && !websocketService.isConnected()) {
        connectWebSocket();
      }
    } catch (error) {
      console.error('Failed to check status:', error);
    }
  };

  const checkDBCStatus = async () => {
    try {
      const dbcStatus = await apiService.getCurrentDBC();
      if (dbcStatus.loaded) {
        setDbcLoaded(true);
        setDbcFile(dbcStatus.filename);
      }
    } catch (error) {
      console.error('Failed to check DBC status:', error);
    }
  };

  const connectWebSocket = useCallback(() => {
    websocketService.connect((message) => {
      // Handle incoming CAN message
      setMessages(prev => [...prev, message]);
    });
  }, []);

  const handleConnect = async (deviceType, channel, baudrate) => {
    console.log('handleConnect called with:', { deviceType, channel, baudrate });
    try {
      console.log('Calling API connect...');
      const response = await apiService.connect(deviceType, channel, baudrate);
      console.log('API response:', response);
      
      if (response.success) {
        setConnected(true);
        setConnectionStatus({
          device_type: deviceType,
          channel: channel,
          baudrate: baudrate,
          status: 'Connected'
        });
        connectWebSocket();
        console.log('Connected successfully!');
        return true;
      }
      console.warn('Connection failed:', response);
      return false;
    } catch (error) {
      console.error('Connection failed:', error);
      alert('Failed to connect: ' + (error.response?.data?.detail || error.message));
      return false;
    }
  };

  const handleDisconnect = async () => {
    try {
      await apiService.disconnect();
      websocketService.disconnect();
      setConnected(false);
      setConnectionStatus({
        device_type: null,
        channel: null,
        baudrate: null,
        status: 'Disconnected'
      });
      // Don't clear messages on disconnect - they persist until manually cleared
      return true;
    } catch (error) {
      console.error('Disconnect failed:', error);
      return false;
    }
  };

  const handleSendMessage = async (canId, data, isExtended, isRemote) => {
    try {
      await apiService.sendMessage(canId, data, isExtended, isRemote);
      return true;
    } catch (error) {
      console.error('Send failed:', error);
      return false;
    }
  };

  const handleLoadDBC = async (file) => {
    try {
      const response = await apiService.uploadDBC(file);
      if (response.success) {
        setDbcLoaded(true);
        setDbcFile(file.name);
        alert(`DBC file uploaded successfully!\n${response.message}`);
        return true;
      }
      return false;
    } catch (error) {
      console.error('DBC upload failed:', error);
      alert('Failed to upload DBC file: ' + (error.response?.data?.detail || error.message));
      return false;
    }
  };

  // Update stats periodically
  useEffect(() => {
    if (!connected) return;

    const interval = setInterval(async () => {
      try {
        const statsData = await apiService.getStats();
        setStats(statsData);
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [connected]);

  return (
    <div className="App">
      <div className="tab-content">
        {activeTab === 'explorer' && (
          <CANExplorer
            connected={connected}
            messages={messages}
            onClearMessages={() => setMessages([])}
            onSendMessage={handleSendMessage}
            onLoadDBC={handleLoadDBC}
            dbcLoaded={dbcLoaded}
            dbcFile={dbcFile}
            devices={devices}
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
            onRefreshDevices={fetchDevices}
            connectionStatus={connectionStatus}
            stats={stats}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          />
        )}
        {activeTab === 'bms-status' && (
          <CANExplorer
            connected={connected}
            messages={messages}
            onClearMessages={() => setMessages([])}
            onSendMessage={handleSendMessage}
            onLoadDBC={handleLoadDBC}
            dbcLoaded={dbcLoaded}
            dbcFile={dbcFile}
            devices={devices}
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
            onRefreshDevices={fetchDevices}
            connectionStatus={connectionStatus}
            stats={stats}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          >
            <BMSStatus 
              messages={messages} 
              onSendMessage={handleSendMessage}
              dbcFile={dbcFile}
            />
          </CANExplorer>
        )}
        {activeTab === 'thermistor' && (
          <CANExplorer
            connected={connected}
            messages={messages}
            onClearMessages={() => setMessages([])}
            onSendMessage={handleSendMessage}
            onLoadDBC={handleLoadDBC}
            dbcLoaded={dbcLoaded}
            dbcFile={dbcFile}
            devices={devices}
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
            onRefreshDevices={fetchDevices}
            connectionStatus={connectionStatus}
            stats={stats}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          >
            <ThermistorMonitor messages={messages} />
          </CANExplorer>
        )}
        {activeTab === 'voltage' && (
          <CANExplorer
            connected={connected}
            messages={messages}
            onClearMessages={() => setMessages([])}
            onSendMessage={handleSendMessage}
            onLoadDBC={handleLoadDBC}
            dbcLoaded={dbcLoaded}
            dbcFile={dbcFile}
            devices={devices}
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
            onRefreshDevices={fetchDevices}
            connectionStatus={connectionStatus}
            stats={stats}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          >
            <CellVoltageMonitor messages={messages} />
          </CANExplorer>
        )}
      </div>
    </div>
  );
}

export default App;
