# Creator MD

Biblioteca local organizada por **área → persona → fuentes**. Recopila videos públicos, conserva transcripciones verificables y construye skills por área, persona o grupo. Cada skill puede tener un propósito, usuarios y tareas diferentes. La extracción y transcripción local no requieren una API de IA de pago.

## Abrir y usar

Abre **`Abrir Creator MD.cmd`** en Windows. La interfaz está en **http://127.0.0.1:8770/**.

1. Crea un área, por ejemplo Ads, diseño o desarrollo.
2. Añade una persona y pega sus enlaces de YouTube, TikTok o Instagram. También admite un video individual.
3. Pulsa **Actualizar** en una fuente o **Actualizar biblioteca**. Conserva lo terminado y procesa los videos nuevos.
4. En **Conocimiento**, busca dentro de las transcripciones, abre los fragmentos con tiempos y consulta los criterios revisados.
5. **Descargar skill** entrega las instrucciones, búsqueda portátil y referencias del área.
6. En **Skills**, crea un proyecto, define qué debe resolver y selecciona una o varias personas, incluso de áreas diferentes. Construye el paquete, revisa su evidencia e incorpora los criterios con **Importar síntesis**. Puedes descargar cada proyecto por separado y activar o pausar su actualización.

Consulta [Crear y mantener un skill](docs/CREAR-SKILLS.md) para el flujo completo. El contenido recopilado se distingue de los procedimientos revisados; crear el paquete no entrena un modelo ni reproduce todas las habilidades de una persona.

Puedes añadir las pestañas `/videos` y `/shorts` de YouTube a la misma persona. Los videos individuales no suscriben todo el canal. **Importación avanzada** conserva selección manual, fechas y consulta de historial.

## Actualización y calidad

Configuración permite consultar cada 6, 12, 24 o 48 horas, o cada semana, con un límite por fuente. El servidor debe seguir abierto y el equipo encendido. Cerrar la pestaña no cierra el servidor. Después de reiniciar el equipo, vuelve a abrir el lanzador.

La sincronización consulta fuentes activas, procesa pendientes y reconstruye los índices. Usa bloqueos entre procesos, escrituras atómicas y estados persistentes. Cada video terminado se guarda inmediatamente. Un error no cancela las demás fuentes. Los fallidos y los resultados vacíos aparecen separados. **Reintentar** vuelve sobre esos registros. **Importar texto** permite incorporar una transcripción conservando el enlace del video original.

Primero intenta subtítulos públicos; si faltan, usa audio y Faster Whisper local. Puedes elegir base, small, medium, large-v3 o turbo. Los modelos grandes requieren más recursos y una primera descarga. Para carruseles identificados y videos sin voz útil, usa RapidOCR local. La evidencia visual queda identificada como OCR, con límites de muestreo y advertencias de calidad; no equivale a comprensión completa de todos los elementos de la imagen.

Una transcripción no equivale a una recomendación validada. El conocimiento conserva autor, URL, fecha disponible, tiempos y hash del original. Las etiquetas son automáticas. Los criterios revisados añaden contexto, pasos, excepciones y evidencia exacta. Un cambio del original exige revisar su síntesis. El skill busca fragmentos pertinentes sin cargar cientos de documentos en contexto.

## Alcance gratuito

| Fuente | Alcance | Limitación |
|---|---|---|
| YouTube | Listados públicos, videos, Shorts, subtítulos y audio accesible | Algunos videos rechazan acceso; cada pestaña tiene su propia cobertura |
| TikTok | Historial público paginado con gallery-dl, descarga con yt-dlp, voz y OCR local | «Recuperar historial» consulta hasta 10 000 entradas; la cobertura indica si el proveedor llegó al final |
| Instagram | Perfiles y videos accesibles al extractor público | Puede rechazar la consulta completa; permite importar texto como alternativa |

**Apify está desactivado por defecto**, aunque haya un token guardado en Windows. Permitir Apify afecta las consultas de la aplicación y puede generar cargos en esa cuenta. Un proveedor de pago tampoco garantiza eliminar todas las restricciones.

Cobertura **completa** significa que el listado coincide con el total informado o que la paginación terminó con un indicador explícito del proveedor. Se limita a las publicaciones públicas visibles y no acredita que todas estén procesadas. **Parcial** conserva el límite de consulta. La fecha de generación del MD no reemplaza la fecha real de consulta.

