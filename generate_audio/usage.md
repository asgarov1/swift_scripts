## Example usage:
```
python3 collect_foreign.py ../../german_a1/german_a1
python3 generate_audio_clips.py --lang de
```

---
## Troubleshooting
1. if missing a module:

```
  ! failed: No module named 'edge_tts'
```

make sure venv is activated (`source venv/bin/activate`)
and if still doesn't work try installing it:
```
python3 -m pip install edge-tts
```

---

If nothing else helps (e.g. something got corrupted when changing folder structure), delete venv and reinstall modules:
```
# delete venv
rm -rf venv

#recreate it
python3 -m venv venv
source venv/bin/activate

# reinstall the module
python3 -m pip install edge-tts
```
---

make start <path_to_folder> <language>
