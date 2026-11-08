# Changelog

All notable changes to Light Companion are documented in this file.

## [1.1.0] — 2026-11-08

### Changed
- Each area's effect switch now sits on its own child device of "Light Companion", placed in that area. With the Home Assistant 2026.11 naming model the switch is simply called "Effect" and Home Assistant adds the area from context; entity IDs and unique IDs are unchanged
- Requires Home Assistant 2026.11 or newer (child devices)

## [1.0.2] — 2026-11-08

### Changed
- Repository links, issue tracker and code owner point to the renamed GitHub account JerryT2T (#37)
- The README explains how to remove the old 0.x add-on and its repository from the Home Assistant app store, where it shows up as "unknown" (#37)
- New CHANGELOG (#37)

## [1.0.1] — 2026-11-04

### Fixed
- The card is registered again when mobile Home Assistant swaps the custom element registry, so dashboards no longer show "Custom element doesn't exist: lightcompanion-card" (#36)

## [1.0.0] — 2026-11-01

See the [v1.0.0 release](https://github.com/JerryT2T/homeassistant-lightcompanion/releases/tag/v1.0.0).
