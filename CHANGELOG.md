# Changelog

## [2.0.0](https://github.com/NatLabRockies/R2X/compare/r2x-v1.2.0...r2x-v2.0.0) (2026-04-08)


### ⚠ BREAKING CHANGES

* Replace monolithic parser/exporter with plugin architecture.    - Introduce R2X Plugin Management System with discoverable plugin configs    - Restructure into four independent packages under packages/: r2x-reeds-to-sienna,  r2x-reeds-to-plexos, r2x-sienna-to-plexos, r2x-plexos-to-sienna    - Extract parsing/exporting into separate model plugins, translations are now pure  mapping logic    - Overhaul CI/CD with per-package release-please, dependabot, auto-labeler, and commit  linting    - Add taplo (TOML linting), ty (type checking), and updated pre-commit hooks    - Expand test coverage across all translation packages (getters, rules, utilities)    - Fix min stable level zeroing, duplicated arcs, time series store, and template  injection bugs    - Fix smoke test to build all workspace packages locally for dependency resolution    - Rewrite documentation to match new framework style and update README

### Features

* add check_solve_year method and add it to reeds parser test ([#158](https://github.com/NatLabRockies/R2X/issues/158)) ([366d7c4](https://github.com/NatLabRockies/R2X/commit/366d7c4054b7664c3cd6f16da8f307abd5b76c9d))
* Add compatibility with more operational cost representation on Plexos ([#40](https://github.com/NatLabRockies/R2X/issues/40)) ([77dfceb](https://github.com/NatLabRockies/R2X/commit/77dfcebb008e5ea0f62b09d3d9ec41638bbc5598))
* Add functions to convert recf.h5 to new hdf5 format from ReEDS ([#115](https://github.com/NatLabRockies/R2X/issues/115)) ([cd0863e](https://github.com/NatLabRockies/R2X/commit/cd0863e607a7d2702d00808d51b8a2ae85147c49))
* Add hurdle rate plugin for ReEDS2Plexos ([#60](https://github.com/NatLabRockies/R2X/issues/60)) ([c0d28f6](https://github.com/NatLabRockies/R2X/commit/c0d28f6a71e83d628a11a2c2466f95d77e793f4d))
* Add new function that creates an instance of a model with the option to skip validation ([#110](https://github.com/NatLabRockies/R2X/issues/110)) ([dab93ff](https://github.com/NatLabRockies/R2X/commit/dab93fffe116ae69143069260dc3f017b7a8e78a))
* Add ReEDS parser to the public version and some Plexos exporter fixes ([#43](https://github.com/NatLabRockies/R2X/issues/43)) ([d1a61f0](https://github.com/NatLabRockies/R2X/commit/d1a61f0c7fb214b475f9a577246fa9860614a80f))
* Adding `smr` technology from ReEDS. ([#197](https://github.com/NatLabRockies/R2X/issues/197)) ([0f938e3](https://github.com/NatLabRockies/R2X/commit/0f938e3cde0595198ba9d17549846d89e9f60551))
* Adding cambium and electrolyzer plugin ([#135](https://github.com/NatLabRockies/R2X/issues/135)) ([966e5ac](https://github.com/NatLabRockies/R2X/commit/966e5ac2c7e16937a18b2df7c958c7e67322e4b6))
* Adding new CLI entrypoints and better handling of scenarios ([#94](https://github.com/NatLabRockies/R2X/issues/94)) ([45cda9b](https://github.com/NatLabRockies/R2X/commit/45cda9bdb24b478243d031cc7af059d76dabd3d7))
* Adding updated version of timeseries exporter and dispatch methods to get year from different models ([#125](https://github.com/NatLabRockies/R2X/issues/125)) ([b3d4b3d](https://github.com/NatLabRockies/R2X/commit/b3d4b3d25ddd52bd95f1c410a34076b3997e09d8))
* Cost Function definition and export fixes ([#24](https://github.com/NatLabRockies/R2X/issues/24)) ([eec9cb6](https://github.com/NatLabRockies/R2X/commit/eec9cb6beb204828224454d98818d4b79a3efc62))
* export fuel curves for plexos ([#77](https://github.com/NatLabRockies/R2X/issues/77)) ([bd651e4](https://github.com/NatLabRockies/R2X/commit/bd651e47b2b5bc3e3254deaa29bbdb61a3b747f8))
* First draft of ThermalMultiStart struct ([#148](https://github.com/NatLabRockies/R2X/issues/148)) ([81dda11](https://github.com/NatLabRockies/R2X/commit/81dda111331fdd148e1b37cc7acc8ddbfbeaa249))
* Implements ValueCurves & Improve Prime Mover and Fuel Type Mapping ([#12](https://github.com/NatLabRockies/R2X/issues/12)) ([fcc37c0](https://github.com/NatLabRockies/R2X/commit/fcc37c09dfcdff1e7160ec9264af2be1212be091))
* improve imports fuel costs ([#13](https://github.com/NatLabRockies/R2X/issues/13)) ([c169f1b](https://github.com/NatLabRockies/R2X/commit/c169f1bda29686a7a0725bddf7b74ba08285f4e6))
* **models:** Updating PHES to reflect latest version of PSY. ([#144](https://github.com/NatLabRockies/R2X/issues/144)) ([46ac96e](https://github.com/NatLabRockies/R2X/commit/46ac96e576b1d970419a44263c45700117584a7e))
* Multiple updates to the Plexos parser ([#47](https://github.com/NatLabRockies/R2X/issues/47)) ([bf284f2](https://github.com/NatLabRockies/R2X/commit/bf284f2afa808266ecd10452a3d7c2e445946ae8))
* New emission_cap plugin that sets a custom constraint for Plexos output model. ([#57](https://github.com/NatLabRockies/R2X/issues/57)) ([9114586](https://github.com/NatLabRockies/R2X/commit/9114586e50ec47841e6033aaa692049c5af1d837))
* **plexos:** Adding parsing of `year,month,day` files from plexos ([#175](https://github.com/NatLabRockies/R2X/issues/175)) ([1af4b33](https://github.com/NatLabRockies/R2X/commit/1af4b33f0ba37e10fb9fb4d725577c5636c83f3e))
* **plexos:** plexos parser xml ([#93](https://github.com/NatLabRockies/R2X/issues/93)) ([835e904](https://github.com/NatLabRockies/R2X/commit/835e90442feae85474658b7f89548f800f1e5f53))
* **plugins:** Adding CCS plugin for ReDS and Plexos translation ([#95](https://github.com/NatLabRockies/R2X/issues/95)) ([73087e2](https://github.com/NatLabRockies/R2X/commit/73087e2feb9d2fc8c4c05a6a9a63093be4b9ce43))
* Update issue templates ([ece260b](https://github.com/NatLabRockies/R2X/commit/ece260b5f7afd8b7ed5308a1d9f51f4785ee720a))
* Update runner to UV ([#80](https://github.com/NatLabRockies/R2X/issues/80)) ([03c5e05](https://github.com/NatLabRockies/R2X/commit/03c5e05a56f3cba240e71a7688acd01569ae39a4))
* v2.0.0 ([#187](https://github.com/NatLabRockies/R2X/issues/187)) ([161bcc9](https://github.com/NatLabRockies/R2X/commit/161bcc92a0baea9b6c70afde8be9f188931fc7eb))


### Bug Fixes

* Add correct sorting for plexos files with TS_NYMDH and caching better the data files. ([#152](https://github.com/NatLabRockies/R2X/issues/152)) ([196f0d9](https://github.com/NatLabRockies/R2X/commit/196f0d99d50cc7d28616374221033bf990e534cc))
* Add special handling for load.h5 on ReEDS. ([#149](https://github.com/NatLabRockies/R2X/issues/149)) ([5701526](https://github.com/NatLabRockies/R2X/commit/5701526fa6fcae6b9fd93bd5fc5e71251280e0ba))
* Added correct unit validation for `FuelPrice` ([#86](https://github.com/NatLabRockies/R2X/issues/86)) ([1f4f0b1](https://github.com/NatLabRockies/R2X/commit/1f4f0b122a7cc164b0f5787fbd8c27b64f9b42d7)), closes [#83](https://github.com/NatLabRockies/R2X/issues/83)
* Adding capability to filter by weather year instead of indexing ([#160](https://github.com/NatLabRockies/R2X/issues/160)) ([e70f2e0](https://github.com/NatLabRockies/R2X/commit/e70f2e08090367b99b85554a579c89cda8f6c93f))
* Adding datetime fix for h5files ([#174](https://github.com/NatLabRockies/R2X/issues/174)) ([9199cf3](https://github.com/NatLabRockies/R2X/commit/9199cf3150de702bd83dfcc99d5e19e9047f92ee))
* Adding missing exports from models ([#154](https://github.com/NatLabRockies/R2X/issues/154)) ([2b67581](https://github.com/NatLabRockies/R2X/commit/2b67581384d057da268c61ca0b9c7e67dc8a5db4))
* Cambium fixes and upgrader fixes ([#119](https://github.com/NatLabRockies/R2X/issues/119)) ([f926bb4](https://github.com/NatLabRockies/R2X/commit/f926bb4aabc42b0cb6185a8af0c90ae24ab4a3eb))
* change co2_cap column name to tonne_per_year ([#138](https://github.com/NatLabRockies/R2X/issues/138)) ([553570a](https://github.com/NatLabRockies/R2X/commit/553570a8abfdb715f5ce5b35c8e60486d2436f2d))
* Changed `BaseUnit` and description for `fixed` field for `ThermalGenerationCost` ([#79](https://github.com/NatLabRockies/R2X/issues/79)) ([d2a2140](https://github.com/NatLabRockies/R2X/commit/d2a21403b69111311fc010c0042d2e0f9bf9695f)), closes [#76](https://github.com/NatLabRockies/R2X/issues/76)
* Changing time series name for Regulation reserves ([#145](https://github.com/NatLabRockies/R2X/issues/145)) ([b0efb89](https://github.com/NatLabRockies/R2X/commit/b0efb89c65947d6d284fb8adaa16acbd662e862f))
* Cleaning configuration file for plexos and adding more testing ([#11](https://github.com/NatLabRockies/R2X/issues/11)) ([dee6edc](https://github.com/NatLabRockies/R2X/commit/dee6edc71d10b2fe54fc07d1c9daeaad57d4ba4a))
* Compatibility fixes for standard scenarios ([#62](https://github.com/NatLabRockies/R2X/issues/62)) ([fc505d2](https://github.com/NatLabRockies/R2X/commit/fc505d2d616175c8c7dade0a540275d934668894))
* Correct parsing of TS_NMDH for plexos parser ([#100](https://github.com/NatLabRockies/R2X/issues/100)) ([8fd1a9c](https://github.com/NatLabRockies/R2X/commit/8fd1a9c1947f1ef2f41598e824a04c22a24f5253))
* Correctly assign `output_active_power_limits` ([#59](https://github.com/NatLabRockies/R2X/issues/59)) ([cc76cf2](https://github.com/NatLabRockies/R2X/commit/cc76cf20179089f86b69c9687a648de6e5a5c4c1)), closes [#58](https://github.com/NatLabRockies/R2X/issues/58)
* **docs:** Update README.md ([249ab1b](https://github.com/NatLabRockies/R2X/commit/249ab1b814601315fc67acdf3fbd3f53e077b96f))
* Enable round trip from plexos ([#128](https://github.com/NatLabRockies/R2X/issues/128)) ([a16ea32](https://github.com/NatLabRockies/R2X/commit/a16ea32bae8d88052bf2ee23ec8811379f53ef6f))
* **enums:** Uppercase all enums to be compliant with other languages. ([#29](https://github.com/NatLabRockies/R2X/issues/29)) ([98c2a60](https://github.com/NatLabRockies/R2X/commit/98c2a60c25d5599b50f5d351c180b0c9a54d8370)), closes [#17](https://github.com/NatLabRockies/R2X/issues/17)
* hmap_myr.csv and can_imports_quarter_frac.csv for ReEDS compatibility ([#151](https://github.com/NatLabRockies/R2X/issues/151)) ([c85fd06](https://github.com/NatLabRockies/R2X/commit/c85fd06444c9917584d58df678725ab0d360e346))
* Improve PSY compatibility and incorporate changes to infrasys and data modeling ([#112](https://github.com/NatLabRockies/R2X/issues/112)) ([8a61169](https://github.com/NatLabRockies/R2X/commit/8a61169694d54a27e1717c7e7ee13ada6073a868))
* Infrasys json serialization and compatibiility fixes ([#106](https://github.com/NatLabRockies/R2X/issues/106)) ([40137fd](https://github.com/NatLabRockies/R2X/commit/40137fdb1ba32b7e5eaac9323f76328028e4af2e))
* Make ReEDS parser compatible with new cost functions ([#44](https://github.com/NatLabRockies/R2X/issues/44)) ([0e09279](https://github.com/NatLabRockies/R2X/commit/0e092791ab97688a18fdf5ade175f2536dd3603a))
* **plexos_export:** Added `coalduns` mapping to ReEDS and adding line flow exporter ([#55](https://github.com/NatLabRockies/R2X/issues/55)) ([b8cc616](https://github.com/NatLabRockies/R2X/commit/b8cc616f20ba268588c371943936619a94d722e5))
* **plexos:** Ext data export, Variable defaults, and Data File Scenario Filtering ([#38](https://github.com/NatLabRockies/R2X/issues/38)) ([e963011](https://github.com/NatLabRockies/R2X/commit/e9630115d58040c9c9aca6d28c3ca2c4205ead48))
* **plexos:** Fix Rating and Availability Logic ([#8](https://github.com/NatLabRockies/R2X/issues/8)) ([2658b67](https://github.com/NatLabRockies/R2X/commit/2658b67496f27b2a7c82f918f92a39f5bca04e25))
* ReEDS compatibility changes ([#114](https://github.com/NatLabRockies/R2X/issues/114)) ([b0ef7de](https://github.com/NatLabRockies/R2X/commit/b0ef7deb7f357eaf7593d6898bef12a85603c9e8))
* **reeds:** Adding more technologies and better logging for renewable profile. ([#157](https://github.com/NatLabRockies/R2X/issues/157)) ([708a9d5](https://github.com/NatLabRockies/R2X/commit/708a9d54c0466bd9c27c4cb4ce3ea863e82e9c35))
* **reeds:** Adding new reeds_tech `coal-new_coal-ccs_mod` ([#156](https://github.com/NatLabRockies/R2X/issues/156)) ([a73bc7e](https://github.com/NatLabRockies/R2X/commit/a73bc7ea0b7b223605d2dad89ec523d431760375))
* **reeds:** Correct upgrader function for load.h5 ([#143](https://github.com/NatLabRockies/R2X/issues/143)) ([e962dec](https://github.com/NatLabRockies/R2X/commit/e962decd81393ce17fa22d44db98176816b9b8d4))
* Removing old reference to named tuples and core packages and improving upgrader. ([#170](https://github.com/NatLabRockies/R2X/issues/170)) ([b93efad](https://github.com/NatLabRockies/R2X/commit/b93efad4817bcdc589e1aab5193b5722bab913c2))
* Reverting file name to use the seasons instead of quarters ([#155](https://github.com/NatLabRockies/R2X/issues/155)) ([339ec9a](https://github.com/NatLabRockies/R2X/commit/339ec9a8188631330791221fd34dd815fb859677))
* Sienna exporter incompatibility when starting from ReEDS ([#108](https://github.com/NatLabRockies/R2X/issues/108)) ([05befac](https://github.com/NatLabRockies/R2X/commit/05befac53d12c46ea69a3de5690022bb32c92626))
* update file name for planned outages from ReEDS ([#49](https://github.com/NatLabRockies/R2X/issues/49)) ([a07253e](https://github.com/NatLabRockies/R2X/commit/a07253e53fcdc3be5dcf9a82030c11d87d6ba047))
* Update link on README ([e02aca5](https://github.com/NatLabRockies/R2X/commit/e02aca556683b0bf93f3ac0fb005a576088962cf))
* Updating codebase to match internal ([#16](https://github.com/NatLabRockies/R2X/issues/16)) ([cd4d606](https://github.com/NatLabRockies/R2X/commit/cd4d6061112c834e5fc0a93bb5b083ddc7ac164b))
* variable scenario filtering, and availability TS multiplier ([#91](https://github.com/NatLabRockies/R2X/issues/91)) ([0b37690](https://github.com/NatLabRockies/R2X/commit/0b37690f941cc831c12a14565c1e735dafd0f898))


### Documentation

* Adding first version of documentation ([#42](https://github.com/NatLabRockies/R2X/issues/42)) ([d893a6a](https://github.com/NatLabRockies/R2X/commit/d893a6a5ff36fbe65e1246207c16c363a6f7f8e3))
* Remove missing link for image ([#196](https://github.com/NatLabRockies/R2X/issues/196)) ([baea8a1](https://github.com/NatLabRockies/R2X/commit/baea8a13d05e0e1e34ddd0a81661395447a19054))
* Removing references to other repo. ([9910834](https://github.com/NatLabRockies/R2X/commit/99108340d6203854f47f938a51699b24d7aea213))
* Update README.md ([ac9971c](https://github.com/NatLabRockies/R2X/commit/ac9971c7e22bf6358958114e79b787359a6c21a9))


### CI/CD

* **actions:** Added GitHub actions to the repo ([#6](https://github.com/NatLabRockies/R2X/issues/6)) ([eec81bb](https://github.com/NatLabRockies/R2X/commit/eec81bbbab3306b5335a656c1374452f9d54098f))
* Add capability to run the CI manually ([2332c31](https://github.com/NatLabRockies/R2X/commit/2332c31c2e527b611bde76f86f5e67cb5ed495e9))
* Add codecoverage ([eec2c24](https://github.com/NatLabRockies/R2X/commit/eec2c24c3d5e4c11dfea500b62b80aa15a25863b))
* Adding action on push to main ([a524c6e](https://github.com/NatLabRockies/R2X/commit/a524c6ee3d6f3de80becefc471647b66e011b6db))
* Adding new way of making releases ([#140](https://github.com/NatLabRockies/R2X/issues/140)) ([14d7359](https://github.com/NatLabRockies/R2X/commit/14d7359807796037d4a5c8f89547ecaf1b078ea0))
* Adding publish to pypy ([6dae411](https://github.com/NatLabRockies/R2X/commit/6dae4116d4bd5a192291c28eba6e623c3d91e2c4))


### Build

* **deps:** bump actions/upload-artifact from 4.6.2 to 7.0.0 ([#249](https://github.com/NatLabRockies/R2X/issues/249)) ([4eb4301](https://github.com/NatLabRockies/R2X/commit/4eb4301e5aa07b1e8db9d6f8e1fe00d2e3b4068c))
* **deps:** bump astral-sh/setup-uv from 7.6.0 to 8.0.0 ([#247](https://github.com/NatLabRockies/R2X/issues/247)) ([d8f3cdc](https://github.com/NatLabRockies/R2X/commit/d8f3cdce3509becb7520d6cbdbecd589257ed97d))
* **deps:** bump codecov/codecov-action from 5.5.4 to 6.0.0 ([#248](https://github.com/NatLabRockies/R2X/issues/248)) ([1b7acb5](https://github.com/NatLabRockies/R2X/commit/1b7acb5cf79d75c2d774162a8cb3f62ac265f294))
* **deps:** bump pypa/gh-action-pypi-publish from 1.13.0 to 1.14.0 ([#250](https://github.com/NatLabRockies/R2X/issues/250)) ([bb1fc94](https://github.com/NatLabRockies/R2X/commit/bb1fc9469a673df094c8fdaeb4b3a44f9b66b9e7))


### Tests

* Added PJM test system and fixed enum representation to be just string. ([#21](https://github.com/NatLabRockies/R2X/issues/21)) ([1277159](https://github.com/NatLabRockies/R2X/commit/12771599973c9849256359c33b034854567dbcaf))
* **codecov:** Adding codecov file ([#92](https://github.com/NatLabRockies/R2X/issues/92)) ([959ef4d](https://github.com/NatLabRockies/R2X/commit/959ef4d003d6bdfd6aa583e8615f8dab6b758d3d))
