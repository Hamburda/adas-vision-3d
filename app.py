import cv2
import json
import numpy as np
import subprocess
import sys
import os
import torch
import tempfile
import shutil
import time
import logging
from datetime import datetime
from ultralytics import YOLO, RTDETR

# ============================================================
#  CONFIGURARE
# ============================================================
VIDEO_INPUT = 'video1.mp4'
FISIER_JSON = 'date_pentru_opengl.json'
FISIER_LOG  = 'istoric_decizii.log'
FOCAL_L     = 250

# ============================================================
#  LOGGING
# ============================================================
logging.basicConfig(
    filename=FISIER_LOG,
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log_decizie(risc, frana, viteza, banda, semn, detectii):
    obiecte = [
        f"{o['tip']}@{o['metri']}m({o['distanta_estimata']})"
        for o in detectii if o['distanta_estimata'] != 'semn_trafic'
    ]
    logging.info(
        f"RISC={risc.upper()} | FRANA={frana} | VITEZA={viteza} | "
        f"BANDA={banda} | SEMN={semn} | OBIECTE=[{', '.join(obiecte)}]"
    )

def scrie_json_atomic(fisier, data):
    dir_name = os.path.dirname(os.path.abspath(fisier))
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', dir=dir_name, delete=False, suffix='.tmp'
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_name = tmp.name
        shutil.move(tmp_name, fisier)
    except Exception as e:
        print(f"[WARN] JSON: {e}")

def deseneaza_label(frame, text, x, y, col):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
    cv2.rectangle(frame, (x, y - th - 5), (x + tw + 4, y + 2), (0, 0, 0), -1)
    cv2.putText(frame, text, (x + 2, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.48, col, 1, cv2.LINE_AA)


# ============================================================
#  CLASA PRINCIPALĂ
# ============================================================
class SistemMagna:

    def __init__(self):
        print("--- PAS 1: Device ---")
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"    {self.device}")
        if self.device.type == 'cuda':
            torch.backends.cudnn.benchmark = True

        print("--- PAS 2: Modele ---")
        self.model_masini = RTDETR('rtdetr-l.pt')
        self.model_masini.to(self.device)

        self.model_semne = YOLO('traffic_signs_v8.pt')
        self.model_semne.to(self.device)

        # YOLOP — doar pentru drivable area, rulat o dată la 0.5s
        try:
            self.model_yolop = torch.hub.load(
                'hustvl/yolop', 'yolop',
                pretrained=True, trust_repo=True, force_reload=False
            ).to(self.device)
        except Exception as e:
            print(f"    YOLOP retry: {e}")
            self.model_yolop = torch.hub.load(
                'hustvl/yolop', 'yolop',
                pretrained=True, trust_repo=True, force_reload=True
            ).to(self.device)
        self.model_yolop.eval()

        # State intern
        self.ultima_da       = None   # drivable area mask (0/255)
        self.ultima_ll       = None   # lane lines mask pentru render
        self.linie_st_smooth = None   # [x_jos, y_jos, x_sus, y_sus]
        self.linie_dr_smooth = None   # [x_jos, y_jos, x_sus, y_sus]
        self.prev_boxes      = {}     # {id: dist} pentru viteza relativa

        for script in ['randare.py', 'randare_3D.py']:
            if os.path.exists(script):
                subprocess.Popen([sys.executable, script])
                print(f"    Lansat: {script}")

    # ----------------------------------------------------------
    #  HOUGH LANE DETECTION
    # ----------------------------------------------------------
    def _extinde_linie_la_roi(self, x1, y1, x2, y2, y_jos, y_sus):
        """
        Extinde un segment detectat de Hough la o linie completă
        între y_jos (baza ROI) și y_sus (vârful ROI).
        Returnează [x_jos, y_jos, x_sus, y_sus] sau None dacă e orizontală.
        """
        if x2 == x1:
            return None
        panta = (y2 - y1) / (x2 - x1)
        if abs(panta) < 0.3 or abs(panta) > 2.5:
            return None
        # x = x1 + (y - y1) / panta
        xj = int(x1 + (y_jos - y1) / panta)
        xs = int(x1 + (y_sus - y1) / panta)
        return [xj, y_jos, xs, y_sus]

    def _smooth(self, noua, prev, alpha=0.80):
        """Exponential moving average între linia nouă și cea anterioară."""
        if prev is None:
            return noua
        return [int(alpha * n + (1 - alpha) * p) for n, p in zip(noua, prev)]

    def _detect_lane_hough(self, frame):
        h, w = frame.shape[:2]
        y_jos = h
        y_sus = int(h * 0.58)

        # Preprocesare
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur  = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        # ROI trapezoidal — eliminăm cerul și acostamentele extreme
        roi_pts = np.array([[
            (int(w * 0.05), y_jos),
            (int(w * 0.44), y_sus),
            (int(w * 0.56), y_sus),
            (int(w * 0.95), y_jos),
        ]], dtype=np.int32)
        masca = np.zeros_like(edges)
        cv2.fillPoly(masca, roi_pts, 255)
        edges_roi = cv2.bitwise_and(edges, masca)

        linii = cv2.HoughLinesP(
            edges_roi, rho=1, theta=np.pi / 180,
            threshold=40, minLineLength=60, maxLineGap=100
        )

        seg_st, seg_dr = [], []
        if linii is not None:
            for seg in linii:
                x1, y1, x2, y2 = seg[0]
                ext = self._extinde_linie_la_roi(x1, y1, x2, y2, y_jos, y_sus)
                if ext is None:
                    continue
                panta = (y2 - y1) / (x2 - x1) if x2 != x1 else 999
                if panta < 0:
                    seg_st.append(ext)
                else:
                    seg_dr.append(ext)

        # Media fiecărui grup de segmente extinse
        def medie(grup):
            if not grup:
                return None
            return [int(np.mean([l[i] for l in grup])) for i in range(4)]

        med_st = medie(seg_st)
        med_dr = medie(seg_dr)

        if med_st is not None:
            self.linie_st_smooth = self._smooth(med_st, self.linie_st_smooth)
        if med_dr is not None:
            self.linie_dr_smooth = self._smooth(med_dr, self.linie_dr_smooth)

        # ll_mask — liniile pentru render verde
        ll_mask = np.zeros((h, w), dtype=np.uint8)
        for ln in [self.linie_st_smooth, self.linie_dr_smooth]:
            if ln is not None:
                cv2.line(ll_mask, (ln[0], ln[1]), (ln[2], ln[3]), 255, 6)

        # ego_mask — trapez umplut între cele două linii
        # linie = [x_jos, y_jos, x_sus, y_sus]
        ego_mask = np.zeros((h, w), dtype=np.uint8)
        if self.linie_st_smooth is not None and self.linie_dr_smooth is not None:
            lst = self.linie_st_smooth
            ldr = self.linie_dr_smooth
            pts = np.array([[
                (lst[0], lst[1]),  # jos-stânga
                (ldr[0], ldr[1]),  # jos-dreapta
                (ldr[2], ldr[3]),  # sus-dreapta
                (lst[2], lst[3]),  # sus-stânga
            ]], dtype=np.int32)
            cv2.fillPoly(ego_mask, pts, 255)

        return ego_mask, ll_mask

    # ----------------------------------------------------------
    #  YOLOP — drivable area
    # ----------------------------------------------------------
    def _detect_da_yolop(self, frame):
        h, w = frame.shape[:2]
        img = cv2.resize(frame, (640, 640))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)
        img = torch.from_numpy(img).float().div(255.0).unsqueeze(0).to(self.device)
        with torch.no_grad():
            _, da_out, _ = self.model_yolop(img)
        da = torch.max(da_out, 1)[1].squeeze().cpu().numpy().astype(np.uint8)
        return cv2.resize(da, (w, h)) * 255

    # ----------------------------------------------------------
    #  LOGICĂ BANDĂ EGO — interpolăm liniile la înălțimea obiectului
    # ----------------------------------------------------------
    def _x_linie_la_y(self, linie, y_target):
        """Interpolează x-ul liniei la o înălțime dată (perspectivă corectă)."""
        xj, yj, xs, ys = linie
        if yj == ys:
            return float(xj)
        t = (y_target - yj) / (ys - yj)
        return xj + t * (xs - xj)

    def _pe_banda_ego(self, frame_w, frame_h, x1, y1, x2, y2):
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # Ignorăm obiecte în jumătatea superioară a imaginii
        if cy < frame_h * 0.38:
            return False

        # Fallback fără linii
        if self.linie_st_smooth is None or self.linie_dr_smooth is None:
            return frame_w * 0.30 < cx < frame_w * 0.70

        x_st = self._x_linie_la_y(self.linie_st_smooth, cy)
        x_dr = self._x_linie_la_y(self.linie_dr_smooth, cy)

        if x_dr <= x_st:
            return frame_w * 0.30 < cx < frame_w * 0.70

        marja = (x_dr - x_st) * 0.05
        return (x_st - marja) < cx < (x_dr + marja)

    def _risc_lateral(self, frame_w, frame_h, x1, y1, x2, y2):
        cy = (y1 + y2) / 2
        # Ignorăm obiecte sus sau prea mici (departe)
        if cy < frame_h * 0.45:
            return False
        if (x2 - x1) < frame_w * 0.10:
            return False
        # Nu e deja pe banda ego
        if self._pe_banda_ego(frame_w, frame_h, x1, y1, x2, y2):
            return False
        cx = (x1 + x2) / 2
        return frame_w * 0.05 < cx < frame_w * 0.95

    # ----------------------------------------------------------
    #  SCHIMBARE DE BANDĂ
    # ----------------------------------------------------------
    def _detecteaza_schimbare_banda(self, frame_w, frame_h):
        if self.linie_st_smooth is None or self.linie_dr_smooth is None:
            return "mentinere"

        y_ref  = frame_h - 20
        x_st   = self._x_linie_la_y(self.linie_st_smooth, y_ref)
        x_dr   = self._x_linie_la_y(self.linie_dr_smooth, y_ref)
        latime = x_dr - x_st

        if latime <= 0:
            return "mentinere"

        offset = (x_st + x_dr) / 2 - (frame_w / 2)
        prag   = latime * 0.18

        if offset > prag:
            return "schimbare_dreapta"
        elif offset < -prag:
            return "schimbare_stanga"
        return "mentinere"

    # ----------------------------------------------------------
    #  VITEZĂ RELATIVĂ
    # ----------------------------------------------------------
    def _viteza_relativa(self, obj_id, dist_curenta, dt):
        if obj_id in self.prev_boxes and dt > 0.01:
            delta = self.prev_boxes[obj_id] - dist_curenta
            return round(delta / dt * 3.6, 1)
        return 0.0

    # ----------------------------------------------------------
    #  PROCESARE FRAME
    # ----------------------------------------------------------
    def proceseaza(self, frame, dt):
        h, w = frame.shape[:2]

        # YOLOP drivable area
        da = self._detect_da_yolop(frame)

        # Hough lanes
        ego_mask, ll_mask = self._detect_lane_hough(frame)

        # Intersectăm ego cu DA → banda ego strictă pe asfalt
        self.ultima_da = cv2.bitwise_and(ego_mask, da)
        self.ultima_ll = ll_mask

        detectii = []

        # RT-DETR tracking pe GPU
        rez = self.model_masini.track(
            frame, persist=True, conf=0.4, verbose=False,
            device=self.device
        )[0]

        if rez.boxes.id is not None:
            for box, obj_id, cls in zip(
                rez.boxes.xyxy.tolist(),
                rez.boxes.id.tolist(),
                rez.boxes.cls.tolist()
            ):
                label = self.model_masini.names[int(cls)]
                if label not in ['car', 'truck', 'bus']:
                    continue

                x1, y1, x2, y2 = box
                latime = x2 - x1
                if latime < 1:
                    continue

                dim_reala = 2.5 if label != 'car' else 1.8
                dist      = dim_reala * FOCAL_L / latime
                vid       = int(obj_id)
                vrel      = self._viteza_relativa(vid, dist, dt)
                self.prev_boxes[vid] = dist

                pe_banda = self._pe_banda_ego(w, h, x1, y1, x2, y2)
                lateral  = self._risc_lateral(w, h, x1, y1, x2, y2)

                if pe_banda:
                    if dist < 8:    etich = "foarte_aproape"
                    elif dist < 20: etich = "aproape"
                    else:           etich = "departe"
                elif lateral:
                    etich = "risc_lateral"
                else:
                    etich = "ignorat_extern"

                detectii.append({
                    "id":                  vid,
                    "tip":                 label,
                    "coords":              [int(x1), int(y1), int(x2), int(y2)],
                    "metri":               round(dist, 1),
                    "distanta_estimata":   etich,
                    "viteza_relativa_kmh": vrel,
                })

        # Semne de circulație
        rez_s = self.model_semne(
            frame, conf=0.25, verbose=False, device=self.device
        )[0]
        for b in rez_s.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            latime = x2 - x1
            if latime < 1:
                continue
            detectii.append({
                "tip":                 self.model_semne.names[int(b.cls[0])],
                "coords":              [int(x1), int(y1), int(x2), int(y2)],
                "metri":               round(0.6 * FOCAL_L / latime, 1),
                "distanta_estimata":   "semn_trafic",
                "viteza_relativa_kmh": 0,
            })

        return detectii


