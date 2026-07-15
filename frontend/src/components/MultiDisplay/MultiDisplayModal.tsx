import React, { useEffect, useRef, useState } from 'react';
import { useMultiDisplayModalUI } from '@/stores/uiStore';
import { useMultiDisplaySession, useSessionPeerCount } from '@/stores/sessionStore';
import { connectSocket, disconnectSocket, joinRoom, updatePeerPresence } from '@/services/yjsService';
import { PeerLayoutEditor } from './PeerLayoutEditor';
import type { Peer } from '@/types/session';

export const MultiDisplayModal: React.FC = () => {
  const { isMultiDisplayModalOpen, setMultiDisplayModalOpen } = useMultiDisplayModalUI();
  const {
    serverUrl, roomId, isConnected, localPeer, peers,
    setServerUrl, setRoomId, setLocalPeerConfig, setIdentifying
  } = useMultiDisplaySession();

  // Force re-render when peer count changes (workaround for Map reactivity)
  void useSessionPeerCount();
  

  const [tagsInput, setTagsInput] = useState(localPeer.tags.join(', '));
  const backdropRef = useRef<HTMLDivElement>(null);

  // Sync tags input if localPeer.tags change externally
  useEffect(() => {
    setTagsInput((prev) => {
      const parsed = prev.split(',').map((t) => t.trim()).filter(Boolean);
      const isMatch = parsed.length === localPeer.tags.length &&
                      parsed.every((val, index) => val === localPeer.tags[index]);
      if (isMatch) return prev;
      return localPeer.tags.join(', ');
    });
  }, [localPeer.tags]);

  // Auto-populate viewport size when modal opens (works whether connected or not)
  useEffect(() => {
    if (isMultiDisplayModalOpen) {
      setLocalPeerConfig(localPeer.x, localPeer.y, localPeer.width, localPeer.height, localPeer.tags);
    }
  }, [isMultiDisplayModalOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // Broadcast identification state when modal opens/closes
  // This is a legitimate sync with an external system (Yjs awareness)
  useEffect(() => {
    if (isMultiDisplayModalOpen && isConnected) {
      setIdentifying(true);
      updatePeerPresence({ ...localPeer, isIdentifying: true });
    } else if (!isMultiDisplayModalOpen && isConnected) {
      setIdentifying(false);
      updatePeerPresence({ ...localPeer, isIdentifying: false });
    }
    return () => {
      if (isConnected) {
        setIdentifying(false);
        updatePeerPresence({ ...localPeer, isIdentifying: false });
      }
    };
  }, [isMultiDisplayModalOpen, isConnected, setIdentifying]); // Don't include localPeer to avoid loops

  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMultiDisplayModalOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setMultiDisplayModalOpen]);

  const handleTagsChange = (value: string) => {
    setTagsInput(value);
    const tags = value.split(',').map((t) => t.trim()).filter(Boolean);
    setLocalPeerConfig(localPeer.x, localPeer.y, localPeer.width, localPeer.height, tags);
  };

  const handleConnect = () => {
    if (!roomId) return;
    connectSocket(serverUrl);
    joinRoom(roomId, localPeer);
  };

  const remotePeers = Array.from(peers.values()).filter((p) => !p.isSelf);

  if (!isMultiDisplayModalOpen) return null;

  return (
    <div
      className="md-modal-backdrop"
      ref={backdropRef}
      onClick={(e) => { if (e.target === backdropRef.current) setMultiDisplayModalOpen(false); }}
    >
      <div className="md-modal" role="dialog" aria-modal="true" aria-label="Multi-Display Settings">
        {/* ── Header ─────────────────────────────────────────── */}
        <div className="md-modal-header">
          <div className="md-modal-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
              <rect x="2" y="3" width="20" height="14" rx="2" />
              <path d="M8 21h8M12 17v4" />
            </svg>
            Multi-Display
            <span className={`md-status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
            <span className="md-status-label">{isConnected ? `Connected — ${roomId}` : 'Disconnected'}</span>
          </div>
          <button className="md-close-btn" onClick={() => setMultiDisplayModalOpen(false)} title="Close">
            ×
          </button>
        </div>

        {/* ── Body ───────────────────────────────────────────── */}
        <div className="md-modal-body">
          {/* Left column: settings */}
          <div className="md-col-settings">
            <h3 className="md-section-title">Connection</h3>

            <label className="md-label">Server URL</label>
            <input
              className="md-input"
              type="text"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              placeholder="http://localhost:8000"
              disabled={isConnected}
            />

            <label className="md-label">Room ID</label>
            <input
              className="md-input"
              type="text"
              value={roomId ?? ''}
              onChange={(e) => setRoomId(e.target.value)}
              placeholder="e.g. TEST"
              disabled={isConnected}
            />

            <label className="md-label">Tags <span className="md-hint">(comma-separated)</span></label>
            <input
              className="md-input"
              type="text"
              value={tagsInput}
              onChange={(e) => handleTagsChange(e.target.value)}
              placeholder="e.g. left-screen"
            />

            <>
                <label className="md-label">
                  Offset <span className="md-hint">(drag mini-map to adjust)</span>
                </label>
                <div className="md-offset-row">
                  <div className="md-offset-field">
                    <span>X</span>
                    <input
                      className="md-input md-input-sm"
                      type="number"
                      value={localPeer.x}
                      onChange={(e) => setLocalPeerConfig(Number(e.target.value), localPeer.y, localPeer.width, localPeer.height, localPeer.tags)}
                    />
                  </div>
                  <div className="md-offset-field">
                    <span>Y</span>
                    <input
                      className="md-input md-input-sm"
                      type="number"
                      value={localPeer.y}
                      onChange={(e) => setLocalPeerConfig(localPeer.x, Number(e.target.value), localPeer.width, localPeer.height, localPeer.tags)}
                    />
                  </div>
                </div>
            </>

            <div className="md-connect-row">
              {isConnected ? (
                <button className="md-btn md-btn-disconnect" onClick={disconnectSocket}>
                  Disconnect
                </button>
              ) : (
                <button
                  className="md-btn md-btn-connect"
                  onClick={handleConnect}
                  disabled={!roomId}
                >
                  Connect
                </button>
              )}
            </div>

            {/* Peer list */}
            {isConnected && (
              <>
                <h3 className="md-section-title" style={{ marginTop: '20px' }}>Peers ({remotePeers.length + 1})</h3>
                <ul className="md-peer-list">
                  <li className="md-peer-item md-peer-self">
                    <span className="md-peer-dot self" />
                    <span>{localPeer.tags[0] ?? 'me'}</span>
                    <span className="md-peer-coords">({localPeer.x}, {localPeer.y})</span>
                  </li>
                  {remotePeers.map((peer: Peer) => (
                    <li key={peer.id} className="md-peer-item">
                      <span className="md-peer-dot remote" />
                      <span>{peer.tags[0] ?? peer.id.slice(0, 8)}</span>
                      <span className="md-peer-coords">({peer.x}, {peer.y})</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          {/* Right column: mini-map */}
          <div className="md-col-map">
            <h3 className="md-section-title">Canvas Layout</h3>
            <p className="md-hint" style={{ marginBottom: '10px' }}>
              Drag the blue rectangle to set your display's position on the shared canvas.
            </p>
            <PeerLayoutEditor mapWidth={340} mapHeight={260} />
          </div>
        </div>
      </div>
    </div>
  );
};
