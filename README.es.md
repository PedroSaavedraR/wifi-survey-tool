# WiFi Coverage Survey Tool (Windows)

[English](README.md) | [Español](README.es.md)

Herramienta de línea de comandos para consultar y registrar la conexión WiFi activa y, opcionalmente, las redes visibles. Cada captura incluye una marca temporal y etiquetas de campaña y ubicación; puede incluir coordenadas sobre un plano para repetir medidas y analizarlas con las herramientas Python del proyecto.

## 1. Entorno y requisitos

* **Sistema operativo probado:** Windows 11.
* **Equipo de prueba:** Lenovo LOQ 15 con adaptador WiFi MediaTek MT7921.
* **Intérprete:** Python 3.8 o posterior. La versión comprobada en el equipo de prueba es Python 3.14.6.
* **Utilidades del sistema:** `netsh.exe` y la API WLAN nativa de Windows.
* **Dependencias:** adquisición e interfaz gráfica con bibliotecas incluidas en Python para Windows (incluido Tkinter). Para generar gráficos, instale `matplotlib`:

```cmd
python -m pip install matplotlib
```

La opción `--all` solicita un escaneo mediante la API WLAN de Windows. En el equipo de prueba fue necesario habilitar los servicios de ubicación de Windows y ejecutar el recolector con privilegios de administrador para obtener redes visibles. Estos requisitos pueden variar según la versión de Windows, el adaptador y sus controladores.

## 2. Instalación y archivos

No se requieren paquetes externos para adquirir datos. Abra una terminal en la carpeta del proyecto. Compruebe la instalación de Python con:

```cmd
python --version
```

Para crear la configuración local a partir de la plantilla, ejecute en PowerShell:

```powershell
Copy-Item config.example.json config.json
```

Edite `config.json` con las etiquetas de equipo y campaña. Este archivo local queda excluido de Git.

Instale `matplotlib` únicamente si desea generar gráficos. El código del proyecto incluye:

* `wifi_scanner.py`: adquisición, etiquetado y almacenamiento de capturas.
* `wifi_survey_gui.py`: selección de planta y posición sobre el plano e inicio de capturas de P2.
* `config.example.json`: plantilla sin identificadores personales.
* `validation/generate_chart.py`: generación de gráficos a partir de los datos.
* `validation/practica2_analysis.py` y `validation/map_measurements.py`: funciones de análisis y utilidades de la vista de mapa.
* `tests/test_practica2_analysis.py`: pruebas del análisis y las rutas de almacenamiento.

El archivo `.gitignore` excluye la configuración local, las capturas JSONL, la memoria técnica y los resultados gráficos. Los planos originales `FIC - P0.png` a `FIC - P4.png` y `ap_list_up_*.csv` son materiales descargados de Moodle y no se deben incluir en Git. Para ver la señal asociada a cada router, deja el CSV `ap_list_up_*.csv` en la carpeta del proyecto; el plano se puede seleccionar desde la interfaz. El recolector crea `data/` al ejecutarse.

## 3. Configuración

El recolector carga `config.json` al iniciarse. En la configuración de ejemplo se utilizan estos campos:

* `device_id`: identificador del equipo de medida.
* `default_campaign`: identificador de la campaña.
* `building` y `floor`: edificio y planta.
* `default_interval`: intervalo solicitado entre capturas, en segundos.
* `default_samples`: número de capturas por ejecución.
* `measurement_procedure` y `measurement_incidents`: procedimiento e incidencias opcionales que se copian a las capturas de una ejecución.
* `coordinate_reference`: identificador del plano, imagen local, referencia de ejes y unidades. Para coordenadas en píxeles se recomienda origen arriba a la izquierda, eje X hacia la derecha y eje Y hacia abajo.
* `access_points`: posiciones medidas manualmente de los AP que se quieran analizar. Cada elemento usa `bssid` (dirección MAC), `x`, `y`, `units` y, opcionalmente, `plan_id`, `label` y `meters_per_unit`. No se deben usar coordenadas de un plano distinto.

Las opciones `--room`, `--orientation`, `--interval` y `--samples` permiten indicar esos valores para una ejecución concreta. Para localizar las capturas, use `--point-id`, `--x` y `--y`; las dos coordenadas deben indicarse juntas y usan las unidades de `coordinate_reference`. `--procedure` documenta el procedimiento de la ejecución y `--incident` (repetible) anota incidencias. El intervalo representa la espera solicitada entre capturas, no garantiza por sí solo el tiempo real entre marcas temporales.

## 4. Adquisición

### Interfaz gráfica para seleccionar una posición

Para elegir la planta y marcar la posición directamente sobre el plano, ejecuta:

```cmd
python wifi_survey_gui.py
```

