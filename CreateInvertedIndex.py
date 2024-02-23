import os
import nltk
import sqlite3
from nltk.stem import WordNetLemmatizer
from bs4 import BeautifulSoup
from lxml import html
import math
import json

VALID_DOCUMENTS = 0
UNIQUE_WORDS_SET = set()  # Global set to keep track of unique words

#given a subfolder path, this function returns the path the files as a list inside that subfolder
def find_file_paths(subfolder_path):
    
    #creates the list of files in the current subdirectory
    current_files = []

    #goes through each file and adds that path to the current_files list
    for file in os.listdir(subfolder_path):
        file_path = os.path.join(subfolder_path, file)
        current_files.append(file_path)

    #returns the path list to the current_files
    return current_files

#function to create the tokenized results for a document (Modified Token, Document ID Pairs)
def create_tokenizer_for_individual_doc(file_path):

    #finds the name/Doc ID of the current file_path
    #it will be "subfolder/docname"
    #for example, if the subfolder is 0 and the file name is 25, the DocID will be 0/25
    #this can be used to lookup the link later in the bookeeper.json file when returning search results
    path = os.path.normpath(file_path).split(os.sep)
    fullDocID = path[-2] + "/" + path[-1]

    #opens the file_path
    open_file = open(file_path, 'r', encoding='utf-8')
    try:
        contents = open_file.read()
    except:
        print("ERROR: Could not read file at DocId: {}".format(fullDocID))
        return []
    open_file.close()

    global VALID_DOCUMENTS
    print("Files Read: {} | Current file DocId: {}".format(VALID_DOCUMENTS, fullDocID))
    VALID_DOCUMENTS += 1

    #extracts the html contents 
    text_extracter = BeautifulSoup(contents, 'html.parser')
    
    #gets the words
    words = text_extracter.get_text()

    #tokenizes the words
    tokenized_words = nltk.word_tokenize(words)

    #creates the lemmatizer
    lemmatizer = WordNetLemmatizer()

    #list to hold (Modified Token, DocID) pairs 
    token_DocID_list = []
    
    #loops through each word and adds lemmatized tuple to the list
    for word in tokenized_words:
        if word.isalpha() and word.isascii():
            lemmatized_word = lemmatizer.lemmatize(word)
            token_DocID_list.append((lemmatized_word, fullDocID))
    return token_DocID_list

def create_document_postings(token_DocID_list):
    global UNIQUE_WORDS_SET
    unique_tokens = 0
    postings_dict = {}

    #this section checks for stop words from stopwords.txt
    stop_words = set()
    try:
        with open('stopwords.txt', 'r') as sw_file:
            stop_words = {word.strip().lower() for word in sw_file.readlines()}
    except FileNotFoundError:
            print("stopwords.txt not found")

    #this holds the position of the tokens in the list as we iterate
    iter = 0
    for token in token_DocID_list:
        #if the token is not a stop word
        if token[0] not in stop_words:
            UNIQUE_WORDS_SET.add(token[0])
            #if the token is already in the dictionary, update values
            if token[0] in postings_dict:
                #updates posting with docid, word count, and doc position
                values = postings_dict[token[0]]
                docid = values[0]
                word_count = values[1]
                doc_positions = values[2]
                doc_positions.append(iter)
                #increments word count, and appends the current list position to the list of positions
                postings_dict[token[0]] = [docid, word_count + 1, doc_positions]
            else:
                #creates new dictionary entry with docid, word count = 1, and doc position
                docid = token[1]
                word_count = 1
                doc_positions = [iter]
                postings_dict[token[0]] = [docid, word_count, doc_positions]
                unique_tokens += 1
        iter += 1
    return postings_dict