# ============================================================
#  LOOP PRINCIPAL (OPTIMIZAT)
# ============================================================
cap = cv2.VideoCapture(VIDEO_INPUT)
if not cap.isOpened():
    print(f"EROARE: Nu pot deschide {VIDEO_INPUT}")
    sys.exit(1)


MINUTUL_DE_START = 2
secunde_start = MINUTUL_DE_START * 60
cap.set(cv2.CAP_PROP_POS_MSEC, secunde_start * 1000)

sistem    = SistemMagna()
fps_video = cap.get(cv2.CAP_PROP_FPS) or 30
timp_p    = 0.5
cadre_s   = int(fps_video * timp_p) or 15
c_curent  = 0

# --- CALCULAM DELAY-UL REAL AL VIDEOLUI ---
# Asta va opri procesorul din a rula la infinit. 
# Daca video-ul are 30fps, va astepta ~33ms intre cadre.
delay_cadru = int(1000 / fps_video) 

ultimele_det = []
st_frana  = "fara_frana"
st_risc   = "scazut"
st_viteza = "crestere"
st_banda  = "mentinere"
st_semn   = "Niciunul"

logging.info("=== START SESIUNE ===")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]

    # --- 1. BLOCUL GREU: RULEAZĂ DOAR O DATĂ LA 0.5 SECUNDE ---
    if c_curent % cadre_s == 0:
        ultimele_det = sistem.proceseaza(frame, timp_p)

        st_frana  = "fara_frana"
        st_risc   = "scazut"
        st_viteza = "crestere"
        st_semn   = "Niciunul"
        st_banda  = sistem._detecteaza_schimbare_banda(w, h)

        for o in ultimele_det:
            dist_e = o['distanta_estimata']
            semn_l = o['tip'].lower()

            if dist_e == "semn_trafic":
                st_semn = o['tip']
                if any(k in semn_l for k in ["stop", "yield", "give_way", "no_entry"]):
                    st_frana, st_risc, st_viteza = "franare_puternica", "ridicat", "scadere"
                elif any(k in semn_l for k in ["speed", "limit", "zona"]):
                    if st_frana != "franare_puternica":
                        st_frana, st_risc, st_viteza = "franare_usoara", "mediu", "scadere"
            elif dist_e == "foarte_aproape":
                st_frana, st_risc, st_viteza = "franare_puternica", "ridicat", "scadere"
            elif dist_e == "aproape":
                if st_frana != "franare_puternica":
                    st_frana, st_risc, st_viteza = "franare_usoara", "mediu", "scadere"
            elif dist_e == "risc_lateral":
                if st_risc == "scazut":
                    st_risc = "mediu"

        scrie_json_atomic(FISIER_JSON, {
            "timestamp":      datetime.now().isoformat(),
            "perceptie":      ultimele_det,
            "risc":           st_risc,
            "brake":          st_frana,
            "speed_decision": st_viteza,
            "lane_decision":  st_banda,
            "semn_activ":     st_semn,
        })
        log_decizie(st_risc, st_frana, st_viteza, st_banda, st_semn, ultimele_det)

        # --- OPTIMIZARE CPU: Pre-calculăm straturile de randare tot aici! ---
        sistem.masca_precalculata = np.zeros_like(frame)
        
        if sistem.ultima_da is not None and np.any(sistem.ultima_da > 0):
            da_clean = sistem.ultima_da.copy()
            for o in ultimele_det:
                if o['tip'] in ['car', 'truck', 'bus']:
                    x1, y1, x2, y2 = o['coords']
                    da_clean[max(0, y1):y2, max(0, x1):x2] = 0
            sistem.masca_precalculata[da_clean > 0] = [255, 100, 0] # Banda albastra
            
        if sistem.ultima_ll is not None:
            sistem.masca_precalculata[sistem.ultima_ll > 0] = [0, 230, 0] # Liniile verzi

    # --- 2. RENDER (Ultra Rapid): RULEAZĂ PE FIECARE CADRU ---

    # Aplicăm masca precalculată folosind operații vectorizate de la NumPy (foarte eficient)
    if hasattr(sistem, 'masca_precalculata'):
        # Găsim unde masca are culori
        zone_active = np.any(sistem.masca_precalculata > 0, axis=2)
        # Aplicăm transparența doar pe acele zone (evităm copierea întregii imagini)
        frame[zone_active] = cv2.addWeighted(frame, 0.72, sistem.masca_precalculata, 0.28, 0)[zone_active]

    # Bounding boxes + labels
    for o in ultimele_det:
        x1, y1, x2, y2 = o['coords']
        dist_e = o['distanta_estimata']

        if   dist_e == "foarte_aproape": col = (0,   0,   255)
        elif dist_e == "aproape":        col = (0,   165, 255)
        elif dist_e == "departe":        col = (0,   200, 0)
        elif dist_e == "risc_lateral":   col = (0,   220, 220)
        elif dist_e == "semn_trafic":    col = (255, 0,   255)
        else:                            col = (60,  60,  60)

        cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
        vrel = o.get('viteza_relativa_kmh', 0)
        txt  = f"{o['tip']} {o['metri']}m"
        if vrel != 0:
            txt += f" ({'+' if vrel > 0 else ''}{vrel}km/h)"
        deseneaza_label(frame, txt, x1, y1 - 2, col)

    # HUD
    cv2.rectangle(frame, (10, 35), (360, 195), (0, 0, 0), -1)

    c_risc = (0, 255, 0) if st_risc == "scazut" else \
             ((0, 165, 255) if st_risc == "mediu" else (0, 0, 255))

    cv2.putText(frame, f"RISC:   {st_risc.upper()}",
                (20, 65),  cv2.FONT_HERSHEY_SIMPLEX, 0.70, c_risc,          2, cv2.LINE_AA)
    cv2.putText(frame, f"FRANA:  {st_frana}",
                (20, 95),  cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"VITEZA: {st_viteza}",
                (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0,   255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"BANDA:  {st_banda}",
                (20, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 200, 0),   1, cv2.LINE_AA)
    cv2.putText(frame, f"SEMN:   {st_semn}",
                (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0,   255), 1, cv2.LINE_AA)

    cv2.imshow('Magna Pro', frame)
    
    # AICI ESTE MAGIA PENTRU PROCESOR! 
    # Fortam programul sa ia o pauza pentru a respecta FPS-ul videoului.
    if cv2.waitKey(delay_cadru) & 0xFF == ord('q'):
        break

    c_curent += 1

logging.info("=== STOP SESIUNE ===")
cap.release()
cv2.destroyAllWindows()