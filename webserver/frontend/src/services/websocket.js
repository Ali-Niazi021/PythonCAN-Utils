import { getWebSocketUrl } from './backendUrl';

const WS_URL = getWebSocketUrl();
console.log('[WebSocket] Final WebSocket URL:', WS_URL);

class WebSocketService {
  constructor() {
    this.ws = null;
    this.messageCallback = null;
    this.onOpenCallback = null;
    this.reconnectInterval = null;
    this.reconnectDelay = 3000;
    this.heartbeatTimeoutMs = 10000;
    this.lastMessageAt = 0;
    this.healthInterval = null;
    this.heartbeatInterval = null;
    this.shouldReconnect = true;
  }

  connect(onMessage, onOpen = null) {
    this.messageCallback = onMessage;
    this.onOpenCallback = onOpen;
    this.shouldReconnect = true;

    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.ws = new WebSocket(WS_URL);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.lastMessageAt = Date.now();
      if (this.reconnectInterval) {
        clearInterval(this.reconnectInterval);
        this.reconnectInterval = null;
      }

      if (this.healthInterval) {
        clearInterval(this.healthInterval);
      }

      if (this.heartbeatInterval) {
        clearInterval(this.heartbeatInterval);
      }

      this.heartbeatInterval = setInterval(() => {
        this.sendHeartbeat();
      }, 5000);

      this.healthInterval = setInterval(() => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
          return;
        }

        if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
          return;
        }

        if (Date.now() - this.lastMessageAt > this.heartbeatTimeoutMs) {
          console.warn('WebSocket heartbeat timeout, reconnecting...');
          this.ws.close();
        }
      }, 5000);

      if (this.onOpenCallback) {
        this.onOpenCallback();
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const messages = Array.isArray(payload) ? payload : [payload];
        this.lastMessageAt = Date.now();

        if (!this.messageCallback) {
          return;
        }

        for (const message of messages) {
          if (message.type !== 'heartbeat') {
            this.messageCallback(message);
          }
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
      if (this.healthInterval) {
        clearInterval(this.healthInterval);
        this.healthInterval = null;
      }

      if (this.heartbeatInterval) {
        clearInterval(this.heartbeatInterval);
        this.heartbeatInterval = null;
      }

      // Auto-reconnect
      if (this.shouldReconnect && !this.reconnectInterval) {
        this.reconnectInterval = setInterval(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            return;
          }
          console.log('Attempting to reconnect...');
          this.connect(this.messageCallback, this.onOpenCallback);
        }, this.reconnectDelay);
      }
    };
  }

  disconnect() {
    this.shouldReconnect = false;

    if (this.reconnectInterval) {
      clearInterval(this.reconnectInterval);
      this.reconnectInterval = null;
    }

    if (this.healthInterval) {
      clearInterval(this.healthInterval);
      this.healthInterval = null;
    }

    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.messageCallback = null;
    this.onOpenCallback = null;
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
