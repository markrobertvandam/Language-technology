#!/usr/bin/python3
import sys
import re
import requests

import spacy
from spacy.matcher import Matcher

def print_example_queries():
    print('Example questions: \n')
    queries = ['What is the birthplace of Elvis?',"Who is Taylor Swift's mother?",'When was John Lennon born?','Who are the children of Michael Jackson?','What genre is Metallica?','What are the recording studios of the Script?','Where is the burial place of Kurt Cobain?','What are the awards of The Beatles?','When was Katy Perry born?','When did Elvis die?']
    for line in queries:
        print(line)    
    print('\nPlease ask a question like the example questions.')
    
def create_and_fire_query(line):
    entity = []
    nlp = spacy.load('en')
    matcher = Matcher(nlp.vocab)
    result=nlp(line)
    for w in result:
        ent = w.ent_iob_
        if ent == 'B' or ent == 'I':
            entity.append(w.text)
    entityname = ' '.join(entity)

    pattern1 = [{'LOWER': 'the', 'OP': '?'},
          {'POS': 'NOUN'},
          {'POS': 'NOUN', 'OP' : '?'}]

    pattern = [{'POS': 'PROPN'},
           {'POS': 'PROPN', 'OP': '?'},
           {'POS': 'VERB'}]

    pattern3 = [{'POS': 'PROPN'},
           {'POS': 'PROPN', 'OP': '?'},
           {'POS': 'NOUN'}]       

    pattern2 = [{'POS': 'ADV'},
           {'POS': 'ADJ'}] 
    matcher.add('TEST', None, pattern)
    matcher.add('TEST2', None, pattern3)
    matcher.add('WHO', None, pattern1)
    matcher.add('HOW', None, pattern2)
    matches = matcher(result)
    a = [result[start:end].text for match_id, start, end in matches]

    for e in a:
        if(entityname in e):
            e = e.replace(entityname,'')
        e=e.replace("How","")
        e=e.replace("Was","")
        if(a != 'How'):
            try:
                prop = findproperties(e)
                ent = findentities(entityname)
                return(answer(prop,ent))
            except:
                pass


    
def findproperties(line):
    url = "https://www.wikidata.org/w/api.php"
    params = {'action':'wbsearchentities',
              'language':'en',
              'format':'json',
              'type':'property'}
    params['search'] = line.rstrip()
    json = requests.get(url,params).json()
    return(json['search'][0]['id'])

        
def findentities(line):
    url = "https://www.wikidata.org/w/api.php"
    params = {'action':'wbsearchentities',
              'language':'en',
              'format':'json',}
    params['search'] = line.rstrip()
    json = requests.get(url,params).json()
    return(json['search'][0]['id'])

        
def answer(prop, ent):
    answers = list()
    answers.clear()
    query = "SELECT ?answerLabel WHERE ( wd:{}    p:{}   ?statement . ?statement ps:{} ?answer .  SERVICE wikibase:label (bd:serviceParam wikibase:language 'en' .))"
    query = query.format(ent,prop,prop)
    query = query.replace("(","{")
    query = query.replace(")","}")
    url = 'https://query.wikidata.org/sparql'
    data = requests.get(url,params={'query': query, 'format': 'json'}).json()
    for item in data['results']['bindings']:
        for var in item :
            answers.append('{}'.format(item[var]['value']))
    return(answers)

def main(argv):
    print_example_queries()
#Dit staat buiten de main omdat in de fucntie de example vragen niet werden getoond.    
main(sys.argv)
for line in sys.stdin:
    line = line.replace(" ?","")
    line = line.replace("?","")
    line = line.replace(" the ", " ")
    line = line.replace("'s","")
    line = line.rstrip()

    answerstring = create_and_fire_query(line)
    try:
        for a in answerstring:
            print(a)
    except:
        print("No answer was found, please try again")
        
if __name__ == "__main__":
    main(sys.argv)