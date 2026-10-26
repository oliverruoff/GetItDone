# Spec: Persönliches PO-Arbeitsnotizbuch

Status: abgestimmter Funktionsumfang, technische Integrationsdetails zu validieren.

## Ergänzende verbindliche Bedienregeln (26.10.2026, zweite Überarbeitung)

Diese Regeln haben Vorrang vor abweichenden älteren Erledigungs-, Undo-, Speicher- und Startvorgaben:

- **Kaskadierende Erledigung:** Ein Elternpunkt darf immer abgehakt werden. Seine sämtlichen Nachfahren werden dabei ebenfalls erledigt. **Undo** stellt die Offen-/Erledigt-Zustände aller betroffenen Punkte so wieder her, wie sie vor genau diesem Vorgang waren; zuvor bereits erledigte Kinder bleiben erledigt. Text, Notizen, Kategorien und spätere unabhängige Änderungen werden dadurch nicht zurückgesetzt. Beim Ausblenden laufender Sessions bleibt die bestehende Warnung erhalten, auch wenn diese an Nachfahren hängen.
- **Sofortiges automatisches Speichern:** Aufgabenaktionen und Texteingaben werden ohne manuelles Save atomisch gespeichert. Ein dauerhaft sichtbarer Status meldet **All changes saved** oder einen tatsächlichen Schreibfehler. Das TXT-Dateieditor-Verhalten im Wissensbereich bleibt automatische Speicherung nach kurzer Eingabepause plus Speichern beim Dokumentwechsel; Dateikonflikte dürfen weiterhin nicht still überschrieben werden.
- **Auswahl ist keine Bearbeitung:** Ein einfacher Klick wählt die Zeile aus und lässt ihren Text und die Zeilenfarbe vollständig sichtbar. Der Texteditor öffnet nur durch einen expliziten Bearbeitungsschritt wie Doppelklick/F2; neue Punkte dürfen weiterhin sofort zur Eingabe geöffnet werden. Eine Auswahlmarkierung darf den Zeileninhalt nicht übermalen.
- **Zeilenbreite Notizen:** Das Notizfeld eines Aufgabenpunkts spannt über alle Tabellenspalten. Es enthält ein zugänglich beschriftetes Trash-Icon **Delete note**. Löschen erfolgt ohne Bestätigung; eine eigene Undo-Mitteilung stellt den gelöschten Notiztext wieder her. Mehrere Undo-Mitteilungen sind unabhängig.
- **Systemweite Reminder:** Auf macOS startet der normale Starter die echte GetItDone-App mit eigener Bundle-Identität und nativer UserNotifications-Anbindung. Ein veralteter Build wird automatisch neu gebaut. Der Python-Entwicklungsprozess darf nicht suggerieren, dass er dieselbe native Zustellung garantiert. Die App prüft Berechtigung und Bannerstatus, meldet blockierte Mitteilungen ausdrücklich und bietet Zugang zu den Systemeinstellungen. Eine Testmitteilung muss tatsächlich durch die systemweite Mitteilungszentrale angenommen und dort nachgewiesen werden. Fokus-/Nicht-stören-Regeln bleiben Betriebssystemvorgaben. Es wird kein zusätzlicher Hintergrunddienst eingerichtet.
- **Modernisierte ruhige Oberfläche:** Klarere Tabs, abgerundete Eingabefelder und dezente Auswahlmarkierungen modernisieren die kompakte englische Oberfläche, ohne zusätzliche Dashboards oder Aufgabenhierarchien einzuführen.

## Verbindliche UX-Überarbeitung (26.10.2026)

Die folgenden Nutzerentscheidungen ersetzen bei Widersprüchen die bisherigen Vorgaben zu Sprache, Farbkategorien, Reminder-Bedienung und Session-Aktionen. Die Daten bleiben lokal; bestehende Aufgaben und Session-Verknüpfungen werden erhalten.

- **Englische Programmoberfläche:** Alle app-eigenen Menüs, Dialoge, Schaltflächen, Tooltips, Status- und Fehlermeldungen verwenden Englisch. Die Bereiche heißen **Tasks** und **Knowledge**. Inhalte und selbst vergebene Kategorienamen werden nicht übersetzt. Betriebssystemeigene Dialogelemente können der Systemsprache folgen.
- **Direkte Farbauswahl:** Ein Klick auf die schmale Spalte **Color** öffnet eine kompakte **4×4-Palette mit 16 deutlich unterschiedlichen Farben**. Ein weiterer Klick weist die Farbe sofort zu und speichert sie automatisch. Es gibt keine Namenseingabe, Einstellungsseite oder zusätzliche Bestätigung für diese Zuordnung. **No color** entfernt die Zuordnung. Vorhandene Kategorien mit derselben Farbe werden wiederverwendet; sonst entsteht automatisch eine Kategorie mit englischem Farbnamen. Die erweiterte Kategorienverwaltung darf weiterhin verfügbar bleiben.
- **Ganze Aufgabenzeile einfärben:** Die gewählte Farbe ist der tatsächliche Hintergrund der kompletten Aufgabenzeile einschließlich Text, Checkboxbereich, Color-, Reminder-, Status- und Aktionszellen. Keine bloße Farbmarkierung und keine nur schwache Tönung. Text und Icons erhalten eine kontrastreiche Vordergrundfarbe. Die Auswahl wird zusätzlich durch eine Kontur kenntlich gemacht. Unterpunkte übernehmen die Farbkategorie nicht automatisch. Farbnamen sind mindestens per Tooltip, zugänglichem Namen und Filter erkennbar. Die Color-Spalte bleibt kompakt (etwa 56 Pixel).
- **Klarere Hierarchie:** Stärkere Einrückung, sichtbare Verbindungslinien und gemeinsame farbige Leisten kennzeichnen zusammengehörige Eltern-/Kindgruppen. Hauptpunkte sind fett, höher und durch Trennlinien sowie neutrale Hintergrundabstufungen von Unterpunkten und dem nächsten Hauptpunkt unterscheidbar. Notizen und Sessions bleiben optisch untergeordnete Unterzeilen. Die Hierarchiemarkierungen funktionieren unabhängig von einer gewählten Zeilenfarbe und verändern das Aufgabenmodell nicht.
- **Reminder ohne versteckten Aktivierungsschritt:** Im Dialog **Reminder** genügt es, Datum und Uhrzeit zu wählen und **Save** zu klicken. Der Termin wird immer gesetzt, unmittelbar in der Reminder-Zelle angezeigt, automatisch gespeichert und bei Fälligkeit verarbeitet. Kein standardmäßig deaktiviertes Kontrollkästchen. Zum Entfernen eines bestehenden Termins gibt es **Remove reminder**. Speichern setzt den Benachrichtigungszustand zurück. Zeitzonen, einmalige Auslösung, erledigte Aufgaben, verpasste Termine und native Benachrichtigungen folgen weiterhin den bisherigen Regeln.
- **Eine Session-Aktion:** Eine Session-Zeile hat nur **Resume** zum Öffnen/Fortsetzen und ein Details-Icon. Läuft ihr Terminalprozess bereits, fokussiert Resume diesen Tab. Andernfalls startet Resume unmittelbar die gespeicherte native Session in einem neuen Terminalprozess. Es gibt kein zusätzliches Open und keine zusätzliche Resume-Bestätigung. Eine fehlende native Session-ID muss weiterhin angegeben werden. Eine neue Session wird ausschließlich über **New session** am Aufgabenpunkt erzeugt. Bestätigungen beim Beenden laufender Prozesse bleiben bestehen.
- **Kompakte Icons:** Häufige Zeilenaktionen wie Notiz, neue Session und weitere Aktionen sowie sekundäre Werkzeugleisten verwenden eindeutige Icons statt durchgehend beschrifteter Buttons. Jeder reine Icon-Button besitzt einen englischen Tooltip und zugänglichen Namen und bleibt per Tastatur bedienbar. Zentrale Aktionen wie Resume und Add item dürfen ein Label behalten.

