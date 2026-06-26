import os
import re
import json
import shutil
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.id3 import ID3

# Paths
BASE_DIR = r"C:\Users\pidi\Music\Hörspiele und Hörbücher\DDF"
DR3I_DIR = os.path.join(BASE_DIR, "DiE-DR3i")
SPECIALS_DIR = os.path.join(BASE_DIR, "Die drei ___")

WEBAPP_DIR = r"C:\Users\pidi\.gemini\antigravity\scratch\FragezeichenArchiv"
COVERS_DIR = os.path.join(WEBAPP_DIR, "covers")

def get_natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def extract_embedded_cover(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.flac':
        try:
            audio = FLAC(filepath)
            if audio.pictures:
                pic = audio.pictures[0]
                return pic.data, pic.mime
        except:
            pass
    elif ext == '.mp3':
        try:
            audio = ID3(filepath)
            for tag in audio.keys():
                if tag.startswith("APIC:"):
                    apic = audio[tag]
                    return apic.data, apic.mime
        except:
            pass
    elif ext == '.m4a':
        try:
            audio = MP4(filepath)
            if "covr" in audio:
                covr = audio["covr"][0]
                # covr can be bytes directly
                return covr, "image/jpeg"
        except:
            pass
    return None, None

def save_cover(c_id, folder_path):
    os.makedirs(COVERS_DIR, exist_ok=True)
    
    # 0. Check if cover file already exists in COVERS_DIR
    for ext in ('.jpg', '.png', '.jpeg'):
        existing_path = os.path.join(COVERS_DIR, f"{c_id}{ext}")
        if os.path.exists(existing_path):
            return f"covers/{c_id}{ext}"
            
    # 1. Search for files like Cover.jpg, folder.png, etc.
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d != '__MACOSX' and not d.startswith('__')]
        for f in files:
            if f.startswith('._'):
                continue
            if f.lower() in ('cover.jpg', 'cover.png', 'folder.jpg', 'folder.png', 'front.jpg', 'front.png'):
                ext = os.path.splitext(f)[1].lower()
                dest_name = f"{c_id}{ext}"
                dest_path = os.path.join(COVERS_DIR, dest_name)
                try:
                    shutil.copy(os.path.join(root, f), dest_path)
                    return f"covers/{dest_name}"
                except Exception as e:
                    print(f"Error copying cover file: {e}")
                    
    # 2. Extract embedded cover from first audio file
    audio_files = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d != '__MACOSX' and not d.startswith('__')]
        for f in files:
            if f.startswith('._'):
                continue
            if f.lower().endswith(('.mp3', '.flac', '.m4a')):
                audio_files.append(os.path.join(root, f))
                
    if audio_files:
        audio_files.sort(key=get_natural_sort_key)
        first_file = audio_files[0]
        data, mime = extract_embedded_cover(first_file)
        if data:
            ext = ".png" if "png" in mime.lower() else ".jpg"
            dest_name = f"{c_id}{ext}"
            dest_path = os.path.join(COVERS_DIR, dest_name)
            try:
                with open(dest_path, "wb") as f:
                    f.write(data)
                return f"covers/{dest_name}"
            except Exception as e:
                print(f"Error writing extracted cover: {e}")
                
    return "https://placehold.co/300"

