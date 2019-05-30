#!/user/bin/python3

import sys
import requests
import re
import spacy
from spacy.matcher import Matcher


def do_query(ent, atr):
    url = 'https://query.wikidata.org/sparql'
    query = """SELECT ?answerLabel WHERE {{
    wd:{0}    p:{1}   ?statement .
    ?statement ps:{2} ?answer

    SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "en" .
}}
}}"""

    query = query.format(ent, atr, atr)
    res = requests.get(url, params={'query': query, 'format': 'json'}).json()
    answers = []
    for result in res['results']['bindings']:
        for var in result:
            answers.append('{0}'.format(result[var]['value']))
    return answers


def get_answer(attributes, entities):
    for ent in entities:
        for atr in attributes:
            answer = do_query(ent, atr)
            if not answer:
                continue
            else:
                return answer


def print_example_queries():
    example_queries = ["Who is the mother of Taylor Swift?",
                       "Where is the birth place of Kraantje Pappie?",
                       "What was Avicii's birth name?",
                       "What's Katy Perry's full name?",
                       "What languages does Shakira speak?",
                       "What genre does Miles Davis play?",
                       "What movement was Mozart a part of?",
                       "Which awards did Pink Floyd receive?",
                       "Which country is Queen from?",
                       "Which instruments did Jimi Hendrix play?"]

    print("---- Example questions ----")
    for line in example_queries:
        print(line)
    print("\nPlease ask a question like the example questions shown above.\n")


def get_entities(doc, url):
    entities = [e.text for e in doc.ents]
    betterEnts = []
    # for token in doc:
    #   print(token.text, token.pos_, token.dep_)
    for ent in entities:
        if ent[-2:] == "'s":
            ent = ent[:-2]
        betterEnts.append(ent)
    try:
        entity = betterEnts[0]
    except IndexError:
        return None
    eParams = {'search': entity, 'action': 'wbsearchentities', 'language': 'en', 'format': 'json'}
    entities = requests.get(url, eParams).json()
    entityList = [result['id'] for result in entities['search']]

    return entityList


def get_attributes(doc, matcher, url):
    matches = matcher(doc)
    atts = []
    for match_id, start, end in matches:
        if doc[start].text == "'s" or doc[start].text == "the" or doc[start].text == "'":
            start += 1
        if doc[end - 1].text == "of":
            end = end - 1
        if doc[end - 1].dep_ == "aux" or doc[end - 1].dep_ == "ROOT":
            i = start
            for item in doc[start:end]:
                if item.pos_ == "NOUN" and (item.dep_ == "nsubj" or item.dep_ == "dobj"):
                    matched_span = doc[i]
                    break
                else:
                    i += 1
        else:
            matched_span = doc[start:end]

        atts.append(matched_span.lemma_)

    try:
        attribute = atts[0]
    except IndexError:
        return None
    aParams = {'search': attribute, 'action': 'wbsearchentities', 'language': 'en', 'format': 'json',
               'type': 'property'}
    attributes = requests.get(url, aParams).json()
    attributeList = [result['id'] for result in attributes['search']]

    return attributeList


def create_and_fire_query(line, nlp, matcher):
    url = 'https://www.wikidata.org/w/api.php'
    doc = nlp(line)

    entityList = get_entities(doc, url)
    attributeList = get_attributes(doc, matcher, url)
    if attributeList is None:
        return None
    if entityList is None:
        return None
    answer = get_answer(attributeList, entityList)
    return answer


def make_matcher(nlp):
    matcher = Matcher(nlp.vocab)
    pattern1 = [{"POS:": "PART", "DEP": "case"},
                {"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "attr"}]

    pattern2 = [{"POS:": "PART", "DEP": "case"},
                {"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "nsubj"}]

    pattern3 = [{"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "attr"}, {"LOWER": "of"}]

    pattern4 = [{"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "nsubj"},
                {"LOWER": "of"}]

    pattern5 = [{"DEP": "det"},
                {"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "dobj"},
                {"POS": "VERB", "DEP": "aux"}]

    pattern6 = [{"DEP": "det"},
                {"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "nsubj"},
                {"POS": "VERB", "DEP": "aux"}]

    pattern7 = [{"DEP": "det"},
                {"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "dobj"},
                {"POS": "VERB", "DEP": "ROOT"}]

    pattern8 = [{"DEP": "det"},
                {"POS": "ADJ", "DEP": "amod", "OP": "*"},
                {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                {"POS": "NOUN", "DEP": "nsubj"},
                {"POS": "VERB", "DEP": "ROOT"}]

    matcher.add('PATTERN1', None, pattern1)
    matcher.add('PATTERN2', None, pattern2)
    matcher.add('PATTERN3', None, pattern3)
    matcher.add('PATTERN4', None, pattern4)
    matcher.add('PATTERN5', None, pattern5)
    matcher.add('PATTERN6', None, pattern6)
    matcher.add('PATTERN7', None, pattern7)
    matcher.add('PATTERN8', None, pattern8)
    return matcher


def main():
    print_example_queries()
    nlp = spacy.load('en')
    matcher = make_matcher(nlp)
    for line in sys.stdin:
        line = line.rstrip()
        answer = create_and_fire_query(line, nlp, matcher)
        if answer is None:
            print("No answer was found.\n")
        elif answer == "incorrect":
            pass
        else:
            for an in answer:
                print(an)
            print()


if __name__ == "__main__":
    main()
