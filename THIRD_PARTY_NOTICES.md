# Third-Party Notices

**Status: incomplete working inventory — not a release-ready notice bundle.**

At the initial repository audit on 2026-07-15, no third-party dependency or source code had been incorporated into Keen. Package dependencies and a generated Python sidecar have since been introduced. The records below cover only artifacts whose license files were directly inspected; they do not reconcile every JavaScript, Rust, Python, Python-runtime, or frozen-sidecar dependency.

The projects listed only as candidates in `docs/OPEN_SOURCE_INVENTORY.md` are **not** included merely because they are listed there.

## Verified current component records

### Appica UI visual-system adaptation

- Use: bounded visual and interaction adaptation for Keen-owned Button, Field,
  Card, Badge and Progress primitives; the Appica React package is not installed
  or distributed.
- Source: `https://github.com/appica-dev/appica-ui`
- Exact reviewed commit: `26de9b1e02d2fb48694ae52d2371b1bbd71ee9d6`
- Evidence: exact root `LICENSE` and `packages/react/package.json` declare MIT;
  no root `NOTICE` was found.

MIT License

Copyright (c) 2026 Appica UI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### keyring 3.6.3

- Use: ordinary direct Rust dependency for provider API-secret storage in the macOS Keychain. Keen enables only `apple-native` with default features disabled; no keyring source is copied, patched, or vendored.
- Artifact: crates.io `keyring-3.6.3.crate`, registry source `registry+https://github.com/rust-lang/crates.io-index`.
- SHA-256 / Cargo.lock checksum: `eebcc3aff044e5944a8fbaf69eb277d11986064cba30c468730e8b9909fb551c`.
- Source: the published manifest identifies `https://github.com/hwchen/keyring-rs.git`; embedded Cargo VCS metadata reports revision `315cbdf6c6a9153d8c9f88b56568f29862d3e39d`.
- Evidence: the exact archive declares `MIT OR Apache-2.0`, contains `LICENSE-MIT` and `LICENSE-APACHE`, and has no `NOTICE` or `COPYING` file. Keen elects the MIT option and reproduces its exact text below.
- macOS transitive boundary: `apple-native` selects `security-framework` 3.7.0, which resolves `security-framework-sys` 2.17.0 and `core-foundation` 0.10.1. The exact `security-framework` package contains a `THIRD_PARTY` file stating that documentation was adapted from Apple under APSL-2.0. That package-level text and the remaining Rust transitive notices still require final shipped-target reconciliation; this keyring record does not claim that the overall notice bundle is complete.

Copyright (c) 2016 keyring Developers

Permission is hereby granted, free of charge, to any
person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the
Software without restriction, including without
limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice
shall be included in all copies or substantial portions
of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF
ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

### PDF.js / pdfjs-dist 5.4.624

- Use: local rendering of one authenticated PDF citation page at a time. The PDF.js worker is bundled with Keen; no CDN is used.
- Artifact: npm tarball `pdfjs-dist-5.4.624.tgz`.
- SHA-256: `5c387457cd03cc2e7b9c9b1ed642e8148d1ba44c3b8e5b5b771526feb24b61b9`.
- Source: `https://github.com/mozilla/pdf.js`, exact upstream tag commit `384c6208b257e81fa7bcd4e59dc100e3c99d9528`.
- Evidence: exact tarball `package/LICENSE` and `package.json` declare Apache License 2.0; the tarball has no root `NOTICE`. Keen does not configure the package's optional CMap, standard-font, or WASM resource directories for this viewer. Final bundle inspection remains required.
- License: Apache License 2.0, Version 2.0, January 2004 (`https://www.apache.org/licenses/LICENSE-2.0`). The exact license text is present in the locked installed package and must be reproduced in the packaged notice set; this working inventory remains explicitly incomplete until the distribution-wide Apache text reconciliation is finished.

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

### pdfminer.six 20260107

- Use: runtime PDF layout analysis for page, text-block, and span bounding boxes; no OCR or rendering.
- Artifact: `pdfminer_six-20260107-py3-none-any.whl`.
- SHA-256: `366585ba97e80dffa8f00cebe303d2f381884d8637af4ce422f1df3ef38111a9`.
- Source: `https://github.com/pdfminer/pdfminer.six`, tag `20260107`, commit `9e1243c4ad000bf9bbe60e81fc8dde2fccc0ed3b`.
- Evidence: the exact wheel declares MIT and embeds the main `LICENSE`. The exact source contains no NOTICE and additionally carries `docs/licenses/LICENSE.pyHanko`, also MIT, for elements based on pyHanko. The wheel does not embed that second file, so both inspected texts are retained here.
- Locked runtime: `charset-normalizer` 3.4.9 and `cryptography` 49.0.0, with `cffi` 2.1.0 and `pycparser` 3.0, are hashed in the CPython 3.11/macOS arm64 lock and verified in the frozen sidecar and mounted DMG. Their complete installed notices still require distribution-wide reconciliation.

Main pdfminer.six license:

Copyright (c) 2004-2016  Yusuke Shinyama <yusuke at shinyama dot jp>

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Notice for elements based on pyHanko:

This package contains various elements based on code from the pyHanko project, of which we reproduce the license below.

MIT License

Copyright (c) 2020 Matthias Valvekens

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### sqlite-vec 0.1.9