Zusätzliche Abnahme: Alle 16 Farben lassen sich direkt anklicken und über alle Spalten als Hintergrund nachweisen; Save eines neuen Reminders ohne weiteren Schalter erzeugt einen sichtbaren, persistierten Termin, der genau einmal ausgelöst wird; Entfernen funktioniert explizit; Session-Zeilen enthalten kein zusätzliches Open; mindestens drei Hierarchieebenen und aufeinanderfolgende Hauptpunkte sind visuell klar zugeordnet; die app-eigene Oberfläche ist englisch.

## 1. Ziel

Eine einfache lokale Desktop-App bündelt schnelle Notizen, Aufgaben, Farbkategorien, zeitliche Reminder und Coding-Agent-Sessions. Sie ersetzt das Springen zwischen OneNote, Textdateien, Outlook-Remindern und separaten Agent-Terminals.

Priorität: verständlicher, wartbarer Python-Code statt umfangreicher Framework-Architektur. Windows und macOS werden ab der ersten Version unterstützt. Keine Cloud, kein Server, keine Synchronisierung.

## 2. Oberfläche

### Hauptansicht

- Eine einzige fortlaufende Liste, wie eine OneNote-Seite; keine Themen-, Seiten- oder Ordnerhierarchie.
- Jeder Stichpunkt hat eine Checkbox, editierbaren Text und optional eine Farbkategorie.
- Verschachtelte Unterpunkte und mehrzeilige Notizen sind möglich.
- Notizen sind ein optionales Textfeld am Stichpunkt; Unterpunkte sind eigenständige Stichpunkte.
- Schnelles Erfassen: Enter erzeugt einen weiteren Punkt; Tab/Shift+Tab rückt ein/aus, außerhalb mehrzeiliger Notizfelder.
- Punkte lassen sich umsortieren, mindestens durch einfache Hoch-/Runter-Aktionen; Drag-and-drop ist kein Muss.
- Freitextsuche über Stichpunkte und Notizen.
- Filter für Kategorie sowie offen/erledigt/alle. Standard: offen.
- Bei gefilterten Treffern bleibt notwendiger Elternkontext sichtbar, damit Unterpunkte verständlich bleiben.

### Layout

- Oben: Suche, Filter, Kategorienlegende und Einstellungen.
- Hauptbereich: Stichpunktliste.
- Unter jedem Stichpunkt: seine Session-Zeilen.
- Unterer oder seitlicher Bereich: integrierte Terminal-Tabs, ein Tab pro gestarteter Session.
- Kontext-Inspektor für den ausgewählten Agenten beziehungsweise die Session.

### Arbeitsbereiche: Aufgaben und Wissen

Zusätzlich zur bisherigen Aufgabenliste gibt es einen **eigenständigen Wissens-/Merkzettelbereich** für Inhalte, die ausdrücklich **keine To-dos** sind (z. B. Gesprächsnotizen, technische Erkenntnisse, Prozessbeschreibungen, hilfreiche Informationen zu einem Thema).

- Die App erhält eine **kompakte Umschaltung „Aufgaben | Wissen“** in der klassischen Office-Oberfläche. „Aufgaben“ bleibt die bestehende Hauptansicht mit der einen fortlaufenden Liste; ihre Regeln und Funktionen bleiben unverändert.
- „Wissen“ ist **keine zweite Aufgabenliste**: keine Checkboxen, kein Offen-/Erledigt-Status und keine automatische Zuordnung zu Aufgaben oder Sessions.
- Der Wissensbereich verwendet einen **vom Nutzer auswählbaren lokalen Ordner** als Speicherort. Die Auswahl ist unabhängig vom Standard-Arbeitsverzeichnis der Coding-Agenten.
- Der ausgewählte Ordner und eine kompakte Dokumentenliste bilden zusammen mit einer Inhaltsansicht den Wissensbereich. Neue Merkzettel werden als echte Dateien im ausgewählten Ordner angelegt, nicht als zusätzliche JSON-Notizen.
- Das Erscheinungsbild bleibt konsequent **OneNote-/Office-artig und nüchtern**: einfache Listenzeilen, Dokumenttitel, dezente Dateityp-Kennzeichnung und ein großzügiger Lese-/Schreibbereich statt Kacheln oder einer komplexen Dokumentenverwaltung.

Die Vorgabe „eine einzige fortlaufende Liste ohne Hierarchie“ gilt weiterhin **vollständig für die Aufgabenansicht**. Die Ordnerwahl im separaten Wissensbereich ist lediglich ein Dateisystem-Speicherort und führt keine Projekt- oder Seitenhierarchie für Aufgaben ein.

### Visuelle Gestaltung und Bedienkonzept

Die Hauptansicht soll bewusst wie eine etablierte **Enterprise-Desktop-Anwendung** wirken: primär ein **OneNote-artiges Arbeitsnotizbuch**, ergänzt um die Übersichtlichkeit und Informationsdichte einer **Excel-artigen Tabelle**. Die zusätzlichen Funktionen erweitern die eine Liste, statt aus ihr ein Aufgaben-Dashboard oder eine separate Agent-Verwaltung zu machen.

