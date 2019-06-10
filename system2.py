#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import spacy
import fileinput
import sys

from spacy.matcher import Matcher

from datetime import datetime
from requests import get
from SPARQLWrapper import SPARQLWrapper, JSON
import en_core_web_sm

# handle input
from sys import stdin
from unidecode import unidecode


class NoAnswerError(Exception):
    def __init__(self, *args, **kwargs):
        if not (args or kwargs):
            args = ('Could not find an answer to this question.',)
        super().__init__(*args)


class QuestionParser:
    stop_words = {'a', 'by', 'of', 'the', '\'s', '"', '\''}
    trans_dict = {
        'direct': 'director',
        'write': 'author',
        'compose': 'composer',
        'invent': 'inventor',
        'bear': 'birth',
        'die': 'death',
        'real name': 'full name',
    }

    def __init__(self):
        self.nlp = spacy.load('en')
        self.matcher = self.init_matcher()
    # parse een vraag met de juiste parser functie en translate de entity/property
    def __call__(self, question):
        found = False
        result = self.nlp(question)
        try:
            for results in self.matcher(result):
                match_id, start, end = results[0], results[1], results[2]
                found = True
        except IndexError:
            # question voldoet niet aan een van onze patterns, error dus
            raise NoAnswerError('Question is ill-formed, cannot answer this question')
        # wel een match gevonden, run de juiste parser functie
        if(found == True):
            ent, prop, extra = getattr(self, result.vocab.strings[match_id].lower())(result)
            found = False
        # translate de property en verwijder stopwords uit de entity
            return (result.vocab.strings[match_id], self.translate_query(prop),
                ' '.join(w for w in ent if w not in self.stop_words), extra)

    def init_matcher(self):
        # hier komen de patterns voor het identificeren van vraagtypes
        matcher = Matcher(self.nlp.vocab)
        matcher.add('X_OF_Y', None, [{'DEP': {'IN': ['attr','advmod']}, 'LOWER': {'IN': ['who', 'what','when']}},
                                     {'LOWER': {'IN': ['is', 'are', 'was', 'were']}}])
        #matcher.add('WHEN_WHERE', None, [{'LOWER': {'IN': ['when', 'where']}},
        #                                 {'DEP': {'IN': ['ROOT', 'aux', 'auxpass']}}])
        matcher.add('WHO_DID_X', None, [{'DEP': 'nsubj', 'LOWER': 'who'}, {'DEP': 'ROOT'}])
        matcher.add('WHAT_DID_X', None, [{"DEP": "det"},
                                        {"POS": "ADJ", "DEP": "amod", "OP": "*"},
                                        {"POS": "NOUN", "DEP": "compound", "OP": "*"},
                                        {"POS": "NOUN", "DEP": {'IN': ['dobj', 'nsub']}},
                                        {"POS": "VERB", "DEP": {'IN': ['aux', 'ROOT']}}])
        return matcher

    # translator functie om de uiteindelijke entity en property teksten te filteren/rewriten
    @classmethod
    def translate_query(cls, query):
        query = [w for w in query if w not in cls.stop_words]
        new_query = ' '.join(query)

        if 'members' in query:
            return 'has part'

        if len(query) < 2:
            return new_query

        if query[1] in ['direct', 'write', 'compose', 'invent']:
            if query[0] == 'who':
                new_query = cls.trans_dict[query[1]]
            if query[0] == 'when':
                new_query = 'inception'

        elif query[1] in ['bear', 'die']:
            if query[0] == 'when':
                new_query = 'date of ' + cls.trans_dict[query[1]]
            elif query[0] == 'where':
                new_query = 'place of ' + cls.trans_dict[query[1]]

        elif query[1] == ['publish', 'release']:
            if query[0] == 'who':
                new_query = 'publisher'
            elif query[0] == 'when':
                new_query = 'publication date'

        return new_query

    # in de onderstaande functies komen de parsers voor elke pattern.
    # noem deze hetzelfde als de pattern, maar dan in lower-case.
    #  als derde return value altijd '' returnen als er geen Z in de question template zit.
    # voorbeeld Z in een question template: 'Which award did AC/DC receive in 2013?'
    # hier is "2013" de Z value, omdat er een specifiek jaartal moet worden opgezocht
    @staticmethod
    def when_where(result):
        #print("when_where")
        entity = [w.text for w in next(w for w in result if w.dep_ in ['nsubj', 'nsubjpass']).subtree]
        prop_one = result[0].lemma_
        prop_two = result[-1].lemma_
        prop = [prop_one, prop_two]
        return entity, prop, ''

    @staticmethod
    def x_of_y(result):
        #print("x_of_y")
        prop_ent = next(w for w in result if w.dep_ == 'pobj')
        prop = [w.text for w in prop_ent.head.head.lefts] + [prop_ent.head.head.text]
        entity = [w.text for w in prop_ent.subtree]
        return entity, prop, ''

    @staticmethod
    def who_did_x(result):
        #print("who_did_x")
        prop = ['who', next(w for w in result if w.dep_ == 'ROOT').lemma_]
        entity = [w.text for w in result[end:]]
        return entity, prop, ''

    @staticmethod
    def what_did_x(result):
        #print("what_did_x")
        i = 0
        for item in result:
            if item.pos_ == "NOUN" and (item.dep_ == "nsubj" or item.dep_ == "dobj"):
                prop = result[i].text
                break
            else:
                i += 1
        entity = [e.text for e in result.ents]
        entity = entity[0]
        return entity.split(), prop.split(), ''


