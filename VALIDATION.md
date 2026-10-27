# Prüfstand – 26.10.2026

Implementiert aus `productivity-tool-spec-mit-wissensbereich.md`. Die Spec ist unverändert. Diese Datei unterscheidet lokale Testergebnisse von noch nötiger Zielsystem-Abnahme.

## Lokal automatisiert (macOS, Apple Silicon, Python 3.14.5 / Qt 6.12)

- 39 Tests erfolgreich: Hierarchie, Checkbox-Regeln, Reaktivierung, Reihenfolge, Suche mit Elternkontext und Kategorienentfernung.
- JSON-Roundtrip, letzte gültige Sicherung, beschädigte/zu neue Datenversionen, doppelte IDs und Zyklen.
- TXT-Neuanlage/Bearbeitung, Unicode, reservierte Dateinamen, case-insensitive Konflikte, externe Änderungen und gelöschte Dateien, Symlink-Erhalt, Größen-/Kodierungsfehler.
- Dateiliste mit unterstützten Formaten und nichtrekursivem Scan; Word-Text und Tabellen mit HTML-Escaping.
- GUI-Roundtrip, Markdown-Vorschau, echte zweitseitige PDF-Ansicht und PDF-Seitenrendering.
- Echtes PTY im eingebetteten WebEngine/xterm-Terminal: Unicode, isatty, Eingabe, Größenänderung, Prozessende und Ungelesen-Zustand. Verbergen der App lässt den Prozess laufen und markiert neuen Output; Anzeigen setzt ihn zurück.
- Agent-Kommandos sind Argumentlisten mit exakter Resume-ID. Fehlende CLIs sind Fehler. Kontext-Tests zeigen Servernamen ohne Geheimnisse und melden keine erfundene Aktivität.
- Reminder: einmalige Benachrichtigungsmarkierung, erledigte Punkte, verpasste Termine nach Neustart und neu gesetzter Zeitpunkt.
- Zusätzliche GUI-Tests: Enter/Tab, parallele Terminals, Ctrl+C, Erledigungsbestätigung ohne Prozessabbruch, fehlgeschlagener Start ohne Tab/Verknüpfung, Dateikonflikt ohne Editorverlust sowie Instanzsperre und Schreibfehler.
- Ruff-Prüfung erfolgreich. Quellstart mit `--smoke` und `--smoke-terminal` erfolgreich. macOS-App-Bundle erstellt und mit `--smoke` gestartet (Exit 0). Office-Ansicht visuell per Screenshot geprüft.

## Lokale Agent-Startproben (keine Prompts versendet)

| Agent | Installierte Version | Ergebnis |
|---|---|---|
| OpenCode | 2.0.27 | Start im PTY aktiv, ANSI-/Unicode-Output, Größenänderung, Ctrl+C und Ende geprüft |
| Codex | 0.164.0-alpha.11.1 | Start im PTY aktiv, ANSI-/Unicode-Output, Größenänderung, Ctrl+C und Ende geprüft |
| pi | 0.79.10 | Start im PTY aktiv, ANSI-/Unicode-Output; Ende über Ctrl+C geprüft |
| Claude Code | nicht installiert | Verständliche Fehlermeldung geprüft; tatsächlicher Start auf diesem Rechner nicht möglich |

Die Startprobe prüft Prozess und Terminaltransport; eine Modellantwort, alle TUI-Bedienfolgen oder ein authentifizierter Resume sind damit nicht nachgewiesen. Automatische ID-Erkennung wird ausdrücklich als nicht verfügbar angezeigt. Die Spec erlaubt dafür die manuelle Zuordnung; es gibt keine heuristische Zuordnung.

## Zielsystem-Abnahme vor öffentlicher Auslieferung

- Windows: den vorbereiteten CI-Test-/Buildlauf und Installer auf echtem Windows ausführen; ConPTY mit allen vier Agenten, Paste/Ctrl+C/Resize, parallelen Tabs und Unterprozessen prüfen. In dieser Sitzung stand kein Windows-System zur Verfügung.
- Beide Plattformen: je eine bekannte echte native Session-ID manuell zuordnen und die korrekte Session fortsetzen; parallele Starts dürfen sich nicht beeinflussen.
- Paketierte App: native Reminder mit erteilter und verweigerter Berechtigung, Fokusmodus, Klickzuordnung sowie Tray-/Menüleisten-Betrieb prüfen. Der Quellstart ersetzt keinen Test der nativen Berechtigungen eines App-Bundles.
- Word-/PDF-Varianten mit Bildern, Passwortschutz und defekten Dateien sowie Zugriffsfehler im realen Benutzerverzeichnis prüfen. Netzwerk-/Wechsellaufwerke und konkurrierendes Schreiben anderer Programme separat prüfen.
- Notarisierte/signierte öffentliche Artefakte benötigen eigene Signierzertifikate. Die lokale Test-App ist ad-hoc-signiert.

