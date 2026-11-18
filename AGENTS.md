# Windows Party contributor instructions

- Every new or changed user-facing label, option, choice, hint, dialog and error
  in the configurator must be available in both French and English in the same
  change. Use `tr()` and maintain `scripts/partydeck_i18n.py`.
- Keep the language policy: French when Batocera uses a French locale; English
  for every other language. Batocera's explicit setting takes precedence over
  an inherited terminal locale.
- Translate display text only. Do not translate stored option identifiers,
  file paths, user-provided player names, room IDs or save contents.
- Verify new game options in both languages. Preserve the existing French
  regression tests and extend `tests/check_i18n.py` when adding a UI surface.
