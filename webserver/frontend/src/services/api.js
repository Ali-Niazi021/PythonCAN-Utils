import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

class ApiService {
  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  async getDevices() {
    const response = await this.client.get('/devices');
    return response.data;
  }

  async connect(deviceType, channel, baudrate) {
    const response = await this.client.post('/connect', {
      device_type: deviceType,
      channel: channel,
      baudrate: baudrate,
    });
    return response.data;
  }

  async disconnect() {
    const response = await this.client.post('/disconnect');
    return response.data;
  }

  async getStatus() {
    const response = await this.client.get('/status');
    return response.data;
  }

  async sendMessage(canId, data, isExtended = false, isRemote = false) {
    const response = await this.client.post('/send', {
      can_id: canId,
      data: data,
      is_extended: isExtended,
      is_remote: isRemote,
    });
    return response.data;
  }

  async getStats() {
    const response = await this.client.get('/stats');
    return response.data;
  }

  async uploadDBC(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await this.client.post('/dbc/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  }

  async getCurrentDBC() {
    const response = await this.client.get('/dbc/current');
    return response.data;
  }

  async listDBCFiles() {
    const response = await this.client.get('/dbc/list');
    return response.data;
  }

  async deleteDBC(filename) {
    const response = await this.client.delete(`/dbc/delete/${filename}`);
    return response.data;
  }

  async loadDBC(filePath) {
    const response = await this.client.post('/dbc/load', {
      file_path: filePath,
    });
    return response.data;
  }

  async getDBCMessages() {
    const response = await this.client.get('/dbc/messages');
    return response.data;
  }

  async saveTransmitList(items, dbcFile) {
    const response = await this.client.post('/transmit_list/save', {
      items: items,
      dbc_file: dbcFile,
    });
    return response.data;
  }

  async loadTransmitList(dbcFile) {
    const response = await this.client.get('/transmit_list/load', {
      params: { dbc_file: dbcFile },
    });
    return response.data;
  }

  async encodeMessage(messageName, signals) {
    const response = await this.client.post('/dbc/encode_message', null, {
      params: { 
        message_name: messageName,
        signals: JSON.stringify(signals)
      },
    });
    return response.data;
  }
}

export const apiService = new ApiService();
