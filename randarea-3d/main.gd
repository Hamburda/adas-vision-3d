extends Node3D

# ============================================================
#  CONFIGURARE — schimbă doar astea dacă ceva nu arată bine
# ============================================================
const FISIER_JSON     := "../date_pentru_opengl.json"  # Calea către JSON (relativ la proiect)
const LATIME_SCENA    := 50.0   # Lățimea totală a scenei în metri
const X_OFFSET        := 300.0  # Offset calibrare laterală (din codul original)
const V_WIDTH         := 1280.0 # Lățimea frame-ului video original
const Z_OFFSET        := 10.0   # Cât de aproape apar mașinile față de EGO
const SMOOTHING_SPEED := 6.0    # Viteza de interpolare (mai mare = mai rapid)
const INTERVAL_JSON   := 0.1    # Cât de des citim JSON-ul (secunde)

# ============================================================
#  REFERINȚE NODE-URI (setate automat în _ready)
# ============================================================
var vehicle_container : Node3D
var timer_json        : Timer

# Dicționar: id_obiect -> { "node": Node3D, "target": Vector3, "tip": String }
var obiecte_3d := {}

# ============================================================
#  MATERIALE PRE-CALCULATE
# ============================================================
var mat_masina_verde  : StandardMaterial3D
var mat_masina_rosu   : StandardMaterial3D
var mat_masina_gri    : StandardMaterial3D
var mat_camion        : StandardMaterial3D
var mat_geam          : StandardMaterial3D
var mat_far_galben    : StandardMaterial3D
var mat_stop_rosu     : StandardMaterial3D
var mat_roata         : StandardMaterial3D
var mat_janta         : StandardMaterial3D

# ============================================================
#  UI (Label-uri — setate din editor sau găsite automat)
# ============================================================
var lbl_risc     : Label
var lbl_brake    : Label
var lbl_speed    : Label
var lbl_lane     : Label
var lbl_semn     : Label
var lbl_obiecte  : Label
var indicator_risc : ColorRect


func _ready() -> void:
	_creeaza_materiale()
	_construieste_scena()
	_construieste_ui()
	_construieste_ego_car()

	# Timer pentru citire JSON
	timer_json = Timer.new()
	timer_json.wait_time = INTERVAL_JSON
	timer_json.autostart = true
	timer_json.timeout.connect(_citeste_json)
	add_child(timer_json)


# ============================================================
#  MATERIALE
# ============================================================
func _creeaza_materiale() -> void:
	mat_masina_verde = _mat(Color(0.08, 0.78, 0.35))
	mat_masina_rosu  = _mat(Color(1.0,  0.12, 0.12))
	mat_masina_gri   = _mat(Color(0.40, 0.42, 0.48))
	mat_camion       = _mat(Color(1.0,  0.50, 0.05))
	mat_geam         = _mat(Color(0.35, 0.60, 0.85), 0.35)  # semi-transparent
	mat_far_galben   = _mat(Color(1.0,  0.98, 0.55), 1.0, true)  # emissive
	mat_stop_rosu    = _mat(Color(0.9,  0.08, 0.08), 1.0, true)
	mat_roata        = _mat(Color(0.07, 0.07, 0.07))
	mat_janta        = _mat(Color(0.72, 0.74, 0.76))