- **Grundcharakter:** sachlich, ruhig, funktional und auf tägliche produktive Nutzung ausgelegt. Keine großflächigen Dashboard-Kacheln, schwebenden Karten, überdimensionierten Schaltflächen, dekorativen Verläufe oder unnötigen Effekte im „Vibe-coded“-/SaaS-Dashboard-Stil.
- **Office-Anmutung:** klassische Desktop-Kopfzeile mit einer kompakten, nachvollziehbar gruppierten Werkzeugleiste, gern mit Bereichen wie „Start“, „Einfügen“, „Ansicht“ und „Agenten“. Aktionen wie neuer Punkt, Unterpunkt, Notiz, Ein-/Ausrücken, Hoch/Runter, Reminder und Session-Start sind dort schnell erreichbar. Die Such- und Filterfunktionen bleiben ohne Umwege sichtbar.
- **Eine Liste als Mittelpunkt:** keine zusätzliche Projekt-, Ordner-, Seiten- oder Navigationsleiste. Die Liste ist das dominierende Element; die Agenten-Funktionen sind eine Erweiterung einzelner Stichpunkte und keine konkurrierende Hauptansicht.
- **Kompakte tabellarische Darstellung:** schmale Zeilen, dezente horizontale/vertikale Trennlinien und eine klare Kopfzeile. Geeignete Spalten sind „Stichpunkt / Notizen / Sessions“, „Kategorie“, „Erinnerung“, „Sessions“ und „Aktionen“; eine schmale Nummerierungsspalte ist möglich. Die Textspalte erhält den meisten Platz. Spalten dienen der Übersicht, nicht der Einführung zusätzlicher Datenfelder.
- **OneNote-artiger Listenfluss:** Checkbox und editierbarer Stichpunkttext stehen direkt in der Zeile. Unterpunkte werden eingerückt und bleiben sichtbar als Teil derselben Hierarchie. Mehrzeilige Notizen erscheinen bei Bedarf unmittelbar am zugehörigen Stichpunkt, nicht in einer separaten Detailseite. Ein- und Ausklappen darf die Zuordnung nicht verschleiern.
- **Sessions nah am Kontext:** Verknüpfte Agent-Sessions erscheinen als kompakte, optisch untergeordnete Unterzeilen direkt unter ihrem Stichpunkt. Sichtbar bleiben die in Abschnitt 6 festgelegten Informationen und Aktionen. Die Tabellenform darf keine Session-Funktionalität verstecken oder entfernen.
- **Zurückhaltende Farbgebung:** heller, neutraler Grundaufbau mit Weiß-, Grau- und dezenten Office-Akzentfarben. Farbkategorien werden über kleine farbige Marker **und** ausgeschriebene Kategorienamen gezeigt; kräftige Flächen, große farbige Chips und unnötig viele Statusfarben werden vermieden. Wichtige Zustände müssen auch ohne Farbinterpretation verständlich sein.
- **Klassische Auswahl- und Bearbeitungszustände:** selektierte Zeile mit dezenter Hervorhebung, klare Fokusanzeige und direkt erreichbare Zeilenaktionen. Inline-Bearbeitung und Tastaturbedienung stehen vor Modaldialogen, sofern kein bestehender Sicherheits- oder Bestätigungsschritt erforderlich ist.
- **Sekundärbereiche:** Kontext-Inspektor bevorzugt als schlichte rechte Eigenschaftenleiste, integrierte Terminal-Tabs bevorzugt als unteres, aufteilbares Panel. Beide sind visuell dem Notizbuch untergeordnet und sollten bei Bedarf einklappbar sein; die bereits spezifizierten alternativen Platzierungen bleiben möglich.
- **Informationsdichte:** genügend Inhalt auf einem normalen Desktop-Bildschirm ohne unnötiges Scrollen, bei gleichzeitig lesbarer Schrift und klaren Abständen. Responsives Verhalten bei kleineren Fenstern darf niemals die Listenhierarchie oder die Zuordnung von Sessions zu Stichpunkten zerstören.
- **Konsistente Beschriftung:** nüchterne, eindeutige Begriffe, kleine funktionale Icons und erkennbare Statusangaben. Keine spielerischen Illustrationen, Marketing-Texte oder unnötigen Hervorhebungen in der Arbeitsansicht.

Die visuelle Referenz ist die **überarbeitete Enterprise-Mockup-Richtung**: helle Office-Werkzeugleiste, tabellarische Liste, eingerückte Unterpunkte, dezente Session-Unterzeilen, Kontext-Inspektor rechts und Terminalbereich unten. Das Mockup konkretisiert die Gestaltung; die fachlichen Regeln aus den übrigen Abschnitten haben Vorrang, falls im Prototyp etwas nur simuliert oder unvollständig umgesetzt ist.

## 3. Stichpunkte und Erledigung

Ein Stichpunkt enthält Text, optionale Notizen, Unterpunkte, genau null oder eine Farbkategorie, optional einen Reminder und beliebig viele Session-Verknüpfungen.

- Abgehakte Punkte verschwinden aus der Standardansicht; über Filter sind sie wieder sichtbar.
- Beim Abhaken eines Elternpunkts werden sämtliche Nachfahren automatisch mit erledigt. Undo stellt ihre jeweiligen vorherigen Zustände wieder her.
- Das Abhaken eines letzten Unterpunkts hakt den Elternpunkt nicht automatisch ab.
- Läuft eine verknüpfte Session, erscheint vor dem Abhaken eine Bestätigung: Der Punkt wird ausgeblendet, die Sessions laufen weiter.
- Diese Bestätigung beendet keine Prozesse.
- Bei Reaktivierung eines Unterpunkts werden erledigte Vorfahren wieder geöffnet, um die Hierarchie konsistent zu halten.
- Löschen benötigt eine Bestätigung bei Unterpunkten oder Session-Verknüpfungen. Laufende Sessions werden dadurch nicht beendet.

## 4. Farbkategorien und Legende

- Nutzer kann Kategorien mit Namen und Farbe anlegen, ändern und löschen.
- Pro Stichpunkt maximal eine Kategorie; keine automatische Vererbung an Unterpunkte.
- Beispiel: Rot = wichtig, Grün = PO-Runde.
- Aus den zugewiesenen Kategorien entsteht automatisch eine Legende; keine manuelle Legendenpflege.
- Legende zeigt Name und Farbe, Klick setzt den Kategorienfilter.
- Kategorien bleiben in den Einstellungen verfügbar, auch wenn sie gerade nicht verwendet werden.
- Beim Löschen einer Kategorie bleiben betroffene Punkte erhalten und verlieren nur die Kategorie.
- Farbinformation wird immer auch durch einen Namen ergänzt, nicht ausschließlich visuell vermittelt.