Selecciona la planta, carga su imagen si no aparece automáticamente y haz clic en tu posición. La imagen se muestra a su tamaño original: el origen es la esquina superior izquierda, X aumenta hacia la derecha, Y hacia abajo y las coordenadas guardadas son píxeles de esa imagen. Puedes desplazarte con las barras para llegar a cualquier zona. Completa el identificador del punto, la orientación y el número de capturas; pulsa **Iniciar capturas** para abrir el recolector en una terminal aparte. La interfaz guarda sus datos de la práctica 2 en `data/practica2/screenshots.jsonl`; al activar el escaneo de todas las redes usa `data/practica2/screenshots_all.jsonl` y requiere un intervalo mínimo de 5 segundos. Los JSONL de la práctica 1 en `data/screenshots.jsonl` y `data/screenshots_all.jsonl` no se modifican. Detén la adquisición con `Ctrl+C` en esa terminal.

La interfaz muestra rombos azules para las posiciones con medidas; el número indica cuántas capturas se hicieron allí. Haz clic cerca de un rombo para consultar la tabla de redes; la selección se ajusta al punto medido más cercano si está a menos de 24 píxeles. **Recargar datos** solo vuelve a leer el dataset. Para repetir la medición en ese sitio, pulsa **Medir de nuevo aquí**. Para medir en un punto distinto, haz clic en una zona libre del plano: la interfaz propone un identificador nuevo, que puedes editar, y pulsa **Iniciar capturas en posición seleccionada**. Al terminar, el marcador y la tabla se actualizan automáticamente. Si cancelas antes de que se guarde una muestra, se quita la selección provisional y no aparece un punto medido. El RSSI y las tasas Rx/Tx solo se muestran para el AP conectado: Windows no proporciona esas tasas para las redes vecinas.

Al seleccionar un punto medido, la interfaz cruza los BSSID de `eduroam` detectados con las MAC de radio del inventario `ap_list_up_*.csv` y muestra la señal media observada para cada router. En el plano P2, los routers del inventario se dibujan como círculos: 0-24 % rojo, 25-49 % naranja, 50-74 % amarillo, 75-100 % verde y gris cuando no hay señal disponible. Los rombos azules representan los puntos medidos; la leyenda distingue ambas formas. Para cada router se muestra el BSSID de `eduroam` con mayor señal media y el número de muestras. «No detectado» significa que no apareció en las capturas de ese punto; no se interpola ni se convierte en un 0 %.

El botón **Ver rangos de cobertura** abre un modo exclusivo y oculta la tabla de mediciones. Pulsa **Elegir routers** para abrir el selector; allí puedes marcar uno o varios puntos de acceso, seleccionar todos o quitar la selección. El mapa muestra solo los routers marcados. Cuando hay uno seleccionado, se rellena su rango con una capa PNG de transparencia real para mantener visible el plano; al marcar varios, se muestran sus contornos para comparar los solapamientos. Dibuja círculos centrados en cada router: el modelo ajusta una recta entre la señal porcentual observada y la distancia en píxeles para estimar los radios de 70 % y 40 %. El radio exterior se limita a la distancia de la muestra más lejana y los colores representan las zonas estimadas (verde ≥70 %, amarillo 40-69 %, rojo <40 %). Se necesitan al menos dos distancias de medida distintas por router. Es una estimación radial aproximada: paredes, orientación y obstáculos pueden hacer que la cobertura real no sea circular.

La interfaz guarda junto a cada muestra el edificio, planta, identificador y ruta del plano seleccionado, además de la posición marcada. La ruta permite reconocer qué imagen se usó en este equipo; para compartir el proyecto, descarga los planos `FIC - P0.png` a `FIC - P4.png` de Moodle, selecciónalos con **Cargar plano...** y, si lo deseas, colócalos junto a `wifi_scanner.py` para que la interfaz los encuentre automáticamente.

### Usar un plano y mediciones propios

Puedes usar tu propio plano en formato PNG: selecciona la imagen con **Cargar plano...** y marca las posiciones directamente sobre ella. Las coordenadas se guardan en píxeles respecto a esa imagen. Usa los campos **Edificio** y **Planta** de forma consistente, porque juntos identifican el plano de las mediciones (por ejemplo, `LAB-P1`); al volver a elegir esos valores, la interfaz carga las capturas que tengan ese mismo identificador. Los nuevos datos se guardan en `data/practica2/screenshots.jsonl` o, si activas el escaneo de todas las redes, en `data/practica2/screenshots_all.jsonl`. Las capturas se añaden al final, no sustituyen las anteriores.

