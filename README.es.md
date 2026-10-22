# WiFi Coverage Survey Tool (Windows)

[English](README.md) | [Español](README.es.md)

Herramienta de línea de comandos para consultar y registrar la conexión WiFi activa y, opcionalmente, las redes visibles. Cada captura incluye una marca temporal y etiquetas de campaña y ubicación; puede incluir coordenadas sobre un plano para repetir medidas y analizarlas con el Notebook de la práctica 02.

## 1. Entorno y requisitos

* **Sistema operativo probado:** Windows 11.
* **Equipo de prueba:** Lenovo LOQ 15 con adaptador WiFi MediaTek MT7921.
* **Intérprete:** Python 3.8 o posterior. La versión comprobada en el equipo de prueba es Python 3.14.6.
* **Utilidades del sistema:** `netsh.exe` y la API WLAN nativa de Windows.
* **Dependencias:** adquisición e interfaz gráfica con bibliotecas incluidas en Python para Windows (incluido Tkinter). Para generar los gráficos y ejecutar el Notebook, instale Jupyter y `matplotlib`:

```cmd
python -m pip install jupyter matplotlib
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

Instale Jupyter y `matplotlib` únicamente si desea generar los análisis y gráficos. El código del proyecto incluye:

* `wifi_scanner.py`: adquisición, etiquetado y almacenamiento de capturas.
* `wifi_survey_gui.py`: selección de planta y posición sobre el plano e inicio de capturas de P2.
* `config.example.json`: plantilla sin identificadores personales.
* `validation/generate_chart.py`: generación de gráficos a partir de los datos.
* `validation/analisis_practica2.ipynb`: Notebook de análisis de las capturas P2.
* `validation/practica2_analysis.py` y `validation/map_measurements.py`: utilidades del Notebook y la vista de mapa.
* `tests/test_practica2_analysis.py`: pruebas del análisis y las rutas de almacenamiento.

El archivo `.gitignore` excluye la configuración local, las capturas JSONL, la memoria técnica y los resultados gráficos. Los planos originales `FIC - P0.png` a `FIC - P4.png` y `ap_list_up_*.csv` son materiales descargados de Moodle: no es necesario copiarlos al repositorio; la interfaz permite seleccionar el plano localmente. El recolector crea `data/` al ejecutarse.

## 3. Configuración

El recolector carga `config.json` al iniciarse. En la configuración de ejemplo se utilizan estos campos:

* `device_id`: identificador del equipo de medida.
* `default_campaign`: identificador de la campaña.
* `building` y `floor`: edificio y planta.
* `default_interval`: intervalo solicitado entre capturas, en segundos.
* `default_samples`: número de capturas por ejecución.
* `measurement_procedure` y `measurement_incidents`: procedimiento e incidencias opcionales que se copian a las capturas de una ejecución.
* `coordinate_reference`: identificador del plano, imagen local, referencia de ejes y unidades. Para coordenadas en píxeles se recomienda origen arriba a la izquierda, eje X hacia la derecha y eje Y hacia abajo.
* `access_points`: posiciones medidas manualmente de los AP que se quieran analizar. Cada elemento usa `bssid_hash`, `x`, `y`, `units` y, opcionalmente, `plan_id`, `label` y `meters_per_unit`. No se deben usar coordenadas de un plano distinto.

Las opciones `--room`, `--orientation`, `--interval` y `--samples` permiten indicar esos valores para una ejecución concreta. Para localizar las capturas, use `--point-id`, `--x` y `--y`; las dos coordenadas deben indicarse juntas y usan las unidades de `coordinate_reference`. `--procedure` documenta el procedimiento de la ejecución y `--incident` (repetible) anota incidencias. El intervalo representa la espera solicitada entre capturas, no garantiza por sí solo el tiempo real entre marcas temporales.

## 4. Adquisición

### Interfaz gráfica para seleccionar una posición

Para elegir la planta y marcar la posición directamente sobre el plano, ejecuta:

```cmd
python wifi_survey_gui.py
```

Selecciona la planta, carga su imagen si no aparece automáticamente y haz clic en tu posición. La imagen se muestra a su tamaño original: el origen es la esquina superior izquierda, X aumenta hacia la derecha, Y hacia abajo y las coordenadas guardadas son píxeles de esa imagen. Puedes desplazarte con las barras para llegar a cualquier zona. Completa el identificador del punto, la orientación y el número de capturas; pulsa **Iniciar capturas** para abrir el recolector en una terminal aparte. La interfaz guarda sus datos de la práctica 2 en `data/practica2/screenshots.jsonl`; al activar el escaneo de todas las redes usa `data/practica2/screenshots_all.jsonl` y requiere un intervalo mínimo de 5 segundos. Los JSONL de la práctica 1 en `data/screenshots.jsonl` y `data/screenshots_all.jsonl` no se modifican. Detén la adquisición con `Ctrl+C` en esa terminal.

La interfaz muestra en el plano marcadores amarillos para las posiciones con medidas; el número indica cuántas capturas se hicieron allí. Haz clic cerca de un marcador para consultar la tabla de redes; la selección se ajusta al punto medido más cercano si está a menos de 24 píxeles. **Recargar datos** solo vuelve a leer el dataset. Para repetir la medición en ese sitio, pulsa **Medir de nuevo aquí**. Para medir en un punto distinto, haz clic en una zona libre del plano: la interfaz propone un identificador nuevo, que puedes editar, y pulsa **Iniciar capturas en posición seleccionada**. Al terminar, el marcador y la tabla se actualizan automáticamente. Si cancelas antes de que se guarde una muestra, se quita la selección provisional y no aparece un punto medido. El RSSI y las tasas Rx/Tx solo se muestran para el AP conectado: Windows no proporciona esas tasas para las redes vecinas.

La interfaz guarda junto a cada muestra el edificio, planta, identificador y ruta del plano seleccionado, además de la posición marcada. La ruta permite reconocer qué imagen se usó en este equipo; para compartir el proyecto, descarga los planos `FIC - P0.png` a `FIC - P4.png` de Moodle, selecciónalos con **Cargar plano...** y, si lo deseas, colócalos junto a `wifi_scanner.py` para que la interfaz los encuentre automáticamente. El Notebook de la práctica 2 lee los JSONL de `data/practica2/`.

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

Sustituya `420` y `318` por las coordenadas leídas del plano elegido; no son valores de ejemplo que deban reutilizarse. Cada ejecución recibe un `session_id` y cada captura un `sample_index`. Las capturas se añaden al final del archivo; una ejecución nueva no elimina las anteriores. Si no se indican coordenadas, la adquisición sigue siendo compatible y el Notebook las señala como ausentes.

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
* `active_interface`: estado, SSID, BSSID seudonimizado, señal porcentual, RSSI en dBm, canal, banda, tipo de radio y tasas de recepción y transmisión cuando Windows las proporciona. Si falla la consulta de la interfaz, puede contener `error` en lugar de estos campos.
* `visible_networks`: SSID detectados y sus BSSID seudonimizados, señal porcentual, canal y tipo de radio. En el modo predeterminado contiene el punto de acceso activo; con `--all` contiene las redes visibles del escaneo.
* `network_scan`: estado del escaneo solicitado en modo `--all` y, si se produce un error, su mensaje.

`network_scan.status` puede tomar estos valores:

* `not_requested`: modo predeterminado; no se solicitó un escaneo de redes visibles.
* `success`: el escaneo y la consulta terminaron correctamente. Una lista `visible_networks` vacía significa que no se detectaron redes.
* `error`: Windows no pudo iniciar el escaneo o falló la consulta de redes. El mensaje queda en `network_scan.message`; la lista vacía no debe interpretarse como una medida válida sin redes.

Los valores no disponibles se omiten del JSON, no se sustituyen por cero. `signal_percent` es una estimación porcentual de Windows, no una medida en dBm. El RSSI en dBm corresponde a la conexión activa. Los BSSID se guardan como el prefijo de 12 caracteres hexadecimales de un hash SHA-256 para poder distinguir puntos de acceso entre capturas. Los SSID se conservan tal como los informa Windows.

Las muestras históricas pueden no incluir todas las claves del esquema actual. En los datos revisados el 4 de octubre de 2026, los 59 registros de `screenshots.jsonl` son anteriores a la incorporación de `network_scope` y `network_scan`. Los 10 registros iniciales de `screenshots_all.jsonl` incluyen `network_scope`, pero son anteriores a `network_scan`. Los registros nuevos incluyen ambos campos.

## 6. Gráficos y validación

### Análisis de la práctica 02

El Notebook [`validation/analisis_practica2.ipynb`](validation/analisis_practica2.ipynb) lee ambos JSONL y produce el resumen de AP de un punto, la gráfica de señal frente a distancia y la representación de las posiciones medidas sobre el plano. Instale Jupyter y Matplotlib si aún no están disponibles:

```cmd
python -m pip install jupyter matplotlib
```

Abre el Notebook desde Jupyter iniciado en la carpeta del proyecto. Lee automáticamente `data/practica2/screenshots.jsonl` y `data/practica2/screenshots_all.jsonl`; no necesita acceder a la red WiFi. Los planos originales de Moodle (`FIC - P0.png` a `FIC - P4.png`) se seleccionan desde la interfaz y se conservan localmente.

Antes de ejecutarlo, complete en el `config.json` local `coordinate_reference` con el plano, origen, ejes, unidades y, solo si se ha calibrado, `meters_per_unit`. Añada a `access_points` la posición medida de cada AP usando su `bssid_hash` de las capturas. Mantenga el archivo del plano local en la ruta configurada. En el Notebook se pueden fijar `TARGET_POINT_ID` y `TARGET_BSSID_HASH`; si quedan a `None`, se seleccionan los más representados en los datos.

Ejemplo de entrada para un AP (sustituya los valores por los medidos; las coordenadas de ejemplo no son datos reales):

```json
{
  "label": "AP1",
  "bssid_hash": "hash_de_12_caracteres",
  "plan_id": "example-plan",
  "x": 500,
  "y": 300,
  "units": "px"
}
```

La distancia solo se calcula para un AP y una captura que tengan coordenadas numéricas en el mismo plano. Si no se calibra el plano, la distancia se etiqueta en sus unidades originales (por ejemplo, píxeles), no en metros. La gráfica y el mapa no mezclan RSSI en dBm con calidad porcentual, no rellenan ausencias ni interpolan áreas sin medidas. Los registros históricos sin coordenadas permanecen en los ficheros, pero no aparecen en estos gráficos.

Para generar el gráfico de RSSI y tasa de recepción de la conexión activa, ejecute:

```cmd
python validation/generate_chart.py
```

Para representar la señal porcentual de todos los BSSID del archivo `--all`, ejecute:

```cmd
python validation/generate_chart.py --all
```

Para ver las capturas de la práctica 2 en una gráfica y centrarla en un AP concreto, use su `bssid_hash` (puede consultarlo en `data/practica2/screenshots_all.jsonl`):

```cmd
python validation/generate_chart.py --all --data-dir data/practica2 --bssid-hash HASH_DEL_BSSID
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
