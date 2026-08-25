# Changelog

## [0.3.0](https://github.com/NatLabRockies/R2X/compare/r2x-reeds-to-plexos-v0.2.1...r2x-reeds-to-plexos-v0.3.0) (2026-08-25)


### Features

* enable can-imports translation if parser allows it ([#323](https://github.com/NatLabRockies/R2X/issues/323)) ([a5801e0](https://github.com/NatLabRockies/R2X/commit/a5801e0bba1d9bf32581227a49b644771ef6f4ab))


### Bug Fixes

* resolve prek issues and min errors on reeds translation ([#319](https://github.com/NatLabRockies/R2X/issues/319)) ([bad738d](https://github.com/NatLabRockies/R2X/commit/bad738dbffe21fa329f2131d6ba103d4fff27d60))

## [0.2.1](https://github.com/NatLabRockies/R2X/compare/r2x-reeds-to-plexos-v0.2.0...r2x-reeds-to-plexos-v0.2.1) (2026-08-13)


### Bug Fixes

* bump dependencies for correctly release on r2x ([#301](https://github.com/NatLabRockies/R2X/issues/301)) ([68aa5d6](https://github.com/NatLabRockies/R2X/commit/68aa5d6923cf0126b3d48e37ad6e7b36edda1ac4))
* mix fixes across packages based on recent runs and observations ([#289](https://github.com/NatLabRockies/R2X/issues/289)) ([8f1e6f5](https://github.com/NatLabRockies/R2X/commit/8f1e6f5e9157b65d7d7cf9577be6211c9632c756))
* ReEDS hydro operating mode translation to PLEXOS ([#306](https://github.com/NatLabRockies/R2X/issues/306)) ([62039c5](https://github.com/NatLabRockies/R2X/commit/62039c52552a725d9254697bfab916dbcd1f9e7d))
* ReEDS pumped hydro mapping and hydro operating costs ([#303](https://github.com/NatLabRockies/R2X/issues/303)) ([1ef5875](https://github.com/NatLabRockies/R2X/commit/1ef58758a720cdcdfb649899caf27b6854fd052e))
* ReEDS storage efficiency mapping in PLEXOS and Sienna ([#300](https://github.com/NatLabRockies/R2X/issues/300)) ([c4b12ae](https://github.com/NatLabRockies/R2X/commit/c4b12aef37c1450be177f41f3822493cbf2c43d6))
* ReEDS transmission mappings for Sienna and PLEXOS ([#298](https://github.com/NatLabRockies/R2X/issues/298)) ([27786c2](https://github.com/NatLabRockies/R2X/commit/27786c24ecdc6ad9aa4fbdbd7280f1e0683a2db1))
* remove capacity factor getter entry from r2p translations ([#285](https://github.com/NatLabRockies/R2X/issues/285)) ([d083095](https://github.com/NatLabRockies/R2X/commit/d083095940e9b37d39be510a718a377df73a1b93))
* resolve r2p load participation factor for region/nodes ([#282](https://github.com/NatLabRockies/R2X/issues/282)) ([051fc89](https://github.com/NatLabRockies/R2X/commit/051fc89bbb8ed478faabd92a6affc5106f3a08bc))
* Translate smr and smr_ccs correctly in PLEXOS and Sienna ([#296](https://github.com/NatLabRockies/R2X/issues/296)) ([265a308](https://github.com/NatLabRockies/R2X/commit/265a308274926441dc5f3994e7f8c2a0084c27bb))
* update wheel charging for lines params ([#309](https://github.com/NatLabRockies/R2X/issues/309)) ([334f408](https://github.com/NatLabRockies/R2X/commit/334f40871dc04dffc88002e1a9f8c290b21683c8))


### Build

* **deps-dev:** bump prek from 0.4.3 to 0.4.5 ([#280](https://github.com/NatLabRockies/R2X/issues/280)) ([7d19ed6](https://github.com/NatLabRockies/R2X/commit/7d19ed636f02eec3d12511068f51a5afa2d3951e))

## [0.2.0](https://github.com/NatLabRockies/R2X/compare/r2x-reeds-to-plexos-v0.1.0...r2x-reeds-to-plexos-v0.2.0) (2026-06-22)


### Features

* add new types of loads for reeds to plexos translations ([#256](https://github.com/NatLabRockies/R2X/issues/256)) ([cba09db](https://github.com/NatLabRockies/R2X/commit/cba09db148e7c2b6211d8f0e13840ab7d84d2a7c))
* update codebase for all translation to handle EI system and recent cross changes ([#277](https://github.com/NatLabRockies/R2X/issues/277)) ([863cbea](https://github.com/NatLabRockies/R2X/commit/863cbea973d749c3ac4857a8c9d776062040bd06))

## 0.1.0 (2026-04-08)


### ⚠ BREAKING CHANGES

* Replace monolithic parser/exporter with plugin architecture.    - Introduce R2X Plugin Management System with discoverable plugin configs    - Restructure into four independent packages under packages/: r2x-reeds-to-sienna,  r2x-reeds-to-plexos, r2x-sienna-to-plexos, r2x-plexos-to-sienna    - Extract parsing/exporting into separate model plugins, translations are now pure  mapping logic    - Overhaul CI/CD with per-package release-please, dependabot, auto-labeler, and commit  linting    - Add taplo (TOML linting), ty (type checking), and updated pre-commit hooks    - Expand test coverage across all translation packages (getters, rules, utilities)    - Fix min stable level zeroing, duplicated arcs, time series store, and template  injection bugs    - Fix smoke test to build all workspace packages locally for dependency resolution    - Rewrite documentation to match new framework style and update README

### Features

* v2.0.0 ([#187](https://github.com/NatLabRockies/R2X/issues/187)) ([161bcc9](https://github.com/NatLabRockies/R2X/commit/161bcc92a0baea9b6c70afde8be9f188931fc7eb))
