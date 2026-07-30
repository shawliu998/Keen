# Visual-regression command

Command:

`npm run visual:test`

Result: **capture completed, process exit 1**.

The harness successfully captured all configured routes after the stale Settings action name was corrected from `Capabilities` to `Model`.

Why the gate is not green:

- most historical `references/visual-baselines/*` files are absent in this worktree and are reported as `missing_reference`;
- the current Home and Learning Feed intentionally differ from their zero-threshold Keen baselines by 3.0613% and 3.3020%;
- provisional Figma comparisons remain comparison-only, including Home 3.2237%, Feed 3.3007%, Task Detail 5.8755%, Deep Learn 3.5183%, and Feed failure states 2.3838–3.6954%.

The current report is `artifacts/visual-diff/report.json`. This round does not silently accept or overwrite baselines and makes no pixel-parity claim.