La GUI no tiene un selector para abrir un JSONL arbitrario ni para elegir una carpeta de datos: lee esos dos archivos de la práctica 2 y filtra las capturas por el identificador edificio-planta. Si quieres mantener otros datos separados, guarda o copia sus JSONL fuera de esos archivos y vuelve a colocarlos allí cuando quieras consultarlos; conserva siempre una copia de seguridad antes de sustituirlos. Desde la línea de comandos, `--dataset practica1` y `--dataset practica2` permiten elegir uno de los dos conjuntos admitidos.

### Conexión activa

Para iniciar el recolector con los valores predeterminados, ejecute:

```cmd
python wifi_scanner.py
```

Para especificar las etiquetas y la cadencia directamente, ejecute, por ejemplo:

```cmd
python wifi_scanner.py --room "Sala de pruebas" --orientation "0-Norte" --interval 3 --samples 10
```

Este modo consulta la conexión activa y guarda únicamente el punto de acceso conectado en `data/screenshots.jsonl`. Para registrar un punto sobre el plano, indique su identificador y sus coordenadas:

```cmd
python wifi_scanner.py --room "P1" --point-id "P1" --x 420 --y 318 --procedure "Portátil inmóvil a altura fija" --interval 3 --samples 10
```

Sustituya `420` y `318` por las coordenadas leídas del plano elegido; no son valores de ejemplo que deban reutilizarse. Cada ejecución recibe un `session_id` y cada captura un `sample_index`. Las capturas se añaden al final del archivo; una ejecución nueva no elimina las anteriores. Si no se indican coordenadas, la adquisición sigue siendo compatible y el campo de posición no incluye valores `x` e `y`.

### Todas las redes visibles

Para solicitar un escaneo nuevo de Windows y registrar las redes detectadas, añada `--all`:

```cmd
python wifi_scanner.py --room "Sala de pruebas" --orientation "0-Norte" --interval 5 --samples 10 --all
```

El modo `--all` guarda sus registros por separado en `data/screenshots_all.jsonl` para el conjunto predeterminado de la práctica 1. Su intervalo mínimo es de 5 segundos: si el valor indicado en la línea de comandos o en `config.json` es menor, el recolector lo eleva a 5 segundos y lo comunica. El escaneo añade aproximadamente 4 segundos más por captura; por tanto, el tiempo real entre capturas será superior al intervalo configurado. Consulte `timestamp_utc` para conocer la cadencia observada.

El CLI conserva por defecto las rutas de la práctica 1. Para seleccionar explícitamente el conjunto de la práctica 2, use `--dataset practica2`; las capturas se guardarán bajo `data/practica2/`.

### Parada

Para detener la adquisición, pulse `Ctrl+C` en la terminal. Cada registro se escribe antes de esperar a la siguiente captura, por lo que las medidas ya guardadas se conservan.

## 5. Formato de los datos

Los dos archivos de datos utilizan JSON Lines (JSONL): cada línea es un objeto JSON independiente. Se pueden abrir con un editor de texto o procesar desde otros programas.

Los registros actuales contienen los siguientes campos principales:

* `metadata`: `timestamp_utc`, `device_id`, `campaign`, `building`, `floor`, `room`, `orientation` y `network_scope`.
* `metadata.session_id` y `metadata.sample_index`: identifican la ejecución y el orden de cada captura.
* `metadata.measurement_procedure` y `metadata.measurement_incidents`: procedimiento e incidencias opcionales.
* `metadata.position`: `point_id`, `plan_id`, plano, origen, ejes, sistema de coordenadas, unidades, incertidumbre, calibración y, si se indicó, coordenadas `x` e `y`. Las capturas antiguas no tienen este campo.
* `active_interface`: estado, SSID, BSSID/MAC, señal porcentual, RSSI en dBm, canal, banda, tipo de radio y tasas de recepción y transmisión cuando Windows las proporciona. Si falla la consulta de la interfaz, puede contener `error` en lugar de estos campos.
* `visible_networks`: SSID detectados y sus BSSID/MAC, señal porcentual, canal y tipo de radio. En el modo predeterminado contiene el punto de acceso activo; con `--all` contiene las redes visibles del escaneo.
* `network_scan`: estado del escaneo solicitado en modo `--all` y, si se produce un error, su mensaje.

`network_scan.status` puede tomar estos valores:

* `not_requested`: modo predeterminado; no se solicitó un escaneo de redes visibles.
* `success`: el escaneo y la consulta terminaron correctamente. Una lista `visible_networks` vacía significa que no se detectaron redes.
* `error`: Windows no pudo iniciar el escaneo o falló la consulta de redes. El mensaje queda en `network_scan.message`; la lista vacía no debe interpretarse como una medida válida sin redes.

