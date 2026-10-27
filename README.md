# GetItDone

**Aufgaben ordnen, Gedanken festhalten und Coding-Agenten direkt an der passenden Aufgabe öffnen.**

GetItDone ist dein lokales Arbeitsnotizbuch für macOS und Windows. Du kannst Aufgaben in Unterpunkte aufteilen, Notizen und Erinnerungen ergänzen und Dokumente daneben lesen. Deine Aufgaben und Wissensdateien bleiben auf deinem Rechner. Für das Notizbuch brauchst du kein Konto; angebundene Coding-Agenten benötigen ihre eigene Installation und Anmeldung.

![Aufgaben mit Unterpunkten, Notizen, Pastellfarben und dem breiten Add-Item-Button](docs/images/tasks.png)

Die Screenshots zeigen die macOS-Oberfläche mit Beispieldaten. Die Beschriftungen im Programm sind auf Englisch; diese Anleitung erklärt die Bedienung auf Deutsch.

## Starten und loslegen

Öffne **GetItDone**. Unter macOS kannst du die App in den Programme-Ordner ziehen und von dort starten. Unter Windows startest du sie nach der Installation über das Startmenü. Wenn du das Projekt bereits lokal eingerichtet hast, startet ein Doppelklick auf **run.command** auf dem Mac die aktuelle Version.

