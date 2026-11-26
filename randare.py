import cv2
import json
import numpy as np
import os

# --- SETĂRI VIZUALE ---
LATIME_HARTA = 600
INALTIME_HARTA = 800
SCALA_PIXELI_METRU = 15  
FISIER_JSON = 'date_pentru_opengl.json'

# --- PARAMETRI CALIBRARE LATERALĂ ---
# Crește această valoare pentru a muta toate obiectele mai la DREAPTA
OFFSET_DREAPTA = 300  # Încearcă valori între 100 și 400
SENSIBILITATE_X = 15   # Divizorul pentru mișcarea laterală

def randeaza_2d():
    canvas = np.zeros((INALTIME_HARTA, LATIME_HARTA, 3), dtype=np.uint8)
    
    # Pozitia masinii noastre (Ego Car) - Centru Jos
    ego_x = LATIME_HARTA // 2
    ego_y = INALTIME_HARTA - 50

    while True:
        # Reset fundal (Gri foarte închis)
        canvas[:, :] = (15, 15, 15)
        
        # Desenăm limitele drumului (opțional, pentru context vizual)
        cv2.line(canvas, (ego_x - 100, 0), (ego_x - 100, INALTIME_HARTA), (40, 40, 40), 2)
        cv2.line(canvas, (ego_x + 100, 0), (ego_x + 100, INALTIME_HARTA), (40, 40, 40), 2)

        # Desenăm mașina noastră (Triunghi Albastru)
        puncte_ego = np.array([[ego_x, ego_y], [ego_x - 12, ego_y + 25], [ego_x + 12, ego_y + 25]])
        cv2.drawContours(canvas, [puncte_ego], 0, (255, 120, 0), -1)
        cv2.putText(canvas, "EGO", (ego_x - 15, ego_y + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        if os.path.exists(FISIER_JSON):
            try:
                with open(FISIER_JSON, 'r') as f:
                    data = json.load(f)
                
                perceptie = data.get("perceptie", [])
                viteza_ego = data.get("viteza", 0)

                cv2.putText(canvas, f"RADAR 2D - {int(viteza_ego)} km/h", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                for obj in perceptie:
                    dist_z = obj['metri']
                    # Poziția Y (Adâncimea)
                    pos_y = ego_y - int(dist_z * SCALA_PIXELI_METRU)

                    # --- CALCUL POZIȚIE X CU OFFSET ---
                    x1, y1, x2, y2 = obj['coords']
                    centru_obj_x = (x1 + x2) / 2
                    
                    # Logica: (Poziția pixelului + Offset-ul de calibrare - Centrul teoretic)
                    # Ajustăm 550 ca punct de referință pentru a forța deplasarea la dreapta
                    offset_lateral = (centru_obj_x + OFFSET_DREAPTA - 640) / SENSIBILITATE_X
                    pos_x = ego_x + int(offset_lateral * (SCALA_PIXELI_METRU / 2))

                    # Setări vizuale în funcție de tip
                    if obj['tip'] in ['truck', 'bus']:
                        w, h = 40, 80
                        culoare = (0, 165, 255) # Portocaliu
                    elif obj['tip'] == 'car':
                        w, h = 25, 45
                        culoare = (0, 255, 0)   # Verde
                    else:
                        w, h = 15, 15
                        culoare = (255, 0, 255) # Roz (Semne/Altele)

                    # Schimbăm în ROȘU dacă e critic (foarte aproape)
                    if "foarte_aproape" in obj.get('distanta_estimata', ''):
                        culoare = (0, 0, 255)

                    # Randare obiect dacă este în fața mașinii
                    if 0 < pos_y < INALTIME_HARTA:
                        # Corpul obiectului
                        cv2.rectangle(canvas, (pos_x - w//2, pos_y - h//2), (pos_x + w//2, pos_y + h//2), culoare, -1)
                        # Contur obiect (pentru vizibilitate)
                        cv2.rectangle(canvas, (pos_x - w//2, pos_y - h//2), (pos_x + w//2, pos_y + h//2), (255,255,255), 1)
                        # Text distanță
                        cv2.putText(canvas, f"{int(dist_z)}m", (pos_x - 15, pos_y - h//2 - 5), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            except:
                pass

        cv2.imshow('Radar 2D - Perceptie Magna', canvas)
        
        # Frecvența de 0.1 secunde conform cerinței
        if cv2.waitKey(100) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    randeaza_2d()