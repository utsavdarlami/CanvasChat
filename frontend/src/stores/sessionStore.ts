import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from './appStore';

export const useAppLayoutSession = () =>
  useAppStore(
    useShallow((state) => ({
      localPeer: state.session.localPeer,
      isConnected: state.session.isConnected,
    }))
  );

export const useChatSessionContext = () =>
  useAppStore(
    useShallow((state) => ({
      isConnected: state.session.isConnected,
      localPeerId: state.session.localPeerId,
      virtualDesktop: state.session.virtualDesktop,
      peers: state.session.peers,
      localPeer: state.session.localPeer,
    }))
  );

export const useMultiDisplaySession = () =>
  useAppStore(
    useShallow((state) => ({
      serverUrl: state.session.serverUrl,
      roomId: state.session.roomId,
      isConnected: state.session.isConnected,
      localPeer: state.session.localPeer,
      peers: state.session.peers,
      setServerUrl: state.session.setServerUrl,
      setRoomId: state.session.setRoomId,
      setLocalPeerConfig: state.session.setLocalPeerConfig,
      setIdentifying: state.session.setIdentifying,
    }))
  );

export const usePeerLayoutEditorSession = () =>
  useAppStore(
    useShallow((state) => ({
      peers: state.session.peers,
      localPeer: state.session.localPeer,
      localPeerId: state.session.localPeerId,
      virtualDesktop: state.session.virtualDesktop,
      updatePeer: state.session.updatePeer,
      setLocalPeerConfig: state.session.setLocalPeerConfig,
    }))
  );

export const useDisplayOverlaySession = () =>
  useAppStore(
    useShallow((state) => ({
      localPeerId: state.session.localPeerId,
      peers: state.session.peers,
    }))
  );

export const useDiagnosticSession = () =>
  useAppStore(
    useShallow((state) => ({
      isConnected: state.session.isConnected,
      localPeerId: state.session.localPeerId,
      localPeer: state.session.localPeer,
      virtualDesktop: state.session.virtualDesktop,
      peers: state.session.peers,
    }))
  );

export const useEntityFlowSession = () =>
  useAppStore(
    useShallow((state) => ({
      isConnected: state.session.isConnected,
      localPeerWidth: state.session.localPeer.width,
      localPeerHeight: state.session.localPeer.height,
      virtualDesktop: state.session.virtualDesktop,
      localPeerId: state.session.localPeerId,
      updateLocalPeerDimensions: state.session.updateLocalPeerDimensions,
    }))
  );

export const useSessionPeerCount = () =>
  useAppStore((state) => state.session.peers.size);

export const useSessionConnectionStatus = () =>
  useAppStore((state) => state.session.isConnected);