## Kurzer manueller Durchlauf

1. Zwei Aufgaben mit Unterpunkt und mehrzeiliger Notiz anlegen. Elternpunkt bei offenem Kind abhaken: muss ablehnen. Kind und Elternpunkt erledigen, im Filter „Alle“ das Kind wieder öffnen: beide werden offen.
2. Kategorie anlegen, zuweisen, über Legende filtern, Kategorie löschen: Aufgaben bleiben erhalten.
3. Session aus einem Punkt starten: Clipboard enthält genau dessen Text. Zweite Session starten und zwischen Tabs wechseln. Fenster schließen; Sessions bleiben aktiv. Über Tray öffnen, neue Ausgabe prüfen.
4. Bekannte native Session-ID unter Details eintragen, Agent beenden und über Fortsetzen neu starten. App komplett beenden und erneut öffnen: Verknüpfung bleibt, Output nicht.
5. Reminder kurz in die Zukunft setzen und Benachrichtigung zulassen. Eine weitere Erinnerung bei beendeter App verstreichen lassen: nach Neustart nur „Überfällig“.
6. Wissen: Ordner mit TXT, MD, DOCX und PDF auswählen; alle Vorschauen öffnen. Neue TXT-Notiz mit Unicode-Titel erstellen und extern prüfen. Geöffnete TXT extern ändern, dann im Editor speichern: Konflikt, kein stilles Überschreiben. Als neue Notiz sichern.
7. App neu starten: Aufgaben, Kategorien, Sessions, Wissensordner und Dateiauswahl bleiben erhalten.


## UI- und OpenCode-End-to-End-Prüfung · 26.10.2026

Aktueller Quellstand auf macOS / OpenCode 2.0.27:

- Gesamte lokale Suite: **42 bestanden**, ein kostenpflichtiger Live-Test standardmäßig übersprungen.
- Separater Lauf mit echtem OpenCode und echter Modellantwort: **3 End-to-End-Tests bestanden** (inklusive der beiden UI-/Ordner-Tests).
- In der gerenderten Oberfläche über Plus-Button einen Punkt angelegt, Text bearbeitet und über den Kategorie-Dialog zugewiesen. Die tatsächliche Hintergrundfarbe per Screenshot-Pixel geprüft; Kategorie und Erledigt-Zustand nach dem Speichern erneut eingelesen.
- Checkbox per Klick betätigt und im Erledigt-Filter wiedergefunden.
- Standardordner im Session- und Einstellungsdialog geprüft. Ohne Konfiguration entsteht `~/Documents/GetItDone/Sessions`; ein leeres Session-Feld verwendet den konfigurierten Standard.
- OpenCode über den Session-Button und echten Startdialog im integrierten PTY gestartet; Prompt über dieselbe Bridge wie die Terminal-Tastatur gesendet. „Agent läuft“ sowohl an der Aufgabe als auch an der Session geprüft.
- Nach der Modellantwort: „Bereit“ trotz weiter laufender TUI, „Neue Agent-Nachricht“ an Aufgabe und Session. Antwortmarker zusätzlich im tatsächlichen Assistant-Nachrichtenobjekt der lokalen API geprüft (kein bloßer Prompt-Echo-Abgleich).
- Hinweis bleibt über weitere Statusabfragen bestehen, wird durch „Öffnen“ bestätigt und erscheint bei unveränderter Antwort nicht erneut. Native Session-ID bleibt gespeichert; Antworttext landet nicht in notebook.json.
- Screenshots: `build/e2e/01-category.png`, `02-ready.png`, `03-agent-running.png`, `04-new-message.png`.
- Ruff erfolgreich. Dieser Durchlauf prüft den Quellstart; Windows und das paketierte App-Bundle wurden dabei nicht erneut geprüft.

Wiederholen:

```sh
QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 .venv/bin/pytest -q
GETITDONE_LIVE_OPENCODE=1 QTWEBENGINE_DISABLE_SANDBOX=1 .venv/bin/pytest tests/test_e2e.py -q
```

Der Live-Test benötigt ein angemeldetes OpenCode v2 und sendet einen kurzen echten Modellprompt. Testdaten und Session-Arbeitsverzeichnis liegen in einem temporären Verzeichnis; OpenCode verwaltet seinen eigenen Session-Verlauf.


