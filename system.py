#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import spacy
from spacy.matcher import Matcher

from datetime import datetime
from requests import get
from SPARQLWrapper import SPARQLWrapper, JSON

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
    }

    def __init__(self):
        self.nlp = spacy.load('en')
        self.matcher = self.init_matcher()

    # parse een vraag met de juiste parser functie en translate de entity/property
    def __call__(self, question):
        result = self.nlp(question)
        try:
            match_id, start, end = self.matcher(result)
        except IndexError:
            # question voldoet niet aan een van onze patterns, error dus
            raise NoAnswerError('Question is ill-formed, cannot answer this question')

        # wel een match gevonden, run de juiste parser functie
        ent, prop, extra = getattr(self, result.vocab.strings[match_id].lower())(question)

        # translate de property en verwijder stopwords uit de entity
        return (result.vocab.strings[match_id], self.translate_query(prop),
                ' '.join(w for w in ent if w not in self.stop_words), extra)

    def init_matcher(self):
        # hier komen de patterns voor het identificeren van vraagtypes
        matcher = Matcher(self.nlp.vocab)
        matcher.add('WHEN_WHERE', None, [{'LOWER': {'IN': ['when', 'where']}},
                                         {'DEP': {'IN': ['ROOT', 'aux', 'auxpass']}}])
        matcher.add('X_OF_Y', None, [{'DEP': 'attr', 'LOWER': {'IN': ['who', 'what']}},
                                     {'LOWER': {'IN': ['is', 'are', 'was', 'were']}}])
        matcher.add('WHO_DID_X', None, [{'DEP': 'nsubj', 'LOWER': 'who'}, {'DEP': 'ROOT'}])

        matcher.add('WHAT_IS_THE_LAST', None, [{'LOWER': 'the', 'OP': '?'},
          {'POS': 'NOUN'},
          {'POS': 'NOUN', 'OP' : '?'}])

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
    def pattern_one(question):
        ent = ''
        prop = ''
        return ent, prop, ''

    @staticmethod
    def pattern_two(question):
        ent = ''
        prop = ''
        return ent, prop, ''
    
    @staticmethod
    def what_is_the_last(question):
        ent = ''
        prop = ''
        return ent, prop, ''


class QuestionSolver:
    def __init__(self):
        self.sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
        self.wiki_api_url = 'https://www.wikidata.org/w/api.php'
        self.parser = QuestionParser()

        self.query_dict = {
            'pattern_one': 'SELECT ?answerLabel WHERE {{ '
                           '  wd:{} wdt:{} ?answer . '
                           '  SERVICE wikibase:label {{ '
                           '    bd:serviceParam wikibase:language "en" .'
                           '  }}'
                           '}}',
        #pattern two kan het laatste / eerste dat iemand van iets behaald heeft bepalen
            'pattern_two': 'SELECT ?answerLabel WHERE {{
                           ' wd:{0} p:{1}  ?answer .
                           '?statement ps:{1} ?answer . 
                           '?statement pq:P585 ?date 
                           'SERVICE wikibase:label {{ 
                           'bd:serviceParam wikibase:language "en" .
                           '}}' 
                           'ORDER BY DESC (?date)
                           'LIMIT 1',
            'pattern_three':

        }

    def __call__(self, question):
        try:
            # parse de vraag die gesteld werd, maar haal eerst het vraagteken en evt. witruimte weg
            q_type, prop, ent, extra = self.parser(question.strip().strip(' ?'))
            answers = self.query_answer(q_type, prop, ent)

        # geen antwoord gevonden
        except NoAnswerError as err:
            print(err)
            return

        for answer in answers:
            try:
                date = datetime.strptime(answer, '%Y-%m-%dT%H:%M:%SZ')
                print(date.strftime('%m/%d/%Y'))
            except ValueError:
                print(answer)

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

        # niks gevonden voor de entity of de property
        if wikidata_props is None or wikidata_entities is None:
            raise NoAnswerError

        # we vinden meerdere entities en properties: probeer per entity de gevonden properties
        for wikidata_entity in wikidata_entities:
            for wikidata_prop in wikidata_props:

                # de juiste query moet nog gekozen worden op basis van question type
                query_string = self.query_dict[question_type]

                # vul de query string met de gevonden entity/property/extra in de vraag
                query_string.format(wikidata_entity, wikidata_prop, extra)

                self.sparql.setQuery(query_string)
                self.sparql.setReturnFormat(JSON)
                results = self.sparql.query().convert()['results']['bindings']

                # geen resultaten voor deze combinatie, probeer de volgende
                if not results:
                    continue

                # resultaat / resultaten gevonden, return de resultaten
                # dit gaat ervan uit dat de antwoorden als 'answerLabel' geselecteerd worden in de query
                return map(lambda x: x['answerLabel']['value'], results)

        raise NoAnswerError


def main():
    print('Loading up QA System...')
    qa_system = QuestionSolver()
    print('Ready to go!\n')

    # answer questions from standard input
    with open('all_questions_and_answers.tsv', 'r', encoding='utf-8') as questions:
        for question in questions:
            q, url, *answers = question.split('\t')
            answers_current = qa_system(q)

            if answers:
                got_it_right = True
                for answer in answers:
                    if answer not in answers_current:
                        got_it_right = False
            else:
                got_it_right = False

            if not got_it_right:
                with open('system_log.txt', 'w', encoding='utf-8') as logfile:
                    logfile.write('{}\n'.format(q))


if __name__ == '__main__':
    main()