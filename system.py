#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import spacy
import sys

from spacy.matcher import Matcher

from datetime import datetime
from requests import get
from SPARQLWrapper import SPARQLWrapper, JSON

# handle input
from unidecode import unidecode


class NoAnswerError(Exception):
    def __init__(self, *args, **kwargs):
        if not (args or kwargs):
            args = ('Could not find an answer to this question.',)
        super().__init__(*args)


class QuestionParser:
    stop_words = {'a', 'by', 'of', 'the', '\'s', '"', '\''}
    trans_dict = {
        'direct':    'director',
        'write':     'author',
        'compose':   'composer',
        'invent':    'inventor',
        'bear':      'birth',
        'die':       'death',
        'born':      'birth',
    }

    def __init__(self):
        self.nlp = spacy.load('en')
        self.matcher = self.init_matcher()

    # parse een vraag met de juiste parser functie en translate de entity/property
    def __call__(self, question):
        question = question.strip()
        if question[-1] != "?":
            question+="?"
        result = self.nlp(question)
        try:
            match_id, start, end = self.matcher(result)[0]
        except IndexError:
            # question voldoet niet aan een van onze patterns, error dus
            raise NoAnswerError('Question is ill-formed, cannot answer this question')

        # wel een match gevonden, run de juiste parser functie
        ent, prop, extra = getattr(self, result.vocab.strings[match_id].lower())(result)
        # translate de property en verwijder stopwords uit de entity
        prop = self.translate_query(prop) if prop is not None else None
        ent = ' '.join(w for w in ent if w not in self.stop_words) if ent is not None else None
        return result.vocab.strings[match_id], ent, prop, extra

    def init_matcher(self):
        # hier komen de patterns voor het identificeren van vraagtypes
        matcher = Matcher(self.nlp.vocab)
        matcher.add('X_OF_Y', None,
                    [
                        {'DEP': {'IN': ['attr', 'advmod', 'nsubj']}, 'LOWER': {'IN': ['who', 'what', 'when']}},
                        {'LOWER': {'IN': ['is', 'are', 'was', 'were']}},
                        {'DEP': 'det', 'OP': '?'},
                        {'DEP': {'IN': ['amod', 'compound', 'attr','nsubj']}, 'OP': '*'},
                        {'LOWER': 'of'}
                    ])
        matcher.add('POSSESSIVE', None,
                    [
                        {'DEP': {'IN': ['attr', 'advmod']}, 'LOWER': {'IN': ['who', 'what', 'when']}},
                        {'LOWER': {'IN': ['is', 'are', 'was', 'were']}},
                        {'DEP': 'det', 'OP': '?'},
                        {'POS': {'IN': ['NOUN', 'PROPN']}, 'OP': '*'},
                        {'LOWER': {'IN': ['\'s']}},
                    ])
        matcher.add('WHO_IS', None,
                    [
                        {'LOWER': {'IN': ['who']}},
                        {'LEMMA': 'be'},
                        {'DEP': 'det', 'OP': '?'},
                        {'DEP': 'compound', 'OP': '*'},
                        {'DEP': {'IN': ['attr', 'nsubj']}},{'DEP': 'punct'}
                    ])
        matcher.add('WHAT_IS', None,
                    [
                        {'LOWER': {'IN': ['what']}},
                        {'LEMMA': 'be'},
                        {'DEP': 'det', 'OP': '?'},
                        {'DEP': 'compound', 'OP': '*'},
                        {'DEP': {'IN': ['attr', 'nsubj']}},{'DEP': 'punct'}
                    ])
        matcher.add('WHAT_MEANS', None,
                    [
                        {'LOWER': 'what'},
                        {'LOWER': 'does'},
                        {'DEP': 'compound', 'OP': '*'},
                        {'DEP': 'nsubj'},
                        {'LOWER': 'mean'},
                    ],
                    [
                        {'LOWER': 'what'},
                        {'LOWER': 'is'},
                        {'DEP': 'det', 'OP': '?'},
                        {'LOWER': 'meaning'},
                        {'LOWER': 'of'},
                        {'DEP': 'compound', 'OP': '*'},
                        {'DEP': 'pobj'},
                    ])
        matcher.add('WHEN_WHERE', None,
                    [
                        {'LOWER': {'IN': ['when', 'where']}},
                        {'LEMMA': {'IN': ['be', 'do']}},
                        {'DEP': 'compound', 'OP': '*'},
                        {'DEP': {'IN': ['nsubj', 'nsubjpass', 'adv']}},
                        {'POS': 'VERB'},
                    ])
        matcher.add('HOW_MANY_X', None,
                    [
                        {'LOWER': 'how'},
                        {'LOWER': 'many'},
                    ])
        matcher.add('WHEN_DID_WAS', None,
                    [
                        {'LOWER': {'IN': ['when']}},
                        {'LOWER': {'IN': ['did','was']}},
                    ])
        matcher.add('WHERE_DID_WAS', None,
                    [
                        {'LOWER': {'IN': ['where']}},
                        {'LOWER': {'IN': ['did','was']}},
                    ])

        matcher.add('HOW_DID', None,
                    [
                        {'LOWER': {'IN': ['how']}},
                        {'LOWER': {'IN': ['did']}},
                    ])
        # matcher.add('WHO_DID_X', None, [
        #     {'DEP': 'nsubj', 'LOWER': 'who'},
        #     {'DEP': 'ROOT'},
        # ])
        matcher.add('WHAT_X_DID_Y', None, [
            {'DEP': 'det'},
            {'POS': 'ADJ', 'DEP': 'amod', 'OP': '*'},
            {'POS': 'NOUN', 'DEP': 'compound', 'OP': '*'},
            {'POS': 'NOUN', 'DEP': {'IN': ['dobj', 'nsub', 'pcomp']}},
            {'POS': 'VERB', 'DEP': {'IN': ['aux', 'ROOT']}},
        ])

        matcher.add('FROM_WHICH_X', None, [
            {'LOWER': 'from'},
            {'LOWER': {'IN': ['which', 'what']}},
            {'POS': 'ADJ', 'DEP': 'amod', 'OP': '*'},
            {'POS': 'NOUN', 'DEP': 'compound', 'OP': '*'},
            {'POS': 'NOUN', 'DEP': {'IN': ['dobj', 'nsubj', 'pcomp']}},
            {'POS': 'VERB'},
            ])
    
        matcher.add('DID_X',None,[
            {'LOWER': {'IN': ['did','does']}},
            {'DEP': 'det', 'OP': '?'},
            {'DEP': {'IN': ['amod', 'compound', 'attr','nsubj']}, 'OP': '*'},
            {'LOWER': {'IN': ['play','compose','write','perform','practice','sing','influence']}}
            ])
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

        elif query[1] in ['publish', 'release']:
            if query[0] == 'who':
                new_query = 'publisher'
            elif query[0] == 'when':
                new_query = 'publication date'

        elif query[0] == 'where':
            if query[1] == 'live':
                new_query = 'residence'
            if query[1] == 'from':
                new_query = 'country of citizenship'

        elif query == ['real', 'name']:
            new_query = 'full name'

        elif query == ['bear']:
            new_query = 'birth'

        return new_query

    # in de onderstaande functies komen de parsers voor elke pattern.
    # noem deze hetzelfde als de pattern, maar dan in lower-case.
    # als derde return value altijd None returnen als er geen Z in de question template zit.
    # voorbeeld Z in een question template: 'Which award did AC/DC receive in 2013?'
    # hier is "2013" de Z value, omdat er een specifiek jaartal moet worden opgezocht
    @staticmethod
    def x_of_y(result):
        try:
            prop_ent = next(w for w in result if w.dep_ == 'pobj')
            prop = [w.text for w in prop_ent.head.head.lefts] + [prop_ent.head.head.text]
            entity = [w.text for w in prop_ent.subtree]
            return entity, prop, None
        except StopIteration:
            return None, None, None

    @staticmethod
    def possessive(result):
        try:
            poss = [w for w in result if w.dep_ == 'case']
            entity = [w.text for w in result if w.pos_ == 'PROPN']
            prop = [w.lemma_ for w in result[list(result).index(poss[0])+1:-3]]
            if prop == []:
                prop = [w.lemma_ for w in result[list(result).index(poss[0])+1:-1]]
            # entity = [w.text for w in prop_ent.subtree]
            return entity, prop, None
        except StopIteration:
            return None, None, None

    @staticmethod
    def who_is(result):
        try:
            # zoek de entity. Dit is een nsubj of een attr dependency, maar de eerste attr is altijd
            # "Who" Kies daarom uitsluitend woorden met de POS-tag "NOUN" of "PROPN"
            ent_token = next(w for w in result if w.dep_ in ['nsubj', 'attr'] and w.pos_ in ['NOUN', 'PROPN', 'ADJ'])
            entity = [w.text for w in ent_token.subtree]
            return entity, None, None
        except StopIteration:
            return None, None, None

    @staticmethod
    def what_is(result):
        try:
            # zoek de entity. Dit is een nsubj of een attr dependency, maar de eerste attr is altijd
            # "What". Kies daarom uitsluitend woorden met de POS-tag "NOUN" of "PROPN"
            ent_token = next(w for w in result if w.dep_ in ['nsubj', 'attr'] and w.pos_ in ['NOUN', 'PROPN', 'ADJ'])
            entity = [w.text for w in ent_token.subtree]
            return entity, None, None
        except StopIteration:
            return None, None, None

    @staticmethod
    def what_means(result):
        try:
            # zoek naar de entity. Als er geen pobj is, is de entity een nsubj
            ent_token = next(w for w in result if w.dep_ == 'pobj')
        except StopIteration:
            ent_token = next(w for w in result if w.dep_ == 'nsubj')
        entity = [w.text for w in ent_token.subtree]
        return entity, None, None

    @staticmethod
    def when_where(result):
        # print("when_where")
        try:
            entity = [w.text for w in next(w for w in result[1:] if w.dep_ in ['nsubj', 'nsubjpass', 'advmod']).subtree]
            prop_one = result[0].lemma_
            prop_two = result[-1].lemma_
            prop = [prop_one, prop_two]
            return entity, prop, None
        except StopIteration:
            return None, None, None

    @staticmethod
    def who_did_x(result):
        # print("who_did_x")
        try:
            prop = ['who', next(w for w in result if w.dep_ == 'ROOT').lemma_]
            entity = []
            return entity, prop, None
        except StopIteration:
            return None, None, None

    @staticmethod
    def what_x_did_y(result):
        # print("what_did_x")
        i = 0
        for item in result:
            if item.pos_ == "NOUN" and (item.dep_ == "nsubj" or item.dep_ == "dobj" or item.dep_ == "pcomp"):
                prop = result[i].text
                break
            else:
                i += 1
        entity = [e.text for e in result.ents]
        try:
            entity = entity[0]
        except IndexError:
            for j, it in enumerate(result):
                if it.pos_ == "VERB":
                    entity = result[j+1].text
                    break
        return entity.split(), prop.split(), None

    @staticmethod

    def how_many_x(result):
        i = 0
        for item in result:
            if item.pos_ == "NOUN" and (item.dep_ == "nsubj" or item.dep_ == "dobj"):
                prop = [result[i].text]
                break
            else:
                i += 1
        entity = [e.text for e in result.ents]
        try:
            entity = entity[0]
            entity = entity.split()
        except IndexError:
            entity = []
            for w in result:
                if w.pos_ == "PROPN":
                    entity.append(w.text)
        return entity, prop, None

    @staticmethod
    def when_did_was(result):
        entity = [e.text for e in result.ents]
        try:
            entity = entity[0]
            entity = entity.split()
        except IndexError:
            entity = []
            for w in result:
                if w.pos_ == "PROPN":
                    entity.append(w.text)
        prop  = []
        for item in result:
            prop = result[-3].lemma_
            if prop == 'born':
                prop = ['birth', 'date']
            elif prop == 'died' or prop == 'die':
                prop = ['death', 'date']
            elif prop == 'founded' or prop == 'started' or prop == 'found' or prop == 'begin' or prop == 'start':
                prop = ['the founding']
            
        return entity, prop, None

    @staticmethod
    def where_did_was(result):
        entity = [e.text for e in result.ents]
        try:
            entity = entity[0]
            entity = entity.split()
        except IndexError:
            entity = []
            for w in result:
                if w.pos_ == "PROPN":
                    entity.append(w.text)
        prop = []
        for item in result:
            prop = result[-3].lemma_
            if prop == 'born':
                prop = ['birth', 'place']
            if prop == 'died' or prop == 'die':
                prop = ['death', 'place']

        return entity, prop, None

    @staticmethod
    def from_which_x(result):
        entity = [e.text for e in result.ents]
        try:
            entity = entity[0]
            entity.split()
        except IndexError:
            entity = []
            for w in result:
                if w.pos_ == "PROPN":
                    entity.append(w.text)
        for i, word in enumerate(result):
            if word.text.lower() == "which" or word.text.lower() == "what":
                prop = result[i+1].text
        return entity, prop.split(), None

    @staticmethod
    def how_did(result):
        entity = [e.text for e in result.ents]
        try:
            entity = entity[0]
            entity = entity.split()
        except IndexError:
            entity = []
            for w in result:
                if w.pos_ == "PROPN":
                    entity.append(w.text)
        prop_one = result[-3].lemma_
        prop_two = result[-1].lemma_
        if prop_one == 'die':
            prop_one = 'cause of death'
        prop = [prop_one]
        return entity, prop, None

    @staticmethod
    def did_x(result):
        print("did_x")
        try:
            verb = [next(w for w in result if w.dep_ == 'ROOT')]
            prop = [w.lemma_ for w in verb]
            if prop[0] != "play":
                answer = [w.lemma_ for w in result[1:list(result).index(verb[0])]]
                entity = [w.lemma_ for w in result[list(result).index(verb[0])+1:-1]]
            else:
                entity = [w.lemma_ for w in result[1:list(result).index(verb[0])]]
                answer = [w.lemma_ for w in result[list(result).index(verb[0])+1:-1]]
            print(prop)
            print(entity)
            print(answer)
            return entity, prop, None
        except StopIteration:
            return None, None, None

