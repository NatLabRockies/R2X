# Changelog

All notable changes to this project will be documented in this file. See [conventional commits](https://www.conventionalcommits.org/) for commit guidelines.

---
## [1.0.0](https://github.com/NREL/R2X/compare/v1.0.0rc0..v1.0.0) - 2025-01-15

### Bug Fixes

- **(docs)** Update README.md - ([249ab1b](https://github.com/NREL/R2X/commit/249ab1b814601315fc67acdf3fbd3f53e077b96f)) - pesap
- **(plexos)** Ext data export, Variable defaults, and Data File Scenario Filtering (#38) - ([e963011](https://github.com/NREL/R2X/commit/e9630115d58040c9c9aca6d28c3ca2c4205ead48)) - Kamran Tehranchi
- **(plexos_export)** Added `coalduns` mapping to ReEDS and adding line flow exporter (#55) - ([b8cc616](https://github.com/NREL/R2X/commit/b8cc616f20ba268588c371943936619a94d722e5)) - Jennie Jorgenson
- Update link on README - ([e02aca5](https://github.com/NREL/R2X/commit/e02aca556683b0bf93f3ac0fb005a576088962cf)) - pesap
- Make ReEDS parser compatible with new cost functions (#44) - ([0e09279](https://github.com/NREL/R2X/commit/0e092791ab97688a18fdf5ade175f2536dd3603a)) - pesap
- update file name for planned outages from ReEDS (#49) - ([a07253e](https://github.com/NREL/R2X/commit/a07253e53fcdc3be5dcf9a82030c11d87d6ba047)) - Brian Sergi
- Correctly assign `output_active_power_limits` (#59) - ([cc76cf2](https://github.com/NREL/R2X/commit/cc76cf20179089f86b69c9687a648de6e5a5c4c1)) - pesap
- Compatibility fixes for standard scenarios (#62) - ([fc505d2](https://github.com/NREL/R2X/commit/fc505d2d616175c8c7dade0a540275d934668894)) - pesap
- Changed `BaseUnit` and description for `fixed` field for `ThermalGenerationCost` (#79) - ([d2a2140](https://github.com/NREL/R2X/commit/d2a21403b69111311fc010c0042d2e0f9bf9695f)) - pesap
- Added correct unit validation for `FuelPrice` (#86) - ([1f4f0b1](https://github.com/NREL/R2X/commit/1f4f0b122a7cc164b0f5787fbd8c27b64f9b42d7)) - pesap
- Match the version of the code - ([e0186c7](https://github.com/NREL/R2X/commit/e0186c7cf98dfce9bee78c5307d60785c1362635)) - pesap

### Documentation

- Update README.md - ([ac9971c](https://github.com/NREL/R2X/commit/ac9971c7e22bf6358958114e79b787359a6c21a9)) - pesap
- Adding first version of documentation (#42) - ([d893a6a](https://github.com/NREL/R2X/commit/d893a6a5ff36fbe65e1246207c16c363a6f7f8e3)) - pesap
- Removing references to other repo. - ([9910834](https://github.com/NREL/R2X/commit/99108340d6203854f47f938a51699b24d7aea213)) - pesap
- Cleaning the docs for 1.0 release - ([5d205ff](https://github.com/NREL/R2X/commit/5d205ff1629a34c7fbc3b43e675ed3a9953e5d36)) - pesap
- Adding usage and how-tos to documentation. - ([a7a0c7e](https://github.com/NREL/R2X/commit/a7a0c7ee6cf3acfb1ae617659aa0f7434b9845d9)) - pesap

### Features

- **(plexos)** plexos parser xml (#93) - ([835e904](https://github.com/NREL/R2X/commit/835e90442feae85474658b7f89548f800f1e5f53)) - JensZack
- **(plugins)** Adding CCS plugin for ReDS and Plexos translation (#95) - ([73087e2](https://github.com/NREL/R2X/commit/73087e2feb9d2fc8c4c05a6a9a63093be4b9ce43)) - pesap
- Add compatibility with more operational cost representation on Plexos (#40) - ([77dfceb](https://github.com/NREL/R2X/commit/77dfcebb008e5ea0f62b09d3d9ec41638bbc5598)) - pesap
- Add ReEDS parser to the public version and some Plexos exporter fixes (#43) - ([d1a61f0](https://github.com/NREL/R2X/commit/d1a61f0c7fb214b475f9a577246fa9860614a80f)) - pesap
- Option to Convert Quadratic Value Curves to PWL for Plexos Parser. Fix Reserve Units. (#45) - ([5b5c360](https://github.com/NREL/R2X/commit/5b5c3608cda55f6e1baee71142f4d12e9e8af76a)) - Kamran Tehranchi
- Multiple updates to the Plexos parser (#47) - ([bf284f2](https://github.com/NREL/R2X/commit/bf284f2afa808266ecd10452a3d7c2e445946ae8)) - Kamran Tehranchi
- Update issue templates - ([ece260b](https://github.com/NREL/R2X/commit/ece260b5f7afd8b7ed5308a1d9f51f4785ee720a)) - pesap
- New emission_cap plugin that sets a custom constraint for Plexos output model. (#57) - ([9114586](https://github.com/NREL/R2X/commit/9114586e50ec47841e6033aaa692049c5af1d837)) - pesap
- export fuel curves for plexos (#77) - ([bd651e4](https://github.com/NREL/R2X/commit/bd651e47b2b5bc3e3254deaa29bbdb61a3b747f8)) - JensZack
- Add hurdle rate plugin for ReEDS2Plexos (#60) - ([c0d28f6](https://github.com/NREL/R2X/commit/c0d28f6a71e83d628a11a2c2466f95d77e793f4d)) - pesap
- Update runner to UV (#80) - ([03c5e05](https://github.com/NREL/R2X/commit/03c5e05a56f3cba240e71a7688acd01569ae39a4)) - pesap
- Adding new CLI entrypoints and better handling of scenarios (#94) - ([45cda9b](https://github.com/NREL/R2X/commit/45cda9bdb24b478243d031cc7af059d76dabd3d7)) - pesap

### Miscellaneous Chores

- Adding upgrader package to the repo (#56) - ([93363a9](https://github.com/NREL/R2X/commit/93363a9cea3da903ce95f83a03b48a6ad70aa9ff)) - pesap
- Adding more plexos reports to the default (#85) - ([3caade5](https://github.com/NREL/R2X/commit/3caade5f38ec6e0bffc0586382f0e2668e826cc5)) - pesap

### Tests

- **(codecov)** Adding codecov file (#92) - ([959ef4d](https://github.com/NREL/R2X/commit/959ef4d003d6bdfd6aa583e8615f8dab6b758d3d)) - JensZack

### Ci

- Add codecoverage - ([eec2c24](https://github.com/NREL/R2X/commit/eec2c24c3d5e4c11dfea500b62b80aa15a25863b)) - pesap
- Add capability to run the CI manually - ([2332c31](https://github.com/NREL/R2X/commit/2332c31c2e527b611bde76f86f5e67cb5ed495e9)) - pesap
- Adding action on push to main - ([a524c6e](https://github.com/NREL/R2X/commit/a524c6ee3d6f3de80becefc471647b66e011b6db)) - pesap

### Fi

- Update README.md - ([a7300a6](https://github.com/NREL/R2X/commit/a7300a645fa71e0eb5cb122bec31e904e966b268)) - pesap

---
## [1.0.0rc0] - 2024-09-17

### Bug Fixes

- **(enums)** Uppercase all enums to be compliant with other languages. (#29) - ([98c2a60](https://github.com/NREL/R2X/commit/98c2a60c25d5599b50f5d351c180b0c9a54d8370)) - pesap
- **(plexos)** Fix Rating and Availability Logic (#8) - ([2658b67](https://github.com/NREL/R2X/commit/2658b67496f27b2a7c82f918f92a39f5bca04e25)) - Kamran Tehranchi
- Cleaning configuration file for plexos and adding more testing (#11) - ([dee6edc](https://github.com/NREL/R2X/commit/dee6edc71d10b2fe54fc07d1c9daeaad57d4ba4a)) - pesap
- Updating codebase to match internal (#16) - ([cd4d606](https://github.com/NREL/R2X/commit/cd4d6061112c834e5fc0a93bb5b083ddc7ac164b)) - pesap

### Features

- Implements ValueCurves & Improve Prime Mover and Fuel Type Mapping (#12) - ([fcc37c0](https://github.com/NREL/R2X/commit/fcc37c09dfcdff1e7160ec9264af2be1212be091)) - Kamran Tehranchi
- improve imports fuel costs (#13) - ([c169f1b](https://github.com/NREL/R2X/commit/c169f1bda29686a7a0725bddf7b74ba08285f4e6)) - Kamran Tehranchi
- Cost Function definition and export fixes (#24) - ([eec9cb6](https://github.com/NREL/R2X/commit/eec9cb6beb204828224454d98818d4b79a3efc62)) - Kamran Tehranchi

### Miscellaneous Chores

- Fixing dependencies for runners and fixing testing (#9) - ([718cf22](https://github.com/NREL/R2X/commit/718cf22d3a761160ebc312df83f788579b8b9503)) - pesap

### Plexos

- Fix date_from date_to Filtering (#36) - ([4ba60ce](https://github.com/NREL/R2X/commit/4ba60ce5c7a1bac1707b6567b60c719c1671ff5c)) - Kamran Tehranchi
- Functionalizes field filtering and preparation of ext data (#37) - ([9ddc209](https://github.com/NREL/R2X/commit/9ddc2093bab830cb5a2942c9de4f4c90db3a9561)) - Kamran Tehranchi

### Tests

- Added PJM test system and fixed enum representation to be just string. (#21) - ([1277159](https://github.com/NREL/R2X/commit/12771599973c9849256359c33b034854567dbcaf)) - pesap

### Ci

- **(actions)** Added GitHub actions to the repo (#6) - ([eec81bb](https://github.com/NREL/R2X/commit/eec81bbbab3306b5335a656c1374452f9d54098f)) - pesap
- Adding publish to pypy - ([6dae411](https://github.com/NREL/R2X/commit/6dae4116d4bd5a192291c28eba6e623c3d91e2c4)) - pesap

<!-- generated by git-cliff -->
