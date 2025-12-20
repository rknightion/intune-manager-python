# Changelog

## [0.2.0](https://github.com/rknightion/intune-manager-python/compare/v0.1.0...v0.2.0) (2025-12-20)


### ⚠ BREAKING CHANGES

* **auth:** Azure AD app registrations must now be configured as "Mobile and desktop applications" instead of "Web application" type

### Features

* add comprehensive application management improvements ([a4ce064](https://github.com/rknightion/intune-manager-python/commit/a4ce06476a0ffccbcf0b78d89fd9f610af5d8d7a))
* add comprehensive migration tracking system ([3d13553](https://github.com/rknightion/intune-manager-python/commit/3d135533db88dc6fdc25ae2d45eb4df6a93aaff4))
* add crash recovery flow with safe mode support ([ade3aec](https://github.com/rknightion/intune-manager-python/commit/ade3aecc0f7e0f5550f4ef58d28b8dd368106e58))
* add keyboard shortcuts and cache health management ([4a40418](https://github.com/rknightion/intune-manager-python/commit/4a4041844d7395b5b67010ba11a1dc7683283515))
* add platform-specific app icons and desktop integration ([e0b7d0a](https://github.com/rknightion/intune-manager-python/commit/e0b7d0aef3da5bc6bef14ca5dacd958a09dc020c))
* **auth:** add secure secret storage and input validation ([34a5b0c](https://github.com/rknightion/intune-manager-python/commit/34a5b0ca7f5562d10af77fc05f509fe42c36f208))
* **bootstrap:** add complete service initialization pipeline ([88c640a](https://github.com/rknightion/intune-manager-python/commit/88c640a0788446335f7fd3f78563e19bfe67f85d))
* **ci:** add automated artifact management and cleanup system ([5cdcd6c](https://github.com/rknightion/intune-manager-python/commit/5cdcd6c07db404791dbe25b874f1ef9f2d4b3d23))
* **ci:** add concurrency control to prevent duplicate builds ([5c3ae40](https://github.com/rknightion/intune-manager-python/commit/5c3ae40162dabb3ea9f3589bf9a26503aac0b9b2))
* **crash-recovery:** replace modal crash dialog with non-modal notifications ([9f8eadd](https://github.com/rknightion/intune-manager-python/commit/9f8eadd34d77e00cb446f12e7a39417796d71950))
* **graph:** add dual-version API routing and complete MS Graph endpoint audit ([274030c](https://github.com/rknightion/intune-manager-python/commit/274030c8241b7a065487d8607c037a534996e0f6))
* **license:** add MIT license and license checking ([056daa3](https://github.com/rknightion/intune-manager-python/commit/056daa376eb28c67527cf8427ade1ce0d2fd2827))
* **ui:** improve navigation sidebar and toast interaction ([6181812](https://github.com/rknightion/intune-manager-python/commit/618181209b6765bb58f3db4b2f692ffef107780b))
* **ui:** replace legacy alert banner with enhanced toast notifications ([0b84236](https://github.com/rknightion/intune-manager-python/commit/0b842361b3200459c26032f73d29e937d5c750ef))


### Bug Fixes

* **assignments:** resolve assignment editor filter dropdown issues ([a71530c](https://github.com/rknightion/intune-manager-python/commit/a71530c865adb0bb4d8a677b6071113b86cdc9b4))
* **auth:** improve token handling and user loading ([43b587a](https://github.com/rknightion/intune-manager-python/commit/43b587a05a92014a180acf6b2476be48b5aca628))
* **build:** resolve keyring backend issues in compiled builds ([22330c1](https://github.com/rknightion/intune-manager-python/commit/22330c133a7a70fed05e961d4b0bae788e578eda))
* **ci:** enable ccache compiler wrapper with create-symlink ([f829edc](https://github.com/rknightion/intune-manager-python/commit/f829edc303970b8ae444081bb360a2d60af9c4e8))
* **ci:** resolve macOS code signing certificate format issue ([5e53507](https://github.com/rknightion/intune-manager-python/commit/5e53507de800e6d614b12b98abf2299c97eec3f8))
* **deps:** replace pywin32 with pywin32-ctypes for Windows keyring ([ed8a4f6](https://github.com/rknightion/intune-manager-python/commit/ed8a4f68d62969a715dcbccd1df0196b94f36e87))
* handle HTTP 400 errors gracefully for app icon fetches ([dd82390](https://github.com/rknightion/intune-manager-python/commit/dd82390d4338460d6a51f953d080a91ac78501f3))
* improve model validation and sync error handling ([493b582](https://github.com/rknightion/intune-manager-python/commit/493b5822567ba42d256e1ba259d74dc5d0825ce0))
* increase httpx timeout for complex Graph API queries ([5fe7deb](https://github.com/rknightion/intune-manager-python/commit/5fe7deb6e705741ca3ad77e83b83893a74e22541))
* initialize missing AssignmentService in bootstrap ([5c152eb](https://github.com/rknightion/intune-manager-python/commit/5c152eb638195bc827fc82181d6888fbeb3f487b))
* replace deprecated datetime.utcnow() with timezone-aware UTC handling ([1dbfe89](https://github.com/rknightion/intune-manager-python/commit/1dbfe894b7baaaa359ffa248ba38724bcbdc07a8))
* resolve toast notification display issues on startup ([77b8044](https://github.com/rknightion/intune-manager-python/commit/77b80441c940211fcbe92ef3796559e11da3c499))


### Documentation

* update migration log with session 2025-10-27 changes ([b2fc1fc](https://github.com/rknightion/intune-manager-python/commit/b2fc1fc0d8272b98c0ab0632830bdec584323215))


### Miscellaneous Chores

* **deps:** add pyqt6-charts for data visualization ([8cf331a](https://github.com/rknightion/intune-manager-python/commit/8cf331ae1c94277aecbcc1bb35fd6a399ad6e1be))
* **deps:** update actions/checkout action to v5 ([7f13741](https://github.com/rknightion/intune-manager-python/commit/7f13741ed1cfa8735c8b78896645f89949f71097))
* **deps:** update actions/checkout action to v5 ([dabe6da](https://github.com/rknightion/intune-manager-python/commit/dabe6da2c2084d44cb74736e3c2e1cea87b099ae))
* **deps:** update actions/checkout action to v6 ([bd4f007](https://github.com/rknightion/intune-manager-python/commit/bd4f00737f6996a1b0016fd81350c774aa884754))
* **deps:** update actions/checkout action to v6 ([7e450cb](https://github.com/rknightion/intune-manager-python/commit/7e450cb95f41d6c64880894f99b23d47f3e9c492))
* **deps:** update actions/github-script action to v8 ([355f0e1](https://github.com/rknightion/intune-manager-python/commit/355f0e1d0d02bcff0c88f462578f540b8705919d))
* **deps:** update actions/github-script action to v8 ([3959cf4](https://github.com/rknightion/intune-manager-python/commit/3959cf4d12cd4d5098e4ebe4042b99a580f2794c))
* **deps:** update actions/setup-python action to v6 ([cf259e7](https://github.com/rknightion/intune-manager-python/commit/cf259e7c450cd0e600b0c3cb75d42be94069e910))
* **deps:** update actions/upload-artifact action to v5 ([75f2a31](https://github.com/rknightion/intune-manager-python/commit/75f2a31454f012185503faf744a083044ec61ec8))
* **deps:** update astral-sh/setup-uv action to v7 ([8aa83ee](https://github.com/rknightion/intune-manager-python/commit/8aa83eef1d336a50becee6360176f344a4f62fb4))
* standardize output paths and update dependencies ([6b0d2f0](https://github.com/rknightion/intune-manager-python/commit/6b0d2f066abf4989157c04df146ac1e97a5ae800))


### Code Refactoring

* **auth:** migrate from confidential to public client authentication ([d7256c0](https://github.com/rknightion/intune-manager-python/commit/d7256c0bf9200fed37a3746077d23e86d64c915a))
* **build:** simplify nuitka configuration and clean up project files ([10f8149](https://github.com/rknightion/intune-manager-python/commit/10f81494ffb10d9d42a45250c2102ede2442a3a3))
* remove blocking progress dialogs from device refresh ([af86943](https://github.com/rknightion/intune-manager-python/commit/af8694323302b39d1ac6f7cdb4f0520616cfce45))
* remove blocking progress dialogs from group refresh ([0e84c24](https://github.com/rknightion/intune-manager-python/commit/0e84c24ecafb8c13f903ba7d75f0ab66c3e6c4f0))


### Build System

* add pyyaml dependency and configure nuitka static linking ([36f2830](https://github.com/rknightion/intune-manager-python/commit/36f283080ab2157496ffc9e40407be40e554b5ef))
* **nuitka:** optimize build size by excluding unused dependencies ([d245cb8](https://github.com/rknightion/intune-manager-python/commit/d245cb8e17e2afac00b6d17dad59236dc48eef5c))
* **nuitka:** optimize compilation settings and UI layout ([f52585f](https://github.com/rknightion/intune-manager-python/commit/f52585f224a9695525610e16601fd40a1d4d81db))
* optimize nuitka compilation configuration ([83a8f13](https://github.com/rknightion/intune-manager-python/commit/83a8f13e5e1d32534454e2a606efe378bcb72715))
* remove lowmem flag from nuitka configuration ([92369ea](https://github.com/rknightion/intune-manager-python/commit/92369ea0d72c415f424173f7cac8c80c70f74302))
* remove msvc compiler specification ([712c769](https://github.com/rknightion/intune-manager-python/commit/712c769791314f69191bdd4373e5e4f007c3ed73))