func _mat(col: Color, alpha: float = 1.0, emissive: bool = false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	if alpha < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.albedo_color.a = alpha
	if emissive:
		m.emission_enabled = true
		m.emission = col
		m.emission_energy_multiplier = 2.0
	m.roughness = 0.55
	m.metallic  = 0.15
	return m


# ============================================================
#  CONSTRUIRE SCENĂ (drum, cer, lumini)
# ============================================================
func _construieste_scena() -> void:
	# --- Lumini ---
	var soare := DirectionalLight3D.new()
	soare.rotation_degrees = Vector3(-45, 30, 0)
	soare.light_color = Color(1.0, 0.95, 0.80)
	soare.light_energy = 1.4
	soare.shadow_enabled = true
	add_child(soare)

	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, -150, 0)
	fill.light_color = Color(0.30, 0.40, 0.70)
	fill.light_energy = 0.5
	add_child(fill)

	# --- Mediu (cer + fog) ---
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.04, 0.07, 0.20)
	env.ambient_light_color = Color(0.15, 0.18, 0.30)
	env.ambient_light_energy = 0.8
	env.fog_enabled = true
	env.fog_light_color = Color(0.10, 0.10, 0.22)
	env.fog_density = 0.008
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.glow_enabled = true
	env.glow_intensity = 0.4

	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	# --- Drum principal ---
	var latime_drum := 3 * 4.2 + 2.0
	_box(Vector3(0, -0.05, 150), Vector3(latime_drum, 0.10, 300),
		 _mat(Color(0.11, 0.12, 0.14)))

	# --- Iarbă laterală ---
	for s in [-1, 1]:
		_box(Vector3(s * (latime_drum / 2 + 18), -0.06, 150),
			 Vector3(36, 0.06, 300), _mat(Color(0.07, 0.17, 0.07)))

	# --- Borduri beton ---
	for s in [-1, 1]:
		_box(Vector3(s * (latime_drum / 2 + 0.3), 0.08, 150),
			 Vector3(0.55, 0.28, 300), _mat(Color(0.33, 0.34, 0.36)))

	# --- Linii benzi albe ---
	for banda in range(-1, 3):
		var x_linie := -latime_drum / 2 + (banda + 1) * 4.2
		for z in range(-10, 290, 10):
			_box(Vector3(x_linie, 0.01, z), Vector3(0.12, 0.04, 5.5),
				 _mat(Color(0.85, 0.85, 0.85)))

	# --- Linie centrală dublă galbenă ---
	var mat_galben := _mat(Color(1.0, 0.80, 0.05))
	for z in range(-10, 290):
		_box(Vector3(-0.20, 0.01, z), Vector3(0.10, 0.04, 0.7), mat_galben)
		_box(Vector3( 0.20, 0.01, z), Vector3(0.10, 0.04, 0.7), mat_galben)

	# --- Garduri metalice + stâlpi iluminat ---
	var mat_metal := _mat(Color(0.65, 0.67, 0.70))
	var mat_glob  := _mat(Color(1.0, 0.95, 0.70), 1.0, true)
	for s in [-1, 1]:
		var gx : float = s * (latime_drum / 2 + 0.7)
		# Șina continuă
		_box(Vector3(gx, 0.50, 150), Vector3(0.06, 0.08, 300), mat_metal)
		for z in range(-10, 290, 10):
			_box(Vector3(gx, 0.28, z), Vector3(0.12, 0.58, 0.12), mat_metal)
		# Stâlpi iluminat
		for z in range(15, 280, 35):
			var lx : float = s * (latime_drum / 2 + 3.0)
			_box(Vector3(lx, 4.0, z), Vector3(0.14, 8.0, 0.14), mat_metal)
			_box(Vector3(lx - s * 1.3, 7.9, z), Vector3(2.5, 0.09, 0.09), mat_metal)
			_sphere(Vector3(lx - s * 2.5, 7.85, z), 0.22, mat_glob)

	# Container vehicule detectate
	vehicle_container = Node3D.new()
	vehicle_container.name = "VehicleContainer"
	add_child(vehicle_container)


# ============================================================
#  EGO CAR
# ============================================================
func _construieste_ego_car() -> void:
	var ego := Node3D.new()
	ego.name = "EgoCar"
	add_child(ego)
	_construieste_vehicul(ego, "car", _mat(Color(0.06, 0.30, 0.85)))

	# Label "EGO" deasupra
	var lbl := Label3D.new()
	lbl.text = "EGO"
	lbl.position = Vector3(0, 3.2, 0)
	lbl.font_size = 48
	lbl.modulate = Color(0.3, 0.9, 1.0)
	lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lbl.no_depth_test = true
	ego.add_child(lbl)


# ============================================================
#  CONSTRUCTOR VEHICUL
# ============================================================
func _construieste_vehicul(parinte: Node3D, tip: String, mat_corp: StandardMaterial3D) -> void:
	if tip in ["truck", "bus"]:
		_box_child(parinte, Vector3(0, 1.3, 2.2),  Vector3(2.5, 2.5, 3.0), mat_corp)
		_box_child(parinte, Vector3(0, 1.75, 0.75), Vector3(2.1, 1.3, 0.1), mat_geam)
		_box_child(parinte, Vector3(0, 1.5, -2.5),  Vector3(2.4, 2.8, 8.0), mat_corp)
		for rx in [-1.3, 1.3]:
			for rz in [-4.0, -1.0, 2.0]:
				_box_child(parinte, Vector3(rx, 0.35, rz), Vector3(0.42, 0.62, 0.42), mat_roata)
	else:
		# Caroserie
		_box_child(parinte, Vector3(0, 0.38, 0),    Vector3(1.85, 0.65, 4.3), mat_corp)
		# Habitaclu
		_box_child(parinte, Vector3(0, 1.0, -0.1),  Vector3(1.55, 0.58, 2.3), mat_corp)
		# Geamuri
		_box_child(parinte, Vector3(0, 0.93, 1.21),  Vector3(1.5, 0.48, 0.08), mat_geam)
		_box_child(parinte, Vector3(0, 0.93, -1.26), Vector3(1.5, 0.42, 0.08), mat_geam)
		# Faruri + stopuri
		for fx in [-0.78, 0.78]:
			_box_child(parinte, Vector3(fx, 0.50,  2.18), Vector3(0.28, 0.13, 0.07), mat_far_galben)
			_box_child(parinte, Vector3(fx, 0.50, -2.18), Vector3(0.28, 0.13, 0.07), mat_stop_rosu)
		# Roți
		for rx in [-0.98, 0.98]:
			for rz in [-1.35, 1.35]:
				_box_child(parinte, Vector3(rx, 0.26, rz), Vector3(0.36, 0.55, 0.36), mat_roata)
				_box_child(parinte, Vector3(rx, 0.26, rz), Vector3(0.22, 0.56, 0.22), mat_janta)


