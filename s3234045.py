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
        super().__init__(*args, **kwargs)


class QuestionSolver:
    def __init__(self):
        self.sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
        self.wiki_api_url = 'https://www.wikidata.org/w/api.php'
        self.nlp = spacy.load('en_core_web_md')
        self.matcher = self.init_matcher()
        self.stop_words = {'a', 'by', 'of', 'the', '\'s', '"'}
        # simple translation dictionary to convert some phrasings into query keywords
        self.trans_dict = {
            'direct': 'director',
            'write': 'author',
            'compose': 'composer',
            'invent': 'inventor',
            'bear': 'birth',
            'die': 'death',
        }

    def init_matcher(self):
        matcher = Matcher(self.nlp.vocab)
        matcher.add('WHEN_WHERE', None, [{'LOWER': {'IN': ['when', 'where']}},
                                         {'DEP': {'IN': ['ROOT', 'aux', 'auxpass']}}])
        matcher.add('X_OF_Y', None, [{'DEP': 'attr', 'LOWER': {'IN': ['who', 'what']}},
                                     {'LOWER': {'IN': ['is', 'are', 'was', 'were']}}])
        matcher.add('WHO_DID_X', None, [{'DEP': 'nsubj', 'LOWER': 'who'}, {'DEP': 'ROOT'}])
        return matcher

    def answer_question(self, question):
        try:
            parsed_question = self.parse_question(question.strip().strip(' ?'))
            for answer in self.query_answer(parsed_question[0], parsed_question[1]):
                answer = answer['answerLabel']['value']
                try:
                    date = datetime.strptime(answer, '%Y-%m-%dT%H:%M:%SZ')
                    print(date.strftime('%m/%d/%Y'))
                except ValueError:
                    print(answer)

        except NoAnswerError as err:
            print(err)

    def parse_question(self, question):
        result = self.nlp(question)
        results = self.matcher(result)

        try:
            match_id, start, end = results[0]
        except IndexError:
            raise NoAnswerError('Question is ill-formed, cannot answer this question')

        if result.vocab.strings[match_id] == 'WHEN_WHERE':
            entity = [w.text for w in next(w for w in result if w.dep_ in ['nsubj', 'nsubjpass']).subtree]
            prop_one = result[0].lemma_
            prop_two = result[-1].lemma_
            prop = [prop_one, prop_two]

        elif result.vocab.strings[match_id] == 'X_OF_Y':
            prop_ent = next(w for w in result if w.dep_ == 'pobj')
            prop = [w.text for w in prop_ent.head.head.lefts] + [prop_ent.head.head.text]
            entity = [w.text for w in prop_ent.subtree]

        elif result.vocab.strings[match_id] == 'WHO_DID_X':
            prop = ['who', next(w for w in result if w.dep_ == 'ROOT').lemma_]
            entity = [w.text for w in result[end:]]

        prop = self.translate_query(prop)

        entity = ' '.join(w for w in entity if w not in self.stop_words)

        return prop, entity

    def translate_query(self, query):
        query = [w for w in query if w not in self.stop_words]
        new_query = ' '.join(query)  # default is to simply join the words

        # in some cases, the words in questions must be "translated"
        if 'members' in query:
            return 'has part'

        if len(query) < 2:
            return new_query

        if query[1] in ['direct', 'write', 'compose', 'invent']:
            if query[0] == 'who':
                new_query = self.trans_dict[query[1]]
            if query[0] == 'when':
                new_query = 'inception'

        elif query[1] in ['bear', 'die']:
            if query[0] == 'when':
                new_query = 'date of ' + self.trans_dict[query[1]]
            elif query[0] == 'where':
                new_query = 'place of ' + self.trans_dict[query[1]]

        elif query[1] == ['publish', 'release']:
            if query[0] == 'who':
                new_query = 'publisher'
            elif query[0] == 'when':
                new_query = 'publication date'

        return new_query

    def query_wikidata_api(self, string, prop_search=False):
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'search',
            'srsearch': unidecode(string),
            'srnamespace': 120 if prop_search else 0,
            'srlimit': 5,
            'srprop': '',
        }

        results = get(self.wiki_api_url, params).json()['query']['search']

        if results:
            return [res['title'][9:] if prop_search else res['title'] for res in results]

        return None

    def query_answer(self, prop, entity):
        wikidata_props = self.query_wikidata_api(prop, True)
        wikidata_entities = self.query_wikidata_api(entity)

        if wikidata_props is None or wikidata_entities is None:
            raise NoAnswerError

        for wikidata_entity in wikidata_entities:
            for wikidata_prop in wikidata_props:
                query_string = (
                    'SELECT ?answerLabel WHERE {{ '
                    '  wd:{} wdt:{} ?answer . '
                    '  SERVICE wikibase:label {{ '
                    '    bd:serviceParam wikibase:language "en" .'
                    '  }}'
                    '}}'.format(wikidata_entity, wikidata_prop)
                )

                self.sparql.setQuery(query_string)
                self.sparql.setReturnFormat(JSON)
                results = self.sparql.query().convert()['results']['bindings']

                if not results:
                    continue

                return results

        raise NoAnswerError


def main():
    print('Loading up QA System...')
    qa_system = QuestionSolver()
    print('Ready to go!\n')

    # print example questions
    print('Example questions:')
    print('{:-^60}'.format(''))
    question_list = [
        'What is the highest note of a piano?',
        'When was Michael Jackson born?',
        'What is the release date of Michael Buble\'s Christmas?',
        'Who composed the St Matthew Passion?',
        'Who is the mother of Elvis Presley?',
        'Who invented the Saxophone?',
        'When were the Jackson Five founded?',
        'Who are the members of Imagine Dragons?',
        'Who wrote Harry Potter?',
        'Where did David Bowie die?',
    ]

    for question in question_list:
        print(question)

    print('\nPlease ask a question:\n')

    # answer questions from standard input
    for line in stdin:
        print(line)
        qa_system.answer_question(line)
        print('')


if __name__ == '__main__':
    main()
