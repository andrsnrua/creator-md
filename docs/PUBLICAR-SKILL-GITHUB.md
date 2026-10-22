# Publicar Ads como repositorio independiente

El repositorio de destino es **andrsnrua/ads-evidence** y debe permanecer privado. Su raíz contiene `SKILL.md`, `references/`, `scripts/`, `assets/` y `agents/`. No se publica la aplicación, su configuración, cookies, audio ni sus carpetas de trabajo. El publicador no crea repositorios ni cambia su visibilidad.

La fuente mantenida de instrucciones sigue en `src/creator_skill/skill_resources/ads/`. El paquete exportado está en `Ads/skill/`. La copia Git se mantiene aislada en `.venv/github/ads-evidence`; nunca se modifica el `.git` de Creator MD.

## Preparar sin red

Desde la raíz del proyecto, con Python 3.11 o posterior:

```powershell
python -X utf8 scripts/publish_ads_skill.py --prepare-only
```

En este equipo se puede sustituir `python` por `C:/Users/braya/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`. `--repo-dir` admite otra subcarpeta dentro de `.venv/github`, nunca la aplicación ni la carpeta fuente del skill.

La preparación valida y copia el paquete; no crea commits ni hace llamadas de red. Si ya hay un checkout, requiere cambios locales resueltos y `origin` apuntando al repositorio correcto. Una carpeta preparada sin Git puede prepararse otra vez si conserva intactos los archivos y su manifiesto.

## Publicar

Se requieren `git`, `gh`, autenticación GitHub con acceso al repositorio privado existente y una identidad de commit configurada. Para el primer envío se puede crear el repositorio privado vacío y ejecutar directamente:

```powershell
python -X utf8 scripts/publish_ads_skill.py --publish
```

Si la carpeta destino aún no existe, el comando clona el repositorio existente. Si se usó `--prepare-only` primero, inicializa esa carpeta preparada como repositorio independiente con rama `main` y `origin` `https://github.com/andrsnrua/ads-evidence.git`, revisa y confirma el primer contenido, y luego ejecuta `--publish`. No inicialices el Git de la aplicación para este fin. Un repositorio remoto con historia requiere un clon limpio, no una segunda historia local.

Antes de copiar, el comando comprueba el nombre y visibilidad privados mediante `gh`, verifica el checkout, consulta `main` y solo admite un avance fast-forward. Crea un commit cuando cambia el contenido validado y hace push normal. Nunca usa force push, reset, stash, mezcla divergencias ni pisa archivos manuales. Una nueva consulta oficial o cambio de cobertura es contenido de la versión; ejecutar el publicador otra vez sin cambios no añade una fecha artificial ni otro commit.

## Qué valida

- Archivos portátiles permitidos; sin enlaces simbólicos, junctions, cachés, ejecutables o credenciales reconocibles. La detección de credenciales es una protección acotada, no una garantía de descubrir todos los secretos.
- Enlaces Markdown locales existentes dentro del skill.
- Correspondencia del catálogo con el índice y SHA-256 de todos los originales locales.
- Revisiones exportadas coincidentes con el registro editorial, citas seleccionadas y tiempos dentro de la transcripción. No sustituye la lectura crítica del contenido.
- Criterios publicados y ausencia de una exportación explícitamente pendiente.
- Propiedad de los archivos del checkout mediante `skill-manifest.json`. Solo se retiran archivos antiguos incluidos en ese manifiesto y cuyo hash sigue intacto.

La lectura usa los bloqueos de sincronización y reconstrucción de Ads. Los archivos se escriben mediante reemplazos atómicos individuales; el manifiesto se escribe al final. El commit aparece solo cuando acaba la copia. Si el proceso se interrumpe, un checkout sucio o un hash distinto detiene la siguiente publicación para conservar el trabajo y permitir revisar el estado.

El README generado describe ocho modelos de negocio, instalación, actualización y límites. El manifiesto incluye versión de contenido, hashes, nombres de criterios, número de documentos revisados y cobertura de fuentes. No incluye rutas de los originales ni claves de acceso. El paquete conserva la evidencia de terceros para uso privado; la publicación no cambia sus derechos.

## Mantenimiento

El seguimiento autorizado de Creator MD puede ejecutar este publicador después de recopilar gratuitamente, revisar evidencia nueva, publicar criterios y reconstruir el paquete. Debe respetar pausas, límites y bloqueo por espacio disponible. GitHub almacena versiones; no transcribe ni evalúa fuentes por sí mismo. La actualización requiere que el equipo y el entorno estén disponibles.

En una instalación limpia del skill, `git pull --ff-only` obtiene la versión publicada. Si se instaló copiando archivos al directorio de skills del agente, hay que reemplazar esa copia. Mantén personalizaciones fuera de los archivos generados.

Un push rechazado deja el commit local para revisión; no se repite indefinidamente ni se reescribe historia. Si falla una validación, conserva la última versión publicada y corrige o revisa el archivo indicado. Los errores de herramientas no imprimen URLs autenticadas ni salida de credenciales.
