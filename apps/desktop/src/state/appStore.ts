import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AgentMode, LearningTask, MemoryItem } from "@keen/domain";
import { learningTasks, memories } from "../data/seed";

type InspectorContent = { title: string; eyebrow?: string; body: string; meta?: string[] } | null;

type AppState = {
  sidebarCollapsed: boolean;
  inspectorOpen: boolean;
  commandOpen: boolean;
  agentMode: AgentMode;
  tasks: LearningTask[];
  memories: MemoryItem[];
  inspector: InspectorContent;
  toggleSidebar: () => void;
  toggleInspector: () => void;
  setCommandOpen: (open: boolean) => void;
  setAgentMode: (mode: AgentMode) => void;
  setInspector: (content: InspectorContent) => void;
  updateTask: (id: string, status: LearningTask["status"]) => void;
  toggleMemory: (id: string) => void;
  deleteMemory: (id: string) => void;
};

export const useAppStore = create<AppState>()(persist((set) => ({
  sidebarCollapsed: false,
  inspectorOpen: true,
  commandOpen: false,
  agentMode: "Teach",
  tasks: learningTasks,
  memories,
  inspector: null,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleInspector: () => set((s) => ({ inspectorOpen: !s.inspectorOpen })),
  setCommandOpen: (commandOpen) => set({ commandOpen }),
  setAgentMode: (agentMode) => set({ agentMode }),
  setInspector: (inspector) => set({ inspector, inspectorOpen: true }),
  updateTask: (id, status) => set((s) => ({ tasks: s.tasks.map((task) => task.id === id ? { ...task, status } : task) })),
  toggleMemory: (id) => set((s) => ({ memories: s.memories.map((item) => item.id === id ? { ...item, enabled: !item.enabled } : item) })),
  deleteMemory: (id) => set((s) => ({ memories: s.memories.filter((item) => item.id !== id) })),
}), { name: "keen-desktop-state", partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, tasks: s.tasks, memories: s.memories, agentMode: s.agentMode }) }));
