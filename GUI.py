import tkinter as tk
from tkinter import ttk
import sqlite3
from bs4 import BeautifulSoup
from CreateInvertedIndex import compute_cosine_similarity, get_info

class SearchEngineGUI:
    def __init__(self, root):
        # Title
        self.root = root
        self.root.title("Search Engine")

        # Path input label
        self.path_label = ttk.Label(self.root, text="Enter Path To WEBPAGES_RAW Here: ")
        self.path_label.pack(padx=10, pady=5)

        # Path input field
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(self.root, textvariable=self.path_var, width=50)
        self.path_entry.pack(padx=10, pady=5)
        self.path_entry.insert(0, "")

        # Submit button for path
        self.submit_button = ttk.Button(self.root, text="Submit", command=self.enable_search)
        self.submit_button.pack(pady=5)

        # Search input field
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.root, textvariable=self.search_var, width=50, state=tk.DISABLED)
        self.search_entry.pack(padx=10, pady=5)

        # Search button
        self.search_button = ttk.Button(self.root, text="Search", command=self.perform_search, state=tk.DISABLED)
        self.search_button.pack(pady=5)

        # Scrollable results area
        self.results_frame = ttk.Frame(self.root)
        self.results_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbar for results
        self.scrollbar = ttk.Scrollbar(self.results_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Listbox for results
        self.results_listbox = tk.Listbox(self.results_frame, yscrollcommand=self.scrollbar.set, width=80, height=20)
        self.results_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.results_listbox.yview)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def enable_search(self, event=None):
        path = self.path_var.get()
        if path:
            self.search_entry.config(state=tk.NORMAL)
            self.search_button.config(state=tk.NORMAL)
            self.path_label.pack_forget()
            self.path_entry.pack_forget()
            self.submit_button.pack_forget()

    def perform_search(self):
        # Connect to database
        conn = sqlite3.connect('index.db')
        query = self.search_var.get()
        path = self.path_var.get()
        
        # Make user input a search parameter
        if not query:
            self.status_var.set("Please enter a search query.")
            return

        if not path:
            self.status_var.set("Please enter a path.")
            return

        # Clear previous results and search
        self.results_listbox.delete(0, tk.END)
        self.status_var.set("Searching...")
        self.root.update()

        # Call on helper function
        results = compute_cosine_similarity(conn, query)
      
        # Print out all the results in listbox
        if results:
            for i, (doc_id, _) in enumerate(results, start=1):
                c = conn.cursor()
                c.execute('SELECT path FROM documents WHERE id = ?', (doc_id,))
                doc_path = c.fetchone()[0]
                if '/' in path and path[-1] != '/': path += '/'
                elif '\\' in path and path[-1] != '\\': path += '\\'
                title, description = get_info(path + doc_id)  # Using dynamic path here
                listbox_entry = f"{i}. Title: {title}, Description: {description}, Path: {doc_path}"
                self.results_listbox.insert(tk.END, listbox_entry)
                
            self.status_var.set(str(len(results)) + " results found.")
        else:
            self.results_listbox.insert(tk.END, "No results found.")

if __name__ == "__main__":
    root = tk.Tk()
    app = SearchEngineGUI(root)
    root.mainloop()