## 5. Reminder

- Pro Stichpunkt optional ein Datum mit Uhrzeit; keine Wiederholungen und keine Texteingabe wie „morgen um neun“ in Version 1.
- Fällige Reminder erzeugen eine native Betriebssystem-Benachrichtigung auf Windows und macOS.
- Klick öffnet nach Möglichkeit die App am Stichpunkt; Einschränkungen der Plattform werden dokumentiert.
- Fenster schließen minimiert die App ins Tray beziehungsweise Menüleisten-Symbol. Reminder und Sessions laufen weiter.
- Explizites Beenden der App stoppt die Reminder-Verarbeitung; kein zusätzlicher Hintergrunddienst.
- Während die App komplett beendet war verpasste Reminder werden beim nächsten Start nur als überfällig markiert, nicht nachträglich benachrichtigt.
- Erledigte Punkte lösen keine Reminder aus.
- Pro gesetztem Zeitpunkt höchstens eine Benachrichtigung; Bearbeiten des Termins setzt den Benachrichtigungszustand zurück.
- Speicherung als Zeitpunkt mit Zeitzoneninformation; Anzeige in der aktuellen lokalen Zeitzone.
- Fehlende Benachrichtigungsberechtigung muss sichtbar sein; die In-App-Markierung funktioniert trotzdem.

## 6. Coding-Agent-Sessions

### Unterstützte Agenten

1. OpenCode
2. Codex
3. Claude Code
4. pi

DeepSeek Harness ist nicht Bestandteil der ersten Version.

Die App installiert Agenten nicht selbst und verwaltet keine Zugangsdaten. Bestehende lokale CLI-Installationen und deren Authentifizierung werden verwendet.

### Start aus einem Stichpunkt

1. Nutzer klickt auf „Session starten“.
2. Auswahl von Agent und Arbeitsverzeichnis.
3. Ein konfigurierter Default-Ordner ist vorausgewählt. Für diesen Start kann ein anderer Ordner gewählt werden.
4. Ausschließlich der Stichpunkttext wird ins Clipboard kopiert: keine Notizen, Unterpunkte oder Elterntexte.
5. Der Agent startet im integrierten Terminal, nicht in einem separaten Terminalfenster.
6. Nutzer fügt den Text selbst ein und sendet ihn ab. Kein automatisches Absenden.
7. Die neue Session wird am Stichpunkt verlinkt.

Fehlender Agent, ungültiger Ordner oder Startfehler werden verständlich angezeigt. Ein Start darf keine scheinbar laufende Session hinterlassen.

### Session-Anzeige direkt am Stichpunkt

Jede Session erhält eine eigene Zeile mit:

- Agentname und optional lesbarer Session-Bezeichnung;
- Status: läuft oder beendet; vor Wiederverbindung gegebenenfalls „nicht verbunden“;
- Kennzeichen für neuen, noch nicht angesehenen Output;
- Aktion zum Öffnen des Terminal-Tabs;
- Aktion zum Fortsetzen einer gespeicherten Session;
- Arbeitsverzeichnis, mindestens über Details erreichbar.

„Läuft“ bedeutet: Der von der App gestartete Agent-Prozess ist aktiv. Es bedeutet nicht, dass der Agent gerade arbeitet. Erkennung von Freigabeaufforderungen oder Eingabewartezuständen ist nicht Teil der ersten Version.

### Ungelesener Output

- Tatsächlicher neuer Terminal-Output in einem nicht sichtbaren Tab markiert die Session als ungelesen.
- Sobald der zugehörige Terminal-Tab bei sichtbarer App angezeigt wird, gilt der Output als gelesen.
- Während der Tab sichtbar ist, eingehender Output bleibt gelesen.
- Ein aktiver Tab in einem ausgeblendeten Tray-Fenster gilt nicht als sichtbar.
- Keine Inhaltsanalyse erforderlich; reine Terminal-Steuersequenzen sollen nach Möglichkeit keine Ungelesen-Markierung auslösen.

### Lebenszyklus

- Ein Terminal-Tab je Session; mehrere Sessions je Stichpunkt erlaubt.
- Das Schließen des Hauptfensters lässt Terminal-Prozesse im Hintergrund laufen.
- Das Schließen eines laufenden Terminal-Tabs verlangt eine Bestätigung zum Beenden; kein stiller Prozessabbruch.
- Explizites Beenden der App warnt bei laufenden Sessions und beendet sie kontrolliert. Kein Versprechen, dass Prozesse nach komplettem App-Ende weiterlaufen.
- Nach App-Neustart bleiben Session-Verknüpfungen erhalten, nicht der Terminal-Output.
- Fortsetzung startet einen neuen lokalen Prozess mit dem agentenspezifischen Resume-Mechanismus. Es ist keine Wiederanbindung an einen alten Terminal-Prozess.
- Kein lokales Terminal-Protokoll und keine nachträgliche Terminal-Wiedergabe. Agenten können unabhängig davon ihre eigenen Verläufe speichern.

## 7. Agent-Adapter

Kleine einheitliche Python-Schnittstelle statt verstreuter Agent-Sonderfälle:

- Installation erkennen und Versionsinformation ermitteln.
- Startkommando als Argumentliste erzeugen.
- Resume-Kommando für eine bekannte native Session-ID erzeugen.
- Native Session-ID nach Möglichkeit zuverlässig ermitteln.
- Instructions, MCP-Konfigurationen und Skills für Arbeitsverzeichnis und Nutzerkontext entdecken.
- Fähigkeiten und nicht verfügbare Funktionen explizit melden.

Pro Agent ist die genaue CLI und Konfigurationsstruktur anhand aktueller offizieller Dokumentation und Tests zu prüfen. Keine angenommenen Dateipfade oder Resume-Flags fest einbauen.

Wichtig: Ein gemeinsam genutztes Terminal liefert nicht automatisch eine native Session-ID. Zuverlässige Zuordnung muss pro Adapter gelöst und getestet werden, auch bei parallelen Starts. „Neueste Session im Ordner“ allein reicht nicht.

Wenn die Zuordnung nicht zuverlässig möglich ist, kennzeichnet die App die Session als nicht automatisch fortsetzbar und ermöglicht eine manuelle native Session-ID. Niemals stillschweigend eine andere Session fortsetzen.

