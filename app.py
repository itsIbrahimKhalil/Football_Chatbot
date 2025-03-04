import streamlit as st
import requests
import json
import re
import pandas as pd
from datetime import datetime, timedelta

# Configuration
# API Keys
llm_api_key = st.secrets["api_keys"]["GEMINI_API_KEY"]
data_key = st.secrets["api_keys"]["FOOTBALL_API_KEY"]
# API Base URLs
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
FOOTBALL_BASE_URL = "https://api.football-data.org/v4"

# API Endpoints mapping
ENDPOINTS = [
    {
        "description": "Get information about a specific area (country/region)",
        "endpoint": "/areas/{id}",
        "method": "GET",
        "params": ["id"],
        "filters": []
    },
    {
        "description": "List all available areas (countries/regions)",
        "endpoint": "/areas/",
        "method": "GET",
        "params": [],
        "filters": []
    },
    {
        "description": "Get information about a specific competition (league/tournament)",
        "endpoint": "/competitions/{id}",
        "method": "GET",
        "params": ["id"],
        "filters": []
    },
    {
        "description": "List all available competitions (leagues/tournaments)",
        "endpoint": "/competitions/",
        "method": "GET",
        "params": [],
        "filters": ["areas"]
    },
    {
        "description": "Get standings/league table for a competition",
        "endpoint": "/competitions/{id}/standings",
        "method": "GET",
        "params": ["id"],
        "filters": ["matchday", "season", "date"]
    },
    {
        "description": "Get matches for a specific competition",
        "endpoint": "/competitions/{id}/matches",
        "method": "GET",
        "params": ["id"],
        "filters": ["dateFrom", "dateTo", "stage", "status", "matchday", "group", "season"]
    },
    {
        "description": "Get teams participating in a specific competition",
        "endpoint": "/competitions/{id}/teams",
        "method": "GET",
        "params": ["id"],
        "filters": ["season"]
    },
    {
        "description": "Get top scorers for a specific competition",
        "endpoint": "/competitions/{id}/scorers",
        "method": "GET",
        "params": ["id"],
        "filters": ["limit", "season"]
    },
    {
        "description": "Get information about a specific team",
        "endpoint": "/teams/{id}",
        "method": "GET",
        "params": ["id"],
        "filters": []
    },
    {
        "description": "List teams with pagination",
        "endpoint": "/teams/",
        "method": "GET",
        "params": [],
        "filters": ["limit", "offset"]
    },
    {
        "description": "Get matches for a specific team",
        "endpoint": "/teams/{id}/matches/",
        "method": "GET",
        "params": ["id"],
        "filters": ["dateFrom", "dateTo", "season", "competitions", "status", "venue", "limit"]
    },
    {
        "description": "Get information about a specific person (player/coach)",
        "endpoint": "/persons/{id}",
        "method": "GET",
        "params": ["id"],
        "filters": []
    },
    {
        "description": "Get matches for a specific person (player/coach)",
        "endpoint": "/persons/{id}/matches",
        "method": "GET",
        "params": ["id"],
        "filters": ["dateFrom", "dateTo", "status", "competitions", "limit", "offset"]
    },
    {
        "description": "Get information about a specific match",
        "endpoint": "/matches/{id}",
        "method": "GET",
        "params": ["id"],
        "filters": []
    },
    {
        "description": "List matches across competitions",
        "endpoint": "/matches",
        "method": "GET",
        "params": [],
        "filters": ["competitions", "ids", "dateFrom", "dateTo", "status", "date"]
    },
    {
        "description": "Get head-to-head statistics for teams in a match",
        "endpoint": "/matches/{id}/head2head",
        "method": "GET",
        "params": ["id"],
        "filters": ["limit", "dateFrom", "dateTo", "competitions"]
    }
]

# Competition codes mapping (for common leagues)
COMPETITION_CODES = {
    "premier league": "PL",
    "la liga": "PD",
    "bundesliga": "BL1",
    "serie a": "SA",
    "ligue 1": "FL1",
    "eredivisie": "DED",
    "primeira liga": "PPL",
    "championship": "ELC",
    "champions league": "CL",
    "uefa champions league": "CL",
    "europa league": "EL",
    "uefa europa league": "EL",
    "world cup": "WC",
    "fifa world cup": "WC",
    "european championship": "EC",
    "uefa european championship": "EC",
    "copa libertadores": "CLI"
}