## Animiertes Erledigen und Wiederherstellen · 26.10.2026

- Lokale Suite: **45 bestanden**, ein Live-OpenCode-Test standardmäßig übersprungen; Ruff und Formatprüfung erfolgreich.
- Echter Checkbox-Klick: Erledigung wird gespeichert, die sichtbare Zeile einschließlich Notiz blendet aus und die folgenden Zeilen rücken innerhalb von 340 ms nach.
- Wiederherstellen per Button geprüft: ursprüngliche ID, Kategorie und Notiz bleiben erhalten; der offene Zustand wird wieder gespeichert.
- Mehrere Erledigungen haben unabhängige Hinweise. Wiederherstellen des ersten lässt den zweiten erledigt; dessen Hinweis verschwindet nach fünf Sekunden.
- Abgelehnte Erledigung bei offenem Kind erzeugt weder Animation noch Wiederherstellen-Hinweis.
- Animation und Ergebnis visuell geprüft: `build/e2e/completion-fading.png`, `completion-collapsing.png`, `completion-undo.png`, `completion-restored.png`.

## Update: zuverlässiger Start und Versionswechsel

- Der bisherige Fehler war eine weiterlaufende alte Instanz: Die Instanzsperre verhinderte den neuen Quellstart. Ein Neubau allein ersetzt keinen bereits laufenden Prozess.
- `run.command` fordert nun einen kontrollierten Instanzwechsel an. Die vorhandene App speichert über ihren normalen Beenden-Ablauf; Konflikte und Bestätigungen für laufende Sessions bleiben erhalten.
- Ein normaler zweiter Start desselben Stands aktiviert das vorhandene Fenster. Bei einem anderen Stand wird ein kontrollierter Wechsel angefragt. Ein bereits laufendes App-Bundle erkennt einen Neubau beim erneuten Aktivieren.
- Eine Fingerprint-Kennung steht im Fenstertitel und in `--version`; paketierte Builds enthalten die Kennung ihrer tatsächlichen Quellen.
- 51 Tests erfolgreich, 1 optionaler Modelltest übersprungen. Dazu gehören echte Prozessübergabe, Aktivierung, abgebrochener Wechsel und Erkennung einer erneuerten App.
- Der Starter wurde zusätzlich mit den normalen Benutzerdaten zweimal gestartet: Der alte Prozess endete sauber, der neue meldete den erwarteten aktuellen Stand. Ein App-Start per `open` aktivierte denselben Stand. Die gespeicherten Benutzerdaten wurden zuvor zusätzlich gesichert.
- Paketierter Terminal-Smoke-Test erfolgreich (`TERMINAL_SMOKE_OK`); macOS-Codesign-Struktur geprüft. Der Qt-WebEngine-Helfer wird im Build explizit neben der tatsächlichen Framework-Version abgelegt.

## UX update: colors, reminders, hierarchy and English UI

- App-owned UI text, errors, status labels, agent-context labels and notification text are English. Existing user content and custom category names are preserved. The spec includes a binding UX amendment and README now documents the English controls.
- Color is a 56-pixel column opening a direct 16-swatch palette. No naming or confirmation step. Real rendered pixels are checked in every column for every palette color, including widget backgrounds. Text/icons adapt contrast; clearing a color and keeping child categories independent are tested.
- Parent groups have colored rails, larger bold root rows, separators, deeper indentation and connector lines. Three levels and a second root are covered by UI tests and visual inspection. Icon-only actions have tooltips and accessible names.
- Session rows provide Resume and a details icon; no duplicate Open action. Resume focuses a running tab or resumes the exact stored session without an extra confirmation.
- Reminder root cause: a new reminder's enable checkbox defaulted to off, so Save returned null. The checkbox is removed. Save always creates the selected timezone-aware timestamp; Remove reminder is explicit. An actual dialog test clicks Save, checks the visible cell and JSON persistence, advances processing and verifies exactly one delivery request, then removes the reminder. OS-native delivery still depends on the previously documented platform permissions.
- 55 automated tests passed, 1 optional model-call test skipped. The Office-style view was rendered and visually inspected with full row colors, three hierarchy levels and compact icon actions.


## Follow-up: completion undo, selection, autosave, notes and native reminders

