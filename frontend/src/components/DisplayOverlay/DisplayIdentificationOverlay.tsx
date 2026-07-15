import React, { useEffect, useMemo, useState, useRef } from 'react';
import { useDisplayOverlaySession } from '@/stores/sessionStore';
import { useIsMultiDisplayModalOpen } from '@/stores/uiStore';

export const DisplayIdentificationOverlay: React.FC = () => {
  const { localPeerId, peers } = useDisplayOverlaySession();
  const isMultiDisplayModalOpen = useIsMultiDisplayModalOpen();

  const peer = localPeerId ? peers.get(localPeerId) : null;

  // Track transient visibility: movement-based (2s) and fade-out on modal close (300ms).
  // These are the only behaviors that need effects — the rest is derived.
  const [movedRecently, setMovedRecently] = useState(false);
  const [fadeOutHold, setFadeOutHold] = useState(false);
  const moveTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const fadeTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const prevCoords = useRef<{ x: number; y: number } | null>(null);
  const prevModalOpen = useRef(isMultiDisplayModalOpen);

  // Movement tracking: show for 2s after peer position changes
  useEffect(() => {
    if (!peer) return;

    if (!prevCoords.current) {
      prevCoords.current = { x: peer.x, y: peer.y };
      return;
    }

    const hasMoved = prevCoords.current.x !== peer.x || prevCoords.current.y !== peer.y;
    prevCoords.current = { x: peer.x, y: peer.y };

    if (hasMoved) {
      setMovedRecently(true);
      if (moveTimeoutRef.current) clearTimeout(moveTimeoutRef.current);
      moveTimeoutRef.current = setTimeout(() => {
        setMovedRecently(false);
        moveTimeoutRef.current = undefined;
      }, 2000);
    }

    return () => {
      if (moveTimeoutRef.current) clearTimeout(moveTimeoutRef.current);
    };
  }, [peer?.x, peer?.y]);

  // Brief hold when modal closes so overlay doesn't vanish instantly
  useEffect(() => {
    if (prevModalOpen.current && !isMultiDisplayModalOpen) {
      setFadeOutHold(true);
      fadeTimeoutRef.current = setTimeout(() => {
        setFadeOutHold(false);
        fadeTimeoutRef.current = undefined;
      }, 300);
    }
    prevModalOpen.current = isMultiDisplayModalOpen;
    return () => {
      if (fadeTimeoutRef.current) clearTimeout(fadeTimeoutRef.current);
    };
  }, [isMultiDisplayModalOpen]);

  // Derive visibility from state — no cascading effect needed
  const visible = useMemo(() => {
    if (!peer) return false;
    if (isMultiDisplayModalOpen) return true;
    if (Array.from(peers.values()).some(p => p.isIdentifying)) return true;
    if (peer.isIdentifying) return true;
    if (movedRecently) return true;
    if (fadeOutHold) return true;
    return false;
  }, [peer, isMultiDisplayModalOpen, peers, movedRecently, fadeOutHold]);

  if (!visible || !peer) return null;

  return (
    <div className="display-id-overlay-minimal">
      <div className="display-id-chip">
        <span className="display-id-label">ID:</span>
        <span className="display-id-value">{peer.id.slice(0, 6)}</span>
        {peer.tags.length > 0 && (
          <>
            <span className="display-tag-separator">|</span>
            {peer.tags.map(t => <span key={t} className="display-tag-minimal">{t}</span>)}
          </>
        )}
      </div>

      <style>{`
        .display-id-overlay-minimal {
          position: fixed;
          top: 16px;
          right: 16px;
          z-index: 99999;
          pointer-events: none;
          animation: fadeInMinimal 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .display-id-chip {
          background: rgba(15, 23, 42, 0.75);
          border: 1px solid rgba(148, 163, 184, 0.2);
          border-radius: 8px;
          padding: 8px 16px;
          display: flex;
          align-items: center;
          gap: 12px;
          color: #e2e8f0;
          font-family: 'JetBrains Mono', monospace;
          font-size: 1.1rem;
          box-shadow: 0 4px 12px rgba(0,0,0,0.1);
          backdrop-filter: blur(4px);
        }

        .display-id-label {
          color: #64748b;
          font-weight: 500;
          font-size: 0.9rem;
          text-transform: uppercase;
        }

        .display-id-value {
          color: #60a5fa;
          font-weight: 600;
          font-size: 1.2rem;
        }

        .display-tag-separator {
          color: #334155;
          font-size: 1.2rem;
        }

        .display-tag-minimal {
          color: #cbd5e1;
          font-weight: 400;
          font-size: 1.1rem;
        }

        @keyframes fadeInMinimal {
          from { opacity: 0; transform: translateY(-4px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
};
