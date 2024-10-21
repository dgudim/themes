// SPDX-FileCopyrightText: Vlad Zahorodnii <vlad.zahorodnii@kde.org>, Martin Flöser
// <mgraesslin@kde.org>, Simon Schneegans <code@simonschneegans.de>
// SPDX-License-Identifier: GPL-3.0-or-later

"use strict";

const blacklist = [
  // The logout screen has to be animated only by the logout effect.
  "ksmserver ksmserver",
  "ksmserver-logout-greeter ksmserver-logout-greeter",

  // KDE Plasma splash screen has to be animated only by the login effect.
  "ksplashqml ksplashqml",

  // All the tooltips of IntelliJ IDEs use the same window class as their main window.
  // This results in many awkward animations, so we have to blacklist them all.
  // See https://github.com/Schneegans/Burn-My-Windows/issues/284 for details.
  "jetbrains-studio jetbrains-studio",
  "jetbrains-aqua jetbrains-aqua",
  "jetbrains-clion jetbrains-clion",
  "jetbrains-datagrip jetbrains-datagrip",
  "jetbrains-dataspell jetbrains-dataspell",
  "jetbrains-goland jetbrains-goland",
  "jetbrains-idea jetbrains-idea",
  "jetbrains-idea-ce jetbrains-idea-ce",
  "jetbrains-phpstorm jetbrains-phpstorm",
  "jetbrains-pycharm jetbrains-pycharm",
  "jetbrains-pycharm-ce jetbrains-pycharm-ce",
  "jetbrains-rider jetbrains-rider",
  "jetbrains-rubymine jetbrains-rubymine",
  "jetbrains-webstorm jetbrains-webstorm",
];

class BurnMyWindowsGlideEffect {
  constructor() {
    effect.configChanged.connect(this.loadConfig.bind(this));
    effect.animationEnded.connect(this.cleanupForcedRoles.bind(this));
    effects.windowAdded.connect(this.slotWindowAdded.bind(this));
    effects.windowClosed.connect(this.slotWindowClosed.bind(this));
    effects.windowDataChanged.connect(this.slotWindowDataChanged.bind(this));

    this.shader = effect.addFragmentShader(Effect.MapTexture, "glide.frag");

    this.loadConfig();
  }

  // A small helper which can be used to read a hex color string (e.g. #ff3244) from the
  // settings. This method will return an array of four floating point values
  // [r, g, b, a]. If the settings key only refers to an rgb value, the alpha component
  // will be set to 1.0.
  readRGBAConfig(key) {
    const color = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})?([a-f\d]{2})?$/i
      .exec(effect.readConfig(key, "#ffffff"))
      .slice(1)
      .filter((x) => x !== undefined)
      .map((x) => parseInt(x, 16) / 255);
    return color.length == 3
      ? [color[0], color[1], color[2], 1.0]
      : [color[1], color[2], color[3], color[0]];
  }

  // A small helper which can be used to read a hex color string (e.g. #ff3244) from the
  // settings. This method will return an array of three floating point values [r, g, b]
  // regardless of whether the settings key actually refers to an argb hex string.
  readRGBConfig(key) {
    const color = this.readRGBAConfig(key);
    color.pop();
    return color;
  }

  // This is called when the effect is loaded and whenever the settings of the effect
  // are changed by the user.
  loadConfig() {
    this.duration = animationTime(effect.readConfig("Duration", 1000));

    // SPDX-FileCopyrightText: Simon Schneegans <code.de>
    // SPDX-License-Identifier: GPL-3.0-or-later

    // This part is automatically included in the effect's source during the build
    // process. The code below is called whenever the user changes something in the
    // configuration of the effect.

    effect.setUniform(this.shader, "uScale", effect.readConfig("Scale", 1.0));
    effect.setUniform(this.shader, "uSquish", effect.readConfig("Squish", 1.0));
    effect.setUniform(this.shader, "uTilt", effect.readConfig("Tilt", 1.0));
    effect.setUniform(this.shader, "uShift", effect.readConfig("Shift", 1.0));
  }

  static shouldAnimateWindow(window) {
    return window.modal;
  }

  setupForcedRoles(window) {
    window.setData(Effect.WindowForceBackgroundContrastRole, true);
    window.setData(Effect.WindowForceBlurRole, true);
  }

  cleanupForcedRoles(window) {
    window.setData(Effect.WindowForceBackgroundContrastRole, null);
    window.setData(Effect.WindowForceBlurRole, null);
  }

  slotWindowAdded(window) {
    if (effects.hasActiveFullScreenEffect) {
      return;
    }
    if (!BurnMyWindowsGlideEffect.shouldAnimateWindow(window)) {
      return;
    }
    if (!window.visible) {
      return;
    }
    if (effect.isGrabbed(window, Effect.WindowAddedGrabRole)) {
      return;
    }
    this.setupForcedRoles(window);

    effect.setUniform(this.shader, "uForOpening", 1.0);
    effect.setUniform(
      this.shader,
      "uIsFullscreen",
      window.fullScreen ? 1.0 : 0.0,
    );

    window.bmwInAnimation = animate({
      window: window,
      curve: QEasingCurve.Linear,
      duration: this.duration,
      animations: [
        {
          type: Effect.ShaderUniform,
          fragmentShader: this.shader,
          uniform: "uProgress",
          from: 0.0,
          to: 1.0,
        },
      ],
    });
  }

  slotWindowClosed(window) {
    if (effects.hasActiveFullScreenEffect) {
      return;
    }
    if (!BurnMyWindowsGlideEffect.shouldAnimateWindow(window)) {
      return;
    }
    if (!window.visible || window.skipsCloseAnimation) {
      return;
    }
    if (effect.isGrabbed(window, Effect.WindowClosedGrabRole)) {
      return;
    }
    if (window.bmwInAnimation) {
      cancel(window.bmwInAnimation);
      delete window.bmwInAnimation;
    }
    this.setupForcedRoles(window);

    effect.setUniform(this.shader, "uForOpening", 0.0);
    effect.setUniform(
      this.shader,
      "uIsFullscreen",
      window.fullScreen ? 1.0 : 0.0,
    );

    window.bmwOutAnimation = animate({
      window: window,
      curve: QEasingCurve.Linear,
      duration: this.duration,
      animations: [
        {
          type: Effect.ShaderUniform,
          fragmentShader: this.shader,
          uniform: "uProgress",
          from: 0.0,
          to: 1.0,
        },
      ],
    });
  }

  slotWindowDataChanged(window, role) {
    if (role == Effect.WindowAddedGrabRole) {
      if (window.bmwInAnimation && effect.isGrabbed(window, role)) {
        cancel(window.bmwInAnimation);
        delete window.bmwInAnimation;
        this.cleanupForcedRoles(window);
      }
    } else if (role == Effect.WindowClosedGrabRole) {
      if (window.bmwOutAnimation && effect.isGrabbed(window, role)) {
        cancel(window.bmwOutAnimation);
        delete window.bmwOutAnimation;
        this.cleanupForcedRoles(window);
      }
    }
  }
}

new BurnMyWindowsGlideEffect();
