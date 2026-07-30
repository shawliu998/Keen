import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AgentMode, LearningTask, MemoryItem } from "@keen/domain";
import { learningTasks, memories } from "../data/seed";

export type ContextDrawerView = "activity" | "sources" | "outline";
export type InspectorContent = {
  title: string;
  eyebrow?: string;
  body: string;
  meta?: string[];
  kind?: Exclude<ContextDrawerView, "activity">;
} | null;

type AppState = {
  sidebarCollapsed: boolean;
  inspectorOpen: boolean;
  drawerView: ContextDrawerView;
  commandOpen: boolean;
  agentMode: AgentMode;
  tasks: LearningTask[];
  memories: MemoryItem[];
  inspector: InspectorContent;
  toggleSidebar: () => void;
  toggleInspector: () => void;
  openDrawer: (view: ContextDrawerView) => void;
  closeDrawer: () => void;
  setDrawerView: (view: ContextDrawerView) => void;
  setCommandOpen: (open: boolean) => void;
  setAgentMode: (mode: AgentMode) => void;
  setInspector: (content: InspectorContent) => void;
  updateTask: (id: string, status: LearningTask["status"]) => void;
  toggleMemory: (id: string) => void;
  deleteMemory: (id: string) => void;
};

export const useAppStore = create<AppState>()(persist((set) => ({
  sidebarCollapsed: false,
  inspectorOpen: false,
  drawerView: "activity",
  commandOpen: false,
  agentMode: "Teach",
  tasks: learningTasks,
  memories,
  inspector: null,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleInspector: () => set((s) => ({
    inspectorOpen: !s.inspectorOpen,
    drawerView: s.inspector ? s.inspector.kind ?? "sources" : "activity",
  })),
  openDrawer: (drawerView) => set({ inspectorOpen: true, drawerView }),
  closeDrawer: () => set({ inspectorOpen: false }),
  setDrawerView: (drawerView) => set({ drawerView }),
  setCommandOpen: (commandOpen) => set({ commandOpen }),
  setAgentMode: (agentMode) => set({ agentMode }),
  setInspector: (inspector) => set((state) => inspector
    ? { inspector, inspectorOpen: true, drawerView: inspector.kind ?? "sources" }
    : { inspector: null, inspectorOpen: state.drawerView === "sources" ? false : state.inspectorOpen }),
  updateTask: (id, status) => set((s) => ({ tasks: s.tasks.map((task) => task.id === id ? { ...task, status } : task) })),
  toggleMemory: (id) => set((s) => ({ memories: s.memories.map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item) })),
  deleteMemory: (id) => set((s) => ({ memories: s.memories.filter((item) => item.id !== id) })),
}), { name: "keen-desktop-state", partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, tasks: s.tasks, memories: s.memories, agentMode: s.agentMode }) }));
