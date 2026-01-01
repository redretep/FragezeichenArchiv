# FragezeichenArchiv

Ein moderner Web-Audioplayer, der automatisch die drei Fragezeichen Folgen von [archive.org](https://archive.org) lädt und in einer GitHub Seite darstellt. Die Metadaten der Folgen werden von [dreimetadaten](https://dreimetadaten.de) genommen.

---

## Funktionen

* **Automatische Sortierung:** Alle MP3-Dateien aus einer angegebenen Collection werden in der korrekten Reihenfolge geladen.
* **Cover-System:** Es werden Coverbilder von [dreimetadaten](https://dreimetadaten.de) verwendet.
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

1. Lade die HTML-Datei und die Metadaten in denselben Ordner.
2. Öffne die Datei im Browser.
3. Suche und spiele Tracks ab.

---

## Anpassung

In der Variable `collection` im Skript kannst du den Namen der Archive.org-Collection anpassen, z.B.:

```js
const collection = 'mein-audio-archiv';
```

## Technologien

* **HTML / CSS / JavaScript** (kein Framework notwendig)
* **Fetch API** für Daten von archive.org

## To-Do

* "DiE DR3i"-Folgen im Archiv hinzufügen

## Lizenz

Dieses Projekt ist **frei verwendbar** für nicht-kommerzielle Zwecke. Anpassungen sind erlaubt.
