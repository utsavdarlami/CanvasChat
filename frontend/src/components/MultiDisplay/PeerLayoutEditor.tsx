import React, { useRef, useState, useCallback } from 'react';
import { usePeerLayoutEditorSession } from '@/stores/sessionStore';
import { updatePeerPresence as emitUpdatePeer, setPeerLayout } from '@/services/yjsService';
import { useAppStore } from '@/stores/appStore';
import type { Peer } from '@/types/session';

const MIN_RECT = 20;
// Visual stagger applied to peers that share the same position in the mini-map
const OVERLAP_STAGGER = 20;

interface Props {
  mapWidth?: number;
  mapHeight?: number;
}

interface DragState {
  dragging: boolean;
  peerId: string; // 'local' | remote peer id
  startMouseX: number;
  startMouseY: number;
  startPeerX: number;
  startPeerY: number;
}

function computeScale(
  peers: Peer[],
  localPeer: Omit<Peer, 'id'>,
  mapW: number,
  mapH: number,
): { scaleX: number; scaleY: number; minX: number; minY: number } {
  const all = [...peers, { ...localPeer, id: 'local' }];

  // Use actual peer dimensions for scaling
  const xs = all.flatMap((p) => [p.x, p.x + p.width]);
  const ys = all.flatMap((p) => [p.y, p.y + p.height]);

  let minX = Math.min(...xs);
  let maxX = Math.max(...xs);
  let minY = Math.min(...ys);
  let maxY = Math.max(...ys);

  // Enforce a minimum viewing area to ensure single/few peers don't fill the entire map
  const contentW = maxX - minX || 1920;
  const contentH = maxY - minY || 1080;
  const minViewW = 1920 * 3;
  const minViewH = 1080 * 3;

  if (contentW < minViewW) {
    const diff = minViewW - contentW;
    minX -= diff / 2;
    maxX += diff / 2;
  }
  if (contentH < minViewH) {
    const diff = minViewH - contentH;
    minY -= diff / 2;
    maxY += diff / 2;
  }

  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;

  const padding = 20;
  return {
    scaleX: (mapW - padding * 2) / rangeX,
    scaleY: (mapH - padding * 2) / rangeY,
    minX,
    minY,
  };
}

// Build a key from x,y to detect overlapping peers
function posKey(x: number, y: number) {
  return `${x}:${y}`;
}