# ============================================================
#  CITIRE JSON
# ============================================================
func _citeste_json() -> void:
	var path := "res://" + FISIER_JSON
	if not FileAccess.file_exists(path):
		# Încearcă și calea absolută (lângă executabil)
		path = OS.get_executable_path().get_base_dir() + "/" + FISIER_JSON
		if not FileAccess.file_exists(path):
			return

	var f := FileAccess.open(path, FileAccess.READ)
	if not f:
		return
	var text := f.get_as_text()
	f.close()

	var json := JSON.new()
	if json.parse(text) != OK:
		return
	var data : Dictionary = json.get_data()

	var perceptie : Array = data.get("perceptie", [])

	# UI
	lbl_risc.text    = "RISC: "    + str(data.get("risc", "--")).to_upper()
	lbl_brake.text   = "FRANARE: " + str(data.get("brake", "--"))
	lbl_speed.text   = "VITEZA: "  + str(data.get("speed_decision", "--"))
	lbl_lane.text    = "BANDA: "   + str(data.get("lane_decision", "--"))
	lbl_semn.text    = "SEMN: "    + str(data.get("semn_activ", "--"))
	lbl_obiecte.text = "OBIECTE: " + str(perceptie.size())

	var risc_str : String = str(data.get("risc", "")).to_upper()
	if risc_str in ["RIDICAT", "CRITIC"]:
		indicator_risc.color = Color(1.0, 0.15, 0.15)
		lbl_risc.add_theme_color_override("font_color", Color(1.0, 0.4, 0.4))
	elif risc_str == "MEDIU":
		indicator_risc.color = Color(1.0, 0.63, 0.0)
		lbl_risc.add_theme_color_override("font_color", Color(1.0, 0.70, 0.2))
	else:
		indicator_risc.color = Color(0.15, 0.85, 0.40)
		lbl_risc.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0))

	# Stergere obiecte disparute
	var ids_prezente : Array = []
	for obj in perceptie:
		ids_prezente.append(str(obj.get("id", obj["tip"])))

	for id_ex in obiecte_3d.keys():
		if id_ex not in ids_prezente:
			obiecte_3d[id_ex]["node"].queue_free()
			obiecte_3d.erase(id_ex)

	# Creare / update obiecte
	for obj in perceptie:
		var obj_id    : String = str(obj.get("id", obj["tip"]))
		var coords    : Array  = obj["coords"]
		var dist_m    : float  = float(obj["metri"])
		var dist_cat  : String = str(obj.get("distanta_estimata", ""))
		var viteza_r  : float  = float(obj.get("viteza_relativa_kmh", 0))
		var tip       : String = str(obj["tip"])

		var cx := (float(coords[0]) + float(coords[2])) / 2.0
		var target_x := ((cx + X_OFFSET) / V_WIDTH - 0.5) * LATIME_SCENA
		var target_z := dist_m + Z_OFFSET
		var target_pos := Vector3(target_x, 0, target_z)

		var is_danger  := "foarte_aproape" in dist_cat or "risc" in dist_cat
		var is_ignorat := "ignorat" in dist_cat

		var mat_corp : StandardMaterial3D
		if is_danger:
			mat_corp = mat_masina_rosu
		elif is_ignorat:
			mat_corp = mat_masina_gri
		elif tip in ["truck", "bus"]:
			mat_corp = mat_camion
		else:
			mat_corp = mat_masina_verde

		if obj_id not in obiecte_3d:
			var nod := Node3D.new()
			nod.position = target_pos
			vehicle_container.add_child(nod)
			_construieste_vehicul(nod, tip, mat_corp)

			# Label distanță
			var lbl := Label3D.new()
			lbl.position = Vector3(0, 3.4, 0)
			lbl.font_size = 42
			lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			lbl.no_depth_test = true
			nod.add_child(lbl)

			obiecte_3d[obj_id] = {
				"node":   nod,
				"label":  lbl,
				"target": target_pos,
				"tip":    tip
			}

		obiecte_3d[obj_id]["target"] = target_pos

		var v_str := " %+.1f km/h" % viteza_r if viteza_r != 0 else ""
		var lbl3d : Label3D = obiecte_3d[obj_id]["label"]
		lbl3d.text = "%dm%s" % [int(dist_m), v_str]

		if is_danger:
			lbl3d.modulate = Color(1.0, 0.4, 0.4)
		elif is_ignorat:
			lbl3d.modulate = Color(0.6, 0.6, 0.65)
		else:
			lbl3d.modulate = Color(0.3, 1.0, 0.55)


