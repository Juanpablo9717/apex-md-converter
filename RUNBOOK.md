# RUNBOOK: convertir una release nueva del APEX Message Reference

Ejemplo: llega `APEX_Message_Reference_2024_1_0.pdf`. La release anterior verificada es la 2023.1.10; su carpeta de
trabajo (`ocr/`, `out/`, `audit/`) se guarda fuera de este repo, junto al Markdown publicado.

## 1. Preparar

```bash
export APEX_PDF="/ruta/APEX_Message_Reference_2024_1_0.pdf"
export APEX_WORK="/ruta/work-2024.1.0"          # carpeta nueva, fuera de este repo
export APEX_REUSE="/ruta/work-2023.1.10"            # carpeta de trabajo de la release anterior
```

Antes de correr nada, comprueba dos cosas del PDF nuevo:

- **Outline (marcadores):** `common.py` busca entradas de nivel 1 que empiecen con `Chapter 3`, `Chapter 4`,
  `Appendix B` y `Appendix C`. Si Fiserv renombra o reordena capítulos, el script se detiene y dice cuál falta.
- **Página 2:** tiene que contener la línea `XP2 APEX Suite, Message Reference, Release <X>, <fecha>, <número>-C`, que
  da la release, la fecha y el número de documento del encabezado.

## 2. Primera corrida

```bash
./run.sh
```

Si hay imágenes con contenido sin transcribir, se detiene en `== images` y las lista. `APEX_REUSE` copia
automáticamente las transcripciones cuya imagen es idéntica byte a byte a la de la release anterior (FAQ A52/A53, el
diagrama de la p. 743…), aunque cambie el número de página.

## 3. Transcribir las imágenes que falten

Cada imagen pendiente está recortada en `$APEX_WORK/out/images/p<página>_<n>.png`.

1. **Dos lectores independientes.** Por ejemplo, dos sub-agentes de Claude que no ven el trabajo del otro, cada uno con
   el PNG. Cada uno escribe `$APEX_WORK/ocr/readerA/p<página>_<n>.tsv` y `readerB/…`: una fila por renglón de la
   imagen, columnas separadas por tab, texto exacto (mayúsculas, símbolos, espacios dobles).
2. `./venv/bin/python checks/compare_readers.py` tiene que dar 0 diferencias. Si no, un tercero desempata mirando el PNG.
3. Opcional: `tesseract <png> - --psm 6` como tercera opinión. En la 2023.1.10 difirió en 5 de 1,058 filas, y en todas
   el error era de Tesseract.
4. Escribir `$APEX_WORK/ocr/p<página>_<n>.md` con el formato de las existentes: un comentario
   `<!-- image p<página>_<n> transcribed … -->` y la tabla en Markdown. Un diagrama va como Mermaid más su texto, y una
   imagen sin texto (portada, logo) como un comentario que lo diga.
5. `./run.sh` otra vez.

## 4. Leer el veredicto

`gate.py` imprime:

- **A, B, G y OCR:** tienen que dar `PASS`. Si A falla, `out/verify_report.json` lista las páginas, con los tokens que
  faltan o sobran y los problemas de orden. Una falla real se corrige en `convert.py`, nunca a mano en el `.md`.
- **TRIAGE E/F:** revisar cada entrada de `out/row_diffs.json` y `out/cell_diffs.json` contra la página
  (`pdftoppm -r 80 -png -f N -l N "$APEX_PDF" /tmp/pN`). Los falsos positivos conocidos (en la 2023.1.10 fueron
  todos los candidatos salvo uno): nombres partidos en dos renglones, poppler pegando el Type al nombre, filas con
  Element vacío, texto alineado más abajo dentro de la celda, encabezados centrados, títulos `####`, la "B" oculta. Lo que no
  encaje en esos patrones es un defecto: se corrige en `convert.py` y se vuelve a correr.
- `out/errors_report.txt`: los códigos de error del PDF y del `.md` tienen que coincidir uno a uno.

## 5. Auditoría visual (capas C y D)

No es automática. Se prepara un lote por sub-agente, por ejemplo 60 páginas al azar más algunas elegidas:

```bash
./venv/bin/python checks/audit_prep.py c1 --random 60 --seed 1
./venv/bin/python checks/audit_prep.py c2 --pages 48 613 743 3366 3399
```

Cada lote queda en `$APEX_WORK/audit/<lote>/` (`md/`, `img/`, `pages.txt`), y el sub-agente escribe ahí su
`findings.json`. Los prompts:

- **C:** `docs/audit-visual-prompt.md`. Página del `.md` contra la imagen de la página. Recomendado: 60 páginas al azar
  más las páginas de riesgo (tablas largas, imágenes, apéndices).
- **D:** `docs/audit-pdf-first-prompt.md`. Se toma un elemento del PDF (XSD, ejemplo, fila, código de error) y se busca
  a ciegas en el `.md`. Recomendado: 250 objetivos distribuidos por categoría.

Cada hallazgo real se corrige en el conversor y se vuelve a correr `run.sh`.

## 6. Si cambió el diseño del PDF

Síntomas: A con muchas páginas en rojo, tablas vacías o títulos que no se detectan. Herramientas:

- `./venv/bin/python checks/fonts.py "$APEX_PDF"` muestra las fuentes, tamaños y colores usados. Compáralos con las
  constantes del principio de `convert.py` (`is_code` = CourierNew, `GRAY_LABEL`, `CELL_FILLS`, márgenes
  `HEADER_MAX_Y`/`FOOTER_MIN_Y`).
- `./venv/bin/python checks/spans.py 48 613` imprime cada texto de esas páginas con su posición x/y, fuente y color.
- El recorte de `pdftotext` en `run.sh` (`-y 57 -H 639`) excluye el encabezado y el pie de página. Si cambian los
  márgenes, se ajusta junto con `HEADER_MAX_Y`/`FOOTER_MIN_Y`.

## 7. Publicar

1. Escribir `$APEX_WORK/header_verification.md` con el resumen de las verificaciones de esta release (ver la carpeta
   de la 2023.1.10 como modelo) y volver a correr `./run.sh` para que entre en el encabezado.
2. Copiar `$APEX_WORK/out/final.md` a donde se publica (`APEX_Message_Reference_<release>.md`) y guardar la carpeta
   de trabajo junto a la anterior: es la evidencia y la fuente de `--reuse` para la próxima release.
3. Actualizar los lugares que nombran el archivo publicado (instrucciones de agentes, índices, memoria).