Zusätzlich können frei konfigurierbare Agentenprofile mit ausführbarer Datei und Argumenten angelegt werden. Diese bieten mindestens Terminal-Start und Clipboard; automatische Resume- und Kontext-Erkennung sind nur bei entsprechendem Adapter verfügbar.

## 8. Kontext-Inspektor: Instructions, MCPs und Skills

Nur Anzeige, keine Bearbeitung.

Angezeigt werden:

- Agent und Arbeitsverzeichnis;
- gefundene Instructions-Dateien, etwa AGENTS.md oder agentenspezifische Entsprechungen;
- gefundene MCP-Konfigurationen beziehungsweise konfigurierte Servernamen;
- gefundene Skills;
- Quelle, Dateipfad und Geltungsbereich, soweit feststellbar;
- Erkennungszeit und Möglichkeit zur Aktualisierung.

### Wahrheitsgemäße Zustände

- „Gefunden“: Datei oder Konfiguration entdeckt.
- „Konfiguriert“: Eintrag ist für diesen Agenten konfiguriert.
- „Geladen/aktiv“: nur wenn der Agent diesen Zustand verlässlich meldet.
- „Unbekannt“: tatsächliche Laufzeitnutzung nicht überprüfbar.

Insbesondere bedeutet ein vorhandener Skill nicht, dass er bereits geladen wurde; eine MCP-Konfiguration beweist keine aktive Verbindung. Die erste Version garantiert die transparente Fundstellenanzeige, nicht vollständige Laufzeit-Introspektion jedes Agenten.

Keine Tokens, Passwörter oder vollständigen geheimnishaltigen MCP-Umgebungsvariablen anzeigen oder in den App-Daten speichern.

## 8a. Wissensbereich / Merkzettel und lokale Dokumentenansicht

### Zweck und Abgrenzung

Ein zweiter, bewusst einfacher Bereich dient dem **Nachschlagen und Festhalten von Wissen** ohne Aufgabencharakter. Typische Inhalte sind Informationen über ein Thema, Meeting-Notizen, technische Details, Links oder persönliche Merkhilfen. Die bestehende OneNote-artige Stichpunktliste bleibt allein für Aufgaben und ihre Unterpunkte zuständig; der Wissensbereich ist ein **dateibasierter Dokumentenbrowser mit Notizeditor**.

### Ordnerauswahl und Dokumentenliste

- Nutzer wählt über einen nativen Ordnerdialog einen **lokalen Ordner** aus. Der aktuell ausgewählte Ordner und sein Pfad sind im Wissensbereich sichtbar; er kann jederzeit gewechselt werden.
- Die App merkt sich den zuletzt ausgewählten Ordner lokal und stellt ihn beim nächsten Start wieder her, sofern der Zugriff noch besteht. Ohne gültige Auswahl wird zum Auswählen eines Ordners aufgefordert, ohne eine leere oder falsche Dokumentenliste vorzutäuschen.
- Die Liste zeigt die **unterstützten Dokumentdateien aus dem ausgewählten Ordner**. Für Version 1 werden zunächst Dateien direkt in diesem Ordner erfasst; eine rekursive Suche in Unterordnern ist dafür nicht erforderlich.
- **Mindestens unterstützte Dateitypen:** `.txt`, `.md`, `.markdown`, `.docx` (Word) und `.pdf`. Weitere Formate können per separatem Anzeige-/Leseadapter ergänzt werden, ohne die Grundansicht zu verändern. Für ältere `.doc`-Dateien ist eine verlässliche plattformübergreifende Vorschau gesondert zu validieren; ohne Unterstützung wird ein erkennbarer Hinweis sowie „Extern öffnen“ angeboten, statt Inhalt zu erfinden.
- Der **Dateiname ohne Erweiterung ist der angezeigte Titel**. Die Erweiterung bzw. ein Dateitypsymbol bleibt zusätzlich sichtbar, damit gleichnamige Dateien unterschiedlicher Formate unterscheidbar sind. Es wird kein verstecktes Metadatenfeld für Dokumenttitel geführt.
- Die kompakte Liste lässt sich mindestens nach Dateiname durchsuchen und alphabetisch sortieren. Eine Aktualisieren-Aktion übernimmt zwischenzeitlich extern angelegte, gelöschte oder geänderte Dateien.
- Wählt der Nutzer eine Datei, wird **deren Inhalt innerhalb der App** im angrenzenden Dokumentbereich angezeigt. Der Benutzer muss zum normalen Lesen unterstützter Dokumente nicht erst Word, einen PDF-Reader oder einen externen Editor öffnen.

### Lesen und Vorschau

- **TXT:** reiner Text, mit Zeilenumbrüchen; bestehende `.txt`-Dateien können im Editor bearbeitet werden.
- **Markdown (`.md`, `.markdown`):** gut lesbare Markdown-Darstellung innerhalb der App; Quelltextansicht kann optional ergänzt werden. Keine automatische Umwandlung in TXT.
- **Word (`.docx`):** integrierte, schreibgeschützte Inhaltsansicht für Text und nach Möglichkeit Tabellen. Eine pixelgenaue Office-Darstellung und das Bearbeiten von Word-Dokumenten sind nicht vorausgesetzt. Nicht darstellbare Elemente werden bei Bedarf transparent kenntlich gemacht.
- **PDF:** integrierte, schreibgeschützte Dokumentenansicht mit Seitenanzeige und Scrollen; bei bildbasierten PDFs wird der vorhandene Seiteninhalt visuell angezeigt, ohne eine Texterkennung zu versprechen.
- Sonstige nicht zuverlässig unterstützte Formate erhalten einen klaren Hinweis und optional eine Aktion **„Extern öffnen“**. Sie dürfen nicht stillschweigend wie leere Dateien erscheinen.
- Lesefehler, Passwortschutz, Zugriffsprobleme oder sehr große Dateien führen zu verständlichen Meldungen; die Oberfläche bleibt bedienbar. Das Anzeigen eines Dokuments verändert weder dessen Inhalt noch Dateiformat.

### Neuen Merkzettel erstellen