En este equipo también quedó configurado un seguimiento diario de Codex para revisar evidencia nueva y mantener la síntesis de Ads. Consume el uso normal de la cuenta de Codex, requiere disponibilidad del entorno y no activa proveedores de pago.

## Archivos

```text
Ads/
  LEEME.md
  knowledge.json                 Evidencia para la interfaz
  curated.json                   Criterios revisados y citas
  skill/
    SKILL.md                     Procedimiento
    agents/openai.yaml           Presentación del skill
    scripts/search_evidence.py   Búsqueda con Python estándar
    references/
      catalogo.md                Cobertura y guía de consulta
      index.json                 Índice compacto por autor y tema
      criterios-curados.md       Síntesis revisada
      videos/*.md                Evidencia con tiempos
workspaces/
  .creator-md/library.json       Áreas, personas, fuentes, programación
  .creator-md/jobs/              Tareas persistentes de interfaz
  <categoría>/<colección>/
    project.json
    state.json
    history.json
    raw-results/                 Originales y caché local
    sources/                     MD por video
    <colección>.md               MD acumulativo
projects/<otra-área>/            Skills de las demás áreas
projects/skills/<id>/            Proyectos de una persona o grupo
  curated.json                  Síntesis conservada para revisión
  curation-task.md               Instrucciones para revisar con una IA
  skill/                        Paquete portátil propio
```

Las colecciones anteriores conservan su ubicación. El catálogo las agrupa sin mover los originales. `Ads/`, `projects/` y los datos de `workspaces/` son salidas locales excluidas del Git de la aplicación. El skill de Ads se publica en un repositorio independiente y privado: [andrsnrua/ads-evidence](https://github.com/andrsnrua/ads-evidence). Su acceso depende de los permisos de GitHub. El código de Creator MD y el contenido del skill tienen ciclos de publicación separados.

Los paquetes son portátiles: copia la carpeta que contiene `SKILL.md` al directorio de skills del agente compatible. La aplicación no instala skills globalmente por sorpresa. [Publicar el skill de Ads](docs/PUBLICAR-SKILL-GITHUB.md) describe el destino y las comprobaciones de actualización.

## Instalación y terminal

En otro equipo: Python 3.11+, FFmpeg y Node.js en PATH. Node ayuda a yt-dlp con los desafíos de JavaScript de YouTube.

```powershell
python -m pip install -e ".[dev]"
python run.py
python run.py sync --due
python run.py build
python run.py skills list
python run.py skills build --all
```

Aquí el lanzador utiliza el runtime de Codex y `.venv/runtime-packages`. `sync --due` respeta programación y fuentes pausadas. `sync` sin `--due` actualiza manualmente las fuentes activas. `build` reconstruye conocimiento sin consultar plataformas. Después de sincronizar se reconstruyen los proyectos de skills con actualización activa y cambios detectados; `skills build --all` ejecuta sólo esa parte. Los criterios cuya evidencia dejó de ser válida quedan pendientes de revisión.

La CLI por colección sigue disponible:

```powershell
creator-md sync --category ads --project creador --scan-limit 100
creator-md pending --category ads --project creador --count 10
creator-md history --category ads --project creador --count 10
creator-md retry --category ads --project creador --count 10
creator-md verify --category ads --project creador
creator-md export --category ads --project creador
creator-md doctor
```

`creator-md sync` descubre novedades sin transcribir; `run.py sync` coordina toda la biblioteca. Los motores anteriores quedan como extra opcional `legacy`.

## Verificación

`python -m pytest -q` prueba selección, conservación, duplicados, migración, programación, búsqueda, importación, referencias y rutas web sin depender de redes sociales. La extracción real se comprueba aparte porque las plataformas cambian.

Consulta [la guía de skills](docs/CREAR-SKILLS.md) y [la publicación independiente](docs/PUBLICAR-SKILL-GITHUB.md). Los controles de estructura y trazabilidad no sustituyen una revisión editorial ni prueban superioridad frente a otros productos.

## Licencia

MIT para este proyecto. Las dependencias y los modelos mantienen sus respectivas licencias. Los contenidos recopilados pertenecen a sus autores.