Installationsdateien erfolgreicher Builds findest du in den Artefakten der [GitHub Actions](https://github.com/oliverruoff/GetItDone/actions/workflows/build.yml). Öffne einen erfolgreichen Lauf für dein Betriebssystem und lade das passende Artefakt herunter; dafür kann eine GitHub-Anmeldung nötig sein. Hinweise zur Einrichtung aus dem Quellcode stehen in der [technischen Anleitung](docs/DEVELOPMENT.md).

Für den ersten Einstieg:

1. Klicke im Reiter **Tasks** unten auf **+ Add item**.
2. Gib eine Aufgabe ein. Mit **Enter** legst du direkt die nächste Aufgabe auf derselben Ebene an.
3. Öffne an einer Aufgabe **… → + Add child item**, um sie in kleinere Schritte aufzuteilen.
4. Ergänze bei Bedarf eine Notiz, eine Farbe oder eine Erinnerung.
5. Setze das Häkchen, sobald die Aufgabe erledigt ist.

Änderungen werden automatisch gespeichert. Unten zeigt **All changes saved**, dass der aktuelle Stand gespeichert wurde.

## Aufgaben bearbeiten und sortieren

Ein **Doppelklick auf den Text** öffnet die Bearbeitung direkt in der Zeile. Alternativ klickst du die Aufgabe an und drückst **F2**. Bei langen Titeln zeigt das Symbol mit den senkrechten Pfeilen den vollständigen Text; aufgeklappte Titel lassen sich mehrzeilig bearbeiten.

Zum Verschieben ziehst du eine Aufgabe mit gedrückter Maustaste an ihre neue Position:

- **Zwischen zwei Zeilen ablegen:** Die Aufgabe wird dort einsortiert. Die Einfügemarkierung zeigt die Position.
- **Auf einer anderen Aufgabe ablegen:** Die gezogene Aufgabe wird deren Unterpunkt.
- **Unter die letzte Aufgabe in den freien Listenbereich ziehen:** Die Aufgabe wird ans Ende der obersten Ebene verschoben.

Vorhandene Unterpunkte wandern mit. Du kannst auch **… → Indent / Outdent** verwenden oder die Reihenfolge mit **Move up / Move down** ändern. Ein Klick auf das kleine Dreieck links klappt eine Gruppe ein oder aus. Ein einzelner Klick auf eine Zeile legt den Bezug für Tastaturaktionen fest, ohne eine zusätzliche Umrandung zu zeichnen.

Über das Suchfeld findest du Aufgaben auch anhand ihrer Notizen. Rechts daneben wechselst du zwischen **Open** (offen), **Completed** (erledigt) und **All** (alle). Übergeordnete Aufgaben können als Kontext eines Suchtreffers sichtbar bleiben.

### Die Symbole an einer Aufgabe

Die Bedeutung eines Symbols erscheint auch, wenn du den Mauszeiger kurz darauf stehen lässt.

| Bedienelement | Was du damit machst |
| --- | --- |
| Häkchen links | Aufgabe erledigen oder wieder öffnen |
| **+ / Farbpunkt** in der Spalte **Color** | Zeilenfarbe wählen oder entfernen |
| Glocke unter **Reminder** | Erinnerung anlegen, ändern oder entfernen |
| Notizsymbol rechts | Notiz direkt unter der Aufgabe öffnen und bearbeiten |
| Terminalsymbol rechts | Neue Coding-Agent-Sitzung für diese Aufgabe anlegen |
| **…** | Weitere Aktionen, etwa Unterpunkt anlegen oder Aufgabe löschen |
| Senkrechte Pfeile rechts | Langen Aufgabentext vollständig anzeigen oder wieder verkürzen |

## Farben und Notizen nutzen

Klicke in der Spalte **Color** auf das Plus oder den Farbpunkt. Ein Klick auf eine der **16 Pastellfarben** färbt die Zeile sofort ein. **No color** entfernt die Zuordnung. Unterpunkte behalten ihre eigenen Farben. Bereits vorhandene eigene Farben bleiben erhalten.

<img src="docs/images/colors.png" alt="Farbauswahl mit 16 hellen Pastelltönen und No color" width="260">

Über das Notizsymbol öffnest du ein Textfeld direkt unter der Aufgabe. Hier ist Platz für Details, Fragen oder Ergebnisse. Deine Eingaben werden automatisch gespeichert. Der Papierkorb an der Notiz löscht ihren Inhalt; anschließend kannst du ihn mit **Undo** wiederherstellen.

## Erledigen und rückgängig machen

Setze links das Häkchen. In der Ansicht **Open** verschwindet die erledigte Aufgabe; für fünf Sekunden kannst du die Aktion über **Undo** zurücknehmen. Später findest du sie unter **Completed** oder **All** wieder und kannst das Häkchen entfernen.

**Wenn du eine übergeordnete Aufgabe erledigst, werden auch ihre Unterpunkte erledigt.** Undo stellt deren vorherigen Erledigungsstand wieder her. Öffnest du einen Unterpunkt erneut, werden auch seine übergeordneten Aufgaben wieder geöffnet.

## An etwas erinnert werden

1. Klicke bei der Aufgabe auf die Glocke in **Reminder**.
2. Wähle Datum und Uhrzeit in deiner lokalen Zeitzone.
3. Klicke auf **Save**. Der Zeitpunkt steht anschließend direkt in der Zeile.

<img src="docs/images/reminder.png" alt="Erinnerungsdialog mit Datum, Uhrzeit, Save und Remove reminder" width="640">

Zum Ändern klickst du erneut auf die Glocke. **Remove reminder** entfernt die Erinnerung.

GetItDone muss laufen, damit eine Benachrichtigung erscheinen kann. Das geschlossene Hauptfenster darf dabei im Hintergrund weiterlaufen. War die App zum Termin vollständig beendet, wird die Erinnerung beim nächsten Start als überfällig angezeigt; sie wird nicht nachträglich als Benachrichtigung zugestellt.

Über **Help → Test notification** prüfst du die Zustellung. Der Benachrichtigungsstatus unten im Fenster führt zu Hinweisen und Einstellungen. Erlaube GetItDone Benachrichtigungen in den Systemeinstellungen; Fokusmodi können Banner unterdrücken.

## Wissen und Dokumente griffbereit halten

Im Reiter **Knowledge** arbeitest du mit Dateien aus einem lokalen Ordner.

![Knowledge mit Dateiliste links und einer geöffneten Textnotiz rechts](docs/images/knowledge.png)

1. Klicke auf **Choose folder** und wähle deinen Wissensordner.
2. Wähle links eine Datei aus. Über das Suchfeld kannst du Dateinamen filtern.
3. Mit **New note** erstellst du eine neue Textnotiz. Der Titel wird zum Dateinamen.

| Dateityp | Bedienung in GetItDone |
| --- | --- |
| TXT | Lesen und bearbeiten; Änderungen werden nach einer kurzen Schreibpause automatisch gespeichert |
| Markdown | Formatierte Leseansicht |
| Word (.docx) | Leseansicht für Text und Tabellen; das Layout kann von Word abweichen |
| PDF | Seiten direkt im Programm ansehen |

Die Liste zeigt Dateien direkt im gewählten Ordner, keine Unterordner. Neue Notizen werden als echte `.txt`-Dateien gespeichert und lassen sich auch mit anderen Programmen öffnen. Das Symbol **Open externally** öffnet eine Datei in der zugeordneten Anwendung.

Wurde eine Textdatei gleichzeitig außerhalb von GetItDone geändert, stoppt das Speichern und dein Text bleibt im Editor. Mit **Save as new note** bewahrst du ihn als zusätzliche Datei auf. Mit **Refresh** kannst du nach dem Verwerfen lokaler Änderungen die externe Version neu laden.

## Coding-Agenten an Aufgaben öffnen

Du kannst **OpenCode, Codex, Claude Code oder pi** in integrierten Terminals verwenden. Installiere den gewünschten Agenten zunächst separat und melde dich bei ihm an. Die Nutzung richtet sich nach dessen Konto, Berechtigungen und gegebenenfalls Kosten.

1. Klicke an einer Aufgabe auf das Terminalsymbol **New session**.
2. Wähle den Agenten und den Arbeitsordner, in dem er arbeiten soll.
3. Bestätige mit **New session**.
4. Der Aufgabentext wird in die Zwischenablage kopiert. Füge ihn im Terminal ein und sende ihn selbst ab.

Unter der Aufgabe erscheint die verknüpfte Sitzung. **Resume** öffnet ihr laufendes Terminal oder setzt die gespeicherte Sitzung fort, sofern ihre Sitzungs-ID vorliegt. Das Infosymbol öffnet Details wie Arbeitsordner und Sitzungs-ID. Fehlt diese ID bei einer älteren Sitzung, ist eine Fortsetzung erst möglich, wenn sie gefunden oder in den Details ergänzt wurde.

![Aufgaben oben und integriertes Terminal unten mit Symbolen für Kopieren, Einfügen, Maximieren und Auslagern](docs/images/terminals.png)

*Für diesen Screenshot läuft nur eine lokale Demo-Shell, kein Coding-Agent.*

Die Symbolleiste oberhalb der Terminals bietet von links nach rechts:

| Symbol / Tooltip | Funktion |
| --- | --- |
| **Paste** | Text aus der Zwischenablage einfügen |
| **Copy selection** | Markierten Terminaltext kopieren |
| **Send Ctrl+C** | Ein Strg+C-Signal an den laufenden Prozess senden |
| **Maximize / Restore** | Terminalbereich vergrößern oder Aufgaben wieder einblenden |
| **Pop out / Dock** | Terminals in ein eigenes Fenster auslagern oder wieder einbetten |

Schließt du das ausgelagerte Fenster, werden die Terminals wieder in das Hauptfenster eingebettet. Über **View → Terminal panel** kannst du den Bereich ein- und ausblenden. Der aktuelle Terminalverlauf bleibt nur für die Laufzeit der App erhalten; nach einem Neustart wird er nicht wieder angezeigt.

Im Reiter **Agent context** kannst du für einen Agenten und Arbeitsordner gefundene **Skills**, **MCPs** und **Instructions** ansehen. Das funktioniert auch ohne laufende Sitzung. Die Ansicht zeigt gefundene oder konfigurierte Einträge; sie bestätigt nicht, dass der Agent sie in einer bestimmten Unterhaltung tatsächlich geladen oder aktiviert hat.

## Nützliche Tastenkürzel

Klicke vorher auf die gewünschte Aufgabe. Die Kürzel gelten in der Aufgabenliste, nicht beim Schreiben einer mehrzeiligen Notiz.

| Taste | Aktion |
| --- | --- |
| **Enter** | Nächste Aufgabe auf derselben Ebene anlegen |
| **F2** | Aufgabentext bearbeiten |
| **Tab** | Aufgabe einrücken |
| **Shift + Tab** | Aufgabe ausrücken |
| **Alt + ↑ / ↓** | Aufgabe innerhalb ihrer Ebene verschieben |

## Schließen, speichern und sichern

**Fenster schließen** lässt GetItDone im Hintergrund in der Menüleiste beziehungsweise im Infobereich weiterlaufen. So bleiben Erinnerungen und laufende Sitzungen verfügbar. Gibt es keinen Infobereich, bleibt das Fenster minimiert. Mit **File → Quit** beendest du die App vollständig; bei laufenden Sitzungen fragt sie vorher nach.

Aufgaben, Notizen an Aufgaben, Farben, Erinnerungen und Sitzungsverknüpfungen werden lokal gespeichert. Den genauen Speicherort zeigt **Settings**. Wissensdateien bleiben separat in dem von dir gewählten Ordner. Es gibt keine automatische Synchronisierung zwischen Rechnern.

Für ein Backup beendest du die App und sicherst sowohl den in **Settings** angegebenen Datenordner als auch deinen Wissensordner. Neben `notebook.json` liegt `notebook.backup.json` mit dem vorherigen gültigen Speicherstand. Wenn unten ein Speicherfehler angezeigt wird, behebe ihn, bevor du dich auf den gespeicherten Stand verlässt.

## Wenn etwas nicht klappt

| Problem | Das kannst du prüfen |
| --- | --- |
| Eine Aufgabe ist verschwunden | Suche leeren und den Filter auf **All** stellen; eingeklappte Gruppen öffnen |
| Keine Benachrichtigung | App laufen lassen, **Help → Test notification** nutzen und Systemberechtigung sowie Fokusmodus prüfen |
| Ein Agent fehlt oder startet nicht | Installation und Anmeldung des Agenten sowie den gewählten Arbeitsordner prüfen |
| Resume meldet eine fehlende ID | Sitzungsdetails öffnen; ohne passende ID lässt sich die ursprüngliche Unterhaltung nicht zuverlässig fortsetzen |
| Eine Datei lässt sich nicht bearbeiten | In Knowledge sind TXT-Dateien editierbar; andere Formate über **Open externally** bearbeiten |
| Ein neues Fenster erscheint beim erneuten Start nicht | GetItDone aktiviert normalerweise die bereits laufende Instanz |

Technische Einrichtung, Tests und Builds: [Entwicklerdokumentation](docs/DEVELOPMENT.md). Geprüfte Plattformgrenzen: [Validierung](VALIDATION.md).
