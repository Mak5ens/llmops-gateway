# Changelog

## [0.2.1](https://github.com/Mak5ens/llmops-gateway/compare/v0.2.0...v0.2.1) (2026-10-10)


### Bug Fixes

* **tests:** say why the no-leak test finds fewer request bodies than calls (LAB-141) ([#45](https://github.com/Mak5ens/llmops-gateway/issues/45)) ([0b7da2b](https://github.com/Mak5ens/llmops-gateway/commit/0b7da2b3783d5cd35b4c5deb9ea13c4d2863cafc))

## [0.2.0](https://github.com/Mak5ens/llmops-gateway/compare/v0.1.0...v0.2.0) (2026-10-09)


### Features

* add an annotated dataset and a benchmark of the anonymization ([#10](https://github.com/Mak5ens/llmops-gateway/issues/10)) ([da51c0e](https://github.com/Mak5ens/llmops-gateway/commit/da51c0e0bc850d174e1dcb9776fba5f7c7968ea4))
* add per-team virtual keys, budgets and rate limits ([#4](https://github.com/Mak5ens/llmops-gateway/issues/4)) ([7639bb9](https://github.com/Mak5ens/llmops-gateway/commit/7639bb9fb13b3cbdb319546d4af93c9794424636))
* add Presidio Analyzer and Anonymizer with the French spaCy model ([#7](https://github.com/Mak5ens/llmops-gateway/issues/7)) ([f8572bc](https://github.com/Mak5ens/llmops-gateway/commit/f8572bcbbba2ce8672265f61d28c5819ebe05f7d))
* add Presidio recognizers for French personal data ([#8](https://github.com/Mak5ens/llmops-gateway/issues/8)) ([773eb1f](https://github.com/Mak5ens/llmops-gateway/commit/773eb1fa953d3aa476d00a9d2a1a4e45c723a19b))
* add self-hosted Langfuse to the local stack ([#12](https://github.com/Mak5ens/llmops-gateway/issues/12)) ([078f789](https://github.com/Mak5ens/llmops-gateway/commit/078f7898d78b2ced99675af1cc1b4784d10b35a2))
* **bench:** measure what each layer of the Analyzer adds (LAB-173) ([#23](https://github.com/Mak5ens/llmops-gateway/issues/23)) ([94168e5](https://github.com/Mak5ens/llmops-gateway/commit/94168e538d56bb5b01c3b3e185f2e86052c083bb))
* **ci:** releases with release-please, images tagged X.Y.Z for the platform's Renovate (LAB-141) ([#37](https://github.com/Mak5ens/llmops-gateway/issues/37)) ([fbb07fb](https://github.com/Mak5ens/llmops-gateway/commit/fbb07fbe708caa387871d5fb0b95bc08fb335049))
* customer service team for the demo (LAB-182) ([d19917a](https://github.com/Mak5ens/llmops-gateway/commit/d19917a26c279ab44c32d6d3e69b807cff0c6082))
* find French names without context, two-line addresses and 2-ser… ([#11](https://github.com/Mak5ens/llmops-gateway/issues/11)) ([2fd6d56](https://github.com/Mak5ens/llmops-gateway/commit/2fd6d56baf9dd9ecc83c41a1add6995e91d7628d))
* LiteLLM 1.104.1, patched Presidio, images through the platform's supply chain workflow (LAB-130) ([#26](https://github.com/Mak5ens/llmops-gateway/issues/26)) ([9e1e759](https://github.com/Mak5ens/llmops-gateway/commit/9e1e75936b27d5e73a5d5fb35611d94a08a483db))
* mask French personal data in the gateway with the Presidio guar… ([#9](https://github.com/Mak5ens/llmops-gateway/issues/9)) ([f8ac51b](https://github.com/Mak5ens/llmops-gateway/commit/f8ac51b68578ec375a158f5be4f720ada0f4b24a))
* publish the platform's images and run the integration tests on Kubernetes (LAB-127) ([#25](https://github.com/Mak5ens/llmops-gateway/issues/25)) ([8c53b21](https://github.com/Mak5ens/llmops-gateway/commit/8c53b216309808d187e09b9a4963818a906e2e1e))
* route usage aliases to models with a chat-large fallback ([#3](https://github.com/Mak5ens/llmops-gateway/issues/3)) ([e148c6d](https://github.com/Mak5ens/llmops-gateway/commit/e148c6dc4ed575970f69abf34e9b3fe39188c3d5))
* run LiteLLM, PostgreSQL and Ollama with Docker Compose ([74cfaea](https://github.com/Mak5ens/llmops-gateway/commit/74cfaeae099f2e9ba7b1619f374a91ecdfe6aa71))
* trace every call to the Langfuse project of its team, with its … ([#13](https://github.com/Mak5ens/llmops-gateway/issues/13)) ([bceec28](https://github.com/Mak5ens/llmops-gateway/commit/bceec28c7a67cb271f5cf6879611dc6a033d4cb1))


### Bug Fixes

* **ci:** call the platform's image workflow at a commit of its main branch (LAB-130) ([#27](https://github.com/Mak5ens/llmops-gateway/issues/27)) ([f29635d](https://github.com/Mak5ens/llmops-gateway/commit/f29635dfed743bf7a0aa8359a17d9b9c87879d38))
* **just:** keep quoted recipe arguments whole ([#16](https://github.com/Mak5ens/llmops-gateway/issues/16)) ([38a850c](https://github.com/Mak5ens/llmops-gateway/commit/38a850cb2609aee4bf3e47dbf70b45a76739fa76))
* keep the Presidio package on the Analyzer image's version, one release-please run at a time (LAB-141) ([#42](https://github.com/Mak5ens/llmops-gateway/issues/42)) ([658b664](https://github.com/Mak5ens/llmops-gateway/commit/658b664d9b85b5e7173ff4d014b1fe4a8b04e082))
* **tests:** let a running ArgoCD reconciliation finish before changing a workload by hand (LAB-130) ([#28](https://github.com/Mak5ens/llmops-gateway/issues/28)) ([f94c45d](https://github.com/Mak5ens/llmops-gateway/commit/f94c45d4043aaa2fa30abfb6bf5fa59b00df95a1))


### Documentation

* **adr:** ADR-007, LiteLLM Proxy as the LLM gateway ([#18](https://github.com/Mak5ens/llmops-gateway/issues/18)) ([fa372fd](https://github.com/Mak5ens/llmops-gateway/commit/fa372fd84e0f9b702ea81a157972b7122dffba0f))
* link the Presidio article, update CLAUDE.md (LAB-173) ([#24](https://github.com/Mak5ens/llmops-gateway/issues/24)) ([de9edc9](https://github.com/Mak5ens/llmops-gateway/commit/de9edc9de260104a7685e4bb04ab8cdc2cd6e8f8))
* **readme:** add a demo GIF, results at a glance and next steps ([#19](https://github.com/Mak5ens/llmops-gateway/issues/19)) ([f2b5ac3](https://github.com/Mak5ens/llmops-gateway/commit/f2b5ac386dcfbf57743d1cbf61385a337e33fbc7))
* **readme:** link article 1, anonymize before inference (LAB-122) ([#22](https://github.com/Mak5ens/llmops-gateway/issues/22)) ([96bf3bf](https://github.com/Mak5ens/llmops-gateway/commit/96bf3bf653ac77c061f21e508047d6d420483331))
* **readme:** show the demo call's trace in Langfuse ([#20](https://github.com/Mak5ens/llmops-gateway/issues/20)) ([32b39bc](https://github.com/Mak5ens/llmops-gateway/commit/32b39bc0b331e2d55aa322c4d04bd4639508ff9b))
* renumber the internal price ADR to ADR-014 ([#6](https://github.com/Mak5ens/llmops-gateway/issues/6)) ([4bd52c1](https://github.com/Mak5ens/llmops-gateway/commit/4bd52c1c86039c4e8e4c06f6174d31dfe6176054))
* update the CI timings for the separate leak job ([#17](https://github.com/Mak5ens/llmops-gateway/issues/17)) ([c7f55bb](https://github.com/Mak5ens/llmops-gateway/commit/c7f55bb1e6c18cd7c27141b1cd6a0042a36468c1))