class QuestionSolver:
    def __init__(self):
        self.sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
        self.wiki_api_url = 'https://www.wikidata.org/w/api.php'
        self.parser = QuestionParser()

        self.query_dict = {
            'when_where': 'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" .'
                           '  }}'
                           '}}',
            'x_of_y':      'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" .'
                           '  }}'
                           '}}',
            'what_did_x':   'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" .'
                           '  }}'
                           '}}',
            '4':           'nog iets'
        }

    def __call__(self, question):
        try:
            # parse de vraag die gesteld werd, maar haal eerst het vraagteken en evt. witruimte weg
            q_type, prop, ent, extra = self.parser(question.strip().strip(' ?'))
            answers = self.query_answer(q_type, prop, ent)

        # geen antwoord gevonden
        except:
            #print(err)
            return

        for answer in answers:
            try:
                date = datetime.strptime(answer, '%Y-%m-%dT%H:%M:%SZ')
                #print(date.strftime('%m/%d/%Y'))
            except ValueError:
                #print(answer)
                pass

        return answers

    # deze functie kan entities makkelijk vinden, moet nog worden getest ivm hoofdlettergevoeligheid
    @staticmethod
    def get_entities(question):
        return [w for w in question if w.ent_iob_ in ['B', 'I']]

    # zoeken op wikidata naar entities/properties
    def query_wikidata_api(self, string, prop_search=False):
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'search',
            'srsearch': unidecode(string),
            'srnamespace': 120 if prop_search else 0,
            'srlimit': 5,  # maximaal vijf entities per query
            'srprop': '',
        }

        results = get(self.wiki_api_url, params).json()['query']['search']

        # als we naar properties zoeken moet het eerste deel "Property:" van de titel eraf gehaald worden
        # de wikidata link heeft namelijk de volgende opbouw: https://www.wikidata.org/wiki/Property:P576
        return [res['title'][9:] if prop_search else res['title'] for res in results] if results else None

    def query_answer(self, question_type, prop, entity, extra=None):
        # query de wikidata api om wikidata entities te vinden voor property en entity
        wikidata_props = self.query_wikidata_api(prop, True)
        wikidata_entities = self.query_wikidata_api(entity)
        #print(wikidata_props,"\n",wikidata_entities)
        # niks gevonden voor de entity of de property
        if wikidata_props is None or wikidata_entities is None:
            raise NoAnswerError

        # we vinden meerdere entities en properties: probeer per entity de gevonden properties
        for wikidata_entity in wikidata_entities:
            for wikidata_prop in wikidata_props:
                # de juiste query moet nog gekozen worden op basis van question type
                query_string = self.query_dict[question_type.lower()]


                # vul de query string met de gevonden entity/property/extra in de vraag
                query_string = query_string.format(wikidata_entity, wikidata_prop, extra)
                self.sparql.setQuery(query_string)
                self.sparql.setReturnFormat(JSON)
                results = self.sparql.query().convert()['results']['bindings']

                # geen resultaten voor deze combinatie, probeer de volgende
                if not results:
                    continue

                # resultaat / resultaten gevonden, return de resultaten
                # dit gaat ervan uit dat de antwoorden als 'answerLabel' geselecteerd worden in de query
                answers = []
                for result in results:
                    for var in result:
                        answers.append('{}'.format(result[var]['value']))
                return answers
                # return map(lambda x: x['answerLabel']['value'], results)


        raise NoAnswerError


def main():
    nlp = spacy.load('en')
    print('Loading up QA System...')
    qa_system = QuestionSolver()
    print('Ready to go!\n')
    correct_answers = 0
    wrong_answers = 0
    # answer questions from standard input
    if len(sys.argv)>1:
        for question in fileinput.input():
            right_answer = 0
            wrong_answer = 0
            #print("-----------------------\n")
            q, url, *answers = question.strip().split('\t')
            #print(q)
            #print("Actual answer(s):")
            #for a in answers:
                #print(a)
            answers_current = qa_system(q)
            #print("Our answer(s):")
            if answers_current != None:
                for answer in answers_current:
                    #print(answer)
                    if answer.strip() in answers:
                        right_answer+=1
                    else:
                        wrong_answer+=1
                if right_answer > 0 and (wrong_answer == 0 or right_answer/wrong_answer >= 0.5):
                    correct_answers+=1
                else:
                    wrong_answers+=1
                #print()
            else:
                #print("No answer.\n")
                wrong_answers+=1
    else:
        for question in fileinput.input():
            for token in nlp(question.strip()):
                print("\t".join((token.text, token.lemma_, token.pos_,token.tag_, token.dep_, token.head.lemma_)))
            answers_current = qa_system(question)
            if answers_current != None:
                for answer in answers_current:
                    print(answer)
                print()
            else:
                print("No answer.\n")         
    print("Accuracy: ", correct_answers/(correct_answers+wrong_answers))

if __name__ == '__main__':
    main()
