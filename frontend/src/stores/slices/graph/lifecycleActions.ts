import type { GraphState } from '../graphSlice';
import type { AppSet } from './actionFactoryTypes';
import { clearAllCaches } from '@/components/EntityView/vegaSpecCache';

type GraphLifecycleActionKeys =
  | 'setLoading'
  | 'setError'
  | 'clearGraph';

export function createGraphLifecycleActions(set: AppSet): Pick<GraphState, GraphLifecycleActionKeys> {
  return {
    setLoading: (loading: boolean) => {
      set((state) => ({
        graph: {
          ...state.graph,
          isLoading: loading,
          ...(loading ? { error: null } : {}),
        }
      }));
    },

    setError: (error: string | null) => {
      set((state) => ({
        graph: { ...state.graph, error, isLoading: false }
      }));
    },

    clearGraph: () => {
      clearAllCaches();
      set((state) => ({
        graph: {
          ...state.graph,
          nodes: [],
          graphMetadata: null,
          chatUpdatedNodeIds: new Set<string>(),
          highlightedNodeIds: new Set<string>(),
          highlightedNodeColors: {},
          selectedEntityIds: new Set<string>(),
          entityTags: {},
          pendingCameraCommand: null,
          error: null,
        }
      }));
    },
  };
}
