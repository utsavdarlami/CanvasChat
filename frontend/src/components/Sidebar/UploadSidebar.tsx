import React from 'react';
import { useMultiDisplayModalUI, useSidebarUI } from '@/stores/uiStore';
import { useSessionConnectionStatus } from '@/stores/sessionStore';
import { useAppStore } from '@/stores/appStore';
import { useGraphUpload } from './hooks/useGraphUpload';
import { useSnapshotStore } from '@/stores/snapshotStore';
import { FileUploadSection } from '@/components/Sidebar/FileUploadSection';
import { AnalysisResults } from '@/components/Sidebar/AnalysisResults';
import { MultiDisplaySection } from '@/components/Sidebar/MultiDisplaySection';
import { ChatPanel } from '@/components/Chat/ChatPanel';

function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function truncateLabel(label: string, maxLength: number = 25): string {
  if (label.length <= maxLength) return label;
  return label.substring(0, maxLength - 3) + '...';
}

const TimelineView: React.FC = () => {
  const { timeline } = useAppStore();
  const { entries, currentIndex } = timeline;

  if (entries.length === 0) {
    return (
      <div className="timeline-empty">
        <p>No history yet.</p>
        <p>Move or chat to create snapshots.</p>
      </div>
    );
  }

  return (
    <div className="timeline-list">
      {currentIndex >= 0 && (
        <button
          className="timeline-return-btn"
          onClick={() => useAppStore.getState().timeline.jumpToEntry(entries.length - 1)}
        >
          ← Return to Current
        </button>
      )}
      <div className="timeline-entries">
        {[...entries].reverse().map((entry, idx) => {
          const actualIndex = entries.length - 1 - idx;
          const isActive = actualIndex === currentIndex;
          return (
            <button
              key={entry.id}
              className={`timeline-entry ${entry.source === 'drag' ? 'timeline-entry--drag' : 'timeline-entry--chat'} ${isActive ? 'timeline-entry--active' : ''}`}
              onClick={() => useAppStore.getState().timeline.jumpToEntry(actualIndex)}
            >
              <span className="timeline-entry-dot" />
              <span className="timeline-entry-label">{truncateLabel(entry.label)}</span>
              <span className="timeline-entry-time">{formatTime(entry.timestamp)}</span>
            </button>
          );
        })}
      </div>
      {currentIndex >= 0 && (
        <div className="timeline-info">
          Viewing state from {formatTime(entries[currentIndex].timestamp)}
        </div>
      )}
    </div>
  );
};

export const UploadSidebar: React.FC = () => {
  const { toggleSidebar, leftSidebarTab, setLeftSidebarTab } = useSidebarUI();
  const { setMultiDisplayModalOpen } = useMultiDisplayModalUI();
  const isConnected = useSessionConnectionStatus();

  const {
    entitiesFile,
    imageFiles,
    uploadStatus,
    analysisResult,
    handleEntitiesChange,
    handleImageFilesChange,
    handleUpload,
    isUploadDisabled
  } = useGraphUpload();
  const { isRecording, useFallbackMode, eventCount, startRecording, stopRecording } = useSnapshotStore();

  return (
    <div className="upload-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <h1>Distribution UI</h1>
          <button
            className="sidebar-close-btn"
            onClick={() => toggleSidebar('left')}
            title="Collapse Sidebar"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </button>
        </div>
        <div className="sidebar-tabs">
          <button
            className={`sidebar-tab ${leftSidebarTab === 'current' ? 'sidebar-tab--active' : ''}`}
            onClick={() => setLeftSidebarTab('current')}
          >
            Current
          </button>
          <button
            className={`sidebar-tab ${leftSidebarTab === 'timeline' ? 'sidebar-tab--active' : ''}`}
            onClick={() => setLeftSidebarTab('timeline')}
          >
            Timeline
          </button>
          <button
            className={`sidebar-tab ${leftSidebarTab === 'chat' ? 'sidebar-tab--active' : ''}`}
            onClick={() => setLeftSidebarTab('chat')}
          >
            Chat
          </button>
        </div>
      </div>

      <div className="sidebar-content">
        {leftSidebarTab === 'current' && (
          <div className="sidebar-section">
            <div className="sidebar-section-label">Data</div>
            <FileUploadSection
              entitiesFile={entitiesFile}
              imageFiles={imageFiles}
              uploadStatus={uploadStatus}
              handleEntitiesChange={handleEntitiesChange}
              handleImageFilesChange={handleImageFilesChange}
              handleUpload={handleUpload}
              isUploadDisabled={isUploadDisabled}
            />
            <AnalysisResults analysisResult={analysisResult} />
          </div>
        )}

        {leftSidebarTab === 'current' && (
          <div className="sidebar-section">
            <div className="sidebar-section-label">Study Recording</div>
            <div className="sidebar-recording-controls" style={{ padding: '0.5rem 1rem' }}>
              <button
                className={`upload-btn ${isRecording ? 'upload-btn--success' : ''}`}
                onClick={isRecording ? stopRecording : startRecording}
                style={{
                  width: '100%',
                  background: isRecording ? (useFallbackMode ? '#f59e0b' : '#10b981') : undefined,
                  borderColor: isRecording ? (useFallbackMode ? '#d97706' : '#059669') : undefined,
                  color: isRecording ? '#fff' : undefined,
                }}
              >
                {isRecording
                  ? (useFallbackMode
                      ? `Recording (fallback) — ${eventCount} events`
                      : `Recording — ${eventCount} events (click to stop)`)
                  : 'Enable Study Recording'}
              </button>
              <p style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.5rem', textAlign: 'center' }}>
                {isRecording
                  ? (useFallbackMode
                      ? 'Session JSON will download when you stop.'
                      : 'Session JSON will be saved silently when you stop.')
                  : 'Select a folder; one rrweb session file is written when you stop.'}
              </p>
              <a
                href="/replay.html"
                target="_blank"
                rel="noreferrer"
                style={{ display: 'block', textAlign: 'center', fontSize: '0.8rem', color: '#2563eb', marginTop: '0.25rem' }}
              >
                Open replay viewer ↗
              </a>
            </div>
          </div>
        )}

        {leftSidebarTab === 'current' && (
          <MultiDisplaySection
            isConnected={isConnected}
            setMultiDisplayModalOpen={setMultiDisplayModalOpen}
          />
        )}

        {leftSidebarTab === 'timeline' && (
          <TimelineView />
        )}

        {leftSidebarTab === 'chat' && (
          <div className="sidebar-chat-container">
            <ChatPanel />
          </div>
        )}
      </div>
    </div>
  );
};
