import { StateCreator } from 'zustand';
import type { AppState } from '../appStore';
import type { Entity, EntityPanelData } from '@/types/entity';
import { broadcastUIState } from '@/services/yjsService';
import type { SyncSource } from './syncSource';

export interface EntityState {
  // Panels
  openPanels: Map<string, EntityPanelData>;
  activePanelId: string | null;

  // Actions
  openEntityPanel: (entityId: string, entity: Entity) => void;
  closeEntityPanel: (entityId: string) => void;
  setActivePanel: (entityId: string, source?: SyncSource) => void;
  updatePanelData: (entityId: string, data: Partial<EntityPanelData>) => void;
  closeAllPanels: (source?: SyncSource) => void;
  openAllEntities: (entities: Entity[]) => void;

  resetEntityState: () => void;
}

export interface EntitySlice {
  entity: EntityState;
}

export const createEntitySlice: StateCreator<AppState, [], [], EntitySlice> = (set) => ({
  entity: {
    // Initial state
    openPanels: new Map(),
    activePanelId: null,

    // Actions
    openEntityPanel: (entityId: string, entity: Entity) => {
      set((state) => {
        const newPanels = new Map(state.entity.openPanels);
        
        if (!newPanels.has(entityId)) {
          newPanels.set(entityId, {
            entityId,
            entity,
            isFloating: false,
            isMaximized: false,
          });
        }
        
        return {
          entity: {
            ...state.entity,
            openPanels: newPanels,
            activePanelId: entityId,
          }
        };
      });
    },

    closeEntityPanel: (entityId: string) => {
      set((state) => {
        const newPanels = new Map(state.entity.openPanels);
        newPanels.delete(entityId);
        
        // If we're closing the active panel, clear active
        const newActivePanelId = state.entity.activePanelId === entityId ? null : state.entity.activePanelId;
        
        return {
          entity: {
            ...state.entity,
            openPanels: newPanels,
            activePanelId: newActivePanelId,
          }
        };
      });
    },

    setActivePanel: (entityId: string, source: SyncSource = 'local') => {
      if (source === 'local') {
        broadcastUIState('activePanelId', entityId);
      }
      set((state) => ({
        entity: { ...state.entity, activePanelId: entityId }
      }));
    },

    updatePanelData: (entityId: string, data: Partial<EntityPanelData>) => {
      set((state) => {
        const newPanels = new Map(state.entity.openPanels);
        const existingPanel = newPanels.get(entityId);
        
        if (existingPanel) {
          newPanels.set(entityId, { ...existingPanel, ...data });
        }
        
        return {
          entity: { ...state.entity, openPanels: newPanels }
        };
      });
    },

    closeAllPanels: (source: SyncSource = 'local') => {
      if (source === 'local') {
        broadcastUIState('activePanelId', null);
      }
      set((state) => ({
        entity: {
          ...state.entity,
          openPanels: new Map(),
          activePanelId: null,
        }
      }));
    },

    resetEntityState: () => {
      set((state) => ({
        entity: {
          ...state.entity,
          openPanels: new Map(),
          activePanelId: null,
        }
      }));
    },

    openAllEntities: (entities: Entity[]) => {
      set((state) => {
        const newPanels = new Map<string, EntityPanelData>();
        
        entities.forEach((entity) => {
          newPanels.set(entity.id, {
            entityId: entity.id,
            entity,
            isFloating: false,
            isMaximized: false,
          });
        });
        
        return {
          entity: {
            ...state.entity,
            openPanels: newPanels,
            activePanelId: entities.length > 0 ? entities[0].id : null,
          }
        };
      });
    },
  }
});
