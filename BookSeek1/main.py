import tkinter as tk


def main():
    root = tk.Tk()
    root.title("BookSeek (prototype)")
    root.geometry("800x600")
    tk.Label(root, text="BookSeek — coming soon").pack(expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
