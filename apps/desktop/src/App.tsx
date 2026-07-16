import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./shell/AppShell";
import { HomePage } from "./features/home/HomePage";
import { LearningFeedPage } from "./features/feed/LearningFeedPage";
import { KnowledgeBasePage } from "./features/knowledge/KnowledgeBasePage";
import { ConversationPage } from "./features/conversation/ConversationPage";
import { DeepLearnPage } from "./features/deep-learn/DeepLearnPage";
import { QuizPage } from "./features/quiz/QuizPage";
import { FlashcardsPage } from "./features/flashcards/FlashcardsPage";
import { PlannerPage } from "./features/planner/PlannerPage";
import { MemoryPage } from "./features/memory/MemoryPage";
import { VisualizePage } from "./features/visualize/VisualizePage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { LearningCoreProvider } from "./services/LearningCoreProvider";
import { AgentRuntimeProvider } from "./services/AgentRuntimeProvider";

export function App() {
  return (
    <LearningCoreProvider>
      <AgentRuntimeProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/feed" element={<LearningFeedPage />} />
            <Route path="/knowledge" element={<KnowledgeBasePage />} />
            <Route path="/conversation/:id?" element={<ConversationPage />} />
            <Route path="/deep-learn/:id?" element={<DeepLearnPage />} />
            <Route path="/quiz" element={<QuizPage />} />
            <Route path="/flashcards" element={<FlashcardsPage />} />
            <Route path="/planner" element={<PlannerPage />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/visualize" element={<VisualizePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AgentRuntimeProvider>
    </LearningCoreProvider>
  );
}
