# Chaosfolk companion

The lime-green imp is the shared identity of the test cast. A strong silhouette,
asymmetric ears and a lightning tuft stay consistent across skins. Expressions
and one accessory distinguish behavioral profiles; they do not represent a real
person or imply a diagnosis.

The project-root `logo.png` is used in the README and copied into each report.
The bundled `templates/mascot.png` is the fallback mark. `templates/companions.png` is
a four-column, four-row transparent sprite atlas. The report reads `skin` from
the persona, chooses that cell and uses the same avatar in the cast and timeline.
Older personas without a skin use the newcomer face. A text name and behavior
label always accompany the image.

| Skin | Profile | Visual cue |
| --- | --- | --- |
| 0 | First-time visitor | Wide eyes, backpack straps |
| 1 | In a hurry | Orange headband |
| 2 | Keyboard-focused | Rectangular glasses, headphones |
| 3 | Mobile user | Cap and phone |
| 4 | Careful reader | Round glasses and book |
| 5 | Unfamiliar with jargon | Puzzled expression |
| 6 | Distracted | Purple beanie, sideways glance |
| 7 | Detail checker | Magnifying glass |
| 8 | Cautious | High collar, hesitant smile |
| 9 | Explorer | Outdoor hat |
| 10 | Multitasker | Colored hair clips |
| 11 | Text-focused | Scarf and attentive expression |
| 12 | Copy-paster | Clipboard |
| 13 | Backtracker | Turned pose and return arrow |
| 14 | Search-first | Binoculars |
| 15 | Recovery seeker | Tool pouch |

The companion artwork was generated for this project with the built-in image
generation tool. [The prompts](image-prompts.md) document its creation. The
project includes the files under its MIT license.

Use the dark forest background `#101612`, lime `#dcf78b` and restrained orange
accents. Keep evidence readable: severity must have text, not just color. Do not
use a cheerful avatar or a high score to imply that a failure has been verified.

The supplied `logo.png` combines the `chaosfolk.` wordmark and companions. The
report falls back to a lowercase white wordmark and mascot when no logo is present.
