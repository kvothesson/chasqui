# Changelog

What changed for people who use chasqui. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-10-21

### Added

- **Windows installer** (`chasqui-setup-<version>.exe`): no Python needed,
  installs per user without an admin prompt. Built by GitHub Actions and
  attached to each release. Not code-signed yet, so SmartScreen will warn.
- **Setup window on first run**: asks for your OpenAI key, checks it, and
  tells you whether VB-Audio Cable is installed. The key is saved to
  `~/.chasqui/config.yaml`, never to a project `chasqui.yaml`.
- **Isolated turns** (`api.isolate_turns`, gpt-realtime only, on by default):
  each finished sentence is translated on its own, so a short question like
  "¿Llegaste bien?" is translated instead of answered. Wrong turns in our
  drift test went from 4/30 to 1/30, for about 0.5s more per short turn.
- **Silence gate** (`silence_gate`, off by default): quiet audio is not
  streamed, so it is not billed. It holds open 3s after the last sound,
  because the translate endpoint needs that much to finish a sentence.
  About 52% fewer billed minutes on a call-like test.
- **Passthrough** (`passthrough`, 0 = off): your original voice, quietly,
  under the translation the other side hears (headset, meet, virtual-mic).

### Fixed

- **Cost meter prices**: the input transcription is billed on top of the
  translation, so the real price is $0.051/min per direction ($0.102 for a
  two-way call), not $0.034.

### Docs

- README note on Meet, Teams and Zoom noise suppression, which can eat the
  translated voice.
- Landing page in English and Spanish at https://kvothesson.com/chasqui/.

## [0.2.0] - 2026-10-20

First release on PyPI, as `chasqui-translate` (plain `chasqui` was taken).
The commands are still `chasqui` and `chasqui-ui`.

### Added

- Real-time speech translation over the OpenAI Realtime API, with
  `gpt-realtime-translate` (cheaper) or `gpt-realtime` (follows
  instructions).
- Modes: `text`, `device`, `virtual-mic`, `media` (videos and podcasts),
  `headset` and `meet` (two-way calls), `bridge` (two machines on a LAN).
- Windows default-device switching for media and headset, restored on exit.
- Desktop window (`chasqui ui`): start/stop, languages, devices, live
  transcript, cost meter with an optional budget.
- `chasqui check` (round trip without audio hardware), `chasqui devices`,
  `chasqui langs`, `chasqui translate`, `chasqui init`.

[Unreleased]: https://github.com/kvothesson/chasqui/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/kvothesson/chasqui/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/kvothesson/chasqui/releases/tag/v0.2.0
