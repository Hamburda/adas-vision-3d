extends Camera3D

# ============================================================
#  Controller cameră orbital — WASD + scroll zoom
# ============================================================
@export var viteza_miscare : float = 15.0
@export var viteza_rotatie : float = 0.25
@export var viteza_zoom    : float = 3.0

var _rotatie_x : float = 22.0
var _rotatie_y : float = 0.0
var _drag_activ : bool  = false
var _mouse_prev : Vector2 = Vector2.ZERO


func _ready() -> void:
	position = Vector3(0, 18, -32)
	rotation_degrees = Vector3(_rotatie_x, 180.0, 0)


func _input(event: InputEvent) -> void:
	# Click dreapta = drag rotație
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_RIGHT:
			_drag_activ = event.pressed
			_mouse_prev = event.position

		# Scroll = zoom
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			position += transform.basis.z * -viteza_zoom
		if event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			position += transform.basis.z * viteza_zoom

	if event is InputEventMouseMotion and _drag_activ:
		var delta : Vector2 = event.position - _mouse_prev
		_mouse_prev = event.position
		_rotatie_y -= delta.x * viteza_rotatie
		_rotatie_x -= delta.y * viteza_rotatie
		_rotatie_x = clamp(_rotatie_x, -80, 80)
		rotation_degrees = Vector3(_rotatie_x, _rotatie_y, 0)


func _process(delta: float) -> void:
	# WASD pentru pan
	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W): dir -= transform.basis.z
	if Input.is_key_pressed(KEY_S): dir += transform.basis.z
	if Input.is_key_pressed(KEY_A): dir -= transform.basis.x
	if Input.is_key_pressed(KEY_D): dir += transform.basis.x
	if Input.is_key_pressed(KEY_Q): dir -= transform.basis.y
	if Input.is_key_pressed(KEY_E): dir += transform.basis.y

	if dir != Vector3.ZERO:
		position += dir.normalized() * viteza_miscare * delta

	# R = reset cameră
	if Input.is_key_pressed(KEY_R):
		position = Vector3(0, 18, -32)
		_rotatie_x = 22.0
		_rotatie_y = 0.0
		rotation_degrees = Vector3(_rotatie_x, _rotatie_y, 0)
