# apex-md-converter

Convierte el PDF de Fiserv **XP2 APEX Suite, Message Reference** (release 2023.1.10: 3,404 páginas) en **un solo
Markdown** pensado para que una IA lo busque con grep y un humano lo lea. Sin perder datos, y verificado contra
extracciones independientes del PDF.

> ⚠️ **Confidencialidad.** El PDF es *FISERV CONFIDENTIAL | Intended Only for XP2 Clients*. Este repo tiene **solo el
> código y la documentación**: nunca el PDF, el Markdown generado, las transcripciones de imágenes ni los reportes que
> contienen texto del PDF. El `.gitignore` los excluye (`*.pdf`, `work/`, `out/`, `ref/`, `ocr/`). No subas esos
> archivos a ningún servicio externo.

## Qué produce

`<work>/out/final.md`:

- **Todas las páginas, en orden.** Cada página empieza con `<!-- page N | printed P -->` y `<a id="page-P">`.
- **Encabezado para la IA:** cómo buscar, tabla de contenidos, índices de mensajes, Types, códigos de error y FAQ.
- **Anclas** `id="msg-<Mensaje>"` e `id="type-<Type>"`. Las referencias `"X" on page N` se convierten en links a la
  sección.
- **Tablas Element | Type | Max | Description:** `↳` marca el nivel de anidación y la negrita, un elemento obligatorio.
- **Bloques XML** unidos cuando el PDF los partía en el salto de página, y re-indentados al estilo de Prettier
  (4 espacios por nivel).
- **Imágenes con contenido** (diagramas, tablas que son imagen) transcritas en el lugar donde aparecen.

## Requisitos

- Python 3.12+ (el `run.sh` crea `venv/` e instala `requirements.txt`, que es PyMuPDF).
- poppler (`brew install poppler`): genera las referencias independientes `pdftotext` y `pdftohtml`.
- Opcional: tesseract, para el cruce de las transcripciones de imágenes.

## Uso

```bash
APEX_PDF="/ruta/APEX_Message_Reference_2023_1_10.pdf" APEX_WORK="/ruta/work-2023.1.10" ./run.sh
```

`APEX_WORK` es la carpeta de trabajo de una release. Queda fuera del repo y adentro tiene:

| Carpeta | Qué |
|---|---|
| `ocr/p<página>_<n>.md` | Transcripción de cada imagen con contenido (entrada; ver RUNBOOK paso 3) |
| `ocr/readerA/`, `ocr/readerB/` | Las dos lecturas independientes de cada imagen, en TSV |
| `header_verification.md` | Párrafo de verificación que va en el encabezado del `.md` (se escribe al terminar las auditorías) |
| `out/` | Generado: `final.md`, `final_paged.md`, `meta.json`, `images/` y los reportes de cada check |
| `ref/` | Generado: `body.txt` (`pdftotext`) y `pdf.xml` (`pdftohtml`) |

Al final, `gate.py` imprime un veredicto por capa y sale con código 1 si falla alguna verificación dura.

## Cómo funciona

| Archivo | Paso |
|---|---|
| `hidden.py` | Encuentra texto tapado por un relleno opaco (invisible en el PDF) para descartarlo |
| `convert.py` | Página por página, por geometría: celdas de tabla según los rectángulos dibujados, nivel según la x, código en Courier, re-unión de líneas cortadas en el margen (cada unión queda en `out/joins.tsv`), títulos según la fuente y el outline |
| `images.py` | Lista las imágenes con contenido, las recorta a PNG y reusa transcripciones de una release anterior si la imagen es idéntica (`--reuse`) |
| `assemble.py` | Anclas, links de las referencias cruzadas, encabezado e índices |
| `codeblocks.py` | Une los bloques XML partidos por el salto de página y los re-indenta. Solo cambia espacios |
| `common.py` | Rutas y datos de la release. Los rangos de capítulos salen del outline del PDF y la release, de la página 2 |

## Verificación (`checks/`)

| Capa | Script | Qué compara | Tipo |
|---|---|---|---|
| A | `verify.py` | Cada página contra `pdftotext -raw`: palabras, puntuación y orden | Dura: 0 diferencias |
| B | `check_structure.py` | Marcadores en orden, anclas únicas, links, columnas de tablas, bloques de código, TOC | Dura |
| G | `check_codeblocks.py` | `final.md` contra `final_paged.md`: misma secuencia de tokens, marcadores y anclas | Dura |
| OCR | `compare_readers.py` | Las dos transcripciones de cada imagen, fila por fila | Dura (antes de crear `ocr/*.md`) |
| E | `check_rows.py` | Cada fila de tablas Element: nombre, nivel y negrita contra `pdftohtml` | Triage |
| F | `check_cells.py`, `check_errors.py` | Type, Max y Description de cada fila; cada código de error con su mensaje | Triage |
| C, D | `docs/audit-*-prompt.md` | Auditoría visual con sub-agentes: página contra imagen, y elemento del PDF buscado en el `.md` | Manual |

"Triage" significa que el script lista candidatos y que la mayoría son artefactos del propio chequeo (por ejemplo,
nombres partidos en dos renglones). Cada candidato se revisa contra la imagen de la página; el procedimiento está en
`RUNBOOK.md`.

Resultado de la release 2023.1.10: A 0 diferencias en 3,404 páginas · B limpio · E 17,893 de 17,988 filas idénticas y
1 defecto real, corregido · F 51,147 celdas sin defectos · 888 de 888 códigos de error · G 653,544 tokens idénticos ·
C 755 páginas auditadas · D 10,139 elementos.

## Una release nueva

Ver **[RUNBOOK.md](RUNBOOK.md)**.

## Limitaciones conocidas

- Una fila de tabla que cruza de página queda como dos filas, una por página.
- La itálica no se reproduce.
- Las erratas del PDF se conservan.
- Un bloque XML que cruza páginas pertenece a la página donde empieza.
- `convert.py` depende del diseño de esta publicación: fuentes Arial y CourierNew, colores de celda, márgenes. Si
  Fiserv cambia la plantilla, hay que ajustar las constantes del principio de `convert.py` (ver RUNBOOK, paso 6).