- Use: native SQLite vector storage and exact K-nearest-neighbor queries behind Keen's owned vector-store interface.
- Artifact: `sqlite_vec-0.1.9-py3-none-macosx_11_0_arm64.whl`.
- SHA-256: `1d52e30513bae4cc9778ddbf6145610434081be4c3afe57cd877893bad9f6b6c`.
- Source: `https://github.com/asg017/sqlite-vec`, tag `v0.1.9`, commit `e9f598abfa0c06b328d8fe5da9c3760cce74be10`.
- Evidence: the exact tag contains `LICENSE-MIT` and `LICENSE-APACHE` and no `NOTICE`; Keen elects the MIT option. The wheel metadata says MIT/Apache-2.0 but does not carry either license file, so the selected exact text is reproduced here. The wheel contains the arm64 native library `sqlite_vec/vec0.dylib`, which will enter the frozen sidecar.

MIT License

Copyright (c) 2024 Alex Garcia

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### HTTPX 0.28.1

- Use: runtime async HTTP client for explicitly configured loopback-only embedding providers.
- Artifact: `httpx-0.28.1-py3-none-any.whl`.
- SHA-256: `d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad`.
- Source: `https://github.com/encode/httpx`, tag `0.28.1`, commit `26d48e0634e6ee9cdc0533996db289ce4b430177`.
- Evidence: the exact wheel `METADATA` declares BSD-3-Clause and supports Python 3.11; `httpx-0.28.1.dist-info/licenses/LICENSE.md` exactly matches the inspected tag's `LICENSE.md`. The tag contains no `NOTICE` file.

Copyright © 2019, Encode OSS Ltd.
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

- Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
- Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
- Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The 2026-07-16 CPython 3.11/macOS arm64 runtime lock for this exact HTTPX wheel also selects the following pure-Python runtime artifacts. The lock fixes their wheel URLs and SHA-256 hashes; the table still does not replace their complete license texts:

| Component | Snapshot artifact and SHA-256 | Inspected license evidence | Remaining distribution work |
| --- | --- | --- | --- |
| `httpcore` 1.0.9 | `httpcore-1.0.9-py3-none-any.whl`; `2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55` | BSD-3-Clause; embedded `httpcore-1.0.9.dist-info/licenses/LICENSE.md` | Reproduce its complete BSD notice from the final locked artifact |
| `anyio` 4.14.2 | `anyio-4.14.2-py3-none-any.whl`; `9f505dda5ac9f0c8309b5e8bd445a8c2bf7246f3ce950121e45ea15bc41d1494` | MIT; embedded `anyio-4.14.2.dist-info/licenses/LICENSE` | Reproduce its complete MIT notice from the final locked artifact |
| `certifi` 2026.6.17 | `certifi-2026.6.17-py3-none-any.whl`; `2227dcbaafe0d2f59279d1762ddddc37783ed4354594f194ffc31d20f41fc3db` | MPL-2.0; embedded `certifi-2026.6.17.dist-info/licenses/LICENSE` | Reproduce the full MPL-2.0 text and reconcile source-form availability and the bundled CA certificate data in the final distribution |
| `idna` 3.18 | `idna-3.18-py3-none-any.whl`; `7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2` | BSD-3-Clause; embedded `idna-3.18.dist-info/licenses/LICENSE.md` | Reproduce its complete BSD notice from the final locked artifact |
| `h11` 0.16.0 | `h11-0.16.0-py3-none-any.whl`; `63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86` | MIT; embedded `h11-0.16.0.dist-info/licenses/LICENSE.txt` | Reproduce its complete MIT notice from the final locked artifact |
| `typing_extensions` 4.16.0 | `typing_extensions-4.16.0-py3-none-any.whl`; `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` | PSF-2.0; embedded `typing_extensions-4.16.0.dist-info/licenses/LICENSE` | Required on Python 3.11 by this AnyIO snapshot; reproduce the complete PSF license from the final locked artifact |

`sniffio` is imported only as an optional compatibility path in this snapshot and was not selected or installed by the Python 3.11 resolver. Its separately inspected 1.3.1 wheel is dual MIT/Apache-2.0, but it is not a current shipped-component record. Re-audit it only if the final runtime lock or frozen artifact actually includes it.

### py-fsrs 6.3.1

- Use: deterministic FSRS review scheduling behind Keen's owned adapter; concept mastery is kept separate.
- Artifact: `fsrs-6.3.1-py3-none-any.whl`.
- SHA-256: `ac1bf9939573592d8c9bc1e11a00bd17e04146dc9f2c913127e2bcc431b9040b`.
- Source: `https://github.com/open-spaced-repetition/py-fsrs`, tag `v6.3.1`, commit `3abe686e9c058d3f3c00bbeb92e68b71211b2b31`.
- Evidence: the exact wheel and tag contain the same MIT license. The tag contains no NOTICE or COPYING file, and the inspected runtime Python files have no separate copyright or SPDX headers. The wheel declares Python >=3.10 and only `typing-extensions` as a runtime dependency; optimizer extras are not installed.

MIT License

Copyright (c) 2022 Open Spaced Repetition

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

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

- DeepTutor was inspected in `/tmp` at review SHA `3e3b9a6ecbfe8f921b34462cdb93b57f51d3552a`. Its root license was verified as Apache License 2.0 with a 2025 Data Intelligence Lab, The University of Hong Kong copyright statement. No DeepTutor code or asset is stored in the Keen repository/runtime/distribution. The upstream Home screenshot and `logo.png`, `banner.png`, and `logo_black.png` are retained only in private Figma reference nodes `252:202` and `257:157`.
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
