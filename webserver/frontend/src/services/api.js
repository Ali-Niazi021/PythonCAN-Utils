import axios from 'axios';
import { getApiBaseUrl } from './backendUrl';

const API_BASE_URL = getApiBaseUrl();
console.log('[API] Final API base URL:', API_BASE_URL);

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

  async connect(deviceType, channel, baudrate, busId = null) {
    const response = await this.client.post('/connect', {
      bus_id: busId,
      device_type: deviceType,
      channel: channel,
      baudrate: baudrate,
    });
    return response.data;
  }

  async disconnect(busId = null) {
    const response = await this.client.post('/disconnect', busId ? { bus_id: busId } : undefined);
    return response.data;
  }

  async getStatus() {
    const response = await this.client.get('/status');
    return response.data;
  }

  async getHealth() {
    const response = await this.client.get('/health');
    return response.data;
  }

  async requestBackendShutdown() {
    const response = await this.client.post('/shutdown');
    return response.data;
  }

  getBaseUrl() {
    return this.client.defaults.baseURL;
  }

  async sendMessage(canId, data, isExtended = false, isRemote = false, busId = null) {
    const response = await this.client.post('/send', {
      bus_id: busId,
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

  async startSimulation() {
    const response = await this.client.post('/simulation/start');
    return response.data;
  }

  async stopSimulation() {
    const response = await this.client.post('/simulation/stop');
    return response.data;
  }

  async getSimulationStatus() {
    const response = await this.client.get('/simulation/status');
    return response.data;
  }

  async getHVCTestModeStatus() {
    const response = await this.client.get('/hvc/test_mode/status');
    return response.data;
  }

  async setHVCTestModeEnabled(enabled) {
    const response = await this.client.post('/hvc/test_mode/toggle', { enabled });
    return response.data;
  }

  async setHVCTestModeConfig(config) {
    const response = await this.client.post('/hvc/test_mode/config', {
      min_voltage_v: config.minVoltageV,
      max_voltage_v: config.maxVoltageV,
      min_temp_c: config.minTempC,
      max_temp_c: config.maxTempC,
      error_flags_byte0: config.errorFlagsByte0,
      error_flags_byte1: config.errorFlagsByte1,
      error_flags_byte2: config.errorFlagsByte2,
      error_flags_byte3: config.errorFlagsByte3,
      warning_summary: config.warningSummary,
      fault_count: config.faultCount,
    });
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

  async getDBCConfig() {
    const response = await this.client.get('/dbc/config');
    return response.data;
  }

  async listDBCFiles() {
    const response = await this.client.get('/dbc/list');
    return response.data;
  }

  async updateDBCConfig(files) {
    const response = await this.client.post('/dbc/config', {
      files: files.map(file => ({
        filename: file.filename,
        enabled: file.enabled,
      })),
    });
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

  async flashFirmware(formData, onUploadProgress) {
    const response = await this.client.post('/flash_firmware', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: onUploadProgress,
      timeout: 300000, // 5 minute timeout for flash operation
    });
    return response.data;
  }
}

export const apiService = new ApiService();