def get_audio_info(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    title = os.path.splitext(os.path.basename(filepath))[0].replace('_', ' ').replace('-', ' ').strip()
    duration = 0.0
    
    try:
        if ext == '.flac':
            audio = FLAC(filepath)
            duration = audio.info.length
            if 'title' in audio:
                title = audio['title'][0]
        elif ext == '.mp3':
            audio = MP3(filepath)
            duration = audio.info.length
            # Try to get title from ID3
            try:
                id3 = ID3(filepath)
                if 'TIT2' in id3:
                    title = id3['TIT2'].text[0]
            except:
                pass
        elif ext == '.m4a':
            audio = MP4(filepath)
            duration = audio.info.length
            if '\xa9nam' in audio:
                title = audio['\xa9nam'][0]
    except Exception as e:
        print(f"Error reading info for {filepath}: {e}")
        
    return {
        "title": title,
        "duration": int(duration * 1000), # in ms
        "size": os.path.getsize(filepath),
        "filename": os.path.basename(filepath)
    }

def build_dr3i_metadata():
    print("Building Die dr3i metadata...")
    if not os.path.exists(DR3I_DIR):
        print(f"DR3I directory not found: {DR3I_DIR}")
        return
        
    episodes = []
    folders = []
    
    for entry in os.scandir(DR3I_DIR):
        if entry.is_dir():
            # Parse number
            match = re.match(r'^(\d{2,3})', entry.name)
            if match:
                num = int(match.group(1))
            else:
                num = 9  # e.g., Bonus
            folders.append((num, entry.path, entry.name))
            
    # Sort folders naturally
    folders.sort(key=lambda x: x[0])
    
    for num, path, name in folders:
        print(f"  Processing: {name}")
        c_id = f"D_{num}"
        cover_url = save_cover(c_id, path)
        
        # Scan for audio files recursively
        audio_files = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d != '__MACOSX' and not d.startswith('__')]
            for f in files:
                if f.startswith('._'):
                    continue
                if f.lower().endswith(('.mp3', '.flac', '.m4a')):
                    audio_files.append(os.path.join(root, f))
                    
        if not audio_files:
            continue
            
        audio_files.sort(key=get_natural_sort_key)
        
        tracks = []
        total_duration = 0
        
        for f in audio_files:
            info = get_audio_info(f)
            tracks.append(info)
            total_duration += info["duration"]
            
        # Parse clean title
        title = name
        # Strip number prefix, e.g. "01 - Das Seeungeheuer" -> "Das Seeungeheuer"
        title = re.sub(r'^\d{2,3}\s*-\s*', '', title).strip()
        # Strip "Bonus - "
        title = re.sub(r'^Bonus\s*-\s*', '', title, flags=re.IGNORECASE).strip()
        
        episodes.append({
            "id": c_id,
            "nummer": num,
            "titel": title,
            "autor": "DiE DR3i",
            "beschreibung": f"Folge {num} der Serie Die dr3i.",
            "gesamtdauer": total_duration,
            "links": {
                "cover": cover_url
            },
            "folder": name, # save folder name to map in uploader
            "medien": [{
                "tracks": [{
                    "titel": t["title"],
                    "start": 0, # placeholders, duration is saved in tracks
                    "end": t["duration"]
                } for t in tracks]
            }],
            "tracks": tracks # save direct track info
        })
        
    output_path = os.path.join(WEBAPP_DIR, "dr3imetadata.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"serie": episodes}, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(episodes)} episodes to {output_path}")

def build_specials_metadata():
    print("Building Specials metadata...")
    if not os.path.exists(SPECIALS_DIR):
        print(f"Specials directory not found: {SPECIALS_DIR}")
        return
        
    episodes = []
    folders = []
    
    for entry in os.scandir(SPECIALS_DIR):
        if entry.is_dir():
            # Check if it starts with 3 digits followed by underscore (official episodes)
            if re.match(r'^\d{3}_', entry.name):
                continue
            folders.append((entry.path, entry.name))
            
    # Sort folders alphabetically
    folders.sort(key=lambda x: get_natural_sort_key(x[1]))
    
    for idx, (path, name) in enumerate(folders, 1):
        print(f"  Processing: {name}")
        c_id = f"S_{idx}"
        cover_url = save_cover(c_id, path)
        
        # Scan for audio files recursively
        audio_files = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d != '__MACOSX' and not d.startswith('__')]
            for f in files:
                if f.startswith('._'):
                    continue
                if f.lower().endswith(('.mp3', '.flac', '.m4a')):
                    audio_files.append(os.path.join(root, f))
                    
        if not audio_files:
            continue
            
        audio_files.sort(key=get_natural_sort_key)
        
        tracks = []
        total_duration = 0
        
        for f in audio_files:
            info = get_audio_info(f)
            tracks.append(info)
            total_duration += info["duration"]
            
        episodes.append({
            "id": c_id,
            "nummer": idx,
            "titel": name,
            "autor": "Die drei ???",
            "beschreibung": f"Sonderfolge / Special: {name}.",
            "gesamtdauer": total_duration,
            "links": {
                "cover": cover_url
            },
            "folder": name, # save folder name to map in uploader
            "medien": [{
                "tracks": [{
                    "titel": t["title"],
                    "start": 0,
                    "end": t["duration"]
                } for t in tracks]
            }],
            "tracks": tracks # save direct track info
        })
        
    output_path = os.path.join(WEBAPP_DIR, "specialsmetadata.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"serie": episodes}, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(episodes)} episodes to {output_path}")

if __name__ == '__main__':
    build_dr3i_metadata()
    build_specials_metadata()
