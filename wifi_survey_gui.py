import math
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PROJECT_DIR = Path(__file__).resolve().parent
FLOORS = [f"P{number}" for number in range(5)]
sys.path.insert(0, str(PROJECT_DIR / "validation"))
from map_measurements import load_map_measurements


def _format_measurement(value, units):
    if value is None:
        return "—"
    return f"{value:.1f} {units}"


class SurveyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WiFi Survey - Seleccionar posición")
        self.root.geometry("1050x760")
        self.root.minsize(720, 520)
        self.plan_image = None
        self.image_path = None
        self.image_size = None
        self.selected_position = None
        self.displayed_point_position = None
        self.capture_process = None
        self.capture_position = None
        self.measured_points = {}

        self.building_var = tk.StringVar(value="FIC")
        self.floor_var = tk.StringVar(value="P1")
        self.point_var = tk.StringVar(value="P1")
        self.orientation_var = tk.StringVar(value="0-Norte")
        self.interval_var = tk.StringVar(value="3")
        self.samples_var = tk.StringVar(value="10")
        self.procedure_var = tk.StringVar()
        self.all_networks_var = tk.BooleanVar(value=False)
        self.position_text = tk.StringVar(value="Haz clic en el plano para marcar la posición.")
        self.image_text = tk.StringVar(value="No hay ningún plano cargado.")
        self.status_text = tk.StringVar(value="Selecciona la planta y carga su plano.")

        self.build_controls()
        self.floor_var.trace_add("write", self.on_floor_change)
        self.root.after(1000, self.check_capture_process)
        self.load_default_plan()

    def build_controls(self):
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Edificio").grid(row=0, column=0, sticky=tk.W, padx=(0, 4))
        ttk.Entry(controls, textvariable=self.building_var, width=12).grid(
            row=0, column=1, sticky=tk.W, padx=(0, 12)
        )
        ttk.Label(controls, text="Planta").grid(row=0, column=2, sticky=tk.W, padx=(0, 4))
        ttk.Combobox(
            controls,
            textvariable=self.floor_var,
            values=FLOORS,
            state="readonly",
            width=7,
        ).grid(row=0, column=3, sticky=tk.W, padx=(0, 8))
        ttk.Button(controls, text="Cargar plano...", command=self.choose_plan).grid(
            row=0, column=4, sticky=tk.W
        )
        ttk.Label(controls, textvariable=self.image_text).grid(
            row=0, column=5, sticky=tk.W, padx=8
        )

        ttk.Label(controls, text="Punto").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.point_var, width=12).grid(
            row=1, column=1, sticky=tk.W, pady=(8, 0), padx=(0, 12)
        )
        ttk.Label(controls, text="Orientación").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.orientation_var, width=13).grid(
            row=1, column=3, sticky=tk.W, pady=(8, 0), padx=(0, 8)
        )
        ttk.Label(controls, text="Intervalo (s)").grid(row=1, column=4, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.interval_var, width=6).grid(
            row=1, column=5, sticky=tk.W, pady=(8, 0)
        )
        ttk.Label(controls, text="Capturas").grid(row=1, column=6, sticky=tk.W, pady=(8, 0), padx=(8, 4))
        ttk.Entry(controls, textvariable=self.samples_var, width=6).grid(
            row=1, column=7, sticky=tk.W, pady=(8, 0)
        )

        ttk.Label(controls, text="Procedimiento").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.procedure_var, width=55).grid(
            row=2, column=1, columnspan=4, sticky=tk.EW, pady=(8, 0), padx=(0, 8)
        )
        ttk.Checkbutton(
            controls,
            text="Escanear todas las redes visibles (mínimo 5 s)",
            variable=self.all_networks_var,
            command=self.update_interval_hint,
        ).grid(row=2, column=5, columnspan=3, sticky=tk.W, pady=(8, 0))

        controls.columnconfigure(4, weight=0)
        controls.columnconfigure(5, weight=1)

        map_frame = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        map_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(map_frame, background="#333333", highlightthickness=0)
        horizontal = ttk.Scrollbar(map_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vertical = ttk.Scrollbar(map_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vertical.grid(row=0, column=1, sticky=tk.NS)
        horizontal.grid(row=1, column=0, sticky=tk.EW)
        map_frame.rowconfigure(0, weight=1)
        map_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.select_position)

        measurements_frame = ttk.LabelFrame(
            self.root,
            text="Mediciones del punto seleccionado",
            padding=(8, 5),
        )
        measurements_frame.pack(fill=tk.X, padx=10, pady=(8, 0))
        measurements_header = ttk.Frame(measurements_frame)
        measurements_header.pack(fill=tk.X)
        self.measurements_summary = tk.StringVar(
            value="Haz clic en uno de los marcadores del mapa para consultar sus datos."
        )
        ttk.Label(measurements_header, textvariable=self.measurements_summary).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(
            measurements_header,
            text="Medir de nuevo aquí",
            command=self.start_capture,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(
            measurements_header,
            text="Recargar datos",
            command=self.refresh_measurements,
        ).pack(side=tk.RIGHT)

        table_frame = ttk.Frame(measurements_frame)
        table_frame.pack(fill=tk.X, pady=(5, 0))
        columns = (
            "bssid", "ssid", "detections", "connected", "signal",
            "rssi", "rx", "tx", "band", "channel",
        )
        self.measurements_table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=5,
        )
        headings = {
            "bssid": ("BSSID hash", 105),
            "ssid": ("SSID", 145),
            "detections": ("Detecciones", 85),
            "connected": ("Con conexión", 90),
            "signal": ("Señal media (%)", 105),
            "rssi": ("RSSI medio (dBm)", 110),
            "rx": ("Rx medio (Mbps)", 105),
            "tx": ("Tx medio (Mbps)", 105),
            "band": ("Banda", 75),
            "channel": ("Canal", 65),
        }
        for column in columns:
            title, width = headings[column]
            self.measurements_table.heading(column, text=title)
            self.measurements_table.column(column, width=width, minwidth=55, stretch=True)
        table_scrollbar = ttk.Scrollbar(
            table_frame,
            orient=tk.VERTICAL,
            command=self.measurements_table.yview,
        )
        self.measurements_table.configure(yscrollcommand=table_scrollbar.set)
        self.measurements_table.pack(side=tk.LEFT, fill=tk.X, expand=True)
        table_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        footer = ttk.Frame(self.root, padding=10)
        footer.pack(fill=tk.X)
        ttk.Label(footer, textvariable=self.position_text).pack(anchor=tk.W)
        actions = ttk.Frame(footer)
        actions.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            actions,
            text="Iniciar capturas en posición seleccionada",
            command=self.start_capture,
        ).pack(side=tk.LEFT)
        ttk.Label(actions, textvariable=self.status_text).pack(side=tk.LEFT, padx=12)

    def default_plan_path(self):
        building = self.building_var.get().strip()
        floor = self.floor_var.get().strip()
        if not building or floor not in FLOORS:
            return None
        candidates = [
            PROJECT_DIR / f"{building} - {floor}.png",
            PROJECT_DIR / f"{building}-{floor}.png",
        ]
        return next((path for path in candidates if path.is_file()), None)

    def on_floor_change(self, *_):
        self.selected_position = None
        self.displayed_point_position = None
        self.position_text.set("Haz clic en el plano para marcar la posición.")
        self.load_default_plan()

    def load_default_plan(self):
        path = self.default_plan_path()
        if path is None:
            self.clear_plan()
            return
        self.load_plan(path)

    def choose_plan(self):
        path = filedialog.askopenfilename(
            title="Selecciona el plano de la planta",
            initialdir=str(self.image_path.parent if self.image_path else PROJECT_DIR),
            filetypes=[("Imágenes PNG", "*.png")],
        )
        if path:
            self.load_plan(Path(path))

    def load_plan(self, path):
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError as error:
            messagebox.showerror("No se pudo cargar el plano", str(error))
            return
        self.plan_image = image
        self.image_path = path.resolve()
        self.image_size = (image.width(), image.height())
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=image, anchor=tk.NW, tags=("plan",))
        self.canvas.configure(scrollregion=(0, 0, *self.image_size))
        self.image_text.set(f"{path.name} ({image.width()} x {image.height()} px)")
        self.selected_position = None
        self.displayed_point_position = None
        self.position_text.set("Haz clic en el plano para marcar la posición.")
        self.status_text.set("Plano cargado; haz clic en tu posición.")
        self.refresh_measurements()

    def clear_plan(self):
        self.canvas.delete("all")
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self.plan_image = None
        self.image_path = None
        self.image_size = None
        self.image_text.set("No se encontró el plano; pulsa «Cargar plano...»")
        self.measured_points = {}
        self.clear_measurements_table()
        self.measurements_summary.set("Carga el plano para consultar sus mediciones.")

    def clear_measurements_table(self):
        for item in self.measurements_table.get_children():
            self.measurements_table.delete(item)

    def refresh_measurements(self):
        if self.plan_image is None:
            return
        plan_id = f"{self.building_var.get().strip()}-{self.floor_var.get().strip()}"
        try:
            self.measured_points = load_map_measurements(
                PROJECT_DIR / "data" / "practica2",
                plan_id,
            )
        except (OSError, ValueError) as error:
            self.status_text.set(f"No se pudieron leer las mediciones: {error}")
            messagebox.showerror("Error al leer las mediciones", str(error))
            return

        self.canvas.delete("measurement")
        for (x, y), point in self.measured_points.items():
            marker_tag = f"point_{x}_{y}"
            self.canvas.create_oval(
                x - 9,
                y - 9,
                x + 9,
                y + 9,
                fill="#ffd43b",
                outline="#202020",
                width=2,
                tags=("measurement", marker_tag),
            )
            self.canvas.create_text(
                x + 14,
                y - 10,
                text=str(point["capture_count"]),
                fill="#ffffff",
                font=("Segoe UI", 9, "bold"),
                tags=("measurement", marker_tag),
            )
        if self.measured_points:
            self.status_text.set(
                f"{len(self.measured_points)} punto(s) medido(s) en {plan_id}. "
                "Haz clic en un marcador para ver sus redes."
            )
            if self.displayed_point_position in self.measured_points:
                self.show_measurements(
                    self.displayed_point_position,
                    self.measured_points[self.displayed_point_position],
                )
        else:
            self.displayed_point_position = None
            self.measurements_summary.set(
                f"No hay mediciones guardadas para {plan_id}. Las nuevas capturas aparecerán aquí."
            )
            self.status_text.set(
                f"No hay puntos medidos en {plan_id}; selecciona un punto para iniciar una captura."
            )

    def select_measured_point(self, position):
        point = self.measured_points.get(position)
        if point is not None:
            x, y = position
            self.selected_position = position
            self.displayed_point_position = position
            self.draw_selection_marker(position)
            self.show_measurements(position, point)
            return True
        return False

    def show_measurements(self, position, point):
        self.clear_measurements_table()
        x, y = position
        self.selected_position = position
        self.displayed_point_position = position
        if point["point_ids"]:
            self.point_var.set(point["point_ids"][-1])
        self.position_text.set(f"Posición seleccionada: x={x}, y={y} px")
        self.measurements_summary.set(
            f"Punto ({x}, {y}) px · {point['capture_count']} capturas · "
            f"{point['sessions']} sesión(es) · "
            f"{point['scan_errors']} error(es) de escaneo"
        )
        for network in point["networks"]:
            values = (
                network["bssid_hash"],
                network["ssid"],
                network["detections"],
                network["connected_captures"],
                _format_measurement(network["mean_signal_percent"], "%"),
                _format_measurement(network["mean_rssi_dbm"], "dBm"),
                _format_measurement(network["mean_rx_rate_mbps"], "Mbps"),
                _format_measurement(network["mean_tx_rate_mbps"], "Mbps"),
                network["bands"],
                network["channels"],
            )
            self.measurements_table.insert("", tk.END, values=values)
        self.status_text.set(
            "Las tasas Rx/Tx solo se muestran para el BSSID conectado; "
            "Windows no proporciona esas tasas para los AP vecinos."
        )

    def select_position(self, event):
        if self.plan_image is None:
            return
        click_x = round(self.canvas.canvasx(event.x))
        click_y = round(self.canvas.canvasy(event.y))
        width, height = self.image_size
        if not (0 <= click_x < width and 0 <= click_y < height):
            return
        nearest_point = min(
            self.measured_points,
            key=lambda position: math.hypot(position[0] - click_x, position[1] - click_y),
            default=None,
        )
        if (
            nearest_point is not None
            and math.hypot(nearest_point[0] - click_x, nearest_point[1] - click_y) <= 24
        ):
            self.select_measured_point(nearest_point)
            return

        x, y = click_x, click_y
        self.selected_position = (x, y)
        self.displayed_point_position = None
        self.point_var.set(f"{self.floor_var.get()}-{x}-{y}")
        self.draw_selection_marker((x, y))
        self.position_text.set(f"Posición seleccionada: x={x}, y={y} px")
        self.clear_measurements_table()
        self.measurements_summary.set(
            "Punto sin mediciones. Usa «Iniciar capturas en posición seleccionada» para medir aquí."
        )
        self.status_text.set("Punto nuevo seleccionado; puedes iniciar las capturas.")

    def draw_selection_marker(self, position):
        x, y = position
        self.canvas.delete("selection")
        radius = 8
        self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            outline="#ff2020",
            width=3,
            tags=("selection",),
        )
        self.canvas.create_line(
            x - radius - 4, y, x + radius + 4, y,
            fill="#ff2020", width=2, tags=("selection",),
        )
        self.canvas.create_line(
            x, y - radius - 4, x, y + radius + 4,
            fill="#ff2020", width=2, tags=("selection",),
        )

    def update_interval_hint(self):
        if self.all_networks_var.get():
            try:
                interval = int(self.interval_var.get())
            except ValueError:
                interval = 0
            if interval < 5:
                self.interval_var.set("5")

    def start_capture(self):
        if self.plan_image is None or self.selected_position is None:
            messagebox.showwarning("Falta seleccionar la posición", "Carga un plano y haz clic en tu posición.")
            return
        if self.capture_process is not None and self.capture_process.poll() is None:
            messagebox.showwarning("Captura en curso", "Ya hay una captura ejecutándose en su ventana de terminal.")
            return

        building = self.building_var.get().strip()
        floor = self.floor_var.get().strip()
        point_id = self.point_var.get().strip()
        if not building or floor not in FLOORS or not point_id:
            messagebox.showerror("Datos incompletos", "Indica el edificio, la planta y el identificador del punto.")
            return
        try:
            interval = int(self.interval_var.get())
            samples = int(self.samples_var.get())
        except ValueError:
            messagebox.showerror("Datos no válidos", "El intervalo y el número de capturas deben ser enteros.")
            return
        if interval < (5 if self.all_networks_var.get() else 1) or samples < 1:
            messagebox.showerror(
                "Datos no válidos",
                "El intervalo debe ser positivo (mínimo 5 s al escanear todas las redes) y las capturas deben ser al menos 1.",
            )
            return

        x, y = self.selected_position
        self.capture_position = self.selected_position
        self.displayed_point_position = self.selected_position
        plan_id = f"{building}-{floor}"
        command = [
            sys.executable,
            str(PROJECT_DIR / "wifi_scanner.py"),
            "--room", point_id,
            "--point-id", point_id,
            "--orientation", self.orientation_var.get().strip() or "sin especificar",
            "--interval", str(interval),
            "--samples", str(samples),
            "--dataset", "practica2",
            "--building", building,
            "--floor", floor,
            "--plan-id", plan_id,
            "--map-file", str(self.image_path),
            "--coordinate-system", "image_pixels_top_left",
            "--units", "px",
            "--origin", "top_left",
            "--x-axis", "right",
            "--y-axis", "down",
            "--x", str(x),
            "--y", str(y),
        ]
        procedure = self.procedure_var.get().strip()
        if procedure:
            command.extend(["--procedure", procedure])
        if self.all_networks_var.get():
            command.append("--all")

        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
        try:
            self.capture_process = subprocess.Popen(
                command,
                cwd=str(PROJECT_DIR),
                creationflags=creationflags,
            )
        except OSError as error:
            self.capture_position = None
            messagebox.showerror("No se pudo iniciar la captura", str(error))
            return
        self.status_text.set(
            f"Captura iniciada para {point_id} en {floor}, coordenadas ({x}, {y}) px."
        )

    def check_capture_process(self):
        if self.capture_process is not None:
            return_code = self.capture_process.poll()
            if return_code is not None:
                self.capture_process = None
                self.refresh_measurements()
                if (
                    self.capture_position is not None
                    and self.capture_position not in self.measured_points
                    and self.selected_position == self.capture_position
                ):
                    self.canvas.delete("selection")
                    self.selected_position = None
                    self.displayed_point_position = None
                    self.position_text.set("No se guardaron capturas en la posición cancelada.")
                    self.measurements_summary.set(
                        "La adquisición terminó sin guardar medidas en este punto."
                    )
                self.capture_position = None
                self.status_text.set(f"Captura finalizada (código {return_code}).")
        self.root.after(1000, self.check_capture_process)

def main():
    root = tk.Tk()
    SurveyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
