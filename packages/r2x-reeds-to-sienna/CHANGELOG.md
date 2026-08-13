# Changelog

## [0.2.1](https://github.com/NatLabRockies/R2X/compare/r2x-reeds-to-sienna-v0.2.0...r2x-reeds-to-sienna-v0.2.1) (2026-08-13)


### Bug Fixes

* Fix ReEDS-Sienna natural unit serialization ([#311](https://github.com/NatLabRockies/R2X/issues/311)) ([399d173](https://github.com/NatLabRockies/R2X/commit/399d1732e60386c6a27b5697d2c5ee82107f9a04))
* Map ReEDS hydro by operating mode in Sienna ([#305](https://github.com/NatLabRockies/R2X/issues/305)) ([3336fed](https://github.com/NatLabRockies/R2X/commit/3336fed870a00c2bcc292e1985b459e539896332))
* mix fixes across packages based on recent runs and observations ([#289](https://github.com/NatLabRockies/R2X/issues/289)) ([8f1e6f5](https://github.com/NatLabRockies/R2X/commit/8f1e6f5e9157b65d7d7cf9577be6211c9632c756))
* Normalize Sienna max_active_power timeseries ([#304](https://github.com/NatLabRockies/R2X/issues/304)) ([3a77498](https://github.com/NatLabRockies/R2X/commit/3a774987330ac48f3a4087f9f491793bc9627f49))
* ReEDS consuming technology mapping in Sienna ([#312](https://github.com/NatLabRockies/R2X/issues/312)) ([e3ebd67](https://github.com/NatLabRockies/R2X/commit/e3ebd6770f1fe7f28319c587855b73edebcab4d7))
* ReEDS data center demand mapping to Sienna ([#297](https://github.com/NatLabRockies/R2X/issues/297)) ([5c0fcb3](https://github.com/NatLabRockies/R2X/commit/5c0fcb36f7ae7653ec1c545a2a792ec7cff4b87f))
* ReEDS pumped hydro mapping and hydro operating costs ([#303](https://github.com/NatLabRockies/R2X/issues/303)) ([1ef5875](https://github.com/NatLabRockies/R2X/commit/1ef58758a720cdcdfb649899caf27b6854fd052e))
* ReEDS storage efficiency mapping in PLEXOS and Sienna ([#300](https://github.com/NatLabRockies/R2X/issues/300)) ([c4b12ae](https://github.com/NatLabRockies/R2X/commit/c4b12aef37c1450be177f41f3822493cbf2c43d6))
* ReEDS transmission mappings for Sienna and PLEXOS ([#298](https://github.com/NatLabRockies/R2X/issues/298)) ([27786c2](https://github.com/NatLabRockies/R2X/commit/27786c24ecdc6ad9aa4fbdbd7280f1e0683a2db1))
* Translate smr and smr_ccs correctly in PLEXOS and Sienna ([#296](https://github.com/NatLabRockies/R2X/issues/296)) ([265a308](https://github.com/NatLabRockies/R2X/commit/265a308274926441dc5f3994e7f8c2a0084c27bb))


### Build

* **deps-dev:** bump prek from 0.4.3 to 0.4.5 ([#280](https://github.com/NatLabRockies/R2X/issues/280)) ([7d19ed6](https://github.com/NatLabRockies/R2X/commit/7d19ed636f02eec3d12511068f51a5afa2d3951e))

## [0.2.0](https://github.com/NatLabRockies/R2X/compare/r2x-reeds-to-sienna-v0.1.0...r2x-reeds-to-sienna-v0.2.0) (2026-06-22)


### Features

* add new types of loads for reeds to plexos translations ([#256](https://github.com/NatLabRockies/R2X/issues/256)) ([cba09db](https://github.com/NatLabRockies/R2X/commit/cba09db148e7c2b6211d8f0e13840ab7d84d2a7c))
* update codebase for all translation to handle EI system and recent cross changes ([#277](https://github.com/NatLabRockies/R2X/issues/277)) ([863cbea](https://github.com/NatLabRockies/R2X/commit/863cbea973d749c3ac4857a8c9d776062040bd06))


### Bug Fixes

* resolve reeds translation issues and update to latest code base ([#266](https://github.com/NatLabRockies/R2X/issues/266)) ([28addb2](https://github.com/NatLabRockies/R2X/commit/28addb2aec553303a0bb62f3872f2af01c00c387))
* resolve reserve association issues and handle code base with recent r2x-reeds and r2x-sienna updates. ([#274](https://github.com/NatLabRockies/R2X/issues/274)) ([6d30202](https://github.com/NatLabRockies/R2X/commit/6d3020279356ec343ca089df75cc05d91362d7ef))

## 0.1.0 (2026-04-08)


### ⚠ BREAKING CHANGES

* Replace monolithic parser/exporter with plugin architecture.    - Introduce R2X Plugin Management System with discoverable plugin configs    - Restructure into four independent packages under packages/: r2x-reeds-to-sienna,  r2x-reeds-to-plexos, r2x-sienna-to-plexos, r2x-plexos-to-sienna    - Extract parsing/exporting into separate model plugins, translations are now pure  mapping logic    - Overhaul CI/CD with per-package release-please, dependabot, auto-labeler, and commit  linting    - Add taplo (TOML linting), ty (type checking), and updated pre-commit hooks    - Expand test coverage across all translation packages (getters, rules, utilities)    - Fix min stable level zeroing, duplicated arcs, time series store, and template  injection bugs    - Fix smoke test to build all workspace packages locally for dependency resolution    - Rewrite documentation to match new framework style and update README

### Features

* v2.0.0 ([#187](https://github.com/NatLabRockies/R2X/issues/187)) ([161bcc9](https://github.com/NatLabRockies/R2X/commit/161bcc92a0baea9b6c70afde8be9f188931fc7eb))