class QuestionSolver:
    def __init__(self):
        self.sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
        self.wiki_api_url = 'https://www.wikidata.org/w/api.php'
        self.parser = QuestionParser()

        self.query_dict = {

            'X_OF_Y':      'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'POSSESSIVE':  'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHO_IS': 'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:P1477 ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHAT_IS': 'SELECT ?entityDescription WHERE {{ '
                           '  BIND(wd:{} as ?entity) . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHAT_MEANS':  'SELECT ?entityLabel ?entityDescription WHERE {{ '
                           '  BIND(wd:{} as ?entity) . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHEN_WHERE':  'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHO_DID_X':  'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHAT_X_DID_Y':  'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHEN_DID_WAS':  'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'WHERE_DID_WAS':  'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'HOW_DID':  'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'HOW_MANY_X':  'SELECT (count(?answer) as ?answerLabel) WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'FROM_WHICH_X':'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" . '
                           '  }}'
                           '}}',
            'DID_X':       'ASK {{wd:{} wdt:{} wd:{} .}}',
        }

    def __call__(self, question):
        try:
            # parse de vraag die gesteld werd, maar haal eerst het vraagteken en evt. witruimte weg
            q_type, ent, prop, extra = self.parser(question)
            if ent == None and prop == None:
                raise NoAnswerError
            else:
                return self.query_answer(q_type, ent, prop, extra)

        # geen antwoord gevonden
        except NoAnswerError:
            raise

    def print_question(self, question):
        for token in self.parser.nlp(question.strip()):
            print('\t'.join((token.text, token.lemma_, token.pos_, token.tag_, token.dep_, token.head.lemma_)))

    @staticmethod
    def print_answers(answers):
        for i in range(len(answers)):
            try:
                date = datetime.strptime(answers[i], '%Y-%m-%dT%H:%M:%SZ')
                answers[i] = date.strftime('%m/%d/%Y')
            except ValueError:
                pass
            print(answers[i])
        return answers

    # deze functie kan entities makkelijk vinden, moet nog worden getest ivm hoofdlettergevoeligheid
    @staticmethod
    def get_entities(question):
        return [w for w in question if w.ent_iob_ in ['B', 'I']]

    # zoeken op wikidata naar entities/properties
    def query_wikidata_api(self, string, prop_search=False):
        params = {
            'action':      'query',
            'format':      'json',
            'list':        'search',
            'srsearch':    unidecode(string),
            'srnamespace': 120 if prop_search else 0,
            'srlimit':     5,  # maximaal vijf entities per query
            'srprop':      '',
        }
        try:
            results = get(self.wiki_api_url, params).json()['query']['search']
        except KeyError:
            raise NoAnswerError
        # als we naar properties zoeken moet het eerste deel "Property:" van de titel eraf gehaald worden
        # de wikidata link heeft namelijk de volgende opbouw: https://www.wikidata.org/wiki/Property:P576
        return [res['title'][9:] if prop_search else res['title'] for res in results] if results else None

    def query_answer(self, question_type, ent, prop, extra):
        # query de wikidata api om wikidata entities te vinden voor property en entity
        # dirty hack om een element in de lijst te hebben als de property unset is (zoals bij "What is X?" vragen)
        wikidata_props = self.query_wikidata_api(prop, True) if prop is not None else ['']
        wikidata_entities = self.query_wikidata_api(ent) if ent is not None else ['']
        # niks gevonden voor de entity of de property
        if wikidata_props is None:
            raise NoAnswerError('Could not find the property you asked for')

        if wikidata_entities is None:
            raise NoAnswerError('Could not find the entity you asked about')

        # we vinden meerdere entities en properties: probeer per entity de gevonden properties
        for wikidata_entity in wikidata_entities:
            for wikidata_prop in wikidata_props:
                # de juiste query moet nog gekozen worden op basis van question type
                query_string = self.query_dict[question_type]
                # vul de query string met de gevonden entity/property/extra in de vraag
                query_string = query_string.format(wikidata_entity, wikidata_prop, extra)
                self.sparql.setQuery(query_string)
                self.sparql.setReturnFormat(JSON)
                results = self.sparql.query().convert()['results']['bindings']

                # geen resultaten voor deze combinatie, probeer de volgende
                if not results:
                    continue

                # resultaat / resultaten gevonden, return de resultaten
                answers = []
                for result in results:
                    for var in result:
                        answer = result[var]['value']
                        try:
                            # convert resultaat naar een datum als het nodig is
                            date = datetime.strptime(answer, '%Y-%m-%dT%H:%M:%SZ')
                            answer = date.strftime('%Y-%m-%d')
                        except ValueError:
                            pass
                        answers.append(answer)

                return answers

        raise NoAnswerError


def main():
    print('Loading up QA System...')
    qa_system = QuestionSolver()
    print('Ready to go!\n')
    # answer questions from standard input
    if len(sys.argv) == 2:
        correct_answers = 0
        num_questions = 0
        with open(sys.argv[1], 'r') as questions_file:
            with open('syslog.txt', 'w') as log_file:
                with open('answer_file', 'w') as answer_file:
                    for question in questions_file:

                        # skip gecommentte vragen
                        if question[0] == "#":
                            continue
                        num_questions += 1
                        q_id, q = question.strip().split('\t')
                        answer_file.write(q_id)
                        try:
                            answers_current = qa_system(q)
                            #right_answer = 0
                            if answers_current != None:
                                for answer in answers_current:
                                    answer_file.write("\t"+answer)
                                    #if answer.strip() in answers:
                                        #right_answer += 1
                                #if right_answer / len(answers_current) >= 0.5:
                                    #correct_answers += 1
                            else:
                                answer_file.write("\tAnswer not found")
                        except NoAnswerError:
                            answer_file.write("\tAnswer not found")
                        answer_file.write("\n")
                    
        #print('Accuracy: ', correct_answers / num_questions)
    else:
        for question in sys.stdin:
            qa_system.print_question(question)
            try:
                answers_current = qa_system(question)
                qa_system.print_answers(answers_current)
            except NoAnswerError as err:
                print(err)


if __name__ == '__main__':
    main()