# Status mapping for natural language to API format
STATUS_MAPPING = {
    "scheduled": "SCHEDULED",
    "live": "LIVE",
    "in play": "IN_PLAY",
    "paused": "PAUSED",
    "finished": "FINISHED",
    "postponed": "POSTPONED",
    "suspended": "SUSPENDED",
    "cancelled": "CANCELLED"
}

# Time-related keywords
TIME_KEYWORDS = {
    "yesterday": -1,
    "today": 0,
    "tomorrow": 1
}

def parse_date_from_query(query):
    """
    Extract date information from the user query.
    Returns a tuple (date_str, date_type) where date_type is 'specific', 'relative', or None.
    """
    query_lower = query.lower()

    # Check for relative date keywords
    for keyword, days_offset in TIME_KEYWORDS.items():
        if keyword in query_lower:
            date = datetime.now() + timedelta(days=days_offset)
            return date.strftime("%Y-%m-%d"), 'relative'

    # Try to find a specific date in the query using regex
    date_patterns = [
        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
        r'(\d{2}-\d{2}-\d{4})',  # DD-MM-YYYY
        r'(\d{2}/\d{2}/\d{4})',  # DD/MM/YYYY
        r'(\d{2}/\d{2}/\d{2})'   # DD/MM/YY
    ]

    for pattern in date_patterns:
        match = re.search(pattern, query)
        if match:
            date_str = match.group(1)
            # Try to parse and standardize the date format
            try:
                if pattern == r'(\d{4}-\d{2}-\d{2})':
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                elif pattern == r'(\d{2}-\d{2}-\d{4})':
                    date = datetime.strptime(date_str, "%d-%m-%Y")
                elif pattern == r'(\d{2}/\d{2}/\d{4})':
                    date = datetime.strptime(date_str, "%d/%m/%Y")
                elif pattern == r'(\d{2}/\d{2}/\d{2})':
                    date = datetime.strptime(date_str, "%d/%m/%y")
                return date.strftime("%Y-%m-%d"), 'specific'
            except ValueError:
                continue

    return None, None

def get_matches_by_date(date_str):
    """Get matches for a specific date"""
    url = f"{FOOTBALL_BASE_URL}/matches"
    headers = {"X-Auth-Token": data_key}
    params = {"date": date_str}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error: {response.status_code}\n{response.text}")
        return {"error": f"API Error: {response.status_code}"}

def format_matches_data(matches_data):
    """Format matches data into a structured format"""
    if not matches_data or 'matches' not in matches_data or 'error' in matches_data:
        return {"error": "No matches found or error in data"}

    formatted_matches = []
    for match in matches_data['matches']:
        match_info = {
            'competition': match['competition']['name'],
            'homeTeam': match['homeTeam']['shortName'],
            'awayTeam': match['awayTeam']['shortName'],
            'status': match['status'],
            'date': match['utcDate']
        }

        # Add score if available
        if 'score' in match and match['score']['fullTime']['home'] is not None:
            match_info['score'] = f"{match['score']['fullTime']['home']} - {match['score']['fullTime']['away']}"
        else:
            match_info['score'] = 'Not played yet'

        formatted_matches.append(match_info)

    return {"matches": formatted_matches, "count": len(formatted_matches)}

def handle_date_based_query(query):
    """Handle queries specifically related to matches on a certain date"""
    date_str, date_type = parse_date_from_query(query)

    if not date_str:
        return None

    # Get the matches for the specified date
    matches_data = get_matches_by_date(date_str)

    # Format the matches data
    formatted_data = format_matches_data(matches_data)

    # Add context about the date
    if date_type == 'relative':
        for keyword, days_offset in TIME_KEYWORDS.items():
            if keyword in query.lower():
                formatted_data["date_context"] = keyword
                break
    else:
        formatted_data["date_context"] = date_str

    return formatted_data

