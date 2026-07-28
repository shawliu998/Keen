# Targeted frontend tests

Command:

`npm run test --workspace=@keen/desktop -- historyPage.test.tsx learningCore.integration.test.tsx agentHome.integration.test.tsx flashcardsPage.test.tsx settingsBrowserDemo.test.tsx settingsProviderRecovery.test.tsx app.test.tsx activeRecallPage.test.tsx`

Result: **8 files passed, 158 tests passed, exit 0**.

The suite includes:

- Home Ask/Study creation and provider recovery;
- Knowledge Base empty/live/import states;
- History empty, partial, service failure, mastery, and cached-refetch continuity;
- Review loading, error, reveal/rating, formula display, and completion;
- Settings Browser Demo refusal, provider save/restart/test, and return-to-learning continuity;
- release navigation and Deep Learn active recall.

After the final Review empty-state copy change:

`npm run test --workspace=@keen/desktop -- flashcardsPage.test.tsx`

Result: **1 file passed, 21 tests passed, exit 0**.

The only emitted warnings are the existing React Router v7 future-flag notices.
