import React, { useCallback, useEffect, useRef } from 'react';
import { Group, Panel, Separator, type PanelSize } from 'react-resizable-panels';
import { useSidebarUI } from '@/stores/uiStore';
import { useAppLayoutSession } from '@/stores/sessionStore';
import { updatePeerPresence } from '@/services/yjsService';
import { UploadSidebar } from '../Sidebar/UploadSidebar';
import { EntityFlowView } from '../EntityView/EntityFlowView';
import { MultiDisplayModal } from '../MultiDisplay/MultiDisplayModal';
import { DisplayIdentificationOverlay } from '../DisplayOverlay/DisplayIdentificationOverlay';

const SIDEBAR_MIN_WIDTH = 200;
const SIDEBAR_MAX_WIDTH = 600;

export const AppLayout: React.FC = () => {
  const {
    leftSidebarOpen,
    leftSidebarWidth,
    toggleSidebar,
    setSidebarWidth,
  } = useSidebarUI();
  const { localPeer, isConnected } = useAppLayoutSession();
  const lastEmittedPeerRef = useRef<string>('');

  // Sync localPeer changes to server (debounced)
  useEffect(() => {
    if (!isConnected) return;

    const currentPeerStr = JSON.stringify({
      x: localPeer.x,
      y: localPeer.y,
      width: localPeer.width,
      height: localPeer.height,
      tags: localPeer.tags,
      isIdentifying: localPeer.isIdentifying
    });

    if (currentPeerStr !== lastEmittedPeerRef.current) {
      const timeoutId = setTimeout(() => {
        updatePeerPresence(localPeer);
        lastEmittedPeerRef.current = currentPeerStr;
      }, 100); // 100ms debounce
      return () => clearTimeout(timeoutId);
    }
  }, [localPeer, isConnected]);

  const handleSidebarResize = useCallback((panelSize: PanelSize) => {
    const clamped = Math.max(SIDEBAR_MIN_WIDTH, Math.min(SIDEBAR_MAX_WIDTH, panelSize.inPixels));
    setSidebarWidth('left', clamped);
  }, [setSidebarWidth]);

  const renderMainContent = (showExpandButton: boolean) => (
    <main className="main-content" style={{ height: '100%' }}>
      {showExpandButton && (
        <button
          className="sidebar-toggle-overlay"
          onClick={() => toggleSidebar('left')}
          title="Expand Sidebar"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </button>
      )}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <EntityFlowView />
      </div>
    </main>
  );

  return (
    <div className="app-layout">
      <DisplayIdentificationOverlay />
      <MultiDisplayModal />
      <div className="app-content">
        {leftSidebarOpen && (
          <Group orientation="horizontal" className="app-panel-group">
            <Panel
              id="left-sidebar"
              minSize={SIDEBAR_MIN_WIDTH}
              maxSize={SIDEBAR_MAX_WIDTH}
              defaultSize={leftSidebarWidth}
              onResize={handleSidebarResize}
              className="left-sidebar-panel"
            >
              <aside className="left-sidebar">
                <UploadSidebar />
              </aside>
            </Panel>
            <Separator className="resize-handle" />
            <Panel id="main-content">
              {renderMainContent(false)}
            </Panel>
          </Group>
        )}
        {!leftSidebarOpen && renderMainContent(true)}
      </div>
    </div>
  );
};
