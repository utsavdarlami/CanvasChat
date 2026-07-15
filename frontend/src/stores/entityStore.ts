import { useAppStore } from './appStore';

export const useResetEntityState = () =>
  useAppStore((state) => state.entity.resetEntityState);
