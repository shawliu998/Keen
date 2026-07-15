# Third-Party Notices

At the initial repository audit on 2026-07-15, no third-party dependency or source code had been incorporated into Keen. Accordingly, there are no third-party notice texts to reproduce in this file yet.

The projects listed as candidates in `docs/OPEN_SOURCE_INVENTORY.md` are **not** included merely because they are listed there.

## Reviewed upstreams not distributed with Keen

- DeepTutor was inspected in `/tmp` at review SHA `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a`. Its root license was verified as Apache License 2.0 with a 2025 Data Intelligence Lab, The University of Hong Kong copyright statement. No DeepTutor code or assets were copied into Keen.
- OATutor-LLM-Learner was inspected in `/tmp` at review SHA `0d376e23302485bebef6e1cad04da3816a164cd6`. Its root license was verified as MIT with a 2023 Zachary A. Pardos / CAHL research lab copyright statement. No OATutor code, content, parameters, or assets were copied into Keen.

These review records are not notices for shipped software. Do not include the full upstream license text in a Keen distribution unless material from that upstream is actually introduced and its exact source paths, revision, modifications, embedded third-party material, and required notices are recorded.

First-round implementation now incorporates package dependencies from the Rust, JavaScript, and Python ecosystems. Resolved metadata reports were generated under `artifacts/license-scan/` and summarized in `docs/OPEN_SOURCE_INVENTORY.md`: 307 external npm packages reported license metadata, 442 of 443 Cargo packages reported license metadata (the null record is Keen itself), and the resolved Python development environment was scanned with `pip-licenses`. Top-level runtime families include Tauri and official plugins, React/React Router, TanStack Query, Zustand, Zod, Lucide, FastAPI, Pydantic, and Uvicorn.

Those reports establish an inventory, not a complete notice bundle. The current arm64 development `.app` and `.dmg` must not be treated as release-ready distribution artifacts until the actually bundled macOS-target subset is reconciled against installed license/NOTICE files and all required texts and attributions are included here and inside the app. In particular, the npm metadata includes a CC-BY-4.0 data-package record that requires manual attribution review, and Cargo vulnerability auditing remains open.

When third-party material is introduced, update this file from the exact installed artifact or checked-out revision. Preserve required copyright and `NOTICE` text, identify modifications where required, and ensure the same notices ship in source and packaged distributions. Do not infer a license or notice from a project name, memory, or an unrelated release.