teams_json = json.dumps({
    "PL": {
        "Arsenal FC": 57, "Aston Villa FC": 58, "Chelsea FC": 61, "Everton FC": 62, "Fulham FC": 63, 
        "Liverpool FC": 64, "Manchester City FC": 65, "Manchester United FC": 66, "Newcastle United FC": 67, 
        "Tottenham Hotspur FC": 73, "Wolverhampton Wanderers FC": 76, "Leicester City FC": 338, 
        "Southampton FC": 340, "Ipswich Town FC": 349, "Nottingham Forest FC": 351, 
        "Crystal Palace FC": 354, "Brighton & Hove Albion FC": 397, "Brentford FC": 402, 
        "West Ham United FC": 563, "AFC Bournemouth": 1044
    },
    "PD": {
        "Athletic Club": 77, "Club Atlético de Madrid": 78, "CA Osasuna": 79, "RCD Espanyol de Barcelona": 80,
        "FC Barcelona": 81, "Getafe CF": 82, "Real Madrid CF": 86, "Rayo Vallecano de Madrid": 87, 
        "RCD Mallorca": 89, "Real Betis Balompié": 90, "Real Sociedad de Fútbol": 92, "Villarreal CF": 94,
        "Valencia CF": 95, "Real Valladolid CF": 250, "Deportivo Alavés": 263, "UD Las Palmas": 275,
        "Girona FC": 298, "RC Celta de Vigo": 558, "Sevilla FC": 559, "CD Leganés": 745
    },
    "BL1": {
        "TSG 1899 Hoffenheim": 2, "Bayer 04 Leverkusen": 3, "Borussia Dortmund": 4, "FC Bayern München": 5,
        "VfB Stuttgart": 10, "VfL Wolfsburg": 11, "SV Werder Bremen": 12, "FSV Mainz 05": 15, 
        "FC Augsburg": 16, "SC Freiburg": 17, "Borussia Mönchengladbach": 18, "Eintracht Frankfurt": 19,
        "FC St. Pauli 1910": 20, "FC Union Berlin": 28, "VfL Bochum 1848": 36, "FC Heidenheim 1846": 44,
        "Holstein Kiel": 720, "RB Leipzig": 721
    },
    "SA": {
        "AC Milan": 98, "ACF Fiorentina": 99, "AS Roma": 100, "Atalanta BC": 102, "Bologna FC 1909": 103,
        "Cagliari Calcio": 104, "Genoa CFC": 107, "FC Internazionale Milano": 108, "Juventus FC": 109, 
        "SS Lazio": 110, "Parma Calcio 1913": 112, "SSC Napoli": 113, "Udinese Calcio": 115, "Empoli FC": 445,
        "Hellas Verona FC": 450, "Venezia FC": 454, "Torino FC": 586, "US Lecce": 5890, "AC Monza": 5911,
        "Como 1907": 7397
    },
    "FL1": {
        "Toulouse FC": 511, "Stade Brestois 29": 512, "Olympique de Marseille": 516, "Montpellier HSC": 518,
        "AJ Auxerre": 519, "Lille OSC": 521, "OGC Nice": 522, "Olympique Lyonnais": 523, "Paris Saint-Germain FC": 524,
        "AS Saint-Étienne": 527, "Stade Rennais FC 1901": 529, "Angers SCO": 532, "Le Havre AC": 533,
        "FC Nantes": 543, "Racing Club de Lens": 546, "Stade de Reims": 547, "AS Monaco FC": 548,
        "RC Strasbourg Alsace": 576
    },
    "DED": {
        "FC Twente '65": 666, "Heracles Almelo": 671, "Willem II Tilburg": 672, "SC Heerenveen": 673, "PSV": 674,
        "Feyenoord Rotterdam": 675, "FC Utrecht": 676, "FC Groningen": 677, "AFC Ajax": 678, "NAC Breda": 681,
        "AZ": 682, "RKC Waalwijk": 683, "PEC Zwolle": 684, "Go Ahead Eagles": 718, "Almere City FC": 1911,
        "NEC": 1915, "Fortuna Sittard": 1920, "Sparta Rotterdam": 6806
    },
    "CL": {
        "Bayer 04 Leverkusen": 3, "Borussia Dortmund": 4, "FC Bayern München": 5, "VfB Stuttgart": 10,
        "Arsenal FC": 57, "Aston Villa FC": 58, "Liverpool FC": 64, "Manchester City FC": 65,
        "Club Atlético de Madrid": 78, "FC Barcelona": 81, "Real Madrid CF": 86, "AC Milan": 98,
        "Atalanta BC": 102, "Bologna FC 1909": 103, "FC Internazionale Milano": 108, "Juventus FC": 109,
        "Girona FC": 298, "Sporting Clube de Portugal": 498, "Stade Brestois 29": 512, "Lille OSC": 521,
        "Paris Saint-Germain FC": 524, "AS Monaco FC": 548, "PSV": 674, "Feyenoord Rotterdam": 675,
        "RB Leipzig": 721, "Celtic FC": 732, "GNK Dinamo Zagreb": 755, "Club Brugge KV": 851,
        "AC Sparta Praha": 907, "BSC Young Boys": 1871, "FC Red Bull Salzburg": 1877,
        "FK Shakhtar Donetsk": 1887, "Sport Lisboa e Benfica": 1903, "SK Sturm Graz": 2021,
        "FK Crvena Zvezda": 7283, "ŠK Slovan Bratislava": 7509
    }
})

