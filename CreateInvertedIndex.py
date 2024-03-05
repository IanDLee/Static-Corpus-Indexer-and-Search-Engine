import os
import nltk
import sqlite3
from nltk.stem import WordNetLemmatizer
from bs4 import BeautifulSoup
from lxml import html
import math
import json
import time

VALID_DOCUMENTS = 0
UNIQUE_WORDS_SET = set()  # Global set to keep track of unique words
L1_TAGS = ['head', 'title', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
L2_TAGS = ['b', 'i', 'em', 'u', 'mark', 'meta']

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
def create_tokenizer_for_individual_doc(file_path, url_dict):

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
    print(f"\rFiles Read: {VALID_DOCUMENTS} | Current file DocId: {fullDocID}", end = "", flush = True)

    #extracts the html contents 
    text_extracter = BeautifulSoup(contents, 'html.parser')

    #list to hold (Modified Token, DocID, htmlWeight) pairs 
    token_DocID_list = []

    #sets the html tags by a tier-based ranking
    for tag in text_extracter.find_all():

        #gets the weight of the html tag
        if tag.name in L1_TAGS:
            weight = 2
        elif tag.name in L2_TAGS:
            weight = 1.5
        else:
            weight = 1
        
        #handles anchor text by adding the anchor text to the tokens of target
        if tag.name == 'a':
            #gets the anchor words
            anchor_words= tag.text.strip()
            #gets the URL of the target
            url = tag.get('href')
            targetDocID = ""

            #finds the URL key from the bookkeepign file
            if anchor_words:
                targetDocID = url_dict.get(url)

            if targetDocID:
                #tokenizes the words
                tokenized_words = nltk.word_tokenize(anchor_words)

                #creates the lemmatizer
                lemmatizer = WordNetLemmatizer()

                #loops through each word and adds lemmatized tuple to the list
                for word in tokenized_words:
                    if word.isalpha() and word.isascii():
                        lemmatized_word = lemmatizer.lemmatize(word)
                        token_DocID_list.append((lemmatized_word.lower(), targetDocID, weight))

        #gets the words
        words = tag.text.strip()

        #tokenizes the words
        tokenized_words = nltk.word_tokenize(words)

        #creates the lemmatizer
        lemmatizer = WordNetLemmatizer()

        #loops through each word and adds lemmatized tuple to the list
        for word in tokenized_words:
            if word.isalpha() and word.isascii():
                lemmatized_word = lemmatizer.lemmatize(word)
                token_DocID_list.append((lemmatized_word.lower(), fullDocID, weight))
    
    if len(token_DocID_list) > 0:
        VALID_DOCUMENTS += 1
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
                html_weight_dict = values[3]
                if token[2] in html_weight_dict:
                    html_weight_dict[token[2]] += 1
                else:
                    html_weight_dict[token[2]] = 1

                #increments word count, and appends the current list position to the list of positions
                postings_dict[token[0]] = [docid, word_count + 1, doc_positions, html_weight_dict]
            else:
                #creates new dictionary entry with docid, word count = 1, and doc position
                docid = token[1]
                word_count = 1
                doc_positions = [iter]
                html_weight_dict = {token[2]: 1}
                postings_dict[token[0]] = [docid, word_count, doc_positions, html_weight_dict]
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
    conn.commit()
    return conn

# Replaces all word_counts in postings_dict with term frequencies
def calculate_tf(postings_dict):
    # Loop through token posting dictionary
    for token, posting in postings_dict.items():
        tf = 0

        # Separate values to find IDF
        doc_id, token_frequency, positions, html_weight_dict = posting

        #gets the html tag weights as the keys of the dictionary
        html_weights = list(html_weight_dict.keys())
        
        #calculates individual tf weight for each html tag word, and adds to tf
        for weight in html_weights:
            tf += ((math.log10(html_weight_dict[weight]) + 1) * weight)

        # Return a tfidf dictionary sorted by token key
        postings_dict[token][1] = tf
    return postings_dict

# Stores tokens and posting values into database
def store_tokens(conn, postings_dict):
    c = conn.cursor()
    # Loop through tokens and values and insert every pair
    for token, values in postings_dict.items():
        doc_id, tf, positions, html_weights = values
        #convert positions list into storable string (format is [pos1 pos2 pos3 etc]. To return to list use split())
        positions_string = " ".join(str(i) for i in positions)
        c.execute('INSERT INTO tokens (token, doc_id, frequency, tf, positions) VALUES (?, ?, ?, ?, ?)',
                  (token, doc_id, len(positions), tf, positions_string))
    conn.commit()

# Retrieves tokens and posting values into database
def retrieve_tokens(conn, token=None):
    c = conn.cursor()
    # Check if token exists or not
    if token:
        c.execute('SELECT * FROM final_postings WHERE token = ?', (token,))
    else:
        c.execute('SELECT * FROM final_postings')
    
    rows = c.fetchall()
    return rows

def calculate_weight(conn):
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS postings
            (token TEXT, doc_id INTEGER, frequency INTEGER, tf REAL, weight REAL, nweight REAL, positions TEXT,
            FOREIGN KEY(doc_id) REFERENCES documents(id))''') 
    global UNIQUE_WORDS_SET
    word_set = sorted(UNIQUE_WORDS_SET)
    global VALID_DOCUMENTS
    counter = 1
    for token in word_set:
        #Report processing progress
        print(f"\rProgress: {(counter/len(UNIQUE_WORDS_SET))*100:.2f}%", end="", flush= True)
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

#goes through the postings table and normalizes the weight vectors for each document
def normalize_weight(conn):
    c = conn.cursor()
    #creates new table to store final postings list
    c.execute('''CREATE TABLE IF NOT EXISTS final_postings
                 (token TEXT, doc_id INTEGER, positions TEXT, nweight REAL,
                  FOREIGN KEY(doc_id) REFERENCES documents(id))''')
    #gets all unique docs
    c.execute('SELECT DISTINCT doc_id FROM postings')
    doc_list = c.fetchall()
    counter = 1
    for doc in doc_list:
        #Report processing progress
        print(f"\rProgress: {(counter/len(doc_list))*100:.2f}% | Current Doc: {doc}", end="", flush= True)
        counter += 1

        #gets (token, weight) tuple for all postings with the same doc_id
        c.execute('SELECT token, weight, positions FROM postings WHERE doc_id = ?', (doc))
        #stores (token, weight) for all tokens in doc
        token_list = c.fetchall()
        sum = 0
        #calculates magnitude of vector
        for token, weight, positions in token_list:
            sum += math.pow(weight,2)
        #holds magnitude
        magnitude = math.sqrt(sum)

        #normalizes the weights and stores it in new table
        for token, weight, positions in token_list:
            nweight = weight/magnitude
            c.execute('INSERT INTO final_postings (token, doc_id, positions, nweight) VALUES(?, ?, ?, ?)', (token, doc[0], positions, nweight))
    conn.commit()

def compute_cosine_similarity(conn, query):
    # Tokenize and lemmatize the query terms
    lemmatizer = WordNetLemmatizer()
    query_terms = nltk.word_tokenize(query)
    query_terms = [lemmatizer.lemmatize(term.lower()) for term in query_terms if term.isalpha()]
    # Initialize scores and length
    scores = {}

    # Initialize all doc_id's with default scores and length
    c = conn.cursor()

    # Calculate scores for each document
    for term in query_terms:
        c.execute('SELECT doc_id, nweight FROM final_postings WHERE token = ?', (term,))
        postings = c.fetchall()
        # Add to scores and length based on weight of doc_id
        for doc_id, weight in postings:
            if doc_id in scores:
                scores[doc_id] += weight
            else:
                scores[doc_id] = weight

    # Return sorted scores
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)

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
    start = time.time()
    url_dict = {}
    for key, value in bookkeeping_data.items():
        url_dict[value] = key
    # # #loops through each subfolder
    # for file in find_file_paths(webpages_raw_directory):
    #     #checks if the subfolder is a directory
    #     if os.path.isdir(file):
    #         #goes through each file in the subfolder
    #         for subfile in find_file_paths(file):
    #             #tokenizes the document
    #             token_DocID_list = create_tokenizer_for_individual_doc(subfile, bookkeeping_data)
    #             #creates the token_list
    #             postings_dict = create_document_postings(token_DocID_list)
    #             # Calculate TF-IDF for token and document postings
    #             postings_dict = calculate_tf(postings_dict)
    #             # Store the tokens in the database
    #             store_tokens(conn, postings_dict)
                        #tokenizes the document
    file = "C:\\Users\\ianle\\Documents\\UCI\\CS121\\Project3\\webpages\\WEBPAGES_RAW\\0" # AGGGGG
    for subfile in find_file_paths(file): 
        token_DocID_list = create_tokenizer_for_individual_doc(subfile, url_dict)
        #creates the token_list
        postings_dict = create_document_postings(token_DocID_list)
        # Calculate TF-IDF for token and document postings
        postings_dict = calculate_tf(postings_dict)
        # Store the tokens in the database
        store_tokens(conn, postings_dict)
    end = time.time()
    print(f"\nTime Elapsed: {end-start:.2f} s")

    print("\nCorpus Processed. Now calculating tf-idf weight for tokens...")
    start = time.time()
    calculate_weight(conn)
    end = time.time()
    print(f"\nTime Elapsed: {end-start:.2f} s")

    start = time.time()
    normalize_weight(conn)
    end = time.time()
    print(f"\nTime Elapsed: {end-start:.2f} s")

    db_size = int(os.path.getsize(os.path.join(os.getcwd(), "index.db"))/1000)

    print(f"\nDatabase complete! Files successfully read: {VALID_DOCUMENTS} Size of database: {db_size} kb")
    print(f"Total unique words across all documents: {len(UNIQUE_WORDS_SET)}")

if __name__ == "__main__":
    main()
