from ursina import *
import json
import os

# ============================================================
#  CONFIGURARE (Calibrare vizuală)
# ============================================================
FISIER_JSON = 'date_pentru_opengl.json'
LATIME_SCENA = 40    
V_WIDTH = 1280       
X_OFFSET = 320       
Z_OFFSET = 12        # <--- SCĂZUT: Vehiculele sunt acum mai aproape de tine
SMOOTHING_SPEED = 8.0 

app = Ursina()

# --- FIX MOUSE & UI ---
window.title = 'Magna 3D - Highway Edition'
window.borderless = False
window.exit_button.visible = False
window.color = color.rgb(135, 206, 235) # Cer albastru
mouse.visible = True
mouse.locked = False 

# --- LUMINI ---
DirectionalLight(y=20, rotation=(45, -45, 45))
AmbientLight(color=color.rgba(120, 120, 120, 1))

# --- DRUMUL ---
ground = Entity(model='cube', scale=(LATIME_SCENA, 0.1, 1000), y=-0.1, z=490, color=color.dark_gray)

# --- NOU: LINIILE BENZII (EGO LANE) ---
# Generăm linii albe discontinue pe o lungime de 200 de metri
LATIME_BANDA_EGO = 4.5 # Lățimea benzii tale (distanța dintre linii)
for z_pos in range(-10, 250, 8): 
    # Linia din stânga
    Entity(model='cube', color=color.white, scale=(0.15, 0.12, 4), position=(-LATIME_BANDA_EGO/2, -0.05, z_pos))
    # Linia din dreapta
    Entity(model='cube', color=color.white, scale=(0.15, 0.12, 4), position=(LATIME_BANDA_EGO/2, -0.05, z_pos))

# ============================================================
#  CONSTRUCTOR VEHICULE
# ============================================================
def construieste_vehicul(parinte, tip, culoare_baza):
    """ Construiește geometria mașinii atașată de un părinte """
    if tip in ['truck', 'bus']:
        Entity(parent=parinte, model='cube', color=culoare_baza, scale=(2.4, 2.8, 7), y=1.5, z=-1)
        Entity(parent=parinte, model='cube', color=color.gray, scale=(2.4, 2.2, 2.5), y=1.2, z=3.75)
    else:
        Entity(parent=parinte, model='cube', color=culoare_baza, scale=(1.8, 0.7, 4.2), y=0.4, z=0)
        Entity(parent=parinte, model='cube', color=color.black, scale=(1.4, 0.6, 2.2), y=1.05, z=-0.3)

# ============================================================
#  VEHICULE INITIALE
# ============================================================
ego_parent = Entity(position=(0, 0, 0))
construieste_vehicul(ego_parent, 'car', color.blue)
Text(text="EU (EGO)", parent=ego_parent, y=2.5, scale=10, origin=(0,0), color=color.cyan)

obiecte_3d = {}

# ============================================================
#  LOGICA DE UPDATE (Rulează la 60 FPS)
# ============================================================
def update():
    global V_WIDTH
    
    if os.path.exists(FISIER_JSON):
        try:
            with open(FISIER_JSON, 'r') as f:
                raw_data = f.read()
                if not raw_data: return
                data = json.loads(raw_data)
            
            perceptie = data.get("perceptie", [])
            
            ids_prezente = [str(obj.get('id', obj['tip'])) for obj in perceptie]
            for id_existent in list(obiecte_3d.keys()):
                if id_existent not in ids_prezente:
                    destroy(obiecte_3d[id_existent]["parinte"])
                    del obiecte_3d[id_existent]

            for obj in perceptie:
                obj_id = str(obj.get('id', obj['tip']))
                x1, y1, x2, y2 = obj['coords']
                dist_metri = obj['metri']
                
                if x2 > V_WIDTH: V_WIDTH = x2 
                
                # Math pentru poziția 3D
                centru_x_px = (x1 + x2) / 2
                target_x = ((centru_x_px + X_OFFSET) / V_WIDTH - 0.5) * LATIME_SCENA
                target_z = dist_metri + Z_OFFSET 

                # Construim obiect nou
                if obj_id not in obiecte_3d:
                    parinte = Entity(position=(target_x, 0, target_z))
                    culoare_initiala = color.orange if obj['tip'] in ['truck', 'bus'] else color.lime
                    
                    construieste_vehicul(parinte, obj['tip'], culoare_initiala)

                    lbl = Text(parent=parinte, text="", y=4, scale=8, origin=(0,0))
                    
                    obiecte_3d[obj_id] = {
                        "parinte": parinte,
                        "label": lbl,
                        "target_pos": Vec3(target_x, 0, target_z),
                        "tip": obj['tip']
                    }

                # Update target pt LERP
                obiecte_3d[obj_id]["target_pos"] = Vec3(target_x, 0, target_z)
                obiecte_3d[obj_id]["label"].text = f"{int(dist_metri)}m"
                
                # Vizualizare Risc
                is_danger = "foarte_aproape" in obj.get('distanta_estimata', '')
                for piesa in obiecte_3d[obj_id]["parinte"].children:
                    if isinstance(piesa, Entity) and not isinstance(piesa, Text):
                        if is_danger:
                            piesa.color = color.red
                        else:
                            piesa.color = color.orange if obiecte_3d[obj_id]["tip"] in ['truck', 'bus'] else color.lime

        except Exception as e:
            pass 

    # --- INTERPOLAREA ---
    for obj_id, info in obiecte_3d.items():
        parinte = info["parinte"]
        tinta = info["target_pos"]
        parinte.position = lerp(parinte.position, tinta, time.dt * SMOOTHING_SPEED)

# --- CONTROL CAMERA ---
def input(key):
    if key == 'scroll up': camera.z += 2
    if key == 'scroll down': camera.z -= 2
    if key == 'f': 
        mouse.locked = not mouse.locked
        mouse.visible = not mouse.locked

camera.position = (0, 18, -32)
camera.rotation_x = 22
EditorCamera() 

app.run()