def ask_gemini_for_endpoint(query):
    """Use Gemini API to determine the most appropriate endpoint based on user query"""
    
    # Get current date and time formatted as YYYY-MM-DD HH:MM:SS
    current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    endpoints_json = json.dumps(ENDPOINTS)
    competition_codes_json = json.dumps(COMPETITION_CODES)
    
    prompt = f"""
    You are an expert football data API assistant. Your task is to determine the most appropriate API endpoint to use from the list provided below based on the user's query. The endpoints, along with their details (HTTP method, required path parameters, and supported filters), are given in the JSON below:
    {endpoints_json}
    The following conditions must be fulfilled no matter what:
    - If team id not specified or calculated, do not use the dateto and datefrom filters.
    Current Date and Time: {current_datetime}
    ### **Available Teams and IDs**
    The following JSON contains teams mapped to their respective IDs across various leagues:
    {teams_json}
    Analyze the user's query carefully and decide which endpoint best fits the request. Also, extract any necessary path parameters and query filters with their appropriate values. Make sure:
    
    - To only include parameters and filters that are supported by the chosen endpoint.
    - For path parameters (e.g., "id"), provide a valid value. If the endpoint expects a competition code, map common names (e.g., "Premier League") to their code (e.g., "PL") using the following mapping: {competition_codes_json}.
    - For date filters, ensure the date is formatted as YYYY-MM-DD.
    - For status filters, use the correct API status value (e.g., "SCHEDULED", "LIVE", "FINISHED", etc.) based on the input query.
    - Do not include any extra parameters or filters that are not defined for the selected endpoint.
    - If a parameter or filter is not mentioned or needed, return an empty object for that field.
    - Oldest DateFrom which can be used is 2023-07-01
    - Some examples:
      - For next 10 matches of a team: Full URL: https://api.football-data.org/v4/teams/id/matches/
        Parameters: {{'status': 'SCHEDULED', 'limit': '10'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - All matches of Barcelona in the 2023 season: Full URL: https://api.football-data.org/v4/teams/81/matches/
        Parameters: {{'season': '2023'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - PL Standings of 2023 season: Full URL: https://api.football-data.org/v4/competitions/PL/standings
        Parameters: {{'season': '2023'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - Current Standings of PL: Full URL: https://api.football-data.org/v4/competitions/PL/standings
      - Matches of Real Madrid from 1st Jan 2025 to 3rd March 2025: Full URL: https://api.football-data.org/v4/teams/86/matches
        Parameters: {{ 'dateFrom': '2025-01-01','dateTo': '2025-03-03'}} (Date Format: YYYY-MM-DD). Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - List all available competitions: Full URL: https://api.football-data.org/v4/competitions/
      - Get details of UEFA Champions League (UCL): Full URL: https://api.football-data.org/v4/competitions/CL
      - Top 20 goalscorers of Laliga in 2023 season: url = 'https://api.football-data.org/v4/competitions/PD/scorers'
        Parameters = {{'season': '2023','limit': '20'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - Show last 5 matches of Bayern Munich: Full URL: https://api.football-data.org/v4/teams/5/matches/
        Parameters: {{'status': 'FINISHED', 'limit': '5'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - Get the upcoming matches for AC Milan: Full URL: https://api.football-data.org/v4/teams/98/matches/
        Parameters: {{'status': 'SCHEDULED'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - List all teams in the Bundesliga for the 2023 season: Full URL: https://api.football-data.org/v4/competitions/BL1/teams
        Parameters: {{'season': '2023'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - Find the matches happening today in Serie A: Full URL: https://api.football-data.org/v4/competitions/SA/matches
        Parameters: {{'dateFrom': '2025-03-04', 'dateTo': '2025-03-04'}}. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - Get head-to-head stats of the last 5 El Clásico matches: Full URL: https://api.football-data.org/v4/teams/id/matches/
        Then llm should be able to find instances where Real madrid and fc barcelona played. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - What was the score of last real madrid vs manchester city?  Full URL: https://api.football-data.org/v4/teams/id/matches/
        Then llm should be able to find instances where Real madrid and Manchester City played. Note: - Critical Importance: If dateTo is used, dateFrom also needs to be used. If dateFrom is used, dateTo also needs to be used. One can not be without the other.
      - Find the latest match of Manchester United: Full URL: https://api.football-data.org/v4/teams/66/matches/
        Parameters: {{'status': 'FINISHED', 'limit': '1'}}
      - Scores of the playoff round of UCL: Full URL: https://api.football-data.org/v4/competitions/CL/matches
        Parameters: {{'stage': 'PLAYOFFS'}}
      - Find all matches of Arsenal in 2024: Full URL: https://api.football-data.org/v4/teams/57/matches/
        Parameters: {{'season': '2024'}}
      - Show fixtures of the next matchday of Premier League: Full URL: https://api.football-data.org/v4/competitions/PL/matches 
        Parameters: {{'status': 'SCHEDULED'}}

    Your response should be a valid JSON object with exactly the following keys:
    - "endpoint": the endpoint path to use (for example, "/competitions/{id}/matches")
    - "params": an object mapping path parameter names to their values (or an empty object if none)
    - "filters": an object mapping query filter names to their values (or an empty object if none)
    - "explanation": a brief explanation of why this endpoint was chosen and how parameters were determined
    
    Make sure the JSON is correctly formatted and does not include any markdown formatting.
    
    User query: "{query}"
    """
    
    try:
        response = requests.post(
            f"{GEMINI_URL}?key={llm_api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
        )

        response.raise_for_status()
        result = response.json()

        # Extract the JSON from the Gemini response
        json_text = result["candidates"][0]["content"]["parts"][0]["text"]

        # Extract JSON object using regex (in case there's markdown formatting)
        json_match = re.search(r'```json\s*(.*?)\s*```', json_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find just a JSON object
            json_match = re.search(r'({.*})', json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)

        return json.loads(json_text)

    except Exception as e:
        st.error(f"Error asking Gemini for endpoint: {e}")
        return None

def make_football_api_call(endpoint_info):
    """Make the actual API call to the football data API"""
    try:
        # Build the URL
        endpoint = endpoint_info["endpoint"]

        # Replace parameter placeholders in the URL
        if "params" in endpoint_info and endpoint_info["params"]:
            for param, value in endpoint_info["params"].items():
                # Handle competition codes mapping
                if param == "id" and endpoint.startswith("/competitions/"):
                    value = value.upper() if len(value) <= 3 else value
                    # Try to map competition name to code
                    if value.lower() in COMPETITION_CODES:
                        value = COMPETITION_CODES[value.lower()]
                endpoint = endpoint.replace(f"{{{param}}}", str(value))

        url = f"{FOOTBALL_BASE_URL}{endpoint}"

        # Add query parameters
        params = {}
        if "filters" in endpoint_info and endpoint_info["filters"]:
            for filter_name, value in endpoint_info["filters"].items():
                # Handle date formatting
                if filter_name in ["date", "dateFrom", "dateTo"] and value:
                    try:
                        date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"]
                        parsed_date = None
                        for fmt in date_formats:
                            try:
                                parsed_date = datetime.strptime(value, fmt)
                                break
                            except ValueError:
                                continue
                        if parsed_date:
                            value = parsed_date.strftime("%Y-%m-%d")
                    except:
                        pass
                # Handle status mapping
                if filter_name == "status" and value.lower() in STATUS_MAPPING:
                    value = STATUS_MAPPING[value.lower()]
                params[filter_name] = value

        response = requests.get(
            url,
            headers={"X-Auth-Token": data_key},
            params=params
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:
        st.error(f"Error making football API call: {e}")
        return {"error": str(e)}

def format_response_with_gemini(query, data, data_type="api_response"):
    """Use Gemini to format the API response into a natural language response"""
    try:
        data_str = json.dumps(data, ensure_ascii=False)
        if len(data_str) > 10000:
            data_str = data_str[:10000] + "..."
        if data_type == "date_matches":
            prompt = f"""
            You are a football chatbot assistant that provides information about football matches.
            The user asked: "{query}"
            We found the following matches data for the date they mentioned:
            {data_str}
            Please format this information into a helpful, conversational response for the user.
            If there's an error or no matches found, explain what might have gone wrong.
            If matches were found, organize them by competition and include the score if available.
            Be concise but comprehensive, and present the information in an easy-to-read format.
            If a specific date was mentioned, include that in your response.
            """
        else:
            endpoint_info = data.get("endpoint_info", {})
            api_response = data.get("api_response", {})
            prompt = f"""
            You are a football chatbot assistant that provides information from a football data API.
            The user asked: "{query}"
            Based on their question, we queried the following API endpoint:
            {endpoint_info.get("endpoint", "Unknown endpoint")}
            The API returned the following response:
            {json.dumps(api_response, ensure_ascii=False)}
            Please format this information into a helpful, conversational response for the user.
            Focus on directly answering their question with the most relevant information.
            If there's an error or no relevant data, explain what might have gone wrong.
            Be concise but comprehensive, and present the information in an easy-to-read format when appropriate.
            """
        response = requests.post(
            f"{GEMINI_URL}?key={llm_api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
        )
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        st.error(f"Error formatting response with Gemini: {e}")
        return f"I'm sorry, but I encountered an error processing the football data. Error: {e}"

def chatbot_response(query):
    """Main function to process user query and return a response"""
    # First, check if it's a date-based query
    date_matches = handle_date_based_query(query)
    if date_matches:
        return format_response_with_gemini(query, date_matches, "date_matches")
    
    # Regular flow: determine endpoint, call API, and format response
    endpoint_info = ask_gemini_for_endpoint(query)
    if not endpoint_info:
        return "I'm sorry, but I couldn't determine how to process your request. Could you try rephrasing your question?"
    
    api_response = make_football_api_call(endpoint_info)
    return format_response_with_gemini(query, {"endpoint_info": endpoint_info, "api_response": api_response})

def get_date_range_matches(date_from, date_to):
    """Get matches for a date range"""
    url = f"{FOOTBALL_BASE_URL}/matches"
    headers = {"X-Auth-Token": data_key}
    params = {"dateFrom": date_from, "dateTo": date_to}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error: {response.status_code}\n{response.text}")
        return {"error": f"API Error: {response.status_code}"}

def display_matches_dataframe(matches_data):
    """Convert matches data to a pandas DataFrame for display"""
    if not matches_data or 'matches' not in matches_data or len(matches_data['matches']) == 0:
        return pd.DataFrame()
    formatted_matches = []
    for match in matches_data['matches']:
        match_info = {
            'Competition': match['competition']['name'],
            'Home Team': match['homeTeam']['shortName'],
            'Away Team': match['awayTeam']['shortName'],
            'Status': match['status'],
            'Date': match['utcDate']
        }
        if 'score' in match and match['score']['fullTime']['home'] is not None:
            match_info['Score'] = f"{match['score']['fullTime']['home']} - {match['score']['fullTime']['away']}"
        else:
            match_info['Score'] = 'Not played yet'
        formatted_matches.append(match_info)
    df = pd.DataFrame(formatted_matches)
    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d %H:%M')
    return df

# ------------------- Streamlit Interface -------------------

st.title("Football Chatbot Assistant")
st.write("Ask about football matches, standings, teams, and more!")

# Input text area for the user's query
user_query = st.text_area("Enter your football query here:")

if st.button("Submit"):
    if user_query.strip() == "":
        st.warning("Please enter a query to continue.")
    else:
        st.write("Processing your request...")
        # Get the chatbot response (this might take a few seconds depending on API response times)
        response_text = chatbot_response(user_query)
        st.markdown("### Response:")
        st.write(response_text)

        # Optional: If the query is date-based and you want to display the matches in a table
        date_info = parse_date_from_query(user_query)
        if date_info[0]:
            matches_data = get_matches_by_date(date_info[0])
            df_matches = display_matches_dataframe(matches_data)
            if not df_matches.empty:
                st.write("### Matches Data")
                st.dataframe(df_matches)
            else:
                st.info("No match data available for the specified date.")
