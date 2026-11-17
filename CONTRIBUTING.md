# Contributing to Tuckly

Thanks for helping. This page covers what you need to change the code or the translations.

## Setup

```
python -m pip install -r requirements.txt pyflakes
python run.py
```

Python 3.11 or newer on Windows 10 or 11.

## Before you open a pull request

| Check | Command | Expected |
| --- | --- | --- |
| Lint | `python -m pyflakes tuckly tests` | no output |
| Smoke test | `python tests/smoke_test.py` | ends with `TAMAM` |
| Translations | `python tools/extract_strings.py` | every language `N/N`, exit code 0 |

The smoke test runs the whole app against a fake desktop and a temporary settings folder
(`TUCKLY_DATA_DIR`). It does not touch your desktop, your settings or the registry.

## Layout

| Path | What it holds |
| --- | --- |
| `tuckly/app.py` | Application object: cards, organizing, options, startup and command-line requests |
| `tuckly/card.py` | Card window, title bar, file list, card settings popup |
| `tuckly/card_settings.py` | Card settings form (used in the popup and in the control panel) |
| `tuckly/panel.py` | Control panel: navigation, search and pages |
| `tuckly/theme.py` | Themes, the computed `Look`, style sheets |
| `tuckly/widgets.py` | Shared widgets: setting rows, toggles, swatches |
| `tuckly/winapi.py` | Windows API helpers: desktop folders, blur, hidden attributes, context menu |
| `tuckly/i18n.py`, `tuckly/i18n/*.json` | Translation lookup and the translation files |
| `tuckly/tour.py`, `tuckly/updater.py`, `tuckly/notifications.py` | Guided tour, update check, notification badges |
| `tools/` | Icon generation, string extraction, launcher helper |
| `installer/tuckly.iss` | Inno Setup script |

## Two rules that protect users' files

1. **Placing an item in a card must never move, copy or delete it.** Desktop cards store references only.
   When a card accepts a drop it must not report a *move* to the drag source: Explorer deletes the original
   when it is told a move happened.
2. **Anything Tuckly hides, Tuckly must restore.** Desktop icons hidden for placed items are restored when the
   item leaves its card, when Tuckly quits, and by `Tuckly.exe --temizle` (used by the uninstaller).

## Translations

Source strings are Turkish and live in the code, wrapped in `t("...")` (or `mark("...")` for module-level
constants). Each language is one JSON file mapping the Turkish string to its translation.

To fix a translation, edit the value in `tuckly/i18n/<code>.json`.

To add a language:

1. Add `("<code>", "<native name>")` to `LANGUAGES` in `tuckly/i18n.py`, and the Windows language id to
   `system_language()`.
2. Run `python tools/extract_strings.py --template`, copy `tuckly/i18n/_template.json` to
   `tuckly/i18n/<code>.json` and fill in the values.
3. Keep `{0}`, `{1}` placeholders and leading or trailing spaces exactly as in the source.
4. Run `python tools/extract_strings.py` until your language shows `N/N`.

There are no plural rules. Phrase counted strings so they read acceptably for any number.

## Releasing

1. Update the version in `tuckly/__init__.py`, `tools/version_info.txt` and `CHANGELOG.md`.
2. Tag the commit `v<version>` and push the tag. The release workflow builds `Tuckly.exe`, the installer and
   a portable zip, and attaches them to a GitHub release.

Set `REPO_URL` in `tuckly/config.py` to the repository address. The update check and the GitHub buttons on
the About page stay hidden while it is empty.

## Running next to a packaged app

If you start Tuckly from inside an MSIX-packaged program (some editors and tools are packaged this way),
Windows redirects its registry and `%APPDATA%` writes into that package. The right-click entries then never
reach Explorer. Start it through Explorer instead: `python tools/run_outside.py dist\Tuckly\Tuckly.exe`.
