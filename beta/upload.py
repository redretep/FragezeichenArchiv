import os
import re
import sys
import json
import time
import urllib.parse
import http.client

# Target directories and settings
DEFAULT_MUSIC_DIR = r"C:\Users\pidi\Music\Hörspiele und Hörbücher\DDF\Die drei ___"
METADATA_FILE = "fileditch_tracks.json"
FILEDITCH_HOST = "new.fileditch.com"
UPLOAD_URL_PATH = "/upload.php?filename="

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"

def get_natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def get_audio_files(folder_path):
    audio_files = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d != '__MACOSX' and not d.startswith('__')]
        for f in files:
            if f.startswith('._'):
                continue
            if f.lower().endswith(('.mp3', '.flac', '.m4a')):
                audio_files.append(os.path.join(root, f))
    return audio_files


def extract_episode_number(folder_name):
    # Match patterns like "001", "1", "Folge 184", "Nr. 05"
    match = re.search(r'(?:folge|nr|no)?\.?\s*(\d{1,3})(?:\D|$)', folder_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def upload_file_raw(filepath):
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    
    # URL encode filename
    url_path = UPLOAD_URL_PATH + urllib.parse.quote(filename)
    
    conn = http.client.HTTPSConnection(FILEDITCH_HOST, timeout=60)
    
    conn.putrequest("POST", url_path)
    conn.putheader("Content-Type", "application/octet-stream")
    conn.putheader("Content-Length", str(filesize))
    conn.endheaders()
    
    chunk_size = 512 * 1024  # 512 KB chunks for smooth progress updates
    uploaded = 0
    start_time = time.time()
    
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            conn.send(chunk)
            uploaded += len(chunk)
            
            # Progress bar calculation
            percent = (uploaded / filesize) * 100
            elapsed = time.time() - start_time
            speed = uploaded / elapsed if elapsed > 0 else 0
            eta = (filesize - uploaded) / speed if speed > 0 else 0
            
            bar_len = int(percent / 3.33)  # 30 chars wide
            bar = '#' * bar_len + '-' * (30 - bar_len)
            
            print(f"\r[{bar}] {percent:5.1f}% | {format_size(uploaded)}/{format_size(filesize)} | {format_size(speed)}/s | ETA: {int(eta)}s", end="", flush=True)
            
    response = conn.getresponse()
    response_data = response.read().decode("utf-8")
    conn.close()
    
    if response.status != 200:
        raise Exception(f"HTTP Error {response.status}: {response_data}")
        
    try:
        res_json = json.loads(response_data)
        if not res_json.get("success"):
            raise Exception(res_json.get("error", "Unknown server error"))
        return res_json
    except json.JSONDecodeError:
        raise Exception(f"Invalid JSON response: {response_data}")

def load_metadata_maps():
    folder_to_metadata = {}
    
    # 1. Load dr3imetadata.json
    try:
        with open("dr3imetadata.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for ep in data["serie"]:
                folder_to_metadata[ep["folder"]] = {
                    "id": ep["id"],
                    "num": ep["nummer"],
                    "category": "dr3i",
                    "title": ep["titel"]
                }
    except:
        pass
        
    # 2. Load specialsmetadata.json
    try:
        with open("specialsmetadata.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            for ep in data["serie"]:
                folder_to_metadata[ep["folder"]] = {
                    "id": ep["id"],
                    "num": ep["nummer"],
                    "category": "special",
                    "title": ep["titel"]
                }
    except:
        pass
        
    return folder_to_metadata

def main():
    print("==================================================")
    print("       FragezeichenArchiv FileDitch Uploader       ")
    print("==================================================")
    
    music_dir = DEFAULT_MUSIC_DIR
    if len(sys.argv) > 1:
        music_dir = sys.argv[1]
        
    if not os.path.exists(music_dir):
        print(f"Error: Music directory not found: {music_dir}")
        print("Please check the path or pass it as an argument.")
        sys.exit(1)
        
    print(f"Scanning directory: {music_dir}")
    
    # Load metadata maps
    folder_to_metadata = load_metadata_maps()
    
    # Load existing metadata if it exists
    tracks_db = {}
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                tracks_db = json.load(f)
            print(f"Loaded existing database with {len(tracks_db)} episodes/specials.")
        except Exception as e:
            print(f"Warning: Could not read {METADATA_FILE}: {e}. Creating new database.")
            
    # Walk directory to find episodes
    folders = []
    
    # Check if music_dir contains subdirectories Die drei ___ and/or DiE-DR3i
    subdirs_to_scan = []
    has_sub = False
    for name in os.listdir(music_dir):
        path = os.path.join(music_dir, name)
        if os.path.isdir(path) and name in ('Die drei ___', 'DiE-DR3i'):
            subdirs_to_scan.append((path, name))
            has_sub = True
            
    if not has_sub:
        subdirs_to_scan.append((music_dir, ""))
        
    for scan_path, scan_type in subdirs_to_scan:
        for entry in os.scandir(scan_path):
            if entry.is_dir():
                folder_name = entry.name
                
                # Check metadata mapping first
                meta = folder_to_metadata.get(folder_name)
                if meta:
                    folders.append({
                        "id": meta["id"],
                        "num": meta["num"],
                        "category": meta["category"],
                        "path": entry.path,
                        "folder_name": folder_name,
                        "title": meta["title"]
                    })
                else:
                    # Check if it's an official episode (starts with 3 digits followed by underscore or space)
                    match = re.match(r'^(\d{3})_', folder_name)
                    if match:
                        num = int(match.group(1))
                        folders.append({
                            "id": str(num),
                            "num": num,
                            "category": "official",
                            "path": entry.path,
                            "folder_name": folder_name,
                            "title": folder_name[4:].replace('_', ' ')
                        })
                    else:
                        ep_num = extract_episode_number(folder_name)
                        if ep_num is not None:
                            folders.append({
                                "id": str(ep_num),
                                "num": ep_num,
                                "category": "official",
                                "path": entry.path,
                                "folder_name": folder_name,
                                "title": folder_name
                            })
                            
    # Sort folders
    def sort_key(x):
        cat_order = {"official": 0, "dr3i": 1, "special": 2}
        return (cat_order.get(x["category"], 3), x["num"])
        
    folders.sort(key=sort_key)
    
    print(f"Found {len(folders)} audiobook folder(s).")
    
    total_files_uploaded = 0
    
    try:
        for candidate in folders:
            c_id = candidate["id"]
            folder_path = candidate["path"]
            folder_name = candidate["folder_name"]
            
            # Find all audio files in the folder
            audio_files = get_audio_files(folder_path)
            
            if not audio_files:
                continue
                
            # Sort files naturally so tracks play in order
            audio_files.sort(key=get_natural_sort_key)
            
            ep_key = c_id
            
            # Check if this episode is already fully uploaded
            existing_tracks = tracks_db.get(ep_key, [])
            if len(existing_tracks) == len(audio_files):
                # Verify matches by filename and size (roughly)
                matches_all = True
                for idx, filepath in enumerate(audio_files):
                    fname = os.path.basename(filepath)
                    fsize = os.path.getsize(filepath)
                    
                    if idx >= len(existing_tracks):
                        matches_all = False
                        break
                    
                    ex_track = existing_tracks[idx]
                    if ex_track.get("filename") != fname or ex_track.get("size") != fsize:
                        matches_all = False
                        break
                
                if matches_all:
                    print(f"Episode {ep_key} ('{folder_name}') already uploaded. Skipping.")
                    continue
            
            print(f"\nProcessing Episode {ep_key}: {folder_name}")
            print(f"Found {len(audio_files)} track(s) to upload.")
            
            ep_tracks = []
            for idx, filepath in enumerate(audio_files):
                filename = os.path.basename(filepath)
                filesize = os.path.getsize(filepath)
                
                # Check if this specific track was already uploaded in a previous incomplete run
                if idx < len(existing_tracks):
                    ex_track = existing_tracks[idx]
                    if ex_track.get("filename") == filename and ex_track.get("size") == filesize:
                        print(f"  Track {idx+1}/{len(audio_files)} already uploaded: {filename}")
                        ep_tracks.append(ex_track)
                        continue
                
                print(f"  Uploading track {idx+1}/{len(audio_files)}: {filename}")
                
                retry_count = 3
                success = False
                res_data = None
                
                for attempt in range(1, retry_count + 1):
                    try:
                        res_data = upload_file_raw(filepath)
                        success = True
                        break
                    except Exception as e:
                        print(f"\n    [Attempt {attempt}/{retry_count}] Upload failed: {e}")
                        if attempt < retry_count:
                            time.sleep(2)
                            
                if not success:
                    print(f"\nFATAL ERROR: Failed to upload track {filename} after {retry_count} attempts. Stopping.")
                    sys.exit(1)
                    
                print("\n    Upload complete!")
                
                # FileDitch returns URL in 'url'
                direct_url = res_data.get("url")
                
                track_meta = {
                    "filename": filename,
                    "url": direct_url,
                    "size": filesize
                }
                ep_tracks.append(track_meta)
                total_files_uploaded += 1
                
                # Intermediate save of database to prevent data loss on crash
                tracks_db[ep_key] = ep_tracks
                with open(METADATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(tracks_db, f, indent=2, ensure_ascii=False)
            
            # Save at the end of the episode
            tracks_db[ep_key] = ep_tracks
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(tracks_db, f, indent=2, ensure_ascii=False)
                
        print("\n==================================================")
        print("Upload process completed successfully!")
        print(f"Total new tracks uploaded: {total_files_uploaded}")
        print(f"Database updated and saved to '{os.path.abspath(METADATA_FILE)}'")
        print("==================================================")
        
    except KeyboardInterrupt:
        print("\nUpload process interrupted by user. Progress saved.")
        sys.exit(0)

if __name__ == "__main__":
    main()
