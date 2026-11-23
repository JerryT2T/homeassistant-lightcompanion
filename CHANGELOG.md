# Changelog

All notable changes to Light Companion are documented in this file.

## [1.2.0] — 2026-11-22

### Added
- Several rooms at once: tap more than one room chip and the same plan is applied to all of them, with a single AI call
- Rooms can be named in the chat instead of tapped. The AI picks them from the fixed room list, so typos, nicknames, aliases and descriptions ("where I cook", "upstairs", "everywhere") work; the reply shows which rooms were used
- Special lights (opt-in), for example a star projector: mark a light in the card settings and add a note saying when it fits. It is never part of "all lights" and is only switched on when you ask for exactly that light or the note allows it right now
- The AI is told which media players of a room are on or playing (state, source, app, title), so it can tell a running film from background music

### Changed
- The card keeps one chat for all rooms instead of one per room

### Fixed
- Rooms with several Music Assistant players no longer pick an unavailable or switched-off player while another one is usable, and following the music now watches all players of the room instead of only the one that was chosen first

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
