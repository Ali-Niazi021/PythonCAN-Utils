import React, { useState, useEffect } from 'react';
import { Send, Plus, Trash2, Edit2 } from 'lucide-react';
import { apiService } from '../services/api';
import './TransmitList.css';

function TransmitList({ dbcFile, onSendMessage }) {
  const [transmitItems, setTransmitItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [dbcMessages, setDbcMessages] = useState([]);
  const [editingItem, setEditingItem] = useState(null);

  // Load transmit list when DBC file changes
  useEffect(() => {
    if (dbcFile) {
      loadTransmitList();
      loadDBCMessages();
    }
  }, [dbcFile]);

  // Load DBC messages for picker
  const loadDBCMessages = async () => {
    try {
      console.log('Loading DBC messages...');
      const response = await apiService.getDBCMessages();
      console.log('DBC messages response:', response);
      if (response.success && response.messages) {
        console.log(`Loaded ${response.messages.length} messages`);
        setDbcMessages(response.messages);
      } else {
        console.error('Invalid response format:', response);
      }
    } catch (error) {
      console.error('Failed to load DBC messages:', error);
      console.error('Error details:', error.response?.data);
    }
  };

  // Load transmit list from backend
  const loadTransmitList = async () => {
    try {
      const response = await apiService.loadTransmitList(dbcFile);
      if (response.success) {
        setTransmitItems(response.items || []);
      }
    } catch (error) {
      console.error('Failed to load transmit list:', error);
    }
  };

  // Save transmit list to backend
  const saveTransmitList = async (items) => {
    try {
      await apiService.saveTransmitList(items, dbcFile);
    } catch (error) {
      console.error('Failed to save transmit list:', error);
    }
  };

  // Handle keyboard events
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.code === 'Space' && selectedId && !showAddDialog) {
        e.preventDefault();
        const item = transmitItems.find(i => i.id === selectedId);
        if (item) {
          handleSendItem(item);
        }
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [selectedId, transmitItems, showAddDialog]);

  // Send a transmit item
  const handleSendItem = async (item) => {
    try {
      await onSendMessage(item.can_id, item.data, item.is_extended, false);
      console.log(`Sent message: ${item.message_name || `0x${item.can_id.toString(16)}`}`);
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  // Add new item to transmit list
  const handleAddItem = (item) => {
    const newItems = [...transmitItems, item];
    setTransmitItems(newItems);
    saveTransmitList(newItems);
    setShowAddDialog(false);
  };

  // Remove item from transmit list
  const handleRemoveItem = (id) => {
    const newItems = transmitItems.filter(i => i.id !== id);
    setTransmitItems(newItems);
    saveTransmitList(newItems);
    if (selectedId === id) {
      setSelectedId(null);
    }
  };

  return (
    <div className="transmit-list">
      <div className="transmit-list-header">
        <h4>Transmit List</h4>
        <button className="btn btn-sm btn-primary" onClick={() => setShowAddDialog(true)}>
          <Plus size={16} />
          Add Message
        </button>
      </div>

      {transmitItems.length === 0 ? (
        <div className="transmit-list-empty">
          No transmit messages defined. Click "Add Message" to get started.
        </div>
      ) : (
        <div className="transmit-list-items">
          {transmitItems.map(item => (
            <div
              key={item.id}
              className={`transmit-item ${selectedId === item.id ? 'selected' : ''}`}
              onClick={() => setSelectedId(item.id)}
            >
              <div className="transmit-item-info">
                <div className="transmit-item-name">
                  {item.message_name || `Custom 0x${item.can_id.toString(16).toUpperCase()}`}
                </div>
                <div className="transmit-item-id">
                  ID: 0x{item.can_id.toString(16).toUpperCase().padStart(3, '0')}
                  {item.is_extended && ' (Ext)'}
                </div>
                <div className="transmit-item-data">
                  Data: {item.data.map(b => b.toString(16).toUpperCase().padStart(2, '0')).join(' ')}
                </div>
                {item.description && (
                  <div className="transmit-item-desc">{item.description}</div>
                )}
              </div>
              <div className="transmit-item-actions">
                <button
                  className="btn btn-icon btn-sm btn-success"
                  onClick={(e) => { e.stopPropagation(); handleSendItem(item); }}
                  title="Send (or press Space when selected)"
                >
                  <Send size={16} />
                </button>
                <button
                  className="btn btn-icon btn-sm btn-danger"
                  onClick={(e) => { e.stopPropagation(); handleRemoveItem(item.id); }}
                  title="Remove"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showAddDialog && (
        <AddTransmitDialog
          dbcMessages={dbcMessages}
          onAdd={handleAddItem}
          onCancel={() => setShowAddDialog(false)}
        />
      )}

      <div className="transmit-list-hint">
        💡 Tip: Select a message and press Spacebar to send it
      </div>
    </div>
  );
}

// Dialog for adding a new transmit message
function AddTransmitDialog({ dbcMessages, onAdd, onCancel }) {
  const [mode, setMode] = useState('dbc'); // 'dbc' or 'custom'
  const [selectedMessage, setSelectedMessage] = useState('');
  const [customId, setCustomId] = useState('123');
  const [customData, setCustomData] = useState('00 00 00 00 00 00 00 00');
  const [dbcData, setDbcData] = useState('00 00 00 00 00 00 00 00');
  const [isExtended, setIsExtended] = useState(false);
  const [description, setDescription] = useState('');
  const [signalValues, setSignalValues] = useState({});
  const [editMode, setEditMode] = useState('signals'); // 'signals' or 'raw'

  const selectedDbcMessage = dbcMessages.find(m => m.name === selectedMessage);

  // Update dbcData when a DBC message is selected
  useEffect(() => {
    if (selectedDbcMessage) {
      const length = selectedDbcMessage.length || 8;
      const zeros = Array(length).fill(0).map(b => '00').join(' ');
      setDbcData(zeros);
      
      // Initialize signal values to 0
      const initialSignals = {};
      if (selectedDbcMessage.signals) {
        selectedDbcMessage.signals.forEach(sig => {
          initialSignals[sig.name] = 0;
        });
      }
      setSignalValues(initialSignals);
    }
  }, [selectedDbcMessage]);

  // Encode signal values to data bytes
  const encodeSignals = async () => {
    if (!selectedDbcMessage) return null;
    
    try {
      const response = await apiService.encodeMessage(selectedDbcMessage.name, signalValues);
      if (response.success) {
        const hexData = response.data.map(b => b.toString(16).toUpperCase().padStart(2, '0')).join(' ');
        setDbcData(hexData);
        return response; // Return the full response so we can get can_id and is_extended
      }
    } catch (error) {
      console.error('Failed to encode signals:', error);
      alert('Failed to encode signals. Using raw bytes instead.');
    }
    return null;
  };

  const handleSignalChange = (signalName, value) => {
    setSignalValues(prev => ({
      ...prev,
      [signalName]: parseFloat(value) || 0
    }));
  };

  const handleAdd = async () => {
    let item;
    
    if (mode === 'dbc' && selectedDbcMessage) {
      let encodedResponse = null;
      
      // If in signals mode, encode signals first
      if (editMode === 'signals') {
        encodedResponse = await encodeSignals();
      }
      
      // Create message from DBC with manual data bytes
      const dataBytes = dbcData.split(/\s+/).map(b => parseInt(b, 16));
      
      if (dataBytes.some(b => isNaN(b) || b < 0 || b > 255)) {
        alert('Invalid data bytes. Use hex values (00-FF).');
        return;
      }
      
      // Use the encoded response if available, otherwise fall back to selectedDbcMessage
      const canId = encodedResponse ? encodedResponse.can_id : selectedDbcMessage.frame_id;
      const isExt = encodedResponse ? encodedResponse.is_extended : selectedDbcMessage.is_extended;
      
      item = {
        id: `${Date.now()}-${Math.random()}`,
        can_id: canId,
        data: dataBytes,
        is_extended: isExt,
        message_name: selectedDbcMessage.name,
        signals: editMode === 'signals' ? signalValues : null,
        description: description || `DBC: ${selectedDbcMessage.name}`
      };
    } else {
      // Custom message
      const id = parseInt(customId, 16);
      const dataBytes = customData.split(/\s+/).map(b => parseInt(b, 16));
      
      if (isNaN(id) || dataBytes.some(b => isNaN(b) || b < 0 || b > 255)) {
        alert('Invalid ID or data. Use hex values.');
        return;
      }
      
      item = {
        id: `${Date.now()}-${Math.random()}`,
        can_id: id,
        data: dataBytes,
        is_extended: isExtended,
        message_name: null,
        signals: null,
        description: description || `Custom message 0x${id.toString(16)}`
      };
    }
    
    onAdd(item);
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Transmit Message</h3>
        </div>
        
        <div className="modal-body">
          <div className="form-group">
            <label>Message Type</label>
            <div className="button-group">
              <button
                className={`btn ${mode === 'dbc' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setMode('dbc')}
              >
                From DBC File
              </button>
              <button
                className={`btn ${mode === 'custom' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setMode('custom')}
              >
                Custom Message
              </button>
            </div>
          </div>

          {mode === 'dbc' ? (
            <>
              <div className="form-group">
                <label>Select Message</label>
                <select
                  value={selectedMessage}
                  onChange={(e) => setSelectedMessage(e.target.value)}
                  className="form-control"
                >
                  <option value="">Choose a message...</option>
                  {dbcMessages.map(msg => (
                    <option key={msg.name} value={msg.name}>
                      {msg.name} (0x{msg.frame_id.toString(16).toUpperCase()})
                    </option>
                  ))}
                </select>
              </div>

              {selectedDbcMessage && (
                <>
                  <div className="message-info">
                    <p><strong>ID:</strong> 0x{selectedDbcMessage.frame_id.toString(16).toUpperCase()}</p>
                    <p><strong>Length:</strong> {selectedDbcMessage.length} bytes</p>
                    <p><strong>Signals:</strong> {selectedDbcMessage.signal_count}</p>
                  </div>

                  {/* Toggle between signal editing and raw bytes */}
                  <div className="form-group">
                    <label>Edit Mode</label>
                    <div className="button-group">
                      <button
                        className={`btn ${editMode === 'signals' ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setEditMode('signals')}
                      >
                        Edit Signals
                      </button>
                      <button
                        className={`btn ${editMode === 'raw' ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setEditMode('raw')}
                      >
                        Edit Raw Bytes
                      </button>
                    </div>
                  </div>

                  {editMode === 'signals' ? (
                    <>
                      {selectedDbcMessage.signals && selectedDbcMessage.signals.length > 0 ? (
                        <div className="signals-editor">
                          <label style={{ marginBottom: '10px', display: 'block' }}>Signal Values</label>
                          <div className="signals-list">
                            {selectedDbcMessage.signals.map(signal => {
                              // Check if signal has choices (enumerated values)
                              const hasChoices = signal.choices && Object.keys(signal.choices).length > 0;
                              
                              return (
                                <div key={signal.name} className="signal-input-row">
                                  <label className="signal-label">
                                    <span>{signal.name}</span>
                                    {signal.unit && <span className="signal-unit">{signal.unit}</span>}
                                  </label>
                                  
                                  {hasChoices ? (
                                    // Dropdown for enumerated signals
                                    <select
                                      value={signalValues[signal.name] || 0}
                                      onChange={(e) => handleSignalChange(signal.name, e.target.value)}
                                      className="signal-select"
                                    >
                                      {Object.entries(signal.choices).map(([value, label]) => (
                                        <option key={value} value={value}>
                                          {label} ({value})
                                        </option>
                                      ))}
                                    </select>
                                  ) : (
                                    // Number input for numeric signals
                                    <input
                                      type="number"
                                      value={signalValues[signal.name] || 0}
                                      onChange={(e) => handleSignalChange(signal.name, e.target.value)}
                                      step="any"
                                      className="signal-input"
                                      title={`Min: ${signal.minimum || 'N/A'}, Max: ${signal.maximum || 'N/A'}`}
                                      placeholder="0"
                                    />
                                  )}
                                </div>
                              );
                            })}
                          </div>
                          <button
                            className="btn btn-secondary btn-block"
                            onClick={encodeSignals}
                            style={{ marginTop: '10px' }}
                          >
                            Preview Encoded Bytes
                          </button>
                        </div>
                      ) : (
                        <p style={{ color: '#999', fontSize: '13px', textAlign: 'center', padding: '20px' }}>
                          No signals defined for this message
                        </p>
                      )}
                    </>
                  ) : null}

                  {/* Show raw bytes input (always visible or when in raw mode) */}
                  {(editMode === 'raw' || editMode === 'signals') && (
                    <div className="form-group">
                      <label>Data Bytes (Hex) {editMode === 'signals' && '(Preview)'}</label>
                      <input
                        type="text"
                        value={dbcData}
                        onChange={(e) => setDbcData(e.target.value)}
                        placeholder="00 00 00 00 00 00 00 00"
                        className="form-control"
                        readOnly={editMode === 'signals'}
                      />
                      {editMode === 'raw' && (
                        <small style={{ color: '#999', fontSize: '11px', marginTop: '4px', display: 'block' }}>
                          Edit the data bytes directly (space-separated hex values)
                        </small>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          ) : (
            <>
              <div className="form-group">
                <label>CAN ID (Hex)</label>
                <input
                  type="text"
                  value={customId}
                  onChange={(e) => setCustomId(e.target.value)}
                  placeholder="123"
                  className="form-control"
                />
              </div>

              <div className="form-group">
                <label>Data (Hex bytes)</label>
                <input
                  type="text"
                  value={customData}
                  onChange={(e) => setCustomData(e.target.value)}
                  placeholder="00 00 00 00 00 00 00 00"
                  className="form-control"
                />
              </div>

              <div className="form-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={isExtended}
                    onChange={(e) => setIsExtended(e.target.checked)}
                  />
                  Extended ID (29-bit)
                </label>
              </div>
            </>
          )}

          <div className="form-group">
            <label>Description (Optional)</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description..."
              className="form-control"
            />
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleAdd}
            disabled={mode === 'dbc' && !selectedMessage}
          >
            Add to List
          </button>
        </div>
      </div>
    </div>
  );
}

export default TransmitList;
