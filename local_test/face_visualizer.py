import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
import face_recognition

# ค่าคงที่สำหรับขนาดการแสดงผลรูปภาพ
DISPLAY_SIZE = (400, 400)

class FaceVisualizer:
    def __init__(self, root):
        """
        ตั้งค่าเริ่มต้นสำหรับหน้าต่างโปรแกรมและองค์ประกอบต่างๆ
        """
        self.root = root
        self.root.title("Face Recognition Visualizer")
        self.root.geometry("850x550")

        # ตัวแปรสำหรับเก็บข้อมูลของรูปภาพและใบหน้า
        self.encoding1 = None
        self.encoding2 = None
        self.photo_image1 = None
        self.photo_image2 = None

        # ---- สร้าง Frame หลัก ----
        # Frame สำหรับแสดงรูปภาพ
        image_frame = tk.Frame(root, padx=10, pady=10)
        image_frame.pack(expand=True, fill=tk.BOTH)

        # Frame สำหรับปุ่มควบคุมและผลลัพธ์
        control_frame = tk.Frame(root, pady=10)
        control_frame.pack(fill=tk.X)

        # ---- ส่วนของรูปภาพที่ 1 (ซ้าย) ----
        frame1 = tk.Frame(image_frame, bd=2, relief=tk.GROOVE)
        frame1.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)

        self.btn1 = tk.Button(frame1, text="เลือกรูปภาพที่ 1", command=lambda: self.load_image(1))
        self.btn1.pack(pady=10)

        self.lbl_img1 = tk.Label(frame1, text="ยังไม่มีรูปภาพ", bg="lightgrey")
        self.lbl_img1.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        # ---- ส่วนของรูปภาพที่ 2 (ขวา) ----
        frame2 = tk.Frame(image_frame, bd=2, relief=tk.GROOVE)
        frame2.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH, padx=5)

        self.btn2 = tk.Button(frame2, text="เลือกรูปภาพที่ 2", command=lambda: self.load_image(2))
        self.btn2.pack(pady=10)

        self.lbl_img2 = tk.Label(frame2, text="ยังไม่มีรูปภาพ", bg="lightgrey")
        self.lbl_img2.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        # ---- ส่วนควบคุม (ล่าง) ----
        self.btn_compare = tk.Button(control_frame, text="เปรียบเทียบความเหมือน", font=("Arial", 12, "bold"), command=self.compare_faces)
        self.btn_compare.pack(pady=10)

        self.lbl_result = tk.Label(control_frame, text="ผลลัพธ์: -", font=("Arial", 14))
        self.lbl_result.pack(pady=5)

    def load_image(self, panel_num):
        """
        เปิด File Dialog เพื่อให้ผู้ใช้เลือกรูปภาพ และเรียกฟังก์ชันเพื่อประมวลผล
        """
        file_path = filedialog.askopenfilename(
            filetypes=[("Image Files", "*.jpg *.jpeg *.png"), ("All files", "*.*")]
        )
        if not file_path:
            return

        self.process_and_display_image(file_path, panel_num)

    def process_and_display_image(self, file_path, panel_num):
        """
        ประมวลผลรูปภาพ: หาใบหน้า, หา landmarks, สร้าง encoding, และวาด landmarks ลงบนรูป
        """
        try:
            # โหลดรูปภาพด้วย face_recognition
            image_data = face_recognition.load_image_file(file_path)

            # ค้นหาตำแหน่งใบหน้า, landmarks และ encodings
            face_locations = face_recognition.face_locations(image_data)
            face_landmarks_list = face_recognition.face_landmarks(image_data, face_locations)
            face_encodings = face_recognition.face_encodings(image_data, face_locations)

            if not face_encodings:
                messagebox.showwarning("ไม่พบใบหน้า", "ไม่สามารถตรวจจับใบหน้าในรูปภาพที่เลือกได้")
                return

            # ใช้ใบหน้าแรกที่เจอเท่านั้น
            current_encoding = face_encodings[0]

            # โหลดรูปภาพด้วย Pillow เพื่อวาด landmarks
            pil_image = Image.open(file_path).convert("RGB")
            draw = ImageDraw.Draw(pil_image)

            # วาดจุด landmarks ลงบนใบหน้า
            for face_landmarks in face_landmarks_list:
                for facial_feature in face_landmarks.keys():
                    # วาดจุดเล็กๆ (ellipse) บนแต่ละตำแหน่ง
                    for point in face_landmarks[facial_feature]:
                         draw.ellipse([point[0]-2, point[1]-2, point[0]+2, point[1]+2], fill='white', outline='white')

            # ย่อขนาดรูปภาพเพื่อแสดงผล
            pil_image.thumbnail(DISPLAY_SIZE, Image.LANCZOS)
            photo_image = ImageTk.PhotoImage(pil_image)

            # แสดงผลและเก็บข้อมูลตาม panel ที่เลือก
            if panel_num == 1:
                self.lbl_img1.config(image=photo_image, text="")
                self.photo_image1 = photo_image  # สำคัญ: ต้องเก็บ reference ไว้
                self.encoding1 = current_encoding
            else:
                self.lbl_img2.config(image=photo_image, text="")
                self.photo_image2 = photo_image  # สำคัญ: ต้องเก็บ reference ไว้
                self.encoding2 = current_encoding
            
            # เมื่อมีการเลือกรูปใหม่ ให้รีเซ็ตผลลัพธ์
            self.lbl_result.config(text="ผลลัพธ์: -")

        except Exception as e:
            messagebox.showerror("เกิดข้อผิดพลาด", f"ไม่สามารถโหลดหรือประมวลผลรูปภาพได้:\n{e}")

    def compare_faces(self):
        """
        เปรียบเทียบ face encodings ทั้งสองและแสดงผลเป็นเปอร์เซ็นต์
        """
        if self.encoding1 is None or self.encoding2 is None:
            messagebox.showinfo("ข้อมูลไม่ครบ", "กรุณาเลือกรูปภาพทั้งสองรูปก่อนทำการเปรียบเทียบ")
            return

        # face_distance จะคืนค่าความแตกต่าง (0.0 คือเหมือนที่สุด)
        # เราจะใช้ค่านี้กับ array ของ encoding แรก
        distance = face_recognition.face_distance([self.encoding1], self.encoding2)
        
        # แปลงค่า distance (0.0 - 1.0+) เป็น %ความเหมือน (100% - 0%)
        # โดยทั่วไป ค่า distance < 0.6 ถือว่าเป็นคนเดียวกัน
        similarity = (1.0 - distance[0]) * 100
        
        # ป้องกันไม่ให้ค่าติดลบ หากใบหน้าต่างกันมาก
        if similarity < 0:
            similarity = 0

        result_text = f"ผลลัพธ์: มีความเหมือนกัน {similarity:.2f}%"
        self.lbl_result.config(text=result_text)


if __name__ == "__main__":
    root = tk.Tk()
    app = FaceVisualizer(root)
    root.mainloop()