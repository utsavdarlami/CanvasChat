import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from './appStore';

export const useEntityFlowGraph = () =>
  useAppStore(
    useShallow((state) => ({
      nodes: state.graph.nodes,
      currentEntities: state.graph.currentEntities,
      graphMetadata: state.graph.graphMetadata,
      chatUpdatedNodeIds: state.graph.chatUpdatedNodeIds,
      highlightedNodeIds: state.graph.highlightedNodeIds,
      pendingCameraCommand: state.graph.pendingCameraCommand,
      setNodePositionsBulk: state.graph.setNodePositionsBulk,
      clearChatUpdatedNodeIds: state.graph.clearChatUpdatedNodeIds,
      clearHighlightedNodeIds: state.graph.clearHighlightedNodeIds,
      setPendingCameraCommand: state.graph.setPendingCameraCommand,
    }))
  );

export const useGraphNodes = () =>
  useAppStore((state) => state.graph.nodes);

export const useGraphCurrentEntities = () =>
  useAppStore((state) => state.graph.currentEntities);

export const useGraphUploadActions = () =>
  useAppStore(
    useShallow((state) => ({
      setGraphData: state.graph.setGraphData,
      setOriginalData: state.graph.setOriginalData,
      setLoading: state.graph.setLoading,
      setError: state.graph.setError,
    }))
  );
