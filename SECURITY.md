# Alcance de seguridad

Esta es una demostración de portafolio, no un sistema de producción ni una auditoría certificada.

## Protecciones de esta copia

- Datos creados desde cero, no derivados de registros reales.
- Sin lectura automática de Excel del equipo ni conexión a sistemas de negocio.
- Carga de archivos desactivada por defecto. Si se habilita localmente, los resultados se conservan en la sesión, no en una caché compartida de datos privados.
- Sin contraseñas ni tokens incluidos. La aplicación no requiere credenciales para la demo.
- Exclusión de hojas de cálculo, documentos, imágenes, exportaciones, claves, entornos y archivos de configuración privada mediante `.gitignore`.
- Lista explícita de archivos publicables y comprobación del contenido del índice de Git mediante `python scripts/check_publication.py --staged`.
- Pruebas y configuración de actualizaciones de dependencias. Una configuración no significa que las comprobaciones de GitHub ya se hayan ejecutado.

`.gitignore` no elimina archivos que ya estén en el historial ni evita que alguien los agregue de forma forzada. El verificador solo reconoce ciertos patrones; siempre revisar también el contenido y el historial antes de publicar. No incluir capturas de operaciones reales en el README, incidencias ni comentarios.

## Límites del modo local

No hay autenticación, roles ni aislamiento de un servicio multiusuario. La carga opcional acepta XLSX conocidos y de confianza; el límite de tamaño comprimido no garantiza un procesamiento seguro de archivos maliciosos ni limita toda la memoria utilizada. No habilitarla en una demo pública.

Los adaptadores leen valores guardados y no ejecutan fórmulas de Excel. Las descargas neutralizan texto que parece una fórmula, pero quien abra/exporte información debe revisar su contenido. No hay garantía de borrado forense de la memoria del proceso.

## Antes de cada publicación

1. Mantener archivos reales fuera de esta carpeta.
2. Ejecutar pruebas y el verificador de publicación.
3. Revisar archivos preparados, cambios e historial. No publicar claves aunque el repositorio sea privado.
4. Usar un correo de commit privado de GitHub si se desea proteger la dirección personal.
5. Activar, cuando estén disponibles, alertas de dependencias, detección de secretos y protección al subir cambios.

Si se expone una credencial, revocarla o rotarla primero. Borrar el archivo en un commit posterior no elimina su historial. No adjuntar secretos o datos reales a un reporte público de seguridad.
