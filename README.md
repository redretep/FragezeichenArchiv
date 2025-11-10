# FragezeichenArchiv

Ein moderner Web-Audioplayer, der automatisch die drei Fragezeichen Folgen von [archive.org](https://archive.org) lädt und in einer GitHub Seite darstellt.

---

## Funktionen

* **Automatische Playlist:** Alle MP3-Dateien aus einer angegebenen Collection werden geladen.
* **Eigenes Cover-System:** Es werden lokale Coverbilder verwendet (`001.png`, `002.png`, ...).
* **Suchfunktion:** Durchsucht Titel.
* **Sleep-Timer:** Stellt einen Timer ein, um die Wiedergabe automatisch zu stoppen, gut zum Einschlafen).
* **Wiedergabegeschwindigkeit:** Passt die Geschwindigkeit an (0.5x bis 2x).

---

## Benutzung

1. öffne [das FragezeichenArchiv](https://redretep.github.io/FragezeichenArchiv) im Browser
2. Such nach deiner Folge
3. Stelle einen Sleeptimer ein (optional)
4. Fertig!

oder

1. Lade die HTML-Datei und die Coverbilder (`001.png`, `002.png`, `003.png`, ...) in denselben Ordner.
2. Öffne die Datei im Browser.
3. Suche und spiele Tracks ab.

---

## Anpassung

In der Variable `collection` im Skript kannst du den Namen der Archive.org-Collection anpassen, z.B.:

```js
const collection = 'mein-audio-archiv';
```

## Aufbau der Cover

* `001.png` = Folge 1
* `002.png` = Folge 2
* usw.
* Notiz: funktioniert zum bestehenden Zeitpunkt noch nicht, siehe ToDo

## Technologien

* **HTML / CSS / JavaScript** (kein Framework notwendig)
* **Fetch API** für Daten von archive.org

## To-Do

* Cover-Arts über API finden
* "DiE DR3i"-Folgen hinzufügen
* Header Farbe fixen

## Lizenz

Dieses Projekt ist **frei verwendbar** für nicht-kommerzielle Zwecke. Anpassungen sind erlaubt.
