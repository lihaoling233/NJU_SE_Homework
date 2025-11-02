import tkinter as tk

root = tk.Tk()
root.title("中文输入测试")

# 创建输入框并强制获取焦点
entry = tk.Entry(root, font=('WenQuanYi Zen Hei', 12), width=30)
entry.pack(padx=20, pady=20)
entry.focus_set()  # 关键：让输入框默认获取焦点

root.mainloop()