export const PeerLayoutEditor: React.FC<Props> = ({ mapWidth = 250, mapHeight = 180 }) => {
  const {
    peers,
    localPeer,
    localPeerId,
    virtualDesktop,
    updatePeer: updatePeerInStore,
    setLocalPeerConfig,
  } = usePeerLayoutEditorSession();
  const svgRef = useRef<SVGSVGElement>(null);
  const dragState = useRef<DragState>({
    dragging: false,
    peerId: 'local',
    startMouseX: 0,
    startMouseY: 0,
    startPeerX: 0,
    startPeerY: 0,
  });
  const [activePeerId, setActivePeerId] = useState<string | null>(null);
  const [frozenScale, setFrozenScale] = useState<{ scaleX: number; scaleY: number; minX: number; minY: number } | null>(null);
  const [, forceRender] = useState(0);


  const allRemotePeers = Array.from(peers.values()).filter((p) => !p.isSelf);

  // Use frozen scale if dragging, otherwise compute fresh
  const currentScale = frozenScale ?? computeScale(allRemotePeers, localPeer, mapWidth, mapHeight);
  const { scaleX, scaleY, minX, minY } = currentScale;

  const pad = 5;

  const toMapX = (gx: number) => pad + (gx - minX) * scaleX;
  const toMapY = (gy: number) => pad + (gy - minY) * scaleY;
  // Use actual peer dimensions for box sizes
  const toMapW = (w: number) => Math.max(MIN_RECT, w * scaleX);
  const toMapH = (h: number) => Math.max(MIN_RECT, h * scaleY);

  // Count how many peers share each canvas position so we can stagger them visually
  const overlapCount = new Map<string, number>();
  const overlapIndex = new Map<string, number>();

  const trackOverlap = (id: string, x: number, y: number) => {
    const key = posKey(x, y);
    const idx = overlapCount.get(key) ?? 0;
    overlapIndex.set(id, idx);
    overlapCount.set(key, idx + 1);
  };
  allRemotePeers.forEach((p) => trackOverlap(p.id, p.x, p.y));
  trackOverlap('local', localPeer.x, localPeer.y);

  const staggerOffset = (id: string) => overlapIndex.get(id) ?? 0;

  const getSVGCoords = useCallback((e: React.MouseEvent): { x: number; y: number } => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }, []);

  const startDrag = useCallback(
    (e: React.MouseEvent, peerId: string, peerX: number, peerY: number) => {
      e.preventDefault();
      e.stopPropagation();
      const { x, y } = getSVGCoords(e);
      dragState.current = {
        dragging: true,
        peerId,
        startMouseX: x,
        startMouseY: y,
        startPeerX: peerX,
        startPeerY: peerY,
      };
      setActivePeerId(peerId);
      setFrozenScale(currentScale);
    },
    [getSVGCoords, currentScale],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragState.current.dragging) return;
      const { x, y } = getSVGCoords(e);
      const dx = (x - dragState.current.startMouseX) / scaleX;
      const dy = (y - dragState.current.startMouseY) / scaleY;
      const newX = Math.round(dragState.current.startPeerX + dx);
      const newY = Math.round(dragState.current.startPeerY + dy);

      if (dragState.current.peerId === 'local') {
        setLocalPeerConfig(newX, newY, localPeer.width, localPeer.height, localPeer.tags);
      } else {
        updatePeerInStore(dragState.current.peerId, { x: newX, y: newY });
      }
      forceRender((n) => n + 1);
    },
    [getSVGCoords, scaleX, scaleY, localPeer.width, localPeer.height, localPeer.tags, setLocalPeerConfig, updatePeerInStore],
  );

  const handleMouseUp = useCallback(() => {
    if (!dragState.current.dragging) return;
    const { peerId } = dragState.current;
    dragState.current.dragging = false;
    setActivePeerId(null);
    setFrozenScale(null);

    const session = useAppStore.getState().session;
    if (peerId === 'local') {
      emitUpdatePeer(session.localPeer);
    } else {
      const peer = session.peers.get(peerId);
      if (peer) setPeerLayout(peerId, peer.x, peer.y);
    }
  }, []);

  const lx = toMapX(localPeer.x) + staggerOffset('local') * OVERLAP_STAGGER;
  const ly = toMapY(localPeer.y) + staggerOffset('local') * OVERLAP_STAGGER;
  const lw = toMapW(localPeer.width);
  const lh = toMapH(localPeer.height);

  const activeLabel = (() => {
    if (!activePeerId) return null;
    if (activePeerId === 'local') {
      return localPeer.tags[0] ? `me · ${localPeer.tags[0]}` : 'me';
    }
    const p = peers.get(activePeerId);
    return p ? (p.tags[0] ?? p.id) : activePeerId;
  })();

  return (
    <div className="peer-layout-editor">
      <svg
        ref={svgRef}
        width={mapWidth}
        height={mapHeight}
        style={{
          background: '#0f0f1a',
          borderRadius: '6px',
          cursor: 'crosshair',
          display: 'block',
          border: '1px solid #2a2a3e',
        }}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {/* Grid lines */}
        <defs>
          <pattern id="md-grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#1e1e30" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width={mapWidth} height={mapHeight} fill="url(#md-grid)" />

        {/* Combined canvas outline when auto-layout active */}
        {virtualDesktop && (
          <rect
            x={toMapX(0)}
            y={toMapY(0)}
            width={toMapW(virtualDesktop.totalWidth)}
            height={toMapH(virtualDesktop.totalHeight)}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={1}
            strokeDasharray="4,4"
            opacity={0.4}
            rx={2}
          />
        )}

        {/* Remote peers */}
        {allRemotePeers.map((peer) => {
          const so = staggerOffset(peer.id);
          const px = toMapX(peer.x) + so * OVERLAP_STAGGER;
          const py = toMapY(peer.y) + so * OVERLAP_STAGGER;
          const pw = toMapW(peer.width);
          const ph = toMapH(peer.height);
          const isActive = activePeerId === peer.id;
          return (
            <g
              key={peer.id}
              onMouseDown={(e) => startDrag(e, peer.id, peer.x, peer.y)}
              style={{ cursor: 'grab' }}
            >
              <rect
                x={px}
                y={py}
                width={pw}
                height={ph}
                fill={isActive ? 'rgba(120,120,150,0.4)' : 'rgba(100,100,120,0.25)'}
                stroke={isActive ? '#aaa' : '#555'}
                strokeWidth={isActive ? 2 : 1}
                rx={3}
              />
              <text
                x={px + 5}
                y={py + 13}
                fill={isActive ? '#ccc' : '#888'}
                fontSize={10}
                fontFamily="monospace"
              >
                {peer.tags[0] ?? peer.id.slice(0, 6)}
              </text>
              {(isActive || activePeerId) && (
                <text x={px + 5} y={py + 24} fill={isActive ? "#aaa" : "#666"} fontSize={8} fontFamily="monospace">
                  {peer.id}
                </text>
              )}
            </g>
          );
        })}

        {/* Local peer */}
        <g
          onMouseDown={(e) => startDrag(e, 'local', localPeer.x, localPeer.y)}
          style={{ cursor: 'grab' }}
        >
          <rect
            x={lx}
            y={ly}
            width={lw}
            height={lh}
            fill={activePeerId === 'local' ? 'rgba(59,130,246,0.35)' : 'rgba(59,130,246,0.2)'}
            stroke="#3b82f6"
            strokeWidth={activePeerId === 'local' ? 2 : 1.5}
            rx={3}
          />
          <text x={lx + 5} y={ly + 13} fill="#60a5fa" fontSize={10} fontFamily="monospace">
            {localPeer.tags[0] ?? 'me'}
          </text>
          {(activePeerId) && (
            <text x={lx + 5} y={ly + 24} fill="#93c5fd" fontSize={8} fontFamily="monospace">
              {localPeerId ?? ''}
            </text>
          )}
          {/* Corner handles (only when manual layout) */}
            <>
              <circle cx={lx} cy={ly} r={3} fill="#3b82f6" />
              <circle cx={lx + lw} cy={ly} r={3} fill="#3b82f6" />
              <circle cx={lx} cy={ly + lh} r={3} fill="#3b82f6" />
              <circle cx={lx + lw} cy={ly + lh} r={3} fill="#3b82f6" />
            </>
        </g>
      </svg>

      {/* Status label */}
      {activeLabel ? (
        <div style={{ fontSize: '0.75rem', color: '#60a5fa', marginTop: '6px', fontFamily: 'monospace' }}>
          dragging: <strong>{activeLabel}</strong>
        </div>
      ) : (
        <div style={{ fontSize: '0.75rem', color: '#555', marginTop: '6px', fontFamily: 'monospace' }}>
          offset: ({localPeer.x}, {localPeer.y}) &nbsp;·&nbsp; viewport: {localPeer.width}x{localPeer.height}
        </div>
      )}
    </div>
  );
};