Los valores no disponibles se omiten del JSON, no se sustituyen por cero. `signal_percent` es una estimación porcentual de Windows, no una medida en dBm. El RSSI en dBm corresponde a la conexión activa. Los BSSID se guardan como direcciones MAC sin hash para poder asociarlos directamente a puntos de acceso medidos en el plano. Los SSID se conservan tal como los informa Windows. Las capturas antiguas con el campo `bssid_hash` siguen leyéndose en los análisis, pero no se pueden asociar automáticamente con las MAC nuevas.

Las muestras históricas pueden no incluir todas las claves del esquema actual. En los datos revisados el 4 de octubre de 2026, los 59 registros de `screenshots.jsonl` son anteriores a la incorporación de `network_scope` y `network_scan`. Los 10 registros iniciales de `screenshots_all.jsonl` incluyen `network_scope`, pero son anteriores a `network_scan`. Los registros nuevos incluyen ambos campos.

## 6. Gráficos y validación

### Gráficos de capturas

No hace falta Jupyter para usar la aplicación. Para generar gráficos de las capturas se utiliza `validation/generate_chart.py`; instala `matplotlib` si aún no está disponible:

```cmd
python -m pip install matplotlib
```

El script permite representar la señal frente al índice de captura y filtrar por BSSID o SSID. El modo de rangos de la interfaz gráfica ofrece la visualización radial estimada sobre el plano.

Para generar el gráfico de RSSI y tasa de recepción de la conexión activa, ejecute:

```cmd
python validation/generate_chart.py
```

Para representar la señal porcentual de todos los BSSID del archivo `--all`, ejecute:

```cmd
python validation/generate_chart.py --all
```

Para ver las capturas de la práctica 2 en una gráfica y centrarla en un AP concreto, use su `bssid` (dirección MAC; puede consultarla en `data/practica2/screenshots_all.jsonl`):

```cmd
python validation/generate_chart.py --all --data-dir data/practica2 --bssid 00:11:22:33:44:55
```

La gráfica muestra la señal porcentual de ese BSSID frente al índice de captura. Para filtrar por SSID en lugar de por BSSID:

```cmd
python validation/generate_chart.py --all --data-dir data/practica2 --ssid "NOMBRE_DEL_SSID"
```

Estas gráficas sirven para comparar capturas/repeticiones. No son una gráfica frente a distancia: para esta última y para representar las posiciones en el plano también hace falta registrar medidas en varios puntos y configurar la posición real del AP y la calibración del plano en `config.json`. El directorio `data/practica2` contiene el conjunto de P2; si se omite `--data-dir`, el script conserva su comportamiento anterior y usa `data`.

Puede filtrar el gráfico por el nombre SSID exacto:

```cmd
python validation/generate_chart.py --all --ssid "SSID_de_ejemplo"
```

Los gráficos se guardan como `validation/validation_chart.png`, `validation/validation_chart_all.png` y, al filtrar, `validation/validation_chart_all_<SSID>.png`. Los valores ausentes se muestran como huecos, no como valores inventados.

El plano de validación se conserva localmente en `validation/floorplan.png` y se excluye del repositorio porque muestra la distribución de la vivienda.

Las capturas y resultados experimentales se conservan localmente en los archivos JSONL; no se incluyen en el repositorio público porque contienen identificadores de redes y etiquetas de ubicación.

Para contrastar manualmente los campos con Windows, ejecute las consultas del sistema en una terminal:

```cmd
netsh wlan show interfaces
netsh wlan show networks mode=bssid
```

Anote los valores observados y la hora de la comprobación e incluya la comparación en la memoria técnica. Las consultas no son simultáneas con la captura de la aplicación; tenga en cuenta esta diferencia temporal al interpretar los resultados.

## 7. Limitaciones y solución de problemas

Los datos conservan los SSID sin transformación y las ubicaciones definidas en `config.json`. Revise esta información antes de publicar el repositorio o compartir los datos.

* El recolector está orientado a Windows y depende de `netsh` y de la API WLAN nativa.
* La cantidad de redes visibles depende del adaptador, los controladores, los permisos y las condiciones del entorno. Un escaneo puede devolver menos redes que la interfaz gráfica de Windows.
* Si `network_scan.status` es `error`, compruebe que la interfaz WiFi está habilitada, que los servicios de ubicación de Windows están activos y que la terminal tiene los permisos necesarios. El mensaje de error se conserva en el JSONL.
* Si el escaneo termina con `success` y `visible_networks` está vacío, no se detectaron redes en esa consulta; no es lo mismo que un error.
* El intervalo real puede superar el solicitado por el tiempo de adquisición, especialmente en modo `--all`. Utilice las marcas temporales para calcularlo.
* Las ubicaciones y orientaciones se introducen manualmente; la herramienta no obtiene coordenadas GPS ni genera mapas.
