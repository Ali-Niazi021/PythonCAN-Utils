const trimTrailingSlash = (url) => url.replace(/\/+$/, '');

const getBrowserOrigin = () => {
  if (window.location.origin && window.location.origin !== 'null') {
    return window.location.origin;
  }

  return `${window.location.protocol}//${window.location.host}`;
};

const deriveWebSocketUrl = (httpUrl) => {
  try {
    const url = new URL(httpUrl);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = '/api/ws/can';
    url.search = '';
    url.hash = '';
    return url.toString();
  } catch (error) {
    console.warn('[BackendURL] Failed to derive WebSocket URL from API URL:', error);
    return null;
  }
};

export const getApiBaseUrl = () => {
  if (process.env.REACT_APP_API_URL) {
    const configuredUrl = trimTrailingSlash(process.env.REACT_APP_API_URL);
    console.log('[API] Using environment variable API URL:', configuredUrl);
    return configuredUrl;
  }

  const url = getBrowserOrigin();
  console.log('[API] Using same-origin API URL:', url);
  return url;
};

export const getWebSocketUrl = () => {
  if (process.env.REACT_APP_WS_URL) {
    console.log('[WebSocket] Using environment variable WS URL:', process.env.REACT_APP_WS_URL);
    return process.env.REACT_APP_WS_URL;
  }

  if (process.env.REACT_APP_API_URL) {
    const derivedUrl = deriveWebSocketUrl(process.env.REACT_APP_API_URL);
    if (derivedUrl) {
      console.log('[WebSocket] Derived WebSocket URL from API URL:', derivedUrl);
      return derivedUrl;
    }
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/api/ws/can`;
  console.log('[WebSocket] Using same-origin WebSocket URL:', url);
  return url;
};