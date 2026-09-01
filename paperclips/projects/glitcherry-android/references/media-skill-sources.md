# Media role source lockbox

Last reviewed: 2026-09-01

This record is reference only. The Glitcherry company must not install, vendor,
import, or invoke these third-party skills at runtime. Agents must not execute
their install or update scripts. They grant domain guidance only, never Git,
Paperclip, roadmap, merge, release, or publication authority.

## Official Android sources

- Media3 Transformer and transformations:
  <https://developer.android.com/media/media3/transformer> and
  <https://developer.android.com/media/media3/transformer/transformations>.
- CompositionPlayer:
  <https://developer.android.com/media/media3/transformer/compositionplayer>.
  It is an early-preview `@ExperimentalApi` surface and requires explicit slice
  acceptance plus single-thread access.
- Android supported formats and AGSL:
  <https://developer.android.com/media/platform/supported-formats> and
  <https://developer.android.com/develop/ui/views/graphics/agsl>.
- Media3 release notes:
  <https://developer.android.com/jetpack/androidx/releases/media3>.
  Media3 1.11.0 is the approved stable dependency baseline as of this review.

Official documentation controls API, format, HDR, compatibility, and version
decisions. It must be freshness-checked again in each slice that changes those
decisions.

## Pinned third-party references

### Android Media Pack

- Repository: <https://github.com/sunnat629/android-media-pack>
- Immutable revision: `1d74b4953d21ee31a3acf61eff68972e100c2ac3`
- License: Apache-2.0
- Selected guidance: `media3-transformer-editing`,
  `media3-video-effects-lottie-muxer`,
  `media3-inspector-metadata-thumbnails`, and
  `media3-test-utils-robolectric`.
- Adaptation: workflow/checklist input only. Its Media3 1.10.1 statement is stale
  relative to the official Media3 1.11.0 baseline and must not pin dependencies.

### MiniMax shader-dev

- Repository: <https://github.com/MiniMax-AI/skills>
- Immutable revision: `60aaae52bb2af8162732751a4332f62a5fef518b`
- Selected path: `skills/shader-dev`
- License: MIT
- Adaptation: translate ShaderToy/WebGL assumptions to the explicitly selected
  OpenGL ES, AGSL, or Media3 Effect surface. Verify coordinate, precision,
  multipass, lifecycle, and device performance behavior. Upstream is beta.

### Android media files and sharing

- Repository: <https://github.com/krutikJain/android-agent-skills>
- Immutable revision: `c5bf6731b8441019418784484cca1578413e6ad3`
- Selected path: `skills/android-media-files-sharing`
- License: MIT
- Adaptation: Android Engineer reference for URI, MediaStore, and system share
  boundaries only. It is not render/export authority and contributes no release
  or CI instructions.

Generic FFmpeg commands may inspect host-side fixtures. FFmpeg does not replace
the on-device Media3/MediaCodec path, and no unlicensed command collection may be
copied.

Copying upstream text or assets later requires a separate reviewed change that
records selected files, immutable revision, license, adaptation delta, and a new
official-documentation freshness check.
