import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import face_recognition
import sqlite3
import numpy as np
import os

# --- ค่าคงที่ (เหมือนเดิม) ---
DB_FILE = "face_encodings.db"
RESULT_IMAGE_DISPLAY_SIZE = (150, 150)
MATCH_THRESHOLD = 0.5

class GuestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ค้นหารูปภาพของคุณจากในงาน")
        self.root.geometry("500x400")

        self.uploaded_images_data = [] # ใช้ List เก็บข้อมูลรูปที่อัปโหลด

        # --- เฟรมหลัก ---
        main_frame = tk.Frame(root, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- ส่วนแสดงรูปที่อัปโหลด ---
        upload_frame = tk.LabelFrame(main_frame, text="รูปเซลฟี่ของคุณ (อัปโหลดได้ 1-3 รูป)", padx=10, pady=10)
        upload_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        self.thumb_frame = tk.Frame(upload_frame) # Frame สำหรับวาง Thumbnail
        self.thumb_frame.pack()

        # --- ส่วนปุ่มควบคุม ---
        control_frame = tk.Frame(main_frame)
        control_frame.pack(pady=10, fill=tk.X)

        btn_upload = tk.Button(control_frame, text="อัปโหลดเซลฟี่", command=self.upload_photos)
        btn_upload.pack(side=tk.LEFT, expand=True, padx=5)
        
        btn_clear = tk.Button(control_frame, text="เลือรูปใหม่", command=self.clear_selection)
        btn_clear.pack(side=tk.LEFT, expand=True, padx=5)

        btn_search = tk.Button(control_frame, text="ค้นหารูปภาพ", font=("Arial", 12, "bold"), command=self.search_photos)
        btn_search.pack(side=tk.RIGHT, expand=True, padx=5)

        self.status_label = tk.Label(main_frame, text="สถานะ: กรุณาอัปโหลดรูปเซลฟี่ของคุณ", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def upload_photos(self):
        """
        เปิด File Dialog ให้เลือกได้หลายไฟล์ และแสดง Thumbnail
        """
        # askopenfilenames (มี s) จะคืนค่าเป็น tuple ของ path หลายๆ ไฟล์
        file_paths = filedialog.askopenfilenames(
            title="เลือกรูปเซลฟี่ของคุณ (สูงสุด 3 รูป)",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png")]
        )

        if not file_paths: return
        if len(file_paths) > 3:
            messagebox.showwarning("เลือกรูปเกิน", "กรุณาเลือกรูปภาพไม่เกิน 3 รูป")
            return

        self.clear_selection() # ล้างของเก่าก่อนเลือกใหม่

        for path in file_paths:
            try:
                image = face_recognition.load_image_file(path)
                encodings = face_recognition.face_encodings(image)
                if not encodings: continue # ข้ามรูปที่หาหน้าไม่เจอ

                # สร้าง Thumbnail เพื่อแสดงผล
                pil_image = Image.open(path)
                pil_image.thumbnail((100, 100), Image.LANCZOS)
                photo_image = ImageTk.PhotoImage(pil_image)

                # เก็บข้อมูลและแสดงผล
                self.uploaded_images_data.append({'encoding': encodings[0], 'photo': photo_image})
                lbl_thumb = tk.Label(self.thumb_frame, image=photo_image)
                lbl_thumb.pack(side=tk.LEFT, padx=5)

            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการประมวลผล {path}: {e}")
        
        self.status_label.config(text=f"สถานะ: อัปโหลดแล้ว {len(self.uploaded_images_data)} รูป, พร้อมค้นหา")


    def clear_selection(self):
        """
        ล้างรูปที่เลือกไว้ทั้งหมด
        """
        for widget in self.thumb_frame.winfo_children():
            widget.destroy()
        self.uploaded_images_data.clear()
        self.status_label.config(text="สถานะ: กรุณาอัปโหลดรูปเซลฟี่ของคุณ")


    def search_photos(self):
        """
        เหมือนฟังก์ชัน compare_faces เดิม แต่ใช้ชื่อใหม่ให้เข้าใจง่าย
        """
        if not self.uploaded_images_data:
            messagebox.showwarning("ยังไม่ได้เลือกรูป", "กรุณาอัปโหลดรูปเซลฟี่อย่างน้อย 1 รูปก่อน")
            return

        guest_encodings = [data['encoding'] for data in self.uploaded_images_data]
        master_encoding = np.mean(guest_encodings, axis=0)

        # ส่วนที่เหลือเหมือนเดิม: เชื่อมต่อ DB, เปรียบเทียบ, และแสดงผล
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT filepath, encoding FROM encodings")
            all_data = cursor.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("ข้อผิดพลาดฐานข้อมูล", f"ไม่สามารถเชื่อมต่อฐานข้อมูลได้: {e}\n(ตรวจสอบว่ามีไฟล์ {DB_FILE} อยู่)")
            return
            
        if not all_data:
            messagebox.showinfo("ไม่พบข้อมูล", "ยังไม่มีรูปภาพในฐานข้อมูลของงานอีเวนต์นี้")
            return

        db_filepaths = [item[0] for item in all_data]
        db_encodings = [np.frombuffer(item[1]) for item in all_data]
        
        distances = face_recognition.face_distance(db_encodings, master_encoding)
        matching_filepaths = [db_filepaths[i] for i, dist in enumerate(distances) if dist <= MATCH_THRESHOLD]
        
        self.status_label.config(text=f"สถานะ: ค้นหาเสร็จสิ้น พบ {len(set(matching_filepaths))} รูปที่ตรงกัน")
        self.show_results(matching_filepaths)


    def show_results(self, matching_filepaths):
        # ฟังก์ชันนี้เหมือนเดิม ไม่มีการเปลี่ยนแปลง
        result_window = tk.Toplevel(self.root)
        result_window.title(f"ผลการค้นหา: พบ {len(set(matching_filepaths))} รูป")
        result_window.geometry("800x600")
        unique_paths = sorted(list(set(matching_filepaths)))
        if not unique_paths:
            lbl_no_result = tk.Label(result_window, text="ไม่พบรูปภาพที่ตรงกัน", font=("Arial", 16))
            lbl_no_result.pack(pady=20)
            return
        
        canvas = tk.Canvas(result_window)
        scrollbar = tk.Scrollbar(result_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        for i, path in enumerate(unique_paths):
            frame = tk.Frame(scrollable_frame, bd=1, relief=tk.SOLID, padx=5, pady=5)
            frame.grid(row=i // 4, column=i % 4, padx=5, pady=5)
            try:
                img = Image.open(path)
                img.thumbnail(RESULT_IMAGE_DISPLAY_SIZE, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl_img = tk.Label(frame, image=photo)
                lbl_img.image = photo
                lbl_img.pack()
                lbl_path = tk.Label(frame, text=os.path.basename(path), wraplength=RESULT_IMAGE_DISPLAY_SIZE[0])
                lbl_path.pack()
            except Exception as e:
                print(f"ไม่สามารถแสดงผลรูป {path}: {e}")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


if __name__ == "__main__":
    # ข้อควรจำ: โปรแกรมนี้ต้องการไฟล์ face_encodings.db ที่ถูกสร้างไว้ล่วงหน้า
    if not os.path.exists(DB_FILE):
        messagebox.showerror("ไม่พบฐานข้อมูล", f"ไม่พบไฟล์ฐานข้อมูล '{DB_FILE}'\nโปรแกรมนี้สำหรับแขกในงาน และต้องรันหลังจากที่ช่างภาพสร้างฐานข้อมูลแล้ว")
    else:
        root = tk.Tk()
        app = GuestApp(root)
        root.mainloop()