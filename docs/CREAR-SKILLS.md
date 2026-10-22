# Crear skills de una persona o un grupo

Creator MD reúne conocimiento publicado y lo convierte en un paquete que una IA puede consultar y aplicar. El paquete combina instrucciones, evidencia, procedimientos revisados y herramientas de consulta. No entrena un modelo ni incorpora la experiencia privada de un creador.

## Flujo en la aplicación

1. En la biblioteca, crea áreas y personas. Añade sus fuentes públicas o videos individuales y recopila el contenido accesible. Conserva los límites que indique cada plataforma.
2. Abre **Skills** y crea un proyecto. Dale un nombre, explica el propósito, los usuarios o negocios a los que se aplicará y las tareas concretas que debe resolver.
3. Selecciona una persona o un grupo. Pueden pertenecer a áreas distintas. La selección combina sus fuentes sin mover las colecciones originales.
4. Guarda y construye el skill. La construcción utiliza lo ya recopilado; no descarga nuevos videos. Revisa los documentos disponibles, criterios y estado del proyecto.
5. Copia la solicitud de revisión y úsala con una IA que pueda leer los archivos del proyecto, o revisa tú la evidencia. Comprueba contexto, fechas, tiempos, cifras y contradicciones. Adapta cada idea al propósito elegido.
6. Importa la síntesis en JSON. El sistema comprueba estructura, pertenencia de la evidencia, intervalos y hashes originales antes de reemplazar la versión válida. Esta comprobación técnica no demuestra que una recomendación sea correcta.
7. Descarga el ZIP del proyecto. Contiene un directorio con `SKILL.md`, referencias, búsqueda y metadatos. Se puede instalar en un agente compatible con skills.

Un buen propósito describe decisiones o entregables: «Diagnosticar embudos de captación para servicios locales y proponer experimentos medibles» sirve mejor que «Ser experto en todo». Las tareas pueden ser diagnosticar pérdidas, calcular límites económicos, diseñar una prueba y revisar sus resultados.

## Revisión que convierte evidencia en un procedimiento

Para cada criterio documenta:

- Qué principio se sostiene y con qué evidencia exacta.
- Cuándo aplicarlo y qué datos requiere.
- Pasos, resultado observable y condiciones para detener o corregir.
- Límites, excepciones, diferencias entre autores y adaptación propia.
- Autor, URL, segmento, tiempo disponible y hash del original.

No copies promesas de resultados como garantías. La coincidencia entre creadores no reemplaza una prueba. Cuando el contenido mencione una pantalla no inspeccionada, una función cambiante o una cifra dudosa, conserva ese límite. Consulta documentación oficial actual para funciones y políticas.

La solicitud de revisión generada explica el esquema de `curated.json`. Cada evidencia necesita un ID y `source_hash` existentes en el `knowledge.json` de ese proyecto. No uses títulos como identificadores ni inventes tiempos. La importación reemplaza la síntesis completa: conserva los criterios vigentes dentro del JSON que importas. Se guarda `curated.previous.json` como copia de la versión anterior.

## Actualización

Con **actualización automática** activa, la sincronización reconstruye un proyecto cuando detecta cambios en su perfil, fuentes o evidencia local. `run.py build` y `run.py skills build --all` también actualizan esos proyectos. Pausar un proyecto conserva su paquete; la reconstrucción manual de ese proyecto sigue disponible.

Las nuevas transcripciones no se convierten automáticamente en criterios aprobados. Una referencia eliminada de la selección, un original modificado o una revisión excluida apartan el criterio afectado de la publicación y lo conservan para revisar. Los criterios heredados de un área también necesitan comprobar su encaje con el nuevo propósito.

La app puede recopilar y construir sin una API de síntesis. Para evaluar y ampliar la metodología se necesita una revisión humana o una IA con acceso a los archivos. El seguimiento local de Codex de este equipo realiza esa revisión dentro de los límites configurados; no es un servicio incorporado para cualquier instalación. La app y los seguimientos locales requieren que el equipo y el proceso correspondiente estén disponibles.

## Archivos y terminal

Los perfiles se guardan en `workspaces/.creator-md/skill-projects.json`. Cada proyecto tiene su carpeta `projects/skills/<id>/`, independiente de las colecciones y del repositorio de la aplicación. Los datos y paquetes generados están excluidos de Git.

```powershell
python run.py skills list
python run.py skills preview --id mi-skill
python run.py skills create --file perfil.json
python run.py skills update --id mi-skill --file perfil.json
python run.py skills build --id mi-skill
python run.py skills build --all
python run.py skills import-curation --id mi-skill --file sintesis.json
python run.py skills export --id mi-skill
```

`create` requiere `name`, `purpose`, `tasks` como lista y `person_ids` como lista de IDs existentes. Admite `id`, `audience` y `auto_update`. `update` acepta cambios parciales sin cambiar el ID. `build --all` respeta proyectos pausados y evita reconstruir los que no cambiaron. Los comandos no consultan plataformas ni contratan una IA.

El skill de Ads se mantiene en su [repositorio independiente](https://github.com/andrsnrua/ads-evidence). Su publicación sigue [un procedimiento separado](PUBLICAR-SKILL-GITHUB.md); crear un proyecto en la app no publica sus datos en GitHub.
