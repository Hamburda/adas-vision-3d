import torch
import cv2
import numpy as np

def preprocess_frame(frame):
    # Redimensionăm la dimensiunea acceptată de model
    img = cv2.resize(frame, (640, 640))
    # Convertim din BGR (OpenCV) în RGB
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    # Mutăm canalele de culoare: din (H, W, C) în (C, H, W)
    img = img.transpose(2, 0, 1)
    # Transformăm în tensor și normalizăm (0-1)
    img = torch.from_numpy(img).float() / 255.0
    # Adăugăm dimensiunea de batch -> [1, 3, 640, 640]
    img = img.unsqueeze(0)
    return img

def main():
    video_path = r"video1.mp4"
    
    print("Se descarcă și se configurează modelul automat... (Necesită net prima dată)")
    # PyTorch Hub face toată munca grea de a lega arhitectura de model!
    model = torch.hub.load('hustvl/yolop', 'yolop', pretrained=True)
    model.eval() # Mod de testare, nu antrenare
    
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print("Eroare: Nu s-a putut deschide videoclipul.")
        return

    print("Model încărcat cu succes! Apasă 'q' pentru a închide.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # 1. Preprocesare
        tensor_img = preprocess_frame(frame)
        
        # 2. Inferență (Procesarea imaginii)
        with torch.no_grad():
            # YOLOP dă 3 rezultate: cutii mașini, zonă carosabilă și benzi. Pe noi ne interesează ultimul.
            _, _, lane_seg_out = model(tensor_img)
            
        # 3. Postprocesare (Transformăm probabilitățile modelului în mască de pixeli)
        # Extragem pixelii unde modelul este sigur că există o bandă (clasa 1 din tensor)
        lane_mask = torch.max(lane_seg_out, 1)[1].squeeze().cpu().numpy()
        
        # Redimensionăm masca benzilor înapoi la dimensiunea originală a videoclipului
        h, w = frame.shape[:2]
        lane_mask_resized = cv2.resize(lane_mask.astype(np.uint8), (w, h))
        
        # 4. Desenăm rezultatul pe videoclip
        # Colorăm toți pixelii identificați ca benzi într-un verde neon [0, 255, 0]
        frame[lane_mask_resized == 1] = [0, 255, 0]
        
        cv2.imshow('Detectie Benzi - YOLOP', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()