- Completing a parent now completes every descendant. Undo restores each previous done state, including previously completed children, and keeps later text edits. Running descendant sessions participate in the normal hide warning.
- Task actions and typed item/note text save immediately to atomic JSON. The permanent save indicator reflects actual success or failure. Knowledge TXT files retain their separate automatic file-save/conflict behavior.
- The blank selected row was reproduced with zero active text editors: the delegate retained a white paint brush when drawing its selection rectangle, covering the text. The brush is now explicitly non-filling, and focused selection uses a subtle outline. A regression test checks rendered text pixels before/after a real single click and double-click editing separately.
- Task notes span all columns and have a Delete note icon. Deletion has no confirmation; its independent Undo notice restores the text and persists it. UI tests verify actual editor width, trash clicks and disk contents.
- macOS native notification probe initially reported authorization denied. System Settings confirmed GetItDone notifications were Off. At the user's request for system-wide reminders, notifications were enabled (desktop banners, Notification Center and sound). A second real probe returned `accepted: true`, and `getDeliveredNotifications` confirmed the test was present in the system Notification Center (`NOTIFICATION_IN_SYSTEM_CENTER True`). This verifies actual OS delivery, not only a mocked send call.
- The macOS launcher now uses the real .app bundle and automatically rebuilds stale source revisions. Native permission and banner state are reported; the development-only Python process no longer silently relies on Qt's tray fallback. No additional service was installed.
- 61 automated tests passed; 1 optional model-call test skipped. Native notification and normal bundled terminal smoke tests are additional checks. Remaining Windows target-system validation is unchanged.

## Follow-up: independent agent context inspector

- The right panel now works without a selected session: installed CLI selector, independent folder picker, Skills/MCPs/Instructions tabs with counts, source scope/status and read-only text preview. Session selection follows that agent and working directory. Refresh rechecks installations; settings changes refresh profiles. Stale asynchronous responses are discarded.
- Codex's read-only app-server skills/list returned 15 registered skills here, including plugin skills. Its local configuration contained two MCP definitions; these are shown as configured, not connected. OpenCode v2 skill.list and mcp.list were queried read-only and returned empty registries here. No model turn or MCP connection was initiated by the inspector. Full skill content in an existing conversation is not exposed by these integrations.
- Local sources include global/inherited/project instructions. Codex override precedence is tested; JSONC comments/trailing commas preserve quoted strings. Configuration credentials are never previewed. Instruction and skill documents are displayed as plain text without external resources. Custom profiles explicitly report unsupported discovery.
- 65 tests passed, 1 optional real model-call test skipped. Added coverage for global/inherited overrides, nested skills, JSONC/credential exclusion, use without sessions and stale-response handling. The row-selection pixel test now samples empty text-cell background rather than an action icon whose position changes with inspector width.
- The inspector and full window were rendered and visually inspected. The macOS bundle built successfully, passed strict deep signature verification and printed TERMINAL_SMOKE_OK from its bundled PTY smoke test. The DMG was rebuilt. The old app had no active child session, closed through its regular IPC shutdown, and the new bundle is running with revision 96511e5c6293 matching source.
- Remaining limits: CLI presence does not verify authentication. Extra CLI flags, imports, extension resources, trust decisions and some version-specific instruction rules are not fully reproduced; running sessions can retain old instructions. Windows runtime verification remains pending.

## Follow-up: compact task rows

- Main item rows reduced from 40 to 28 px, nested items from 34 to 26 px. Reduced action-button size, checkbox indicators, table-header padding and Add item row. Multiline status retains sufficient height.
- Measured actual rendered parent/child rows at 28/26 px and visually inspected a rendered hierarchy. 65 tests passed, 1 optional model-call test skipped.

## Follow-up: agent context workspace tab

- Moved the complete inspector to the top-level Agent context tab beside Tasks and Knowledge. Tasks now spans the available width above its terminal panel. Removed the obsolete inspector visibility toggle; session/folder synchronization and Knowledge's unsaved-change guard are retained.
- Verified tab labels, widget ownership and task layout in a rendered window, then visually inspected the new tab. 65 tests passed, 1 optional model-call test skipped.

## Feedback-Überarbeitung · 27.10.2026