# Set up sqlite3 database
def setup_database():
    # Initialize connection
    conn = sqlite3.connect('index.db')
    c = conn.cursor()
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS documents
                 (id TEXT PRIMARY KEY, path TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tokens
                 (token TEXT, doc_id INTEGER, frequency INTEGER, tf REAL, positions TEXT,
                  FOREIGN KEY(doc_id) REFERENCES documents(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS postings
                 (token TEXT, doc_id INTEGER, frequency INTEGER, tf REAL, weight REAL, nweight REAL, positions TEXT,
                  FOREIGN KEY(doc_id) REFERENCES documents(id))''')
    conn.commit()
    return conn

# Replaces all word_counts in postings_dict with term frequencies
def calculate_tf(postings_dict):
    # Loop through token posting dictionary
    for token, posting in postings_dict.items():
        # Separate values to find IDF
        doc_id, token_frequency, positions = posting
        tf = math.log10(token_frequency) + 1

        # Return a tfidf dictionary sorted by token key
        postings_dict[token][1] = tf
    return postings_dict

# Stores tokens and posting values into database
def store_tokens(conn, postings_dict):
    c = conn.cursor()
    # Loop through tokens and values and insert every pair
    for token, values in postings_dict.items():
        doc_id, tf, positions = values
        #convert positions list into storable string
        positions_string = " ".join(str(i) for i in positions)
        c.execute('INSERT INTO tokens (token, doc_id, frequency, tf, positions) VALUES (?, ?, ?, ?, ?)',
                  (token, doc_id, len(positions), tf, positions_string))
    conn.commit()

# Retrieves tokens and posting values into database
def retrieve_tokens(conn, token=None):
    c = conn.cursor()
    # Check if token exists or not
    if token:
        c.execute('SELECT * FROM postings WHERE token = ?', (token,))
    else:
        c.execute('SELECT * FROM postings')
    
    rows = c.fetchall()
    return rows

def calculate_weight(conn):
    c = conn.cursor()
    global UNIQUE_WORDS_SET
    word_set = sorted(UNIQUE_WORDS_SET)
    global VALID_DOCUMENTS
    counter = 1
    for token in word_set:
        #Report processing progress
        print(f"Progress: {(counter/len(UNIQUE_WORDS_SET))*100:.2f}%")
        counter += 1

        #for every token, calculate the idf
        c.execute('SELECT * FROM tokens WHERE token = ?', (token,))
        token_list = c.fetchall()

        document_count = len(token_list)
        idf = math.log10(VALID_DOCUMENTS/(document_count + 1))
        for posting in token_list:
            #calculate the weight using the tf and idf and update value in posting table
            token, doc_id, frequency, tf, positions = posting
            weight = posting[3]*idf
            c.execute('INSERT INTO postings (token, doc_id, frequency, tf, weight, positions) VALUES(?, ?, ?, ?, ?, ?)', (token, doc_id, frequency, tf, weight, positions))
    conn.commit()


def main():
    conn = setup_database()
    #asks user for input to webpages_raw_directory
    webpages_raw_directory = input("Please enter your path to the WEBPAGES_RAW Folder: ")

    #gets the bookkeeping file as a json object
    bookkeeping = open(os.path.join(webpages_raw_directory, "bookkeeping.json"), 'r')
    bookkeeping_data = json.load(bookkeeping)
    bookkeeping.close()

    for doc, path in bookkeeping_data.items():
        conn.execute('INSERT INTO documents VALUES (?, ?)', (doc, path))

    # #loops through each subfolder
    # for file in find_file_paths(webpages_raw_directory):
    #     #checks if the subfolder is a directory
    #     if os.path.isdir(file):
    #         #goes through each file in the subfolder
    #         for subfile in find_file_paths(file):
    #             #tokenizes the document
    #             token_DocID_list = create_tokenizer_for_individual_doc(subfile)
    #             #creates the token_list
    #             postings_dict = create_document_postings(token_DocID_list)
    #             # Calculate TF-IDF for token and document postings
    #             postings_dict = calculate_tf(postings_dict)
    #             # Store the tokens in the database
    #             store_tokens(conn, postings_dict)
            #             #tokenizes the document
    file = "C:\\Users\\ianle\\Documents\\UCI\\CS121\\Project3\\webpages\\WEBPAGES_RAW\\0" # AGGGGG
    for subfile in find_file_paths(file): 
        token_DocID_list = create_tokenizer_for_individual_doc(subfile)
        #creates the token_list
        postings_dict = create_document_postings(token_DocID_list)
        # Calculate TF-IDF for token and document postings
        postings_dict = calculate_tf(postings_dict)
        # Store the tokens in the database
        store_tokens(conn, postings_dict)

    print("Corpus Processed. Now calculating tf-idf weight for tokens...")

    calculate_weight(conn)

    db_size = int(os.path.getsize(os.path.join(os.getcwd(), "index.db"))/1000)
    print(f"Database complete! Files successfully read: {VALID_DOCUMENTS} Size of database: {db_size} kb")
    print(f"Total unique words across all documents: {len(UNIQUE_WORDS_SET)}")

    all = retrieve_tokens(conn,"computer")
    for i in range(1,100):
        print(all[i])

if __name__ == "__main__":
    main()