# ============================================================
#  PROCESS — interpolare smoothă
# ============================================================
func _process(delta: float) -> void:
	for obj_id in obiecte_3d:
		var info   : Dictionary = obiecte_3d[obj_id]
		var nod    : Node3D     = info["node"]
		var tinta  : Vector3    = info["target"]
		nod.position = nod.position.lerp(tinta, delta * SMOOTHING_SPEED)


# ============================================================
#  CONSTRUIRE UI
# ============================================================
func _construieste_ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)

	# Panel background
	var panel := PanelContainer.new()
	panel.position = Vector2(20, 20)
	panel.custom_minimum_size = Vector2(280, 0)

	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.02, 0.04, 0.12, 0.88)
	style.border_color = Color(0.0, 0.70, 1.0, 0.90)
	style.set_border_width_all(2)
	style.set_corner_radius_all(6)
	style.content_margin_left   = 14
	style.content_margin_right  = 14
	style.content_margin_top    = 12
	style.content_margin_bottom = 12
	panel.add_theme_stylebox_override("panel", style)
	canvas.add_child(panel)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 6)
	panel.add_child(vbox)

	# Titlu
	var titlu := Label.new()
	titlu.text = "ADAS VISION 3D"
	titlu.add_theme_color_override("font_color", Color(0.0, 0.78, 1.0))
	titlu.add_theme_font_size_override("font_size", 15)
	vbox.add_child(titlu)

	# Separator
	var sep := HSeparator.new()
	var sep_style := StyleBoxFlat.new()
	sep_style.bg_color = Color(0.0, 0.70, 1.0, 0.5)
	sep_style.content_margin_top = 1
	sep.add_theme_stylebox_override("separator", sep_style)
	vbox.add_child(sep)

	# Rând RISC cu indicator colorat
	var risc_row := HBoxContainer.new()
	risc_row.add_theme_constant_override("separation", 8)
	vbox.add_child(risc_row)

	indicator_risc = ColorRect.new()
	indicator_risc.custom_minimum_size = Vector2(12, 12)
	indicator_risc.color = Color(0.15, 0.85, 0.40)
	# Centrat vertical
	var risc_center := CenterContainer.new()
	risc_center.custom_minimum_size = Vector2(12, 20)
	risc_center.add_child(indicator_risc)
	risc_row.add_child(risc_center)

	lbl_risc = _make_label("RISC: --")
	risc_row.add_child(lbl_risc)

	# Restul label-urilor
	lbl_brake   = _make_label("FRANARE: --")
	lbl_speed   = _make_label("VITEZA: --")
	lbl_lane    = _make_label("BANDA: --")
	lbl_semn    = _make_label("SEMN: --", Color(1.0, 0.90, 0.20))
	lbl_obiecte = _make_label("OBIECTE: 0")

	for lbl in [lbl_brake, lbl_speed, lbl_lane, lbl_semn, lbl_obiecte]:
		vbox.add_child(lbl)

	# Help text jos
	var help := Label.new()
	help.text = "W/S/A/D - camera   Q/E - sus/jos   Scroll - zoom"
	help.add_theme_color_override("font_color", Color(0.5, 0.6, 0.7, 0.7))
	help.add_theme_font_size_override("font_size", 11)
	help.position = Vector2(20, 0)
	help.anchor_top = 1.0
	help.anchor_bottom = 1.0
	help.offset_top = -30
	help.offset_bottom = -8
	canvas.add_child(help)


func _make_label(text_val: String, col: Color = Color.WHITE) -> Label:
	var l := Label.new()
	l.text = text_val
	l.add_theme_color_override("font_color", col)
	l.add_theme_font_size_override("font_size", 13)
	return l


# ============================================================
#  HELPER — creare mesh-uri simple
# ============================================================
func _box(pos: Vector3, size: Vector3, mat: StandardMaterial3D) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	add_child(mi)
	return mi


func _box_child(parinte: Node3D, pos: Vector3, size: Vector3, mat: StandardMaterial3D) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	parinte.add_child(mi)
	return mi


func _sphere(pos: Vector3, radius: float, mat: StandardMaterial3D) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	add_child(mi)
	return mi
