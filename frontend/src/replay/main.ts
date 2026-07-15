import rrwebPlayer from 'rrweb-player';
import 'rrweb-player/dist/style.css';
import './replay.css';
import type { eventWithTime } from '@rrweb/types';
import { toPng } from 'html-to-image';

// rrweb event type discriminator for Custom events.
// See https://github.com/rrweb-io/rrweb/blob/master/docs/recipes/custom-event.md
const CUSTOM_EVENT_TYPE = 5;
const META_EVENT_TYPE = 4;

interface CustomMarker {
  offsetMs: number;
  tag: string;
  payload: unknown;
}

interface SessionFile {
  version?: number;
  startedAt?: number;
  endedAt?: number;
  roomId?: string;
  events: eventWithTime[];
}

interface ReplayViewport {
  width: number;
  height: number;
}

function formatOffset(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  const millis = Math.floor(ms % 1000);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${millis.toString().padStart(3, '0')}`;
}

function extractMarkers(events: eventWithTime[]): CustomMarker[] {
  if (events.length === 0) return [];
  const t0 = events[0].timestamp;
  const markers: CustomMarker[] = [];
  for (const ev of events) {
    if (ev.type !== CUSTOM_EVENT_TYPE) continue;
    // ev.data shape for custom events: { tag: string, payload: unknown }
    const data = ev.data as { tag?: string; payload?: unknown };
    markers.push({
      offsetMs: ev.timestamp - t0,
      tag: data.tag ?? '(untagged)',
      payload: data.payload,
    });
  }
  return markers;
}

function extractViewport(events: eventWithTime[]): ReplayViewport | null {
  for (const ev of events) {
    if (ev.type !== META_EVENT_TYPE) continue;
    const data = ev.data as { width?: unknown; height?: unknown };
    if (typeof data.width === 'number' && typeof data.height === 'number') {
      return { width: data.width, height: data.height };
    }
  }
  return null;
}

function renderLayout(): {
  fileInput: HTMLInputElement;
  fileName: HTMLElement;
  playerMount: HTMLElement;
  markerList: HTMLElement;
  summary: HTMLElement;
  captureBtn: HTMLButtonElement;
  captureStatus: HTMLElement;
} {
  const root = document.getElementById('replay-root')!;
  root.innerHTML = `
    <div class="replay-shell">
      <aside class="replay-sidebar">
        <header class="replay-sidebar-header">
          <h1>Session Replay</h1>
          <label class="replay-file-btn">
            Load session JSON
            <input type="file" accept="application/json,.json" hidden />
          </label>
          <div class="replay-file-name" data-empty="true">No session loaded</div>
          <div class="replay-summary"></div>
          <div class="replay-capture-controls">
            <button class="replay-capture-btn" disabled>Capture current frame (PNG)</button>
            <div class="replay-capture-status"></div>
          </div>
        </header>
        <div class="replay-marker-list"></div>
      </aside>
      <main class="replay-main">
        <div class="replay-player-mount"></div>
        <div class="replay-hint">Load a session file to begin.</div>
      </main>
    </div>
  `;
  return {
    fileInput: root.querySelector<HTMLInputElement>('.replay-file-btn input')!,
    fileName: root.querySelector<HTMLElement>('.replay-file-name')!,
    playerMount: root.querySelector<HTMLElement>('.replay-player-mount')!,
    markerList: root.querySelector<HTMLElement>('.replay-marker-list')!,
    summary: root.querySelector<HTMLElement>('.replay-summary')!,
    captureBtn: root.querySelector<HTMLButtonElement>('.replay-capture-btn')!,
    captureStatus: root.querySelector<HTMLElement>('.replay-capture-status')!,
  };
}

function renderMarkers(
  container: HTMLElement,
  markers: CustomMarker[],
  onJump: (offsetMs: number) => void,
): void {
  if (markers.length === 0) {
    container.innerHTML = '<div class="replay-empty">No custom event markers in this session.</div>';
    return;
  }
  const items = markers
    .map(
      (m, i) => `
      <button class="replay-marker" data-index="${i}" data-offset="${m.offsetMs}">
        <span class="replay-marker-time">${formatOffset(m.offsetMs)}</span>
        <span class="replay-marker-tag">${escapeHtml(m.tag)}</span>
      </button>`,
    )
    .join('');
  container.innerHTML = items;
  container.querySelectorAll<HTMLButtonElement>('.replay-marker').forEach((btn) => {
    btn.addEventListener('click', () => {
      const offset = Number(btn.dataset.offset);
      onJump(offset);
      container
        .querySelectorAll('.replay-marker')
        .forEach((el) => el.classList.remove('replay-marker--active'));
      btn.classList.add('replay-marker--active');
    });
  });
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => {
    const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return map[c];
  });
}

function mountPlayer(
  target: HTMLElement,
  events: eventWithTime[],
  viewport: ReplayViewport | null,
): rrwebPlayer {
  target.innerHTML = '';
  // rrweb-player needs at least 2 events to replay; callers handle empty sessions.
  return new rrwebPlayer({
    target,
    props: {
      events,
      showController: true,
      autoPlay: false,
      maxScale: 1,
      ...(viewport ? { width: viewport.width, height: viewport.height } : {}),
    },
  });
}

function getReplayIframe(playerMount: HTMLElement): HTMLIFrameElement | null {
  return playerMount.querySelector<HTMLIFrameElement>('.replayer-wrapper > iframe');
}

function downloadDataUrl(filename: string, dataUrl: string): void {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function buildCaptureFilename(baseName: string): string {
  const safeBase = baseName.replace(/\.[a-z0-9]+$/i, '').replace(/[^a-z0-9._-]+/gi, '-');
  const date = new Date().toISOString().replace(/[:.]/g, '-');
  return `${safeBase}-frame-${date}.png`;
}

async function captureCurrentFrame(
  playerMount: HTMLElement,
  sourceFileName: string,
): Promise<string> {
  const iframe = getReplayIframe(playerMount);
  const frameRoot = iframe?.contentDocument?.documentElement;
  if (!iframe || !frameRoot) {
    throw new Error('Replay frame is not ready yet.');
  }

  const frameBody = iframe.contentDocument?.body;
  const width = Math.max(frameRoot.scrollWidth, frameBody?.scrollWidth ?? 0, frameRoot.clientWidth);
  const height = Math.max(frameRoot.scrollHeight, frameBody?.scrollHeight ?? 0, frameRoot.clientHeight);
  const scale = Math.max(2, Math.floor(window.devicePixelRatio || 1));

  const dataUrl = await toPng(frameRoot, {
    cacheBust: true,
    pixelRatio: scale,
    width,
    height,
    canvasWidth: width * scale,
    canvasHeight: height * scale,
    backgroundColor: '#ffffff',
  });

  const filename = buildCaptureFilename(sourceFileName || 'session');
  downloadDataUrl(filename, dataUrl);
  return filename;
}

async function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

async function main(): Promise<void> {
  const { fileInput, fileName, playerMount, markerList, summary, captureBtn, captureStatus } = renderLayout();
  let player: rrwebPlayer | null = null;
  let loadedFileName = '';

  captureBtn.addEventListener('click', async () => {
    if (!player) return;
    captureBtn.disabled = true;
    captureStatus.textContent = 'Capturing…';
    try {
      const filename = await captureCurrentFrame(playerMount, loadedFileName);
      captureStatus.textContent = `Saved ${filename}`;
    } catch (err) {
      captureStatus.textContent = `Capture failed: ${(err as Error).message}`;
    } finally {
      captureBtn.disabled = false;
    }
  });

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    if (!file) return;

    loadedFileName = file.name;
    fileName.textContent = file.name;
    fileName.dataset.empty = 'false';
    summary.textContent = 'Parsing…';
    markerList.innerHTML = '';
    captureStatus.textContent = '';
    captureBtn.disabled = true;

    let parsed: SessionFile;
    try {
      const text = await readFileAsText(file);
      parsed = JSON.parse(text);
    } catch (err) {
      summary.textContent = `Parse error: ${(err as Error).message}`;
      return;
    }

    const events = parsed.events ?? [];
    if (events.length < 2) {
      summary.textContent = `Session has ${events.length} events — need at least 2 to replay.`;
      return;
    }

    const viewport = extractViewport(events);
    const durationMs = events[events.length - 1].timestamp - events[0].timestamp;
    const markers = extractMarkers(events);
    summary.innerHTML = `
      <div>${events.length} events · ${markers.length} markers</div>
      <div>${formatOffset(durationMs)} duration</div>
      ${
        viewport
          ? `<div>viewport: ${viewport.width}×${viewport.height}</div>`
          : '<div>viewport: unknown (using player default)</div>'
      }
      ${parsed.roomId ? `<div>room: ${escapeHtml(parsed.roomId)}</div>` : ''}
    `;

    player = mountPlayer(playerMount, events, viewport);
    document.querySelector<HTMLElement>('.replay-hint')!.style.display = 'none';
    captureBtn.disabled = false;

    renderMarkers(markerList, markers, (offsetMs) => {
      player?.goto(offsetMs, true);
    });
  });
}

main();
