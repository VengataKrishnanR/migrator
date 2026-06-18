# DHL DUIL Standard — shared fragment

Canonical source for the `@dhl-official/react-library` mapping. Keep this in sync
in one place; transformer / refactor / validator prompts reference these rules.

| Replace | With |
|---|---|
| `<button>` | `<DhlButton variant={DHL_BUTTON.VARIANT.PRIMARY}>` |
| `<input type="text">` | `<DhlInputField label="..." name="...">` |
| `<input type="checkbox">` | `<DhlCheckbox>` |
| `<input type="radio">` | `<DhlRadioButton>` |
| `<select>` | `<DhlSelect>` |
| `<textarea>` | `<DhlTextareaField>` |
| `<table>` (data) | `<DhlTable>` |
| native `onClick` on a DHL component | `onDhlClick` |
| native `onChange` on a DHL component | `onDhlChange` |

React Hook Form + DHL components: always wrap in `<Controller>`; never spread
`register()` directly onto a DHL component.