1. Im Wissensbereich klickt der Nutzer auf **„Neue Notiz“**.
2. Er gibt einen **Titel** an, der als Dateiname verwendet wird, und schreibt normalen, mehrzeiligen Text in einen einfachen Editor.
3. Die App erstellt im ausgewählten Ordner eine **echte UTF-8-Textdatei `<Titel>.txt`** (keine Datenbank und keine verdeckte JSON-Repräsentation). Der Nutzer sieht den neuen Eintrag unmittelbar in der Dokumentenliste.
4. Die Inhalte können anschließend im selben Editor weiterbearbeitet und gespeichert werden. Für TXT-Eingaben ist eine einfache, unkomplizierte Bearbeitung ohne Rich-Text- oder Markdown-Zwang vorgesehen.
5. Der Speichervorgang darf bestehende Dateien **nie unbemerkt überschreiben**. Ungültige Dateinamen (insbesondere betriebssystemabhängig reservierte Zeichen oder Namen), leere Titel und Namenskonflikte werden abgefangen und mit einer konkreten Korrekturmöglichkeit angezeigt.

- TXT-Änderungen werden zuverlässig gespeichert, vorzugsweise automatisch nach kurzer Eingabepause und zusätzlich beim Verlassen des Dokuments; Schreibfehler müssen sichtbar sein. Vor einem Wechsel bei ungespeicherten Änderungen darf der Text nicht verloren gehen.
- Externe Änderungen an einer gerade geöffneten TXT-Datei dürfen nicht stillschweigend überschrieben werden; bei Konflikten wird der Nutzer darauf hingewiesen.
- In Version 1 werden **keine neuen DOCX-, PDF- oder Markdown-Dateien** aus dem Merkzettel-Editor erzeugt. Neu erstellte Merkzettel sind immer `.txt`.

### Ablage, Sicherheit und Verhalten

- **Der ausgewählte Ordner ist die maßgebliche Datenquelle.** Vorhandene und neue Dokumente bleiben normale Dateien, die auch außerhalb der App mit anderen Programmen genutzt werden können. Die App kopiert sie nicht ungefragt in ihr eigenes Datenverzeichnis.
- In der app-eigenen JSON-Datei wird nur die Ordnerauswahl und gegebenenfalls die zuletzt ausgewählte Datei gespeichert, **nicht der Inhalt der Dokumente**. Das bisherige Aufgaben-/Session-Datenmodell bleibt unverändert.
- Der Ordner darf sich auf einem lokal erreichbaren Laufwerk befinden. Ist der Ordner umbenannt, gelöscht oder nicht verfügbar, zeigt die App dies an und erlaubt eine neue Auswahl. Es dürfen keine Dateien ohne explizite Nutzeraktion gelöscht werden.
- Die Funktion bleibt **rein lokal und offline**; es findet kein Upload von Dateien, kein Cloud-Import und keine stille Konvertierung statt.
- Die Dokumentenansicht darf keine aktiven Inhalte aus Word-, Markdown- oder PDF-Dateien unkontrolliert ausführen. Externe Links werden nur nach bewusster Nutzeraktion geöffnet.

### Layout und Bedienung

- Der Wechsel erfolgt über einen dezenten, dauerhaft auffindbaren Register-/Navigationspunkt „Aufgaben“ und „Wissen“, **nicht** über ein zweites komplexes Dashboard.
- Der Wissensbereich besitzt eine einfache Office-artige Werkzeugleiste mit **Ordner auswählen**, **Neue Notiz**, **Aktualisieren** und **Suche**.
- Darunter vorzugsweise **links eine schmale Liste der Dateititel, rechts ein großer Lese-/Schreibbereich**. Bei geringer Fensterbreite darf die Liste einklappbar sein.
- Ein Dokument wird durch Klick auf seinen Titel geöffnet; der aktuelle Titel und Dateityp sind im Inhaltsbereich erkennbar. Die TXT-Bearbeitung erfordert keinen zusätzlichen externen Editor.
- Der bisherige Aufgaben-Terminalbereich und der Agent-Kontext-Inspektor gehören weiterhin zur Aufgaben-/Session-Arbeit; im Wissensbereich dürfen sie verborgen bleiben, damit der Dokumentinhalt Platz erhält.

## 9. Technik

### Vorgeschlagener Stack

- Python für Anwendungslogik.
- PySide6 für Desktop-Oberfläche, Tray und Ereignisverarbeitung.
- Kleine eingebettete Terminal-Webansicht mit xterm.js über Qt WebEngine.
- Windows: ConPTY-Anbindung, beispielsweise über eine nach Validierung geeignete Python-Bibliothek.
- macOS: PTY-Anbindung über Python/Unix-APIs.
- Plattformadapter für native Benachrichtigungen, falls Qt-Tray-Benachrichtigungen die Anforderungen nicht zuverlässig erfüllen.
- JSON für lokale persistente Daten.

Eine Terminalemulation ist notwendig: ein normales Textfeld reicht für interaktive Coding-Agent-TUIs nicht. Python bleibt Hauptsprache; JavaScript beschränkt sich auf die Terminalansicht und deren Brücke.

### Kleine Modulstruktur

```text
app/
  main.py
  models.py
  storage.py
  reminders.py
  ui/
  terminal/
    bridge.py
    windows.py
    macos.py
    web/
  agents/
    base.py
    opencode.py
    codex.py
    claude_code.py
    pi.py
  notifications/
 tests/
```

Keine Plugin-Plattform, kein Backend, keine Microservices und kein ORM. Kleine Module und einfache Datenklassen statt unnötiger Abstraktionsschichten.


### Ergänzung: lokale Dokumentenansicht

- Ein kleines Modul für Ordnerwahl, Auflistung, Dateityp-Erkennung, Dateiaktualisierung, Vorschau und TXT-Schreiben ergänzt den bestehenden Python-/PySide6-Stack. Keine zusätzliche Datenbank, kein Server und kein externer Dokumentendienst.
- TXT-Dateien werden als einfache Textdateien (neue Dateien: UTF-8) geöffnet und mit einem nativen mehrzeiligen Editor bearbeitet.
- Markdown-Inhalte werden in einer sicheren, lokalen Vorschau dargestellt. Für `.docx` und `.pdf` sind geeignete lokal mitlieferbare Reader-/Renderer-Komponenten plattformübergreifend zu validieren.
- Die verlässliche Anzeige von Word-/PDF-Inhalten, Berechtigungen sowie das Verhindern unbeabsichtigter Dateiveränderungen sind zusätzliche technische Prüfpunkte für Windows und macOS.

## 10. JSON-Datenmodell

Eine versionierte Hauptdatei speichert langlebige Daten. Terminal-Prozesse, Terminal-Puffer und Ungelesen-Zustände bleiben im Arbeitsspeicher.

