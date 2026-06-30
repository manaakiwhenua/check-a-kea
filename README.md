![](icon.png)

[![manaakiwhenua-standards](https://github.com/manaakiwhenua/check-a-kea/workflows/manaakiwhenua-standards/badge.svg)](https://github.com/manaakiwhenua/manaakiwhenua-standards)

# Check-a-Kea

Check-a-Kea is a QGIS plugin for fast human validation of spatial features.

It is designed for quickly stepping through features, assigning validation values using keyboard shortcuts, viewing supporting attribute information, and writing associated comments.

It lets you:

- choose a vector layer to validate
- step through features in the order shown in the QGIS attribute table
- write configurable validation values (including NULL) to one attribute field using keyboard shortcuts
- view selected attributes while validating
- add optional free-text comments to a configurable comment field
- auto-advance after each feature is validated
- use multi-key shortcuts (rather than only single buttons)

## Setup

Your layer needs a field for validation values. If you want to use comments, your layer should also have a text field for that.

Open Check-a-Kea from the QGIS plugin menu and click **Settings / preferences** to configure the plugin. Validation starts automatically when you save the settings.

## Settings

Settings are split into two tabs:

**Settings** (saved in the `.qgz`/`.qgs` project file — different per project):

| Setting | Description |
|---|---|
| Layer | The vector layer whose features will be validated. |
| Validation field | Attribute field that receives the validation value. Select an existing field or choose *Create field…* to add one. |
| Comment field | Attribute field that receives optional free-text comments. Set to *— none —* to hide the comment box, or *Create field…* to add one. |
| Unvalidated filter | QGIS expression used to select features for validation. Leave blank to include all features. |
| Display fields | Attributes shown in the feature preview panel. Use *Select all* to show everything; leave blank to hide the preview entirely. |
| Shortcuts | Keyboard shortcuts and the values they write to the validation field. |

**Preferences** (saved in QGIS user settings — shared across all projects):

| Setting | Description |
|---|---|
| Zoom buffer | Extra zoom padding around the current feature (%). |
| Auto-advance | If enabled, the plugin moves to the next feature after a shortcut is pressed. |
| Auto-advance delay | Delay in milliseconds before auto-advancing. |
| Auto-identify | Automatically "identifies" the current feature using the built-in identify tool as you navigate. |

## Usage

1. Open Check-a-Kea from the QGIS plugin menu.
2. Click **Settings / preferences**.
3. Select a vector layer, validation field, and configure shortcuts.
4. Click **Save** — the validation queue starts automatically.
5. Review the current feature's attributes.
6. Add an optional comment.
7. Press a shortcut key to validate and advance.
8. Use **◀ Previous** / **Next ▶** or the left/right arrow keys to navigate manually.

NB users must manually save all layer edits when finished for them to be written to disk. This plugin edits the validation data using the built-in edit functionality.

NB the auto-identify option is useful for seeing the full set of layer attributes, and also those of coincident layers. To change the identify highlight colour, go to **Settings** > **Options** > **Map Tools** > **Identify**.

The **Summary** tab shows a bar chart of how many features currently hold each validation value across the whole layer, including unvalidated features. It updates after each shortcut press and when the queue is started.

If you have the layer's attribute table open in QGIS, the current feature will be kept in view (auto-scrolling). Clicking a row in the attribute table makes that the active feature.

## Keyboard shortcuts

Navigation:

```text
Left Arrow  = Previous feature
Right Arrow = Next feature
```

Default validation shortcuts:

```text
1 = true
2 = false
3 = maybe
```

Shortcuts are fully configurable in the **Settings / preferences** dialog.

### Shortcut key format

Shortcut keys are entered as plain text and normalised automatically:

| Input | Registered as | Notes |
|---|---|---|
| `1` | `1` | Single digit |
| `120` | `1, 2, 0` | Multi-digit: expanded to a keystroke sequence |
| `e` | `E` | Lowercase letter |
| `E` | `Shift+E` | Uppercase letter implies Shift |
| `aa` | `A, A` | Multi-char lowercase: expanded per character |
| `BB` | `Shift+B, Shift+B` | Multi-char uppercase: each gets Shift |
| `aB` | `A, Shift+B` | Mixed case: applied per character |
| `Shift+e` | `Shift+E` | Explicit modifier |
| `F1` | `F1` | Named keys passed through unchanged |

### NULL shortcuts

Any shortcut value can be set to **NULL** (∅) using the checkbox in the shortcuts table. When activated, the shortcut clears the validation field rather than writing a string value.

## Feature order and filtering

By default, Check-a-Kea steps through features in their natural layer order.

**Attribute table sort:** if the QGIS attribute table is open, the **◀ Previous** / **Next ▶** buttons follow its current sort order. The "Feature X of Y" counter in the footer reflects the position in that sorted order. If no attribute table is open, features are visited in the order they were returned by the unvalidated filter.

**Attribute table filter:** if the attribute table is filtered (e.g. "Show selected features"), navigation respects that filter and only steps through visible features that are also in the validation queue.

**Layer filter:** if a permanent filter is set on the layer (via Layer Properties → Source), only matching features are included in the queue. The unvalidated filter is applied on top of this — both must be satisfied for a feature to appear.

**Limiting to unvalidated features:** set the unvalidated filter to a QGIS expression, for example:

```text
validation IS NULL OR validation = ''
```

Leave it empty to include all features (useful for inspection or re-validation).

## Notes

Check-a-Kea starts an edit session automatically if the selected layer is not already editable.

The plugin does not automatically commit/save the layer after every validation. This allows you to use normal QGIS edit workflows, including undo, save edits, or discard edits.

Comments are saved to the edit buffer 500 ms after typing (debounced). Like other edits, they still need to be saved manually to be written to disk.

**Remember to save your layer edits in QGIS!!**

## Development

Install dev dependencies (into your QGIS Python environment or a separate venv):

```bash
pip install -r requirements-dev.txt
```

Format code with [black](https://black.readthedocs.io):

```bash
black .
```

Run unit tests (no QGIS required):

```bash
make test
```

Run integration tests (requires QGIS Python environment):

```bash
make test-qgis
```

### Dev install

Symlink the repo into the QGIS plugins directory so edits are reflected immediately:

```bash
make dev-install
```

Then enable the plugin in QGIS via **Plugins → Manage and Install Plugins**. The [Plugin Reloader](https://plugins.qgis.org/plugins/plugin_reloader/) plugin is recommended during development — it reloads the plugin without restarting QGIS.

To remove the symlink:

```bash
make dev-uninstall
```

### Building a release zip

```bash
make zip
```

This produces `check_a_kea-<version>.zip` (version is read from `metadata.txt`), which can be installed in QGIS via **Plugins → Manage and Install Plugins → Install from ZIP**.

The zip packages only the files needed at runtime — tests, the Makefile, and other dev files are excluded.

For translation workflows, see [i18n/README.md](i18n/README.md).
