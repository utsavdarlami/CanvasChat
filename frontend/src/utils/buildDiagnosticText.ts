/**
 * Pure function that builds the multi-display diagnostic text.
 *
 * Extracted from DiagnosticPanel so that both the UI component and the
 * debug session logger can produce the same output without coupling to
 * React state.
 */
import type { Node as FlowNode } from '@xyflow/react';
import type { GraphNode } from '@/types/graph';
import type { Peer } from '@/types/session';
import type { VirtualDesktop } from '@/utils/peerArrangement';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface YjsNodeSnapshot {
  x: number;
  y: number;
  displayId: string;
  preview?: boolean;
  mirror?: boolean;
}

export interface DiagnosticTextParams {
  peers: Map<string, Peer>;
  localPeerId: string | null;
  localPeer: Omit<Peer, 'id'>;
  virtualDesktop: VirtualDesktop | null;
  graphNodes: GraphNode[];
  yjsSnapshot: Map<string, YjsNodeSnapshot>;
  flowNodes: FlowNode[];
  flowVersion: number;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmt(v: number | undefined | null, decimals = 1, fallback = '?'): string {
  return v != null && isFinite(v) ? v.toFixed(decimals) : fallback;
}

function col(s: string | number | undefined | null, width: number): string {
  const str = s == null ? "" : String(s);
  if (str.length > width) return str.slice(0, width - 2) + '..';
  return str.padEnd(width);
}

function shortId(id: string | number | undefined | null, len = 8): string {
  const str = id == null ? "" : String(id);
  return str.length > len ? str.slice(0, len) : str;
}

// ---------------------------------------------------------------------------
// Main builder
// ---------------------------------------------------------------------------

export function buildDiagnosticText(params: DiagnosticTextParams): string {
  const {
    peers,
    localPeerId,
    localPeer,
    virtualDesktop,
    graphNodes,
    yjsSnapshot,
    flowNodes,
    flowVersion,
  } = params;

  // Build flow node lookup
  const flowMap = new Map<string, FlowNode>();
  for (const n of flowNodes) flowMap.set(n.id, n);

  // Group graph-store nodes by displayId
  const nodesByDisplay = new Map<string, GraphNode[]>();
  for (const n of graphNodes) {
    const key = n.displayId ?? '__unassigned__';
    if (!nodesByDisplay.has(key)) nodesByDisplay.set(key, []);
    nodesByDisplay.get(key)!.push(n);
  }

  // Longest node name for alignment
  let maxNameLen = 8;
  for (const n of graphNodes) {
    const rawName = (n as any).name || (n as any).display_name || n.id;
    const name = rawName == null ? "" : String(rawName);
    if (name.length > maxNameLen) maxNameLen = name.length;
  }
  maxNameLen = Math.min(maxNameLen, 20);

  const peerList = Array.from(peers.values());
  const lines: string[] = [];

  // ---- Peers ----
  lines.push(`=== Peers (${peerList.length}) ===`);
  for (const p of peerList) {
    const isSelf = p.id === localPeerId;
    const tag = p.tags[0] ? ` [${p.tags[0]}]` : '';
    const viewportWidth = isSelf ? localPeer.width : p.width;
    const viewportHeight = isSelf ? localPeer.height : p.height;
    const displayX = isSelf ? localPeer.x : p.x;
    const displayY = isSelf ? localPeer.y : p.y;
    const camera = isSelf ? localPeer.camera : p.camera;
    lines.push(`${isSelf ? '> ' : '  '}${shortId(p.id)}${tag}`);
    lines.push(`    viewport : ${viewportWidth}x${viewportHeight}  offset:(${displayX},${displayY})`);
    if (camera) {
      lines.push(`    camera   : pan(${fmt(camera.x)},${fmt(camera.y)}) zoom:${fmt(camera.zoom, 3)}`);
    } else {
      lines.push(`    camera   : n/a`);
    }
  }
  lines.push('');

  // ---- Virtual Desktop ----
  lines.push(`=== Virtual Desktop ===`);
  if (virtualDesktop) {
    lines.push(`${virtualDesktop.totalWidth}x${virtualDesktop.totalHeight}  (${virtualDesktop.peers.length} peers)`);
    for (const ap of virtualDesktop.peers) {
      lines.push(`  ${shortId(ap.id)} @ (${ap.x},${ap.y}) ${ap.width}x${ap.height}`);
    }
  } else {
    lines.push(`null (need 2+ peers)`);
  }
  lines.push('');

  // ---- Nodes by Display ----
  const displayIds = Array.from(nodesByDisplay.keys()).sort((a, b) => {
    if (a === localPeerId) return -1;
    if (b === localPeerId) return 1;
    if (a === '__unassigned__') return 1;
    if (b === '__unassigned__') return -1;
    return String(a).localeCompare(String(b));
  });

  lines.push(`=== Nodes (${graphNodes.length} total, flow:${flowNodes.length}, yjs:${yjsSnapshot.size}) v${flowVersion} ===`);
  lines.push('');

  const hdrName = col('NAME', maxNameLen);
  lines.push(`  ${hdrName}  ${'store'.padEnd(17)}  ${'flow'.padEnd(17)}  ${'yjs'.padEnd(17)}  flags`);
  lines.push(`  ${''.padEnd(maxNameLen, '-')}  ${'-'.repeat(17)}  ${'-'.repeat(17)}  ${'-'.repeat(17)}  -----`);

  for (const displayId of displayIds) {
    const nodes = nodesByDisplay.get(displayId)!;
    const isSelf = displayId === localPeerId;
    const displayLabel = displayId === '__unassigned__'
      ? 'unassigned'
      : shortId(displayId);
    lines.push(`[${displayLabel}]${isSelf ? ' (me)' : ''} - ${nodes.length} nodes`);

    for (const n of nodes) {
      const rawName = (n as any).name || (n as any).display_name || n.id;
    const name = rawName == null ? "" : String(rawName);

      const gsX = fmt(n.x, 1);
      const gsY = fmt(n.y, 1);

      const flow = flowMap.get(n.id);
      const rfX = flow ? fmt(flow.position.x, 1) : '-';
      const rfY = flow ? fmt(flow.position.y, 1) : '-';

      const yjs = yjsSnapshot.get(n.id);
      const yjX = yjs ? fmt(yjs.x, 1) : '-';
      const yjY = yjs ? fmt(yjs.y, 1) : '-';

      const flags: string[] = [];
      if (yjs?.preview) flags.push('P');
      if (yjs?.mirror) flags.push('M');
      if (flow?.className) flags.push(flow.className.replace('transfer-', 'T:'));
      if (flow?.draggable === false) flags.push('!drag');

      if (flow && n.x != null) {
        const dx = Math.abs(n.x - flow.position.x);
        const dy = Math.abs((n.y ?? 0) - flow.position.y);
        if (dx > 5 || dy > 5) flags.push('DRIFT');
      }

      if (yjs && yjs.displayId !== (n.displayId ?? '__unassigned__')) {
        flags.push(`yjs:${shortId(yjs.displayId, 6)}`);
      }

      const gsCol = `(${gsX},${gsY})`.padEnd(17);
      const rfCol = `(${rfX},${rfY})`.padEnd(17);
      const yjCol = `(${yjX},${yjY})`.padEnd(17);
      const flagStr = flags.length > 0 ? flags.join(' ') : '';

      lines.push(`  ${col(name, maxNameLen)}  ${gsCol}  ${rfCol}  ${yjCol}  ${flagStr}`);
    }
    lines.push('');
  }

  // ---- Orphan check: nodes in React Flow but not in graph store ----
  const graphIds = new Set(graphNodes.map(n => n.id));
  const orphanFlow = flowNodes.filter(n => !graphIds.has(n.id));
  if (orphanFlow.length > 0) {
    lines.push(`=== Orphan React Flow Nodes (${orphanFlow.length}) ===`);
    for (const n of orphanFlow) {
      const cls = n.className ?? '';
      lines.push(`  ${col(n.id, maxNameLen)}  pos:(${fmt(n.position.x, 1)},${fmt(n.position.y, 1)})  class:${cls}`);
    }
    lines.push('');
  }

  // ---- Orphan check: nodes in Yjs but not in graph store ----
  const orphanYjs: Array<{ id: string; x: number; y: number; displayId: string; preview?: boolean; mirror?: boolean }> = [];
  yjsSnapshot.forEach((val, key) => {
    if (!graphIds.has(key)) orphanYjs.push({ id: key, ...val });
  });
  if (orphanYjs.length > 0) {
    lines.push(`=== Orphan Yjs Entries (${orphanYjs.length}) ===`);
    for (const o of orphanYjs) {
      const flags = [o.preview && 'P', o.mirror && 'M'].filter(Boolean).join(' ');
      lines.push(`  ${col(o.id, maxNameLen)}  pos:(${fmt(o.x, 1)},${fmt(o.y, 1)})  display:${shortId(o.displayId)}  ${flags}`);
    }
    lines.push('');
  }

  if (displayIds.length === 0) {
    lines.push(`  (no nodes loaded)`);
    lines.push('');
  }

  return lines.join('\n');
}
