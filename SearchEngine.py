import json
import sqlite3
import os
from CreateInvertedIndex import retrieve_tokens

MAX_QUERY_SIZE = 20

def main():
    conn = sqlite3.connect('index.db')
    c = conn.cursor()
    #gets the query
    query = ""
    while True:
        #gets the users query for the databse until the user enters quit
        query = input("\nPlease enter your query for the database.  Enter 'quit' to quit program: ")
        if query != 'quit':
            results = retrieve_tokens(conn, query)
            result_size = len(results)
            if result_size == 0:
                print("\nNo results found.")
                continue
            else:
                print(f"\n{result_size} results found.")
                print(f"\nPrinting {min(result_size, MAX_QUERY_SIZE)} results: ")
            results = sorted(results, key = lambda x:x[3], reverse = True)
            i = 0
            while i < min(result_size, MAX_QUERY_SIZE):
                print(results[i])
                c.execute('SELECT * FROM documents WHERE id = ?', (results[i][1],))
                link = c.fetchone()
                print(f"{i + 1}. {link[1]}")
                i += 1
        else:
            break

if __name__ == "__main__":
    main()