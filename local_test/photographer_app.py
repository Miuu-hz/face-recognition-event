import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk
import face_recognition
import sqlite3
import numpy as np
import os
import shutil

# --- ค่าคงที่ ---
DB_FILE = "face_encodings.db"
EXPORT_OUTPUT_FOLDER = "export_results" # โฟลเดอร์สำหรับเก็บผลลัพธ์
MATCH_THRESHOLD =  0.5

class PhotographerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("เครื่องมือสำหรับช่างภาพ")
        self.root.geometry("700x600")

        self.reference_images_data = [] # ใช้ List เก็บข้อมูลรูปอ้างอิง

        # --- เฟรมหลัก ---
        main_frame = tk.Frame(root, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- ส่วนที่ 1: จัดการฐานข้อมูล ---
        db_frame = tk.LabelFrame(main_frame, text="ขั้นตอนที่ 1: จัดการฐานข้อมูล", padx=10, pady=10)
        db_frame.pack(pady=5, fill=tk.X)
        btn_scan = tk.Button(db_frame, text="เลือกโฟลเดอร์และสแกนใบหน้า (สร้าง/อัปเดตฐานข้อมูล)", 
                             font=("Arial", 12), command=self.scan_folder)
        btn_scan.pack(fill=tk.X, ipady=10)

        # --- ส่วนที่ 2: เครื่องมือค้นหาและคัดแยก ---
        export_frame = tk.LabelFrame(main_frame, text="ขั้นตอนที่ 2: ค้นหาและคัดแยกรูปภาพ", padx=10, pady=10)
        export_frame.pack(pady=10, fill=tk.X)

        # ส่วนอัปโหลดรูป
        upload_controls_frame = tk.Frame(export_frame)
        upload_controls_frame.pack(fill=tk.X)
        btn_upload = tk.Button(upload_controls_frame, text="อัปโหลดรูปอ้างอิง (1-3 รูป)", command=self.upload_reference_photos)
        btn_upload.pack(side=tk.LEFT, padx=(0, 5))
        btn_clear = tk.Button(upload_controls_frame, text="ล้างรูปที่เลือก", command=self.clear_reference_photos)
        btn_clear.pack(side=tk.LEFT)
        
        self.thumb_frame = tk.Frame(export_frame, bd=1, relief=tk.SUNKEN)
        self.thumb_frame.pack(fill=tk.X, pady=5, ipady=5)

        # ส่วนตั้งชื่อโฟลเดอร์
        name_frame = tk.Frame(export_frame)
        name_frame.pack(fill=tk.X, pady=5)
        lbl_folder_name = tk.Label(name_frame, text="ตั้งชื่อโฟลเดอร์สำหรับผลลัพธ์:")
        lbl_folder_name.pack(side=tk.LEFT)
        self.folder_name_var = tk.StringVar()
        entry_folder_name = tk.Entry(name_frame, textvariable=self.folder_name_var, width=40)
        entry_folder_name.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # ปุ่มดำเนินการหลัก
        btn_export = tk.Button(export_frame, text="ค้นหาและสร้างโฟลเดอร์", font=("Arial", 12, "bold"), bg="#4CAF50", fg="white", command=self.search_and_export)
        btn_export.pack(fill=tk.X, ipady=10, pady=10)

        # --- ส่วนที่ 3: แสดงผลการทำงาน (Log) ---
        log_frame = tk.LabelFrame(main_frame, text="สถานะการทำงาน", padx=10, pady=10)
        log_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', wrap=tk.WORD, font=("Courier New", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.setup_database()

    # --- ฟังก์ชันจัดการ Log และ Database (เหมือนเดิม) ---
    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update_idletasks()

    def setup_database(self):
        # ... โค้ดส่วนนี้เหมือนเดิม ...
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS encodings (id INTEGER PRIMARY KEY, filepath TEXT NOT NULL, encoding BLOB NOT NULL)")
        conn.commit()
        conn.close()
        self.log(f"ฐานข้อมูล '{DB_FILE}' พร้อมใช้งาน")

    def scan_folder(self):
        # ... โค้ดส่วนนี้เหมือนเดิม ...
        folder_path = filedialog.askdirectory(title="เลือกโฟลเดอร์รูปภาพงานอีเวนต์")
        if not folder_path: return
        self.log("="*50)
        self.log(f"กำลังเริ่มสแกนโฟลเดอร์: {folder_path}")
        # ... (ส่วนที่เหลือของ scan_folder เหมือนเดิม) ...
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        new_faces_count = 0
        cursor.execute("SELECT DISTINCT filepath FROM encodings")
        scanned_files = {row[0] for row in cursor.fetchall()}
        self.log(f"พบไฟล์ที่เคยสแกนแล้ว {len(scanned_files)} ไฟล์")
        image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        for filename in image_files:
            filepath = os.path.join(folder_path, filename)
            if filepath in scanned_files: continue
            try:
                self.log(f"  -> กำลังประมวลผล: {filename}")
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    self.log(f"     พบ {len(encodings)} ใบหน้าในไฟล์นี้")
                    for encoding in encodings:
                        encoding_blob = encoding.tobytes()
                        cursor.execute("INSERT INTO encodings (filepath, encoding) VALUES (?, ?)", (filepath, encoding_blob))
                        new_faces_count += 1
                else: self.log("     ไม่พบใบหน้าในไฟล์นี้")
            except Exception as e: self.log(f"     เกิดข้อผิดพลาด: {e}")
        conn.commit()
        conn.close()
        self.log("="*50)
        self.log("สแกนโฟลเดอร์เสร็จสิ้น!")
        self.log(f"เพิ่มใบหน้าใหม่ทั้งหมด: {new_faces_count} ใบหน้า")
        messagebox.showinfo("เสร็จสิ้น", f"สแกนโฟลเดอร์เสร็จสิ้น\nเพิ่มใบหน้าใหม่ลงฐานข้อมูล: {new_faces_count} ใบหน้า")


    # --- ฟังก์ชันใหม่สำหรับเครื่องมือคัดแยก ---
    def upload_reference_photos(self):
        file_paths = filedialog.askopenfilenames(title="เลือกรูปอ้างอิง (สูงสุด 3 รูป)", filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
        if not file_paths: return
        if len(file_paths) > 3:
            messagebox.showwarning("เลือกรูปเกิน", "กรุณาเลือกรูปภาพไม่เกิน 3 รูป")
            return

        self.clear_reference_photos()
        for path in file_paths:
            try:
                image = face_recognition.load_image_file(path)
                encodings = face_recognition.face_encodings(image)
                if not encodings: continue
                pil_image = Image.open(path)
                pil_image.thumbnail((100, 100), Image.LANCZOS)
                photo_image = ImageTk.PhotoImage(pil_image)
                self.reference_images_data.append({'encoding': encodings[0], 'photo': photo_image})
                lbl_thumb = tk.Label(self.thumb_frame, image=photo_image)
                lbl_thumb.pack(side=tk.LEFT, padx=5)
            except Exception as e:
                self.log(f"เกิดข้อผิดพลาดในการประมวลผล {os.path.basename(path)}: {e}")
        self.log(f"อัปโหลดรูปอ้างอิงแล้ว {len(self.reference_images_data)} รูป")

    def clear_reference_photos(self):
        for widget in self.thumb_frame.winfo_children():
            widget.destroy()
        self.reference_images_data.clear()

    def search_and_export(self):
        # 1. ตรวจสอบข้อมูลนำเข้า
        if not self.reference_images_data:
            messagebox.showwarning("ยังไม่ได้เลือกรูป", "กรุณาอัปโหลดรูปอ้างอิงอย่างน้อย 1 รูปก่อน")
            return
        
        folder_name = self.folder_name_var.get().strip()
        if not folder_name:
            messagebox.showwarning("ยังไม่ได้ตั้งชื่อ", "กรุณาตั้งชื่อโฟลเดอร์สำหรับผลลัพธ์")
            return

        # 2. ตรวจสอบว่าโฟลเดอร์มีอยู่แล้วหรือไม่
        output_path = os.path.join(EXPORT_OUTPUT_FOLDER, folder_name)
        if os.path.exists(output_path):
            response = messagebox.askyesno("ยืนยันการเขียนทับ", 
                                           f"โฟลเดอร์ '{folder_name}' มีอยู่แล้ว\nคุณต้องการลบของเก่าและสร้างใหม่หรือไม่?")
            if not response: # ถ้าผู้ใช้กด No
                self.log(f"ยกเลิกการสร้างโฟลเดอร์ '{folder_name}' ตามคำสั่งผู้ใช้")
                return
            else: # ถ้าผู้ใช้กด Yes
                self.log(f"ผู้ใช้ยืนยันการเขียนทับโฟลเดอร์ '{folder_name}'")
                shutil.rmtree(output_path)
        
        os.makedirs(output_path)

        # 3. เริ่มกระบวนการค้นหา
        self.log("\n" + "="*50)
        self.log(f"เริ่มค้นหาและคัดแยกสำหรับ '{folder_name}'...")
        
        ref_encodings = [data['encoding'] for data in self.reference_images_data]
        master_encoding = np.mean(ref_encodings, axis=0)

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT filepath, encoding FROM encodings")
            all_data = cursor.fetchall()
            conn.close()
        except Exception as e:
            self.log(f"!! เกิดข้อผิดพลาดในการอ่านฐานข้อมูล: {e}")
            return

        if not all_data:
            self.log("!! ฐานข้อมูลว่างเปล่า")
            return
            
        db_filepaths = [item[0] for item in all_data]
        db_encodings = [np.frombuffer(item[1]) for item in all_data]
        
        distances = face_recognition.face_distance(db_encodings, master_encoding)
        matching_paths = {db_filepaths[i] for i, dist in enumerate(distances) if dist <= MATCH_THRESHOLD}
        
        # 4. คัดลอกไฟล์
        if not matching_paths:
            self.log(f"ไม่พบรูปภาพที่ตรงกันสำหรับ '{folder_name}'")
        else:
            for path in matching_paths:
                if os.path.exists(path):
                    shutil.copy(path, output_path)
            self.log(f"ค้นพบและคัดลอก {len(matching_paths)} รูป ไปยังโฟลเดอร์ '{folder_name}' เรียบร้อยแล้ว")

        self.log("="*50)
        messagebox.showinfo("เสร็จสิ้น", f"ดำเนินการสำหรับ '{folder_name}' เสร็จสิ้น!\nตรวจสอบผลลัพธ์ได้ที่โฟลเดอร์ '{output_path}'")


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotographerApp(root)
    root.mainloop()