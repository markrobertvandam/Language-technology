#!/usr/bin/env python3

import spacy
import sys
import requests


def questionmaker(possible_properties,possible_entities,parse):
	place = 0
	for i in range(len(parse)):
		token = parse[i]
		if place > 0  and token.text != "is" and token.text != "are" and token.text != "was":
			if token.dep_ == "nsubj" or token.dep_ == "acomp" or (token.dep_ == "attr" and token.pos_=="NOUN"):
				try:
					if token.dep_ == "nsubj" and parse[i+1].text == "of" and parse[i+2].dep_ == "pobj":
						possible_properties.append(token.text + " " + parse[i+1].text + " " + parse[i+2].text)
					if parse[i+1].dep_ == "ROOT" or parse[i+1].pos_ == "NOUN":
						possible_entities.append(token.text + " " + parse[i+1].text)
					elif parse[i+1].dep_ == "acomp" and (parse[i+2].dep_ == "ROOT" or parse[i+2].pos_ == "NOUN"):
						possible_entities.append(token.text + " " + parse[i+1].text + " " + parse[i+2].text)
				except IndexError:
					pass
			if (token.dep_=="nsubj" or token.dep_ == "attr" or token.dep_ == "dobj"):
				if token.text == "members" or token.text == "member":
					possible_properties.append("has part")
				possible_properties.append(token.text)
			if token.dep_ == "pobj" or token.dep_ == "acomp" or token.dep_ == "pcomp" or token.dep_ == "ROOT":
				if token.dep_ == "pobj" and (parse[i-1].pos_ == "ADJ" or parse[i-1].dep_ == "amod"):
					possible_entities.insert(0,parse[i-1].text + " " + token.text)
				elif token.dep_ == "pobj" and parse[i-1].dep_ == "nummod" and parse[i-2].text == "the":
					possible_entities.insert(0,"the "+ parse[i-1].text + " " + token.text)
				elif token.dep_ == "pobj" and parse[i-1].text == "the":
					possible_entities.insert(0,"the "+ token.text)
				else:
					possible_entities.append(token.text)
			if token.dep_ == "compound" and parse[i+1].tag_.startswith("NN"):
				possible_entities.insert(0,token.text + " " + parse[i+1].text)
				possible_properties.append(token.text + " " + parse[i+1].text)
			if token.dep_ == "amod":
				try:
					if parse[i+1].dep_ == "nsubj" or parse[i+1].dep_ == "dobj":
						possible_properties.insert(0,token.text + " " + parse[i+1].text)
					elif (parse[i+1].dep_ == "amod" and parse[i+2].dep_ == "nsubj") or (parse[i+1].dep_ == "compound" and (parse[i+2].dep_ == "dobj" or parse[i+2].dep_ == "nsubj")):
						possible_properties.insert(0,token.text + " " + parse[i+1].text + " " + parse[i+2].text)	
				except IndexError:
					pass
		place+=1
	return(possible_properties,possible_entities)

def create_and_fire_query(property_list,entity_list):
	answer = ""
	url = 'https://www.wikidata.org/w/api.php'
	prop_params = {'action':'wbsearchentities','language':'en', 'format':'json', 'type':'property'}
	params = {'action':'wbsearchentities','language':'en', 'format':'json'}
	properties = []
	entities = []
	property_list.sort(key = len, reverse=True)
	for prop in property_list:
		prop_params['search'] = prop
		json = requests.get(url,prop_params).json()
		for result in json['search']:
			properties.append(result['id'])
	for entity in entity_list:
		params['search'] = entity
		json = requests.get(url,params).json()
		for result in json['search']:
			entities.append(result['id'])
	if len(entities) > 0 and len(properties) > 0:
		for i in range(len(entities)):
			for p in range(min(10,len(properties))):
				select_query = '''SELECT ?val ?valLabel
						WHERE {{wd:{0} wdt:{1} ?val.
						optional{{?val rdfs:label ?valLabel.
				    		FILTER(LANG(?valLabel) ="en")
						}}}}'''.format(entities[i],properties[p])
				data = requests.get('https://query.wikidata.org/sparql',params={'query': select_query, 'format': 'json'}).json()
				if (len(data['results']['bindings'])) > 0:
					for item in data['results']['bindings']:
						for var in item :
							if item[var]['value'].startswith("http://www.wikidata.org"):
								pass
							else:
								answer+='\n{}'.format(item[var]['value'])
					return(answer.lstrip())
					
			if i == len(entities) - 1:
				break
	elif len(properties) == 0:		
		new_properties = [prop[:-1] for prop in property_list if prop.endswith('s')]
		if len(new_properties) > 0:
			return(create_and_fire_query(new_properties,entity_list))
	return("Answer not found")

def main(argv):
	print("Loading spacy model..")
	nlp = spacy.load('en_core_web_sm')
	example_questions = ["Who is the CEO of Sony Music?", "Who are the members of the Beatles?", "Who was the composer of the moonlight sonata?","What are Queen its genres?", "What was the place of death of David Bowie?", "State Sun Studio its location.", "State Bono his birthname?", "State Elton John his sexuality.","Tell me te height of Roger Daltrey.", "Tell me the record labels of linkin park"]
	print("Example questions:")
	print("---------------------------")
	for example in example_questions:
		print(example)
	print("---------------------------\n\nAsk your question below:\n")
	for line in sys.stdin:
		parse = nlp(line.strip().lower())
		possible_properties,possible_entities = questionmaker([],[],parse)
		try:
			print(create_and_fire_query(possible_properties,possible_entities))
		except AttributeError:
			print("Please follow the proper question format\n")

if __name__ == '__main__':
    main(sys.argv)
