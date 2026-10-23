[app]
title = Overlay Ball
package.name = overlayball
package.domain = org.example
source.dir = .
source.include_exts = py
version = 0.1
requirements = python3,kivy,pyjnius,android
orientation = portrait
android.permissions = SYSTEM_ALERT_WINDOW,FOREGROUND_SERVICE,POST_NOTIFICATIONS
android.api = 33
android.minapi = 26
android.archs = arm64-v8a
services = overlay:service.py:foreground

[buildozer]
log_level = 2
warn_on_root = 1
