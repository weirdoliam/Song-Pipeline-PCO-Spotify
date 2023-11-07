import pypco
import datetime
import json
import os    
import spotipy
import Levenshtein
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()
# Get the vars
pco_id = os.getenv("PCO_ID")
pco_secret = os.getenv("PCO_SECRET")
spot_id = os.getenv("SPOT_ID")
spot_secret = os.getenv("SPOT_SECRET") 
retrieve_songs = False
path = os.getenv("HOME_PATH")
pco = pypco.PCO(pco_id, pco_secret)
service_types = []
service_types.append(json.loads(os.getenv("RKRPM")))
service_types.append(json.loads(os.getenv("RKRAM")))
service_types.append(json.loads(os.getenv("NTHAM")))
artist_library = ['activate', 'activate Music', 'equippers', 'equippers worship', 'equippers revolution', 'hillsong', 'elevation', 
                  'elevation band', 'elevation worship', 'maverick city', 'planetshakers', 'planet shakers', 'bethel', 'jesus culture', 'brandon lake']
activate_authors = ['dann','luke rogers','jaarsveld','wilson','paama']
equippers_authors = ['huirua','stephenson','michael watton', 'david darby']
activate_unreleased = ['watching over me','breakthrough is coming','you make all things good', 'here now']#incomplete
# Main function
def main():
    next_sun = get_date()
    refresh_songs()
    for service in service_types:
        name = str(service['name'])
        id = str(service['id'])
        playlist = str(service['playlist'])

        print(f"Generating playlist for: {name} at date: {next_sun}\n")
        names = get_pco_song_ids(next_sun, id)
        metadata = get_song_metadata(names)
        find_spotify_songs(metadata, next_sun, name, playlist)
    input("Press enter to end...")

def refresh_songs():
    # Refresh master song list
    if retrieve_songs:
        print("Refreshing master song list.")
        os.remove("songs.json")
        all_song_list = list()
        for song in pco.iterate("/services/v2/songs?order=-last_scheduled_at"):
            all_song_list.append(song)
        with open(path+"\\songs.json", 'w') as output:
            for song in all_song_list:
                output.write(f'{json.dumps(song)}\n')

def get_date():
    # Get the current date
    current_date = datetime.date.today()
    # Calculate the number of days until the next Sunday (0 = Monday, 1 = Tuesday, ..., 6 = Sunday)
    days_until_sunday = (6 - current_date.weekday() + 7) % 7
    # Calculate the date of the next Sunday
    changed = current_date + datetime.timedelta(days=days_until_sunday)
    next_sunday = str(changed)

    # Test week!
    #next_sunday = '2023-10-29'

    return next_sunday

def get_pco_song_ids(date, service_id):
    plan_id = None
    # Iterate through available services from most in future backwards until we find the right one
    for plan in pco.iterate(f'/services/v2/service_types/{service_id}/plans?order=-sort_date'):
        curr_service_date = f'{plan["data"]["attributes"]["sort_date"].split("T")[0]}'
        # if the plan we are currently on matches the identified date, use this service plan to find songs
        if curr_service_date == date:
            print("Found PCO plan which relates to next Sunday.")
            plan_id = plan['data']['id']
            break
    # RIP
    if plan_id == None:
        print("No plan found")
        exit(0)                
    song_list = list()
    # Iterate through each item of this plan, and identify the song IDs
    for item in pco.iterate(f'/services/v2/service_types/{service_id}/plans/{plan_id}/items'):
        if item['data']['attributes']['item_type'] == 'song':
            song_list.append(item['data']['relationships']['song']['data']['id'])
    return song_list

def get_song_metadata(songs):
    print("Retrieving song metadata")
    read_songs = list()
    # Open the file and read each line
    with open("songs.json", "r") as file:
        for line in file:
            try:
                # Load the JSON data from the line into a dictionary
                song_data = json.loads(line)
                read_songs.append(song_data)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")
    # associated songs information digestion
    songs_with_meta = list()
    for song_id in songs:
        for song in read_songs:
            if song['data']['id'] == song_id:
                key_info = {"title" : None, "author": None, "copyright": None, "arrangement": None}
                key_info['author'] = song['data']['attributes']['author']
                key_info['copyright'] = song['data']['attributes']['copyright']
                key_info['title'] = song['data']['attributes']['title']
                for arrangement in pco.iterate(f"/services/v2/songs/{song_id}/arrangements"):
                    this_arr = arrangement['data']['attributes']['name']
                    if this_arr != "Default Arrangement":
                        key_info['arrangement'] = this_arr
                        break
                songs_with_meta.append(key_info)
    return songs_with_meta


