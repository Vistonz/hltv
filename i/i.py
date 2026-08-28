import re
import json
import os

def extract_player_data():
    file_path = r"c:\Users\10725\Desktop\hltv\i\Counter-Strike Player statistics database _ HLTV.org.html"
    output_path = r"c:\Users\10725\Desktop\hltv\i\players.json"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Reading {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # The user's regex suggestion was: <a href="/stats/players/(.*?)>"
    # Given HLTV URL structure: /stats/players/ID/NAME
    # We extract ID and Name.
    pattern = r'href="/stats/players/(\d+)/([^"]+)"'
    matches = re.findall(pattern, content)

    # Use a set to avoid duplicates as many players might appear multiple times
    unique_players = {}
    for player_id, player_name in matches:
        if player_id not in unique_players:
            unique_players[player_id] = player_name

    # Transform to list of dicts as requested (JSON format)
    result = [{"id": pid, "name": pname} for pid, pname in unique_players.items()]

    print(f"Extracted {len(result)} unique players.")
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    
    print(f"Data saved to {output_path}")

if __name__ == "__main__":
    extract_player_data()
