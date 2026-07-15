# Third-Party Notices

**Status: incomplete working inventory — not a release-ready notice bundle.**

At the initial repository audit on 2026-07-15, no third-party dependency or source code had been incorporated into Keen. Package dependencies and a generated Python sidecar have since been introduced. The records below cover only artifacts whose license files were directly inspected; they do not reconcile every JavaScript, Rust, Python, Python-runtime, or frozen-sidecar dependency.

The projects listed only as candidates in `docs/OPEN_SOURCE_INVENTORY.md` are **not** included merely because they are listed there.

## Verified current component records

### pypdf 6.14.2

- Use: runtime PDF text extraction, one page at a time; no OCR, geometry, or rendering.
- Artifact: `pypdf-6.14.2-py3-none-any.whl`.
- SHA-256: `3f07891af76dc002657e04993ab9b4de81de29f9013b9761d0b7968bff12e946`.
- Evidence: wheel `METADATA` declares `License-Expression: BSD-3-Clause`; `pypdf-6.14.2.dist-info/licenses/LICENSE` was read from the exact wheel.

Copyright (c) 2006-2008, Mathieu Fenniak

Some contributions copyright (c) 2007, Ashish Kulkarni <kulkarni.ashish@gmail.com>

Some contributions copyright (c) 2014, Steve Witham <switham_github@mac-guyver.com>

All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

- Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
- Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
- The name of the author may not be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

### python-multipart 0.0.32

- Use: runtime parsing of multipart document uploads.
- Artifact: `python_multipart-0.0.32-py3-none-any.whl`.
- SHA-256: `ff6d3f776f16878c894e52e107296ffc890e913c611b1a4ec6c44e2821fe2e23`.
- Evidence: wheel `METADATA` declares `License-Expression: Apache-2.0`; `python_multipart-0.0.32.dist-info/licenses/LICENSE.txt` contains the Apache License 2.0.
- Outstanding: the complete Apache License 2.0 text and any package-level NOTICE determination must be included in the final distributed notice set. This entry is not a substitute for that text.

### PyInstaller 6.21.0

- Use: pinned build tool that creates the one-file learning-core executable embedded as Tauri `externalBin`.
- Evidence: exact installed distribution metadata and `pyinstaller-6.21.0.dist-info/licenses/COPYING.txt` were inspected; source project is `https://github.com/pyinstaller/pyinstaller`.
- Terms observed: PyInstaller is GPL version 2 or later. Its inspected **Bootloader Exception** gives unlimited permission to link or embed compiled bootloader and related files into combinations with other programs and distribute those combinations without restriction arising from use of those files; the exception identifies `./bootloader/` and `./PyInstaller/loader` as bootloader/related files. PyInstaller runtime hooks are Apache-2.0.
- Copyright evidence observed in `COPYING.txt`: copyright 2010-2023 PyInstaller Development Team; copyright 2005-2009 Giovanni Bajo; based on previous work copyright 2002 McMillan Enterprises, Inc.
- Outstanding: reproduce/reconcile the complete applicable `COPYING.txt`, Bootloader Exception, runtime-hook terms, embedded Python runtime, and every frozen dependency in the shipped artifact. The summary above is not a complete license text.

### PyInstaller community hooks 2026.6

- Use: build-time hook set used while freezing the sidecar.
- Evidence: exact installed distribution metadata and `pyinstaller_hooks_contrib-2026.6.dist-info/licenses/LICENSE` were inspected; source project is `https://github.com/pyinstaller/pyinstaller-hooks-contrib`.
- Terms observed: standard hooks/files are GPL-2.0-or-later; runtime hooks under `_pyinstaller_hooks_contrib/rthooks` are Apache-2.0.
- Outstanding: determine the exact standard/runtime hook subset affecting or entering the frozen executable and include all applicable full texts. This mixed-license summary is not a complete shipped notice.

## Reviewed upstreams not distributed with Keen

- DeepTutor was inspected in `/tmp` at review SHA `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a`. Its root license was verified as Apache License 2.0 with a 2025 Data Intelligence Lab, The University of Hong Kong copyright statement. No DeepTutor code or assets were copied into Keen.
- OATutor-LLM-Learner was inspected in `/tmp` at review SHA `0d376e23302485bebef6e1cad04da3816a164cd6`. Its root license was verified as MIT with a 2023 Zachary A. Pardos / CAHL research lab copyright statement. No OATutor code, content, parameters, or assets were copied into Keen.

These review records are not notices for shipped software. Do not add their full license text to a Keen distribution unless material from that upstream is actually introduced and its exact source paths, revision, modifications, embedded third-party material, and required notices are recorded.

## Outstanding distribution reconciliation

First-round metadata reports under `artifacts/license-scan/` covered the then-resolved npm, Cargo, and Python development environments. The dependency graph has since changed, and those reports establish inventory evidence rather than a complete notice bundle.

Before release, at minimum:

- regenerate the actually shipped macOS-target JavaScript, Rust, Python, Python-runtime, PyInstaller, and hook inventory from stable locks/build artifacts;
- inspect and reproduce all required installed license, copyright, attribution, source-offer, and NOTICE text, including the unresolved CC-BY-4.0 npm data-package attribution noted in the first scan;
- place the same complete notice set in the repository and packaged application/installer;
- verify the exact contents of a current `.app` and DMG rather than inheriting evidence from earlier bundles; and
- complete Cargo vulnerability auditing and rerun vulnerability/license checks against the release locks.

Any arm64 development `.app` or DMG built from this tree must not be treated as release-ready, even when checksum, architecture, launch, and ad-hoc signature checks pass. Packaging this incomplete working file is useful for audit visibility but does not satisfy the complete-notice requirement. Distribution signing, notarization, Intel/Universal validation, stable release locks, and complete notices remain open.