```json
{
  "schema_version": 1,
  "settings": {
    "default_workdir": "",
    "default_agent": "opencode"
  },
  "categories": [
    {"id": "cat-1", "name": "PO-Runde", "color": "#28A745"}
  ],
  "items": [
    {
      "id": "item-1",
      "parent_id": null,
      "position": 0,
      "text": "Offene API-Frage prüfen",
      "notes": "Zusätzliche Notizen",
      "done": false,
      "category_id": "cat-1",
      "reminder": {
        "at": "2026-10-01T09:00:00+02:00",
        "notified_at": null
      },
      "created_at": "2026-10-01T07:00:00Z",
      "updated_at": "2026-10-01T07:00:00Z"
    }
  ],
  "sessions": [
    {
      "id": "link-1",
      "item_id": "item-1",
      "agent": "opencode",
      "native_session_id": null,
      "workdir": "",
      "title": "API-Frage",
      "created_at": "2026-10-01T07:01:00Z"
    }
  ]
}
```

- IDs werden als UUIDs erzeugt; Kurz-IDs oben dienen nur der Lesbarkeit.
- `position` gilt innerhalb derselben Eltern-ID.
- `reminder` und `category_id` dürfen null sein.
- Die Beispieldaten sind kein Reminder-Auftrag.
- Datenablage im betriebssystemüblichen App-Datenverzeichnis; Pfad in den Einstellungen sichtbar.
- Änderungen automatisch nach kurzer Entprellung speichern und beim regulären Beenden flushen.
- Atomisches Schreiben über temporäre Datei und Ersetzen, letzte gültige Sicherung behalten.
- Beschädigte oder unbekannte Datenversionen niemals still überschreiben.
- Nur eine App-Instanz je Datenverzeichnis, damit parallele Schreibzugriffe keine Daten verlieren.
- Keine eingebauten Zugangsdaten und kein Terminal-Output in der JSON-Datei.


**Ergänzung für den Wissensbereich:** Die Hauptdatei kann unter `settings` zusätzlich z. B. `"knowledge_folder": "/gewählter/ordner"` und optional `"knowledge_last_file": "notiz.txt"` enthalten. Dies sind lediglich Pfad-/Auswahl-Einstellungen; Inhalte, Formatierung und Dateinamen stammen aus den tatsächlichen Dateien im gewählten Verzeichnis. Die bestehende `items`-/`sessions`-Struktur wird nicht verändert.

## 11. Technische Validierung vor vollständigem Ausbau

Der Terminal-Prototyp ist das erste technische Gate, auf echten Windows- und macOS-Systemen:

1. Jeden der vier Agenten starten.
2. Vollbild-/interaktive TUI, ANSI, Farben und Unicode korrekt darstellen.
3. Eingabe, Einfügen, Ctrl+C und Terminal-Größenänderung testen.
4. Mehrere parallele Terminal-Tabs betreiben.
5. Prozesse und Unterprozesse beim Beenden kontrolliert schließen.
6. Native Session-ID zuverlässig bestimmen und korrekte Session fortsetzen.
7. Native Benachrichtigungen aus der paketierten App testen.

Falls eine Fähigkeit agenten- oder plattformspezifisch nicht zuverlässig erreichbar ist, wird sie sichtbar als eingeschränkt markiert, nicht simuliert. Vor allem Resume und „tatsächlich geladen“ sind technische Risiken, keine bereits garantierten Integrationen.


**Zusätzlicher Validierungsumfang Wissensbereich:** Auf Windows und macOS einen lokalen Ordner auswählen, `.txt`, `.md`, `.docx` und `.pdf` zuverlässig darstellen, TXT-Neuanlage/Bearbeitung/Speicherung testen, Unicode-Dateinamen prüfen sowie fehlende Zugriffsrechte, beschädigte oder extern veränderte Dateien und Dateinamenskollisionen abdecken.

## 12. Umsetzung in Etappen

1. **Terminal-Spike:** Windows/macOS, vier Agenten, Start/Resume und Benachrichtigungen validieren.
2. **Notizbuch:** Liste, Unterpunkte, Notizen, Checkbox-Regeln, Kategorien, Suche/Filter, JSON-Speicherung.
3. **Agent-Verknüpfung:** Startdialog, Default-Ordner, Clipboard, Session-Zeilen, Terminal-Tabs, Status und ungelesener Output.
4. **Reminder und Tray:** Datums-/Zeitwahl, native Benachrichtigungen, Überfällig-Markierung, Hintergrundbetrieb.
5. **Kontext-Inspektor:** adapterbasierte Fundstellenanzeige für alle vier Agenten.
6. **Auslieferung:** installierbare Builds und Smoke-Tests auf Windows und macOS; gegebenenfalls erforderliche Plattform-Signierung dokumentieren.

Alle Etappen gehören zum Zielumfang der ersten Version; die Reihenfolge minimiert technische Risiken.


**Ergänzender Implementierungsbaustein:** Der neue Wissensbereich wird als eigener, kleiner UI- und Dateifunktionsbaustein umgesetzt: zunächst Ordnerwahl, Liste und TXT-Neuanlage/-Bearbeitung; anschließend Vorschau für Markdown, DOCX und PDF; danach Tests der Dateizugriffe und plattformübergreifenden Darstellung. Er gehört ebenso zum Zielumfang der ersten Version und muss **vor der in Schritt 6 genannten Auslieferung** abgeschlossen sein. Die ursprünglichen sechs Etappen bleiben inhaltlich bestehen.

## 13. Nicht Teil der ersten Version

- Cloud, Synchronisierung, Konten und Zusammenarbeit.
- Automatisches Absenden von Agent-Prompts.
- Agent-Ergebnisse automatisch in Aufgaben zurückschreiben.
- Verlässliche Erkennung „Agent wartet auf Freigabe“.
- Persistente Terminal-Protokolle.
- Wiederkehrende Reminder oder natürlichsprachige Termine.
- Bearbeiten von Instructions, MCPs und Skills.
- DeepSeek Harness.
- Allgemeine OneNote-/Outlook-Integration.


Für den ergänzten Wissensbereich ebenfalls nicht vorgesehen: cloudbasierte Dokumentenspeicherung, vollwertige Word-/PDF-Bearbeitung, automatische Umwandlung eingelesener Dateien in TXT, Volltext-OCR sowie eine zusätzliche Aufgaben-/Projektstruktur aus Dateiordnern. Dies beschränkt nicht die oben zugesagte Lesevorschau und die Neuanlage von TXT-Merkzetteln.

## 14. Abnahmekriterien

