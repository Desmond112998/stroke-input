"""Print key names as reported by the keyboard library."""
import keyboard
import time

print("Press keys to see their names (10 seconds)...")
print("Try: backspace, delete, escape, page up, page down")
print()

def on_key(e):
    if e.event_type == "down":
        print(f"  name={e.name!r}  scan_code={e.scan_code}")

keyboard.hook(on_key)
time.sleep(10)
keyboard.unhook_all()
print("Done.")
