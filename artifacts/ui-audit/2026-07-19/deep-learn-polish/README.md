# Deep Learn anti-AI polish evidence

Deterministic Browser Demo route: `http://127.0.0.1:1430/deep-learn/demo?course_id=demo`.

- `01-default.png`: 1280×720 default lesson.
- `00-contact-sheet.png`: default, success, paused and 900×700 states together.
- `02-answer-empty.png`: focused empty answer state.
- `03-success.png`: compact success feedback after a bundled demo answer.
- `04-paused.png`: paused state with unit and navigation controls disabled.
- `05-1024.png`: 1024×768 reduced-motion/focus check.
- `05-900.png`: 900×700 compact desktop reduced-motion/focus check.
- `06-before-after.png`: current-run audit default beside polished default.
- `07-reference-current.png`: authorized HyperKnow reading capture beside polished Keen default.

Observed checks: no horizontal overflow at 1280, 1024 or 900 CSS pixels; no duplicate IDs or unnamed focusables in the 1280 state; opening the textarea preserved `scrollY=0`; reduced motion matched; temporary extended lesson copy remained vertically scrollable without horizontal overflow; browser console/page errors were empty.

The visual-regression harness still reports `missing_reference` for all three configured pages. The source/current comparison is qualitative because the viewports, crops, content and states differ. These artifacts do not establish pixel parity, packaged Tauri behavior or a complete accessibility pass.