- Auf Windows und macOS können Punkte inklusive Unterpunkten und Notizen angelegt und nach Neustart verlustfrei geladen werden.
- Pro Punkt höchstens eine frei definierbare Farbkategorie; Legende und Filter aktualisieren sich automatisch.
- Erledigte Punkte werden standardmäßig ausgeblendet. Elternpunkte erledigen offene Nachfahren mit; Undo stellt den vorherigen gemischten Zustand wieder her.
- Agenten starten ausschließlich im integrierten Terminal mit korrektem Arbeitsverzeichnis; Clipboard enthält nur den Stichpunkttext.
- Mehrere Session-Zeilen pro Punkt und unabhängige Terminal-Tabs funktionieren.
- Laufstatus bildet Prozesszustand ab. Neuer Output wird nur für nicht sichtbare Terminals als ungelesen markiert.
- Beim Abhaken mit laufenden Sessions wird nachgefragt; bestätigte Sessions laufen weiter.
- Fenster schließen lässt Reminder und Sessions im Tray weiterlaufen.
- Nach komplettem Neustart sind Verknüpfungen erhalten; Fortsetzen verwendet die richtige native Session, sofern unterstützt und identifiziert.
- Kein Terminal-Verlauf wird durch die App dauerhaft gespeichert.
- Fällige Reminder benachrichtigen auf beiden Plattformen; bei beendeter App verpasste Termine werden nur überfällig markiert.
- Kontextanzeige nennt Quellen und unterscheidet gefunden/konfiguriert von nachweislich geladen.
- Fehlende Agenten, Berechtigungen und defekte Datendateien führen zu verständlichen Fehlermeldungen statt Datenverlust.
- Die Hauptansicht wirkt wie ein kompaktes Office-/OneNote-Arbeitsnotizbuch mit tabellarischen Strukturhilfen, nicht wie ein kartenbasiertes Dashboard. Die eine fortlaufende Liste bleibt bei normalen Desktop-Fenstergrößen visuell dominant.
- Stichpunkte, Unterpunkte, optionale Notizfelder und verknüpfte Session-Unterzeilen sind eindeutig zugeordnet und ohne Wechsel auf andere Seiten nutzbar.
- Kategorien, Reminder und Session-Aktionen sind übersichtlich in der Liste auffindbar; Farben werden sparsam und stets zusammen mit lesbaren Bezeichnungen eingesetzt.
- Der Kontext-Inspektor und der integrierte Terminalbereich fügen sich als untergeordnete Desktop-Panels ein und schränken die Lesbarkeit der eigentlichen Liste nicht unnötig ein.

### Zusätzliche Abnahmekriterien für den Wissensbereich

- Die bestehende Aufgaben-Hauptansicht mit einer fortlaufenden Liste und allen Agent-/Reminder-Funktionen ist unverändert nutzbar. Ein separater, klar erkennbarer „Wissen“-Bereich ist erreichbar, ohne die Aufgabenliste in Ordner oder Seiten zu unterteilen.
- Ein frei auswählbarer lokaler Ordner wird inklusive Pfad angezeigt und beim nächsten Programmstart erneut geöffnet, soweit vorhanden und berechtigt.
- Vorhandene `.txt`, `.md`/`.markdown`, `.docx` und `.pdf` aus dem gewählten Ordner erscheinen unter ihrem Dateinamen (Titel) mit erkennbarem Format in einer kompakten Liste; externe Änderungen können aktualisiert werden.
- Ein Klick auf einen unterstützten Eintrag zeigt dessen Inhalt **innerhalb der App** an: TXT als Text, Markdown lesbar, DOCX als Dokumentinhalt und PDF als Dokumentseiten. Einschränkungen werden ehrlich angezeigt.
- Über „Neue Notiz“ kann man einen Titel und mehrzeiligen Text eingeben. Das Ergebnis wird als `<Titel>.txt` tatsächlich im ausgewählten Ordner gespeichert und ist dort auch außerhalb der App verwendbar.
- Neue und vorhandene TXT-Dateien können bearbeitet und erneut gespeichert werden, ohne dass vorhandene Dateien stillschweigend überschrieben oder externe Änderungen unbemerkt verworfen werden.
- Ungültige Dateinamen, nicht verfügbare Ordner, Lesefehler, unbekannte Formate und Schreibfehler führen zu verständlichen Meldungen statt Datenverlust.
- Der Wissensbereich entspricht der sachlichen Enterprise-/OneNote-Optik: kompakte Titelliste, großer Inhaltsbereich, einfache Werkzeugleiste und keine dominierenden Karten oder Dashboards.


### Ergänzung: verständlicher Agent-Kontext (26.10.2026)

Der rechte Bereich ist unabhängig von Sessions benutzbar. Ein Agent-Auswahlfeld zeigt installierte, ausführbare Coding-CLIs; der Arbeitsordner kann separat gewählt werden. Bei Auswahl einer Session werden deren Agent und Ordner übernommen. Drei Tabs zeigen Skills, MCPs und Instructions mit Anzahl, Herkunft, Status und lesbarer Dateivorschau. Globale, gemeinsame und geerbte Instructions müssen nachvollziehbar sein; verdrängte Codex-AGENTS.md-Dateien werden als „Overridden“ gekennzeichnet.

Die UI bleibt Englisch. Verfügbare bzw. registrierte Skills sind klar von tatsächlich in eine Unterhaltung geladenen Skill-Inhalten zu unterscheiden. Konfigurierte MCPs sind keine bestätigten Verbindungen. Codex liefert seine Skill-Registry über den App-Server, OpenCode v2 registrierte Skills und MCP-Status über lesende API-Aufrufe. Ohne Laufzeitnachweis wird kein „Loaded“ behauptet. Keine Modell-Turns, MCP-Starts oder Änderungen an Agent-Konfigurationen zur Inspektion. MCP-Credentials, URLs, Umgebungswerte und Befehlsargumente werden nicht angezeigt. Laufende Sessions können einen älteren Instruction-Stand haben; zusätzliche CLI-Optionen, Imports und Plugin-Regeln können den Kontext erweitern.

### Ergänzung: kompakte Zeilen

Hauptpunkte nutzen 28 px statt 40 px, Unterpunkte 26 px statt 34 px. Aktionsicons, Checkboxen, Hinzufügen-Zeile und Tabellenkopf werden entsprechend kompakter. Mehrzeilige Agent-Statusanzeigen und Notizen behalten den benötigten Platz.


### Ergänzung: eigener Agent-Tab

Skills, MCPs und Instructions werden im eigenen oberen Tab „Agent context“ neben „Tasks“ und „Knowledge“ angezeigt. In Tasks gibt es keinen rechten Kontextbereich mehr; die Aufgaben nutzen die gesamte Breite.
