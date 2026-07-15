import React, { useRef, useMemo, useState, useEffect, useCallback } from 'react';
import { useGraphNodes } from '@/stores/graphStore';
import { useDiagnosticSession } from '@/stores/sessionStore';
import { getNodePositionsSnapshot } from '@/services/yjs/nodePositions';
import { getLiveFlowNodes, getLiveFlowVersion } from '@/components/EntityView/hooks/useFlowNodeDebug';
import { buildDiagnosticText } from '@/utils/buildDiagnosticText';
import { debugLogger } from '@/services/debugLogger';
import type { Node as FlowNode } from '@xyflow/react';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const DiagnosticPanel: React.FC = () => {
  const {
    isConnected,
    localPeerId,
    localPeer,
    virtualDesktop,
    peers,
  } = useDiagnosticSession();
  const graphNodes = useGraphNodes();
  const preRef = useRef<HTMLPreElement>(null);

  // Tick counter for periodic refresh (live positions change frequently)
  const [tick, setTick] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Debug logger toggle state (force re-render when toggled)
  const [loggerEnabled, setLoggerEnabled] = useState(() => debugLogger.isEnabled());

  useEffect(() => {
    if (!autoRefresh) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    intervalRef.current = setInterval(() => setTick(t => t + 1), 500);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh]);

  // Snapshot Yjs CRDT state and React Flow live state on each tick
  const yjsSnap = useMemo(() => getNodePositionsSnapshot(), [tick]);
  const flowNodes: FlowNode[] = useMemo(() => getLiveFlowNodes(), [tick]);
  const flowVersion = getLiveFlowVersion();

  const handleCopy = useCallback(() => {
    if (preRef.current) navigator.clipboard.writeText(preRef.current.textContent ?? '');
  }, []);

  const handleToggleLogger = useCallback(() => {
    const next = !debugLogger.isEnabled();
    debugLogger.setEnabled(next);
    setLoggerEnabled(next);
  }, []);

  const handleDownloadLog = useCallback(() => {
    debugLogger.downloadLog();
  }, []);

  if (!isConnected) return null;

  // Build diagnostic text via the shared utility
  const text = buildDiagnosticText({
    peers,
    localPeerId,
    localPeer,
    virtualDesktop,
    graphNodes,
    yjsSnapshot: yjsSnap,
    flowNodes,
    flowVersion,
  });

  const hasLogContent = debugLogger.getLogText().length > 0;

  return (
    <div className="diagnostic-panel">
      <div className="diagnostic-panel-header">
        <span className="diagnostic-panel-title">
          Multi-Display Diagnostics
        </span>
        <div className="diagnostic-panel-actions">
          <button
            onClick={() => setAutoRefresh(a => !a)}
            className={`diagnostic-btn ${autoRefresh ? 'diagnostic-btn-active' : ''}`}
          >
            {autoRefresh ? 'Live' : 'Paused'}
          </button>
          {!autoRefresh && (
            <button
              onClick={() => setTick(t => t + 1)}
              className="diagnostic-btn"
            >
              Refresh
            </button>
          )}
          <button onClick={handleCopy} className="diagnostic-btn">
            Copy
          </button>
          <button
            onClick={handleToggleLogger}
            className={`diagnostic-btn ${loggerEnabled ? 'diagnostic-btn-log-active' : ''}`}
            title={loggerEnabled ? 'Debug logging is ON - click to disable' : 'Enable debug session logging'}
          >
            {loggerEnabled ? 'Log ON' : 'Log OFF'}
          </button>
          {hasLogContent && (
            <button
              onClick={handleDownloadLog}
              className="diagnostic-btn diagnostic-btn-download"
              title="Download debug session log"
            >
              DL Log
            </button>
          )}
        </div>
      </div>
      <pre
        ref={preRef}
        className="diagnostic-panel-output"
      >
        {text}
      </pre>
    </div>
  );
};
