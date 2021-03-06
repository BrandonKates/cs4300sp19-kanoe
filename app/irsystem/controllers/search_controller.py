from . import *
from app.irsystem.models.helpers import *
from app.irsystem.models.helpers import NumpyEncoder as NumpyEncoder
from nltk.tokenize import RegexpTokenizer
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import numpy as np
import os
import requests
import pickle
import math
import nltk
import inspect
nltk.download("stopwords")
nltk.download("averaged_perceptron_tagger")
nltk.download("vader_lexicon")
from nltk.corpus import stopwords

sid = SentimentIntensityAnalyzer()

stops = set(stopwords.words('english'))

dirpath = os.getcwd()
data_files = dirpath + "/app/static/data/"
tfidf_files = data_files + "tfidf_data/"
inv_idx = np.load(tfidf_files+"inv_idx.npy").item()
idf = np.load(tfidf_files+"idf_dict.npy").item()
doc_norms = np.load(tfidf_files+"doc_norms.npy").item()
json_data = data_files + "data_jsons/"
urban_rural = np.load(data_files+"urban_cities.npy").item()
climate = np.load(data_files+"city_climates.npy").item()

ps = PorterStemmer()

kmeans_att = pickle.load(open(os.path.join(data_files, "kmeans_att.pickle"), 'rb'))
kmeans_dest = pickle.load(open(os.path.join(data_files, "kmeans_dest.pickle"), 'rb'))

project_name = "Kanoe"
net_id = """Alex Styler (ams698), Brandon Kates (bjk224), David Marchena (dpm247),
	Noam Eshed (ne236), Sofia Nieves (sn529)"""

@irsystem.route('/', methods=['GET','POST'])
def search():
	"""
	Main search function which gets sorted city data and returns
	the top cities for the query. For each city, it also returns top attractions
	located there.
	"""
	query, price, purpose, climate, urban, numLocs, currentLoc = get_inputs()
	
	
	# Stem query words:
	stem_query = ''
	stem_dict = {}

	for term in query.lower().replace(',',' ').split():
		if term not in stops:
			s = ps.stem(term)
			stem_query += str(s + " ")
			stem_dict[s] = term
	
	output_message = ""
	if len(np.unique(stem_query.split(" "))) == 1:
		data = []
	else:
		data = []
		
		# Get city suggestions sorted by tf-idf score
		results, term_tfidf_scores, term_percents = index_search(stem_query, inv_idx, idf, doc_norms)
		if len(results) == 0:
			output_message = "No Results Found"
			
		# Score modifiers based on urban and climate inputs
		for i, (city, score) in enumerate(results):
			# Increase score if rural/urban as user specified
			if (urban==0 and is_urban(city)==0) or (urban==2 and is_urban(city)==2):
				score *= 2
				
			# Increase score if correct climate
			if climate != "" and climate == get_climate(city) and get_climate(city) is not None:
				score *= 2
				
			results[i] = (city, score)
		
		sorted_results = sorted(results, key=lambda x: x[1], reverse=True)

		for city, score in sorted_results:
			
			data_dict = {}
			
			# Get city attraction information
			city_info  = organize_city_info(climate, urban, city, json_data, stem_query, stem_dict, 3, price, purpose)
			city_info['city'] = city
			city_info['score'] = score
			city_info['tfidf_breakdown'] = term_tfidf_scores[city]
			city_info['term_percents'] = term_percents[city]
			
			if city_info.get("overall_attractionscore") is None:
				city_info["overall_attractionscore"] = 0
            
			data.append(city_info)

			numLocs -= 1
			if numLocs == 0:
				break
		#print(data)
		data = sorted(data, key = lambda x: (x['overall_attractionscore'] + x['score'])/2, reverse = True)
		for city in data:
			print(city['overall_attractionscore'])
		#	overall_attractionscore = 0
		#	for attraction in city['attractions']:
		#		num_reviews += len(attraction['reviews'])
	lat = 0
	lon = 0


	if currentLoc != None and len(currentLoc) == 2:
		lat = currentLoc[0]
		lon = currentLoc[1]


	return render_template('search.html', name=project_name, netid=net_id, output_message=output_message, data=data, sim_city_dict = kmeans_dest, sim_att_dict = kmeans_att, latitude = lat, longitude = lon)

def get_inputs():
	"""
	Read and process inputs from the user query & search
	"""
	query = request.args.get('search')
	if query == None:
		query = ""
	price = request.args.get('price')
	if price == None:
		price = ""
	purpose = request.args.get('purpose')
	if purpose == None:
		purpose = ""
	climate = request.args.get('climate')
	if climate == None:
		climate = ""
	urban = request.args.get('urban')
	if urban == None:
		urban = 1
	urban = int(urban)
	numLocs = request.args.get('numberLocs')
	if numLocs == None or numLocs == '':
		numLocs = 4
	numLocs = int(numLocs)
	currentLoc = request.args.get('currentloc')

	if currentLoc == None or len(currentLoc.strip().split(",")) != 2:
		currentLoc = None
	else:
		currentLoc =  currentLoc.strip().split(",")

	return query, price, purpose, climate, urban, numLocs, currentLoc