- Aufgabenbaum: globale Icon-Buttons zum Ein-/Ausklappen; keine farbigen linken Rails; kompakte Plus-Zeile unter jedem geöffneten Punkt einschließlich Blättern; kein „Check to complete“-Hinweis. Sichtbarkeit und Erstellung eines echten Unterpunkts per Klick geprüft.
- Individuelle Aufklappzustände und Titel-/Notizansichten werden sofort mitgespeichert. JSON direkt nach dem Klick eingelesen und mit neuem Tasks-Widget wiederhergestellt; eingeklappte Übersicht mit genau einer Zeile pro Parent geprüft.
- Notizen: `.txt` als Standard, `.md` wählbar, überschreibbarer Titel `Note_YYYY-MM-DD_HH-MM`, Fokus im Inhalt, Enter zum Speichern und Shift+Enter für Zeilenumbruch. Dateiinhalte und Kollisionsschutz geprüft.
- Command/Ctrl+T und Command/Ctrl+N aus allen vier Tabs über echte Qt-Tastaturereignisse geprüft; neue Parent-Zeile unten, direkter Eingabefokus und sofortige Persistenz. Todo-Shortcut auch aus dem Terminal-Popout geprüft. Help → Keyboard shortcuts ergänzt.
- Scheduled tasks: Erstellen, Bearbeiten, Pausieren, manuelles Starten, Löschen, persistierte Inbox, Output-Auswahl und Session-Navigation per GUI geprüft. Datum/Uhrzeit lokal; einmalig oder alle N Minuten/Stunden/Tage/Wochen/Monate. Sommer-/Winterzeit und Monatsende getestet.
- Scheduler mit echten lokalen Prozessen: Ausgabe/Unicode, abgeschlossene und wiederkehrende Runs, keine doppelten Starts, Schreibfehler vor Start, fehlendes Programm, Abbruch und Wiederanlauf nach Unterbrechung. Run wird vor Prozessstart gespeichert; unterbrochene Runs werden nicht automatisch erneut gestartet. Unterprozesse werden beim Stoppen mit beendet.
- Echter Codex-Modelllauf über den Scheduler: `SCHEDULE_OK` empfangen, Exit 0, native Thread-ID und Output in der Inbox gespeichert. Claude ist lokal nicht installiert; dessen Argumentaufbau ist automatisiert geprüft. Live-Modellläufe für Claude, pi und OpenCode sind in dieser Änderung nicht nachgewiesen. Windows-Ausführung bleibt auf einem Windows-System zu prüfen.
- Screenshots visuell geprüft: `build/feedback/tasks-expanded.png`, `tasks-collapsed.png`, `new-note.png`, `scheduled-inbox.png`.
- Scheduler benötigt die geöffnete App (auch versteckt im Tray). Verpasste Ausführungen werden einmal nachgeholt; danach folgt der nächste zukünftige Termin. Pro Run bleiben maximal 1 MB Prozessausgabe erhalten.

Abschluss dieses Durchlaufs: **107 Tests bestanden, 1 optionaler Live-Test übersprungen**; `ruff check app tests` und `git diff --check` erfolgreich. PyInstaller-macOS-Bundle erfolgreich gebaut, `bundle_current(...) == True`; das fertige Bundle mit isoliertem Notebook und `--smoke-terminal` gestartet: **Exit 0, TERMINAL_SMOKE_OK**.

## UX-Abnahme · 27.10.2026

- Shift+Enter fügt in aufgeklappten Aufgabentiteln einen Zeilenumbruch ein; Enter erstellt weiterhin die nächste Aufgabe. Escape entfernt leere neue Entwürfe, ohne bestehende Aufgaben mit Inhalt zu entfernen. Persistenz durch einen zusätzlichen Qt-Test geprüft.
- Zeitplan-Aktionen folgen Auswahl und Laufstatus; Pause/Enable sind eindeutig beschriftet, Stop besitzt ein eigenes Symbol.
- Ohne offene Sessions bleibt der Terminalbereich kompakt. Knowledge bietet ohne Ordner einen zentralen Einstieg; Save as new note und Open externally tragen Beschriftungen.
- Vollständige Qt-Suite mit `QT_QPA_PLATFORM=offscreen`: **108 bestanden, 1 optionaler Live-Test übersprungen**. Nach der letzten Layoutkorrektur zusätzlich **33 betroffene Tests bestanden**. Native Fokusprüfungen waren in dieser Sitzung durch die macOS-Fensteraktivierung unzuverlässig; deshalb wird der vollständige Lauf ausdrücklich als Offscreen-Lauf ausgewiesen.
- Ruff und Diff-Prüfung erfolgreich. Neues macOS-Bundle gebaut und mit isolierten Daten gestartet: **TERMINAL_SMOKE_OK**, Exit 0, `bundle_current(...) == True`.
- Sechs Screenshots mit separaten Beispieldaten unter `build/ux-audit/screenshots/` visuell geprüft; Nutzer hat den Stand abgenommen. Keine persönlichen Notizbuchdaten verändert.
