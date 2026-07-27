# creator-md

Extrae videos públicos de un perfil de TikTok, los transcribe localmente y
mantiene **un único archivo Markdown acumulativo**. Guarda el historial y los
IDs procesados para que la siguiente ejecución continúe donde terminó.

No crea skills, no necesita OpenKB y no necesita una API de IA.

## Qué hace

```text
Perfil TikTok
    ↓
Eliges cuántos videos procesar
    ↓
yt-dlp descubre y descarga
    ↓
summarize + Whisper transcriben localmente
    ↓
un-solo-archivo.md
    ↓
history.json + state.json permiten continuar
```

Cada sección del Markdown conserva:

- ID y URL del video.
- Título, fecha y duración.
- Transcripción con timestamps.
- Enlace a la fuente en cada segmento.

## Instalación

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
pip install yt-dlp martino-summarize openai-whisper
```

También debe existir `ffmpeg` en `PATH`.

## Uso

Procesar los primeros 10 videos:

```bash
creator-md extract \
  --profile "https://www.tiktok.com/@creador" \
  --project creador \
  --count 10
```

Procesar los siguientes 10:

```bash
creator-md continue --project creador --count 10
```

Consultar dónde quedó:

```bash
creator-md status --project creador
```

Reconstruir el Markdown sin volver a descargar:

```bash
creator-md export --project creador
```

Revisar dependencias:

```bash
creator-md doctor
```

## Archivos de cada proyecto

```text
workspaces/creador/
├── creador.md          # Todo el contenido en un solo archivo
├── history.json        # Historial de cada ejecución
├── state.json          # Estado por ID: pending/completed/failed
├── profile.json        # Videos descubiertos y su orden
├── project.json
├── raw-results/        # Transcripciones y caché
├── sources/            # Markdown individual por video
└── reports/
```

`continue` solicita más entradas del perfil, conserva el orden anterior, omite
los IDs completados, reintenta los fallidos y selecciona únicamente la cantidad
indicada con `--count`. Si TikTok falla temporalmente, puede continuar usando el
último manifiesto guardado.

## Configuración local

Los valores predeterminados son Whisper `base` e idioma español:

```bash
export CREATOR_MD_WHISPER_MODEL=base
export CREATOR_MD_LANGUAGE=es
```

Para mayor precisión puede usarse `small` o `medium`, a costa de más descarga,
memoria y tiempo de CPU.

Rutas de herramientas personalizadas:

```bash
export CREATOR_MD_YTDLP=/ruta/a/yt-dlp
export CREATOR_MD_SUMMARIZER=/ruta/a/summarizer
```

## Pruebas

```bash
pytest
```

La suite usa fixtures locales y no accede a TikTok.

## Licencia

Este repositorio usa MIT y no copia código externo. `yt-dlp`,
`martinopiaggi/summarize`, Whisper y ffmpeg conservan sus propias licencias.