def find_spotify_songs(songs, next_sun, playlist_name, playlist_id):
    print("Connecting to spotify...")
    sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        scope="playlist-modify-public",
        redirect_uri="http://localhost:3000",
        client_id=spot_id,
        client_secret=spot_secret,
        cache_path=".cache"
    ))
    print("Connected!")
    clear_spotify_playlist(sp, playlist_id)
    uris = []
    print("Undertaking song lookup.")
    if songs is not None:
        for song in songs:
            arrangement = song['arrangement']
            author = song['author']
            copyright = song['copyright']
            title = song['title'].strip()
            print(f"Song:\t{title} Author: {author} Copyright: {copyright} Arrangement: {arrangement}")
            query = ""
            if title.lower() in activate_unreleased:
                continue
            if arrangement is not None:
                if not verify_arrangement(arrangement):
                    arrangement = select_backup_arrangement(arrangement)
            # If we still don't have an arrangement, try to find one based on copyright
            if arrangement is None and copyright is not None:
                found_arrangement = False
                for artist in artist_library:
                    if artist in copyright.lower():
                        arrangement = artist
                        found_arrangement = True
                if not found_arrangement:
                    #Query is based on if we have an artist or not
                    if author is not None:
                        query = f"{title} {author}%20genre:christian"
                    else:
                        query = f"{title}%20genre:christian"
                else:
                    #Query is normal (arrangement)
                    query = f"{title} {arrangement}%20genre:christian"
            elif arrangement is not None:
                query = f"{title} {arrangement}"
            else:
                query = f"{title}%20genre:christian"
            if query == "":
                print("You stuffed up the logic. Look again")
                exit(401)
            
            #print(f"Search:\t{title}, Arrangement: {arrangement}, Author: {author}")
            #print(f"Query:\t{query}")
            results = sp.search(q=query, type="track",limit=15)
            
            selected_track = None
            selected_sim_score = 0
            for item in results['tracks']['items']:
                #print(item['name'])
                # This logic is for if we have an arrangement
                if arrangement is not None:
                    best_sim = 0
                    for artist in item["artists"]:
                        sim = string_similarity(artist['name'], arrangement)
                        #print(f"{artist['name']} and {arrangement} is {sim}")
                        if sim > best_sim:
                            best_sim = sim
                    if best_sim > selected_sim_score:
                        selected_sim_score = best_sim
                        selected_track = item
                elif author is not None:
                    best_sim = 0
                    for artist in item["artists"]:
                        sim = string_similarity(artist['name'], author)
                        #print(f"{artist['name']} and {author} is {sim}")
                        if sim > best_sim:
                            best_sim = sim
                    if best_sim > selected_sim_score:
                        selected_sim_score = best_sim
                        selected_track = item
                # Special case, do a track only search
                elif arrangement is None and author is None:
                    curr_title = item['name']
                    sim = string_similarity(curr_title, title)
                    if sim > selected_sim_score:
                        selected_sim_score = sim
                        selected_track = item
                else:
                    print("I have no idea how we got here! Continuing")
                    continue
            if arrangement is None and author is None:
                tidied_title = selected_track['name'].split('-')[0].strip().lower()
                #print(f"{tidied_title}, {title}, {string_similarity(tidied_title,title)}")
                if string_similarity(tidied_title, title.lower()) > 0.9:
                    uris.append(selected_track['uri'])
                else:
                    #answer = input(f"Do you want to add: {selected_track['name']} by {selected_track['artists'][0]['name']} ? (y/n)").lower()
                    answer = 'n'
                    if answer == 'y':
                        uris.append(selected_track['uri'])
                    else:
                        print(f"Cant find song: {title}")
                        continue
            else:
                uris.append(selected_track['uri'])
            print(f"Chosen:\t{selected_track['name']}, {selected_track['artists'][0]['name']}")
        #print(uris)
        # No need to create a playlist for every sunday
        #playlist = sp.user_playlist_create("weirdoliam", f"{playlist_name}", True, False, f"Dynamic Playlist for {playlist_name}. This will be updatd weekly automatically on monday ay 11:00pm")
        #print(f"{playlist_name} - ID: {playlist_id}")
        sp.user_playlist_add_tracks("weirdoliam", playlist_id, uris, 0)
        print(f"Success updating playlist: {playlist_name}!\n")

def clear_spotify_playlist(sp, pl_id):
    print("Wiping Playlist")
    playlist = sp.user_playlist('weirdoliam', pl_id)
    uris = []
    for track in playlist['tracks']['items']:
        uris.append(track['track']['uri'])
    sp.user_playlist_remove_all_occurrences_of_tracks('weirdoliam',pl_id,uris)
    print("Wiped.")

def string_similarity(str1, str2):
    # Calculate the Levenshtein distance between the two strings
    distance = Levenshtein.distance(str1, str2)
    # Calculate the maximum length of the two strings
    max_len = max(len(str1), len(str2))
    # Calculate the similarity as a ratio of the distance to the maximum length
    similarity = 1 - (distance / max_len)
    return similarity

def verify_arrangement(arrangement):
    if arrangement.lower() in artist_library:
        return True
    else:
        return False

def select_backup_arrangement(arrangement):
    for act_artist in activate_authors:
        if act_artist in arrangement.lower():
            return "Activate Music"
    for eqw_artist in equippers_authors:
        if eqw_artist in arrangement.lower():
            return "Equippers"
    return None
    
if __name__ == "__main__":
    main()