def organize_city_info(climate, urban, city, folder, query, stemmer, num_attrs, price, purpose):
	"""
	For a city, find and sort relevant attractions
	Adjust scores based on advanced search inputs
	Return the top attractions for a city
	"""
	data = get_city_info(city, folder)	# Read city data

	num_attrs = min(data['size'], num_attrs)

	output_dict = {}
	output_dict['country'] = data['country']
	if output_dict['country'] != output_dict['country']:	#check if nan
		output_dict['country'] = ''

	output_dict['attractions'] = []

	attractions = data['attractions']
	attrac_scores = []
	# Calculate score for each attraction
	for key, value in attractions.items():
		if value is not None:
			attractions[key]['name'] = key
			score = attraction_score(query, value['description'])
			cost_match = price == data['attractions'][key]['cost']
			# Weigh score if cost and/or purpose match advanced search
			if price != "" and cost_match:
				score *= 2
			purpose_match = purpose in set(data['attractions'][key]['purpose'])
			
			if purpose != "" and  purpose_match:
				score *= 2
			attrac_scores.append((key, score))

	
	# Sort by decreasing score
	sorted_scores = sorted(attrac_scores, key=lambda x: x[1], reverse=True)

	# Save & return the top reviews
	for i in range(num_attrs):
		if i >= len(sorted_scores): break
		(name, score) = sorted_scores[i]
		
		# Find all matching terms b/w query and description
		matches = get_matching_terms(query, attractions[name]['description'], stemmer)
		matches_adv = matches_advanced(data, name, matches, price, purpose, climate, urban)
		attractions[name]['matches'] = matches_adv
		output_dict['attractions'].append(attractions[name])

	# Get reviews for each attraction
	api_key = "AIzaSyCJiRPAPsSLaY46PvyNxzISQMXFZx6h-g8"
	tokenizer = RegexpTokenizer(r"\w+")
	grammar = "NP: {<DT>?<JJ>*<NN>}"
	parser = nltk.RegexpParser(grammar)
	
	#the way the parser is set up, the only subtrees are noun phrases
	is_np = lambda phr: str(type(phr)) == "<class 'nltk.tree.Tree'>"
	
	for att in range(len(output_dict['attractions'])):
		place_id = output_dict['attractions'][att]['place_id']
		if place_id is not None and place_id != 'not found':
			#reviews = [{'reviews':["Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."]}]
			reviews = get_reviews(place_id, api_key).get('result')
			output_dict['attractions'][att]['reviews'] = reviews
			phrases = []
			#get noun phrases from reviews
			if reviews.get('reviews') is not None:
				for r in reviews['reviews']:
					tokenized_review = tokenizer.tokenize(r['text'])
					tagged_review = nltk.pos_tag(tokenized_review)
					parsed_review = parser.parse(tagged_review)
					parsed_review = [phrase.leaves() for phrase in parsed_review if is_np(phrase)]
					for phrase in parsed_review:
						words_only = [word for word,pos in phrase]
						if len(words_only) >= 2:
							np = " ".join(words_only)
							phrases.append(np)
						
			#get rid of duplicate phrases and sort by sentiment polarity score
			phrases = set(phrases)
			phrases = [(phrase, sid.polarity_scores(phrase)['compound']) for phrase in phrases]
			phrases = sorted(phrases, key = lambda x: x[1], reverse = True)
			
			overall_score = 0
			
			if len(phrases) > 0:
				overall_score = sum(n for _,n in phrases)/len(phrases)
			
			
			output_dict['attractions'][att]['good-reviews'] = [phrase for phrase, score in phrases if score > 0.2]
			output_dict['attractions'][att]['bad-reviews'] = [phrase for phrase, score in phrases if score < -0.2]
			output_dict['overall_attractionscore'] = overall_score

	return output_dict
	

def get_climate(city):
	"""
	Read city climate from dictionary
	"""
	if city in climate.keys():
		return climate[city]
	else:
		return None

def is_urban(city):
	"""
	Return true for urban cities and false for non-urban
	cities based on population	
	"""
	urban = urban_rural.get(city)
	if urban is not None:
		return urban
	else:
		return 1
		
def get_city_info(city, folder):
	"""
	Read city file
	"""
	with open(folder+str(city) + '.json', 'r') as f:
		data = json.load(f)
		return data.get(city)

