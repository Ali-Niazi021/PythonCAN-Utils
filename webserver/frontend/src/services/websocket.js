// Dynamically determine WebSocket URL
// If REACT_APP_WS_URL is set, use it (for custom deployments)
// Otherwise, use the current host (works for localhost and remote access)
const getWebSocketUrl = () => {
  if (process.env.REACT_APP_WS_URL) {
    console.log('[WebSocket] Using environment variable WS URL:', process.env.REACT_APP_WS_URL);
    return process.env.REACT_APP_WS_URL;
  }
  
  // Use current window location to build WebSocket URL
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname; // e.g., localhost or 192.168.1.100
  const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
  
  console.log('[WebSocket] Current location:', { protocol, host, port });
  
  // If running on dev server (port 3000, 3001, etc.), API is on 8000
  // If running on production (served from backend), use same port
  const apiPort = (port.startsWith('3') || port === '5173') ? '8000' : port;
  
  const url = `${protocol}//${host}:${apiPort}/ws/can`;
  console.log('[WebSocket] Constructed WebSocket URL:', url);
  return url;
};

const WS_URL = getWebSocketUrl();
console.log('[WebSocket] Final WebSocket URL:', WS_URL);

class WebSocketService {
  constructor() {
    this.ws = null;
    this.messageCallback = null;
    this.reconnectInterval = null;
    this.reconnectDelay = 3000;
  }

  connect(onMessage) {
    this.messageCallback = onMessage;
    this.ws = new WebSocket(WS_URL);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      if (this.reconnectInterval) {
        clearInterval(this.reconnectInterval);
        this.reconnectInterval = null;
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type !== 'heartbeat' && this.messageCallback) {
          this.messageCallback(message);
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      // Auto-reconnect
      if (!this.reconnectInterval) {
        this.reconnectInterval = setInterval(() => {
          console.log('Attempting to reconnect...');
          this.connect(this.messageCallback);
        }, this.reconnectDelay);
      }
    };
  }

  disconnect() {
    if (this.reconnectInterval) {
      clearInterval(this.reconnectInterval);
      this.reconnectInterval = null;
    }
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.messageCallback = null;
  }

  sendHeartbeat() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send('heartbeat');
    }
  }

  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}

export const websocketService = new WebSocketService();
