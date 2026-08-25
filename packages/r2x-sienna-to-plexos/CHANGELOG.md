# Changelog

## [0.3.1](https://github.com/NatLabRockies/R2X/compare/r2x-sienna-to-plexos-v0.3.0...r2x-sienna-to-plexos-v0.3.1) (2026-08-25)


### Bug Fixes

* resolve prek issues and min errors on reeds translation ([#319](https://github.com/NatLabRockies/R2X/issues/319)) ([bad738d](https://github.com/NatLabRockies/R2X/commit/bad738dbffe21fa329f2131d6ba103d4fff27d60))

## [0.3.0](https://github.com/NatLabRockies/R2X/compare/r2x-sienna-to-plexos-v0.2.0...r2x-sienna-to-plexos-v0.3.0) (2026-08-13)


### Features

* update translation to match latest EI codebase ([#307](https://github.com/NatLabRockies/R2X/issues/307)) ([3719f3f](https://github.com/NatLabRockies/R2X/commit/3719f3fe12e5e7f61f16547d17a2c1871af794b7))


### Bug Fixes

* bump dependencies for correctly release on r2x ([#301](https://github.com/NatLabRockies/R2X/issues/301)) ([68aa5d6](https://github.com/NatLabRockies/R2X/commit/68aa5d6923cf0126b3d48e37ad6e7b36edda1ac4))
* mix fixes across packages based on recent runs and observations ([#289](https://github.com/NatLabRockies/R2X/issues/289)) ([8f1e6f5](https://github.com/NatLabRockies/R2X/commit/8f1e6f5e9157b65d7d7cf9577be6211c9632c756))


### Build

* **deps-dev:** bump prek from 0.4.3 to 0.4.5 ([#280](https://github.com/NatLabRockies/R2X/issues/280)) ([7d19ed6](https://github.com/NatLabRockies/R2X/commit/7d19ed636f02eec3d12511068f51a5afa2d3951e))

## [0.2.0](https://github.com/NatLabRockies/R2X/compare/r2x-sienna-to-plexos-v0.1.0...r2x-sienna-to-plexos-v0.2.0) (2026-06-22)


### Features

* add new types of loads for reeds to plexos translations ([#256](https://github.com/NatLabRockies/R2X/issues/256)) ([cba09db](https://github.com/NatLabRockies/R2X/commit/cba09db148e7c2b6211d8f0e13840ab7d84d2a7c))
* update codebase for all translation to handle EI system and recent cross changes ([#277](https://github.com/NatLabRockies/R2X/issues/277)) ([863cbea](https://github.com/NatLabRockies/R2X/commit/863cbea973d749c3ac4857a8c9d776062040bd06))
* update logic for general EI translation approach ([#255](https://github.com/NatLabRockies/R2X/issues/255)) ([649eba0](https://github.com/NatLabRockies/R2X/commit/649eba01b9051e175260a124f52a3e9788f4830d))

## 0.1.0 (2026-04-08)


### ⚠ BREAKING CHANGES

* Replace monolithic parser/exporter with plugin architecture.    - Introduce R2X Plugin Management System with discoverable plugin configs    - Restructure into four independent packages under packages/: r2x-reeds-to-sienna,  r2x-reeds-to-plexos, r2x-sienna-to-plexos, r2x-plexos-to-sienna    - Extract parsing/exporting into separate model plugins, translations are now pure  mapping logic    - Overhaul CI/CD with per-package release-please, dependabot, auto-labeler, and commit  linting    - Add taplo (TOML linting), ty (type checking), and updated pre-commit hooks    - Expand test coverage across all translation packages (getters, rules, utilities)    - Fix min stable level zeroing, duplicated arcs, time series store, and template  injection bugs    - Fix smoke test to build all workspace packages locally for dependency resolution    - Rewrite documentation to match new framework style and update README

### Features

* v2.0.0 ([#187](https://github.com/NatLabRockies/R2X/issues/187)) ([161bcc9](https://github.com/NatLabRockies/R2X/commit/161bcc92a0baea9b6c70afde8be9f188931fc7eb))
