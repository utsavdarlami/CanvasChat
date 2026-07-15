import React from 'react';
import { DiagnosticPanel } from '../MultiDisplay/DiagnosticPanel';

interface Props {
  isConnected: boolean;
  setMultiDisplayModalOpen: (open: boolean) => void;
}

export const MultiDisplaySection: React.FC<Props> = ({
  isConnected,
  setMultiDisplayModalOpen
}) => {
  return (
    <div className="sidebar-section">
      <div className="sidebar-section-label">MultiDisplay</div>
      <div className="multi-display-trigger">
        <button
          className="sidebar-btn sidebar-btn-primary md-sidebar-btn"
          onClick={() => setMultiDisplayModalOpen(true)}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 17v4" />
          </svg>
          Multi-Display
          {isConnected && (
            <span className="connection-indicator" />
          )}
        </button>
      </div>

      {isConnected && (
        <DiagnosticPanel />
      )}
    </div>
  );
};
