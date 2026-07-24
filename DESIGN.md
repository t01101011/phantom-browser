---
version: alpha
name: Phantom Research
description: A low-profile research workstation for isolated browser identities; precise, dark-native, and spectral without cyberpunk noise.
colors:
  canvas: "#070A09"
  sidebar: "#0A0E0C"
  surface-1: "#0E1310"
  surface-2: "#131A16"
  surface-elevated: "#18211C"
  text-primary: "#E8F0EB"
  text-secondary: "#A2AFA7"
  text-muted: "#66736B"
  text-disabled: "#414A44"
  primary: "#42F58D"
  green-hover: "#6DFFA7"
  green-muted: "#183C28"
  success: "#42D985"
  warning: "#D7A94B"
  error: "#E05D66"
  info: "#6D92C8"
  control-ink: "#07110B"
typography:
  page-title:
    fontFamily: Geist
    fontSize: 1.375rem
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  section-title:
    fontFamily: Geist
    fontSize: 0.9375rem
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: Geist
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0em"
  control:
    fontFamily: Geist
    fontSize: 0.75rem
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0em"
  metadata:
    fontFamily: Geist Mono
    fontSize: 0.6875rem
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0em"
rounded:
  micro: 3px
  control: 6px
  card: 8px
  panel: 10px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.control-ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: 8px
  button-primary-hover:
    backgroundColor: "{colors.green-hover}"
    textColor: "{colors.control-ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: 8px
  button-secondary:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-secondary}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: 8px
  panel:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.panel}"
    padding: 16px
  profile-row-selected:
    backgroundColor: "{colors.green-muted}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.micro}"
    padding: 12px
---

## Overview

Phantom Research is a dark-native operator workspace, not a theatrical “hacker” skin. It should feel calm, compact, and exact: isolated browser identities are research instruments, and the interface helps an operator scan health, launch state, network identity, and recent activity without decorative noise.

The visual posture combines Linear-grade hierarchy with desktop-tool density and one spectral-green signature. Near-black space provides structure; thin cool-green borders and small luminance changes communicate elevation. The supplied Phantom mark is the only prominent brand graphic.

## Colors

The canvas is nearly black with a subtle green undertone. Elevation moves through `canvas → sidebar → surface-1 → surface-2 → surface-elevated`; do not substitute translucent white card soup or glass blur.

`phantom-green` is reserved for primary actions, keyboard focus, selection, and live/active identity. It is not a generic decoration. Success, warning, error, and info retain independent semantic colors so brand green never hides meaning.

Borders use `rgba(220,255,232,0.06)` for separators and `rgba(220,255,232,0.10)` for controls. Focus uses `rgba(66,245,141,0.40)`. Green ambient glow may appear at no more than 12% opacity and only around live state or the mark.

## Typography

Use Geist/system sans for UI and Geist Mono/JetBrains Mono for profile IDs, proxy addresses, ports, versions, PIDs, timestamps, and keyboard shortcuts. Use only weights 400, 500, and 600. Large headings use slight negative tracking; metadata never uses decorative uppercase unless it is a short status or column label.

Primary desktop UI text should remain between 11px and 15px. Hierarchy comes from weight, luminance, and alignment before boxes or color.

## Layout

Use an 8px base rhythm with 4px optical adjustments. The desktop shell has one compact 44px title/command bar, a narrow navigation rail, and a dense main workspace. Table view is the default profile surface; grid is optional.

Bulk controls replace normal toolbar actions when profiles are selected. Avoid putting both normal and bulk actions in the same row. Profile detail may use a right drawer; forms should progressively disclose advanced identity/network settings.

## Elevation & Depth

Depth is communicated through surface luminance and thin borders, not large shadows or glassmorphism. Floating menus and dialogs may use one restrained shadow. Cards use 8px radius, panels 10px, controls 6px. Avoid 16px+ rounded rectangles in operational screens.

## Shapes

Use compact rectangles with softened 6–10px corners. Status uses a dot plus text rather than large colored pills. The signature Phantom geometry may appear in the logo, profile seed avatars, and a single selected-edge motif; do not repeat it as decoration everywhere.

## Components

Primary buttons are flat spectral green with dark ink and no gradient. Secondary buttons use a slightly raised dark surface and a thin border. Destructive actions remain neutral until hover or confirmation.

Navigation active state uses a 2px green rail plus a muted green surface. Selected profile rows use a restrained green tint and visible checkbox. Running status may pulse gently; idle remains neutral; errors use semantic red and a readable reason.

Inputs are 32–36px high with labels outside the control. Focus uses a thin green ring. Icon-only buttons require tooltips and a minimum 32px desktop hit area.

## Do's and Don'ts

Do:
- optimize scanning, keyboard access, and profile-state clarity;
- use green sparingly for interaction and live identity;
- prefer table density and luminance hierarchy;
- preserve semantic warning/error colors;
- support reduced motion and Windows 100%/125% scaling.

Don't:
- use purple/pink gradients, Matrix rain, scanlines, or glitch effects;
- use glassmorphism, giant shadows, or excessive blur;
- turn every section into a rounded card;
- make every status a saturated pill;
- use glow as a substitute for hierarchy.
