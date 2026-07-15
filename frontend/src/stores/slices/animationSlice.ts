import { StateCreator } from 'zustand';
import type { AppState } from '../appStore';
import type { LayoutStage } from '@/types/api';

export interface GatherTarget {
  x: number;
  y: number;
  label: string;
}

export interface AnimationState {
  /** Map of entityId -> gather target (centroid position for CSS animation) */
  gatherTargets: Record<string, GatherTarget>;
  /** Whether a gather animation is currently active */
  isGathering: boolean;

  // Actions
  setGatherTargets: (stages: LayoutStage[], source?: 'local' | 'remote') => void;
  clearGatherTargets: (source?: 'local' | 'remote') => void;
}

export interface AnimationSlice {
  animation: AnimationState;
}

/** Duration for the gather animation phase (ms) */
export const GATHER_ANIMATION_MS = 350;
/** Total delay before applying final positions (animation + buffer) */
export const GATHER_PHASE_DELAY_MS = GATHER_ANIMATION_MS + 50;

export const createAnimationSlice: StateCreator<AppState, [], [], AnimationSlice> = (set) => ({
  animation: {
    gatherTargets: {},
    isGathering: false,

    setGatherTargets: (stages: LayoutStage[], _source: 'local' | 'remote' = 'local') => {
      const targets: Record<string, GatherTarget> = {};
      for (const stage of stages) {
        for (const entityId of stage.entity_ids) {
          targets[entityId] = {
            x: stage.center[0],
            y: stage.center[1],
            label: stage.label,
          };
        }
      }
      set((state) => ({
        animation: {
          ...state.animation,
          gatherTargets: targets,
          isGathering: true,
        },
      }));
    },

    clearGatherTargets: (_source: 'local' | 'remote' = 'local') => {
      set((state) => ({
        animation: {
          ...state.animation,
          gatherTargets: {},
          isGathering: false,
        },
      }));
    },
  },
});
