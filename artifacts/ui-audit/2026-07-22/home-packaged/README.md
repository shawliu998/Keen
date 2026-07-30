# Home packaged WebView acceptance

Date: 2026-07-22

Bundle: local ad-hoc `Keen Dev.app` (`com.keen.learning.dev`), rebuilt from the current worktree with the bundled learning-core sidecar. The captures are 1220×768 image pixels and show a healthy local core. They are proportional product evidence, not accepted visual-regression references or pixel-parity evidence.

- `03-saved-work-fixed-current-debug.png`: current saved-work Home state.
- `04-live-task-detail-fixed.png`: the exact persisted task opened by Home's `/feed?task=…` continuation; heading focus is visible in the accessibility tree.
- `05-new-learning-current-debug.png`: current explicit New learning state with live source scope.

Native Tab traversal reached Ask sources, Focused study, Question source scope and Message Keen in order before returning to the shell. Tauri's configured minimum is 1180×740, so the separate 760×700 browser capture is not a native-window claim. The current packaged media query was not forced to reduced motion.

`01-saved-work-current-debug.png` and `02-continued-task-detail.png` are retained as rejected iteration evidence: they exposed a Demo/live task-id precedence defect and are not final acceptance images.
