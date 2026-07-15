import type { StateCreator } from 'zustand';
import type { AppState } from '../../appStore';

export type AppSet = Parameters<StateCreator<AppState>>[0];
