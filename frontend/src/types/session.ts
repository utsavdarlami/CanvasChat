export interface Peer {
  id: string;       // socket.id assigned by server
  x: number;        // global canvas X offset (top-left of this display)
  y: number;        // global canvas Y offset
  width: number;    // viewport width in global px
  height: number;   // viewport height in global px
  tags: string[];   // user labels (e.g. "left-screen")
  isSelf?: boolean; // true only on the local peer
  isIdentifying?: boolean; // Signal to show ID overlay (e.g. during setup)
  // Device metadata
  devicePixelRatio?: number;                        // 1.0 = normal, 2.0 = retina
  deviceType?: 'mobile' | 'tablet' | 'desktop';    // inferred from user agent
  orientation?: string;                             // e.g. "landscape-primary"
  touchEnabled?: boolean;                           // true if touch input is available
  // React Flow camera state (pan / zoom), broadcast via Yjs awareness
  camera?: {
    x: number;      // React Flow pan X (pixels)
    y: number;      // React Flow pan Y (pixels)
    zoom: number;   // React Flow zoom level
  };
}

export type NodeUpdateKind =
  | 'commit'        // persisted node position/update
  | 'drag'          // ephemeral same-display drag update
  | 'preview'       // ephemeral cross-display preview ghost
  | 'preview-clear' // clear preview ghost on target display
  | 'mirror'        // ephemeral overlap shadow on adjacent display
  | 'mirror-clear'; // clear overlap shadow on adjacent display

export type NodeCoordinateSpace = 'canvas' | 'screen';

export interface NodeUpdate {
  id: string;
  x: number;        // display-local coordinates in `space`
  y: number;
  displayId: string; // which display/peer owns this node
  kind?: NodeUpdateKind;
  space?: NodeCoordinateSpace;
  // Legacy flags kept for backward compatibility with older payloads.
  preview?: boolean; // true = live drag preview (ghost), false/undefined = committed position
  mirror?: boolean;  // true = live drag shadow (node overlaps adjacent display boundary, no transfer intent)
}
