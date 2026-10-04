# WiFi Coverage Survey Tool (Windows)

[English](README.md) | [Español](README.es.md)

Herramienta de línea de comandos para consultar y registrar la conexión WiFi activa y, opcionalmente, las redes visibles. Cada captura incluye una marca temporal y etiquetas de campaña y ubicación para su análisis posterior. Nombre sugerido para el repositorio: `wifi-coverage-survey`.

## 1. Entorno y requisitos

* **Sistema operativo probado:** Windows 11.
* **Equipo de prueba:** Lenovo LOQ 15 con adaptador WiFi MediaTek MT7921.
* **Intérprete:** Python 3.8 o posterior. La versión comprobada en el equipo de prueba es Python 3.14.6.
* **Utilidades del sistema:** `netsh.exe` y la API WLAN nativa de Windows.
* **Dependencias:** `wifi_scanner.py` utiliza la biblioteca estándar de Python. Para generar gráficos, instale `matplotlib`:

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

Instale `matplotlib` únicamente si desea generar los gráficos. Los archivos que se mantienen en el repositorio son:

* `wifi_scanner.py`: adquisición, etiquetado y almacenamiento de capturas.
* `config.example.json`: plantilla sin identificadores personales.
* `validation/generate_chart.py`: generación de gráficos a partir de los datos.

El archivo `.gitignore` excluye la configuración local, las capturas JSONL, la memoria técnica, las imágenes y el script del plano, ya que pueden contener SSID, ubicaciones o detalles de la vivienda. El recolector crea `data/` al ejecutarse.

## 3. Configuración

El recolector carga `config.json` al iniciarse. En la configuración de ejemplo se utilizan estos campos:

* `device_id`: identificador del equipo de medida.
* `default_campaign`: identificador de la campaña.
* `building` y `floor`: edificio y planta.
* `default_interval`: intervalo solicitado entre capturas, en segundos.
* `default_samples`: número de capturas por ejecución.

Las opciones `--room`, `--orientation`, `--interval` y `--samples` permiten indicar esos valores para una ejecución concreta. El intervalo representa la espera solicitada entre capturas, no garantiza por sí solo el tiempo real entre marcas temporales.

## 4. Adquisición

### Conexión activa

Para iniciar el recolector con los valores predeterminados, ejecute:

```cmd
python wifi_scanner.py
```

Para especificar las etiquetas y la cadencia directamente, ejecute, por ejemplo:

```cmd
python wifi_scanner.py --room "Sala de pruebas" --orientation "0-Norte" --interval 3 --samples 10
```

Este modo consulta la conexión activa y guarda únicamente el punto de acceso conectado en `data/screenshots.jsonl`. Las capturas se añaden al final del archivo; una ejecución nueva no elimina las anteriores.

### Todas las redes visibles

Para solicitar un escaneo nuevo de Windows y registrar las redes detectadas, añada `--all`:

```cmd
python wifi_scanner.py --room "Sala de pruebas" --orientation "0-Norte" --interval 5 --samples 10 --all
```

El modo `--all` guarda sus registros por separado en `data/screenshots_all.jsonl`. Su intervalo mínimo es de 5 segundos: si el valor indicado en la línea de comandos o en `config.json` es menor, el recolector lo eleva a 5 segundos y lo comunica. El escaneo añade aproximadamente 4 segundos más por captura; por tanto, el tiempo real entre capturas será superior al intervalo configurado. Consulte `timestamp_utc` para conocer la cadencia observada.

### Parada

Para detener la adquisición, pulse `Ctrl+C` en la terminal. Cada registro se escribe antes de esperar a la siguiente captura, por lo que las medidas ya guardadas se conservan.

## 5. Formato de los datos

Los dos archivos de datos utilizan JSON Lines (JSONL): cada línea es un objeto JSON independiente. Se pueden abrir con un editor de texto o procesar desde otros programas.

Los registros actuales contienen los siguientes campos principales:

* `metadata`: `timestamp_utc`, `device_id`, `campaign`, `building`, `floor`, `room`, `orientation` y `network_scope`.
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

Para generar el gráfico de RSSI y tasa de recepción de la conexión activa, ejecute:

```cmd
python validation/generate_chart.py
```

Para representar la señal porcentual de todos los BSSID del archivo `--all`, ejecute:

```cmd
python validation/generate_chart.py --all
```

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