def attraction_score(query, desc):
	"""
	Calculates the similarity score between an attraction
	and the user query
	"""
	score = 0
	stemmed_desc = []
	for term in desc:
		stemmed_desc.append(ps.stem(term))

	if len(stemmed_desc) == 0:
		return 0
		
	for q in query.lower().split():
		for d in stemmed_desc:
			if (q in d) or (d in q):
				score += 1
	score /= len(stemmed_desc)
	return score
	
def get_matching_terms(query, desc, stemmer):
	"""
	Find the terms in the description that match the query
	"""
	matches_dict = {}
	stemmed_desc = [ps.stem(term) for term in desc]

	for q in query.lower().split():
		for d in stemmed_desc:
			if (q in d) or (d in q):
				full_term = stemmer[q]
				if full_term not in matches_dict:
					matches_dict[full_term] = 0
				matches_dict[full_term] += 1
				
	# Make into tuple list to sort
	matches_scores_list = [(key, matches_dict[key]) for key in matches_dict]
	sorted_tuples = sorted(matches_scores_list, key=lambda x:x[1], reverse=True)

	return [x[0] for x in sorted_tuples]

def matches_advanced(data, city, matches, price, purpose, climate, urban):	
	"""
	Checks for search matches in the advanced search inputs
	"""
	if price != "" and price == data['attractions'][city]['cost']:
		matches.append(price + ' price')
	for p in data['attractions'][city]['purpose']:
		if purpose != "" and purpose == p:
			matches.append('trip type: ' + p)
	if climate != "" and climate == get_climate(city):
		matches.append(climate + ' climate')
		
	# Urban scale from 0-2 in UI
	urban_poss = ['rural', 'urban']
	if urban == 1:
		urban = 2
	elif urban == 2:
		urban = 1
	if urban == is_urban(city):
		matches.append(urban_poss[urban])
	
	return matches
	

def index_search(query, index, idf, doc_norms):
    """ Search the collection of documents for the given query
    Arguments
    =========
    query: string, the query we are looking for.
    index: an inverted index
    idf: idf values
    doc_norms: document norms

    Returns
    =======
    results, list of tuples (score, doc_id)
        Sorted list of results such that the first element has
        the highest score, and `doc_id` points to the document
        with the highest score.

    Note:

    """
    # Initialize output dictionary, keys = cities, vals = scores
    scores_array = {}

    # Tokenize the query
    tokenizer = RegexpTokenizer(r"\w+")
    tokens = tokenizer.tokenize(query.lower())
    # Calculate tf of query
    q_tf = {}
    for t in tokens:
        if t not in q_tf.keys():
            q_tf[t] = 0
        q_tf[t] += 1

    # Calculate tf-idf vector of query
    q_tf_idf = []
    for k in q_tf.keys():
        if k in idf:
            q_tf_idf.append(q_tf[k]*idf[k])

    q_norm = np.sqrt(np.sum(np.square(q_tf_idf)))

    # Update the score once per token

    term_tfidf_scores = {}
    for t in tokens:
        # Skip if there are no docs containing the token
        if t not in index.keys():
            continue
        # Otherwise add the cossim score to output
        for (city, d_tf) in index[t]:
            if city not in scores_array:
                scores_array[city] = 0
                term_tfidf_scores[city] = {}
            # Fix this mysterious issue in the future
            #idf_t = idf[t]

            if idf.get(t) is not None:
                scores_array[city] += q_tf[t]*idf[t]*d_tf*idf[t]
                if t not in term_tfidf_scores[city]:
                    term_tfidf_scores[city][t] = 0
                term_tfidf_scores[city][t] += q_tf[t]*idf[t]*d_tf*idf[t]

    # Normalize
    for key in scores_array.keys():
        scores_array[key] /= doc_norms[key]*q_norm+1
        for term in term_tfidf_scores[key]:
            term_tfidf_scores[key][term] /= doc_norms[key]*q_norm+1

    # Put in output form as list (city, score)
    output_results = []
    for key in scores_array.keys():
        output_results.append((key, scores_array[key]))
    output_results.sort(key = lambda t: t[1], reverse=True)

    term_percents = {}
    for city in term_tfidf_scores:
        term_percents[city] = {}
        for t in term_tfidf_scores[city]:
            term_tfidf_scores[city][t] = round(term_tfidf_scores[city][t], 2)
            term_percents[city][t] = int(round(100*term_tfidf_scores[city][t]/scores_array[city]))
            
    return output_results, term_tfidf_scores, term_percents

def get_reviews(place_id, api_key):
	"""Gets reviews for a location based on its google place id"""
	reviews = requests.get("https://maps.googleapis.com/maps/api/place/details/json?placeid="+str(place_id)+"&language=en&fields=price_level,rating,review&key=" + api_key).json()
	return reviews