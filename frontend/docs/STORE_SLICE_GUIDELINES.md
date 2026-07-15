# Zustand Store & Slice Guidelines

**Date:** 2026-03-01  
**Context:** Guidelines derived from a review of `src/stores/` to prevent recurring anti-patterns.

---

## When to Create a New Slice

A slice should represent a **single domain of state** with clear boundaries. Ask these questions:

1. **Does this state have a distinct lifecycle?** Session state (connect/disconnect) lives and dies independently from graph data (load/clear). They should be separate slices.

2. **Would changes to this state cause unrelated components to re-render?** If loading state and partition visibility flags live together, toggling partitions forces re-renders in components that only care about loading. Split them.

3. **Can you name the slice in 1-2 words?** If you can't (e.g., "graph data and chat integration and display settings and loading"), it's doing too much.

**Rule of thumb:** If a slice exceeds ~150-200 lines or has more than ~8-10 actions, it's a candidate for splitting.

## When NOT to Create a New Slice

- Don't split state that is **always read and written together**. For example, `nodes` and display settings are almost always consumed as a pair -- putting them in separate slices creates unnecessary cross-slice reads.
- Don't create a slice for a single boolean flag. Use an existing related slice.

---

## Facade Hooks: Selectors, Not Full-Slice Subscriptions

Returning the entire slice object from a facade hook defeats Zustand's selective re-rendering. Every field mutation triggers re-renders in all consumers.

**Guideline:** Facade hooks should expose **granular selectors grouped by use case**, not the raw slice.

```ts
// BAD -- subscribes to everything in the ui slice
export const useUIStore = () => useAppStore((s) => s.ui);

// GOOD -- subscribe only to what you need, with shallow comparison
import { useShallow } from 'zustand/react/shallow';

export const useSidebars = () => useAppStore(
  useShallow((s) => ({
    leftSidebarOpen: s.ui.leftSidebarOpen,
    rightSidebarOpen: s.ui.rightSidebarOpen,
    toggleSidebar: s.ui.toggleSidebar,
  }))
);
```

If a component needs fields from multiple selectors, call multiple hooks. Each hook only triggers re-renders when its specific fields change.

---

## Actions: Keep Them Pure, Push Side Effects Out

Store actions should only call `set()` and optionally `get()`. External side effects (network calls, Yjs broadcasts, localStorage writes) should be handled via:

- Zustand's `subscribe` / `subscribeWithSelector` in the service layer
- Or explicitly by the calling component/hook

This eliminates the need for "silent" action variants (e.g., `_setActivePanelSilent`) that exist solely to prevent broadcast loops.

```ts
// BAD -- side effect embedded in action, requires a _silent duplicate
setActivePanel: (entityId) => {
  broadcastUIState('activePanelId', entityId);
  set((state) => ({ entity: { ...state.entity, activePanelId: entityId } }));
},
_setActivePanelSilent: (entityId) => {
  set((state) => ({ entity: { ...state.entity, activePanelId: entityId } }));
},

// GOOD -- action is pure, broadcast handled externally via subscribe
setActivePanel: (entityId) => {
  set((state) => ({ entity: { ...state.entity, activePanelId: entityId } }));
},
// In yjs service layer:
// useAppStore.subscribe(
//   (s) => s.entity.activePanelId,
//   (entityId) => broadcastUIState('activePanelId', entityId)
// );
```

---

## State Shape: Prefer Serializable Types

`Map` and `Set` work in Zustand but break DevTools inspection and prevent `persist` middleware.

**Guideline:** Unless there is a strong performance reason (e.g., O(1) lookups on thousands of entries), prefer `Record<string, T>` and `string[]`.

| Type | Use When |
|------|----------|
| `Record<string, T>` | ID-keyed lookups with moderate size, need DevTools visibility |
| `Map<string, T>` | Very frequent mutation/lookup on large collections where perf matters |
| `string[]` | Small sets, consumed once and cleared (e.g., highlight IDs) |
| `Set<string>` | Only if membership checks dominate and the set is large |

---

## Cross-Slice Reads: Make Dependencies Explicit

Reading another slice's state via `get()` inside an action creates implicit coupling that is hard to trace and test.

**Guideline:** If an action needs data from another slice, prefer **passing it as a parameter** from the call site.

```ts
// BAD -- implicit dependency on session slice
setGraphData: (data) => {
  set((state) => {
    const displayId = state.session.localPeerId ?? '__local__';
    // ...
  });
}

// BETTER -- explicit dependency, easier to test and trace
setGraphData: (data, localPeerId: string | null) => {
  set((state) => {
    const displayId = localPeerId ?? '__local__';
    // ...
  });
}
```

---

## General Code Quality in Stores

These align with the project's `code_writing_tips.md`:

- **No magic numbers.** Extract width bounds, default values, etc. into named constants.
- **No debug logging in actions.** Remove `console.group`/`console.log` or guard behind `import.meta.env.DEV`.
- **DRY initial/reset state.** If the same default values appear in initial state and reset actions, extract to a constant or factory function.
- **No `undefined` in state.** Be explicit about initial values (`null`, empty string, `false`). Spreading `undefined` as a no-op is obscure.
- **Consistent no-op guards.** If high-frequency actions (e.g., position updates) guard against no-ops for performance, document the convention so similar actions follow the same pattern.

---

## Checklist for New State

Before adding state to a store, run through this:

| Question | Action |
|----------|--------|
| Does this belong to an existing domain? | Add to that slice |
| Is the slice already > 150 lines / 10 actions? | Split the slice first |
| Will I need a `_silent` variant of an action? | Push the side effect out of the action |
| Am I using Map/Set? | Consider Record/array unless performance demands it |
| Am I reading another slice inside an action? | Pass the value as a parameter instead |
| Does my facade hook return the whole slice? | Use `useShallow` with specific fields |
| Are there magic numbers or duplicated defaults? | Extract to named constants |
