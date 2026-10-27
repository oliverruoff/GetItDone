# Manual test folder

`knowledge/` contains three normal TXT files for manually checking folder import, Unicode, content and autosave. Automated tests create separate temporary files and do not depend on this folder.

An isolated manual notebook was prepared locally under `notebook/` (Git-ignored), with sample tasks and this knowledge folder selected. Launch it without opening your existing notebook:

```sh
releases/macos/GetItDone.app/Contents/MacOS/GetItDone --data-dir "$PWD/tests/manual/notebook"
```

Agent sessions require installed authenticated CLIs. The manual fixture suggests `openai/gpt-5.4-mini` for pi because that provider worked during validation; it still needs credentials available in the environment used to launch the app.
