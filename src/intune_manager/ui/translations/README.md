## Qt Translation Catalogs

- Base source strings live in the `.ts` files (generated with `pylupdate6`).
- Compile to `.qm` with `lrelease`:
  ```
  lrelease intune_manager_en.ts -qm intune_manager_en.qm
  ```
- Place compiled `.qm` files in this directory for the application to load.
