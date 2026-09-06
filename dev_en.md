# Developer notes

## Tools
- python 3: scripting
- agbplay (agbplay-gui / agbplay-nc): identify song IDs, audition replacement songs before/after injection
- mGBA: emulator (also used with `-g` as a GDB server for live debugging)
- gdb: attaches to mGBA's GDB server (`target remote localhost:2345`) to find/validate patch points (e.g. the pause routine, song-ID resolution) before baking a fix into a script
- Audacity: trim/align WAV loop points before feeding them to the injection scripts
- Homebrew: install the tools below (`brew install arm-none-eabi-binutils arm-none-eabi-gcc`)
- arm-none-eabi-as / arm-none-eabi-objcopy: assemble the ARM boot stub used by `add_credits_screen.py` (`brew install arm-none-eabi-binutils`)

### Dependencies
- Pillow (`pip install pillow`): only third-party Python package used in the project (image rendering + Mode 3 bitmap conversion in `add_credits_screen.py`). Everything else in the scripts is Python 3 stdlib (`argparse`, `struct`, `wave`, `subprocess`, `pathlib`, etc.).
- Install once for whichever `python3` you use to run the scripts (no venv required, though it also works inside one):
  ```sh
  python3 -m pip install --user --break-system-packages pillow
  ```

## Development process

All of the scripts' code was written by an AI under my supervision.

### 1. Goal
Replace the songs of Harmony of Dissonance with melodies that sound better.

### 2. Circle of the Moon & Aria of Sorrow songs ported to Harmony
At first I thought about using songs from Aria of Sorrow and Circle of the Moon to replace the ones in Harmony of Dissonance.

This turned out to be a success because all three GBA Castlevania games share the same MP2K audio engine (also known as M4A / "Sappy").
To pull this off, I first needed to know how each game's music tracks were identified in memory. To identify the songs I used agbplay:
```sh
./build/src/agbplay-gui/agbplay-gui
```

Afterwards it was necessary to create a script that replaced Harmony's songs with Aria's or Circle's.

This can be found in the scripts:
```sh
python3 port_circle_song_to_harmony.py rom-harmony.gba rom-circle.gba rom-output.gba

python3 port_aria_song_to_harmony.py rom-harmony.gba rom-aria.gba rom-output.gba

python3 inject_music_to_harmony_from_aria_circle.py rom-harmony.gba config_from_aria_circle.txt rom-output.gba --aria rom-aria.gba --circle rom-circle.gba
```

```txt
# Harmony of Dissonance 0001 <- Aria of Sorrow 0004
aria 1 4

# Harmony of Dissonance 0002 <- Circle of the Moon 0008
circle 2 8
```

### 3. Aria of Sorrow Streamed Audio

Swapping Harmony's songs for Aria's or Circle's was fine, but it killed Harmony of Dissonance's musical identity. Then I found Rexius55's guide on [romhacking.net](https://www.romhacking.net/documents/927).
Rexius55 managed to get any music to play in Aria of Sorrow.

So I figured that, since I had already successfully migrated songs from Aria to Harmony, I could use Rexius55's guide to create songs for Aria and then port them over to Harmony.

### 4. REharmonized
I don't have the musical knowledge to turn Harmony's original tracks into high-quality-sounding melodies myself. So I used community-made versions that already sounded good.

With Audacity I trimmed the melodies to grab the loop sections that needed to repeat.

From there I wrote a script that converted the community songs so they'd sound like Aria's, then ported them to Harmony.

```sh
python3 wav_to_harmony_pause-not-resume-music.py rom-harmony.gba wav_config.txt rom-output.gba
```

The result was a success. As Rexius55 points out in the guide, there's a TEMPO value that has to be tuned manually so each song's loop fits together well, and I had to put in quite a bit of work on that.
The script generates negative-gap suggestions to help tune the TEMPO. I found that negative values made loop transitions smoother.

### 5. Only 32MB

Some compositions were left out for space reasons: a GBA ROM can only hold 32MB. I left out the ones I judged would least affect the core gameplay experience.

Discarded songs:
  01. title screen part 1
  02. title screen part 2
  19. game over
  23. successor of fate (Juste Belmont's theme) - variation
  24. pitch-dark door
  26. VK2K2 - Vampire Killer 2002
  27. game over Simon

### 6. Pause problems
In the original game, pausing mutes the music. But with the REharmonized patch applied, the music keeps playing.

This change was intentional, for the following reason: the modified songs play on a single thread. The original game turns off the audio and, once unpaused, resumes exactly where it left off, because in the original there are several "instruments" playing on different execution threads at once. In the script I originally wrote, pausing the game stopped the music, but unpausing it wouldn't bring it back until its own loop finished.
This part took me quite a while to solve. With the AI's help, I initially tried splitting the songs into chunks, but every X seconds there was a slight roughness I didn't like.
Finally, with the AI's help and mGBA's debugger attached, I found the exact point where the pause is triggered, so I could slightly tweak how the audio behaves at that moment and enjoy the game without issues. The only difference from the original is that the music keeps playing during pause.

```sh
python3 wav_to_harmony_pause_fix.py rom-harmony.gba wav_config.txt rom-output.gba
```

### 7. Audio normalization
The modified tracks played back quietly, so the script takes care of normalizing the songs so they play louder.

### 8. Save room and priorities
A heartbeat sound plays in the save room (id 43). The problem is that if you leave the room while that sound is still playing, it keeps playing through the transition, and once it finishes, the song that should play next doesn't.

This happens because sounds have a priority in the game. The save sound has priority 50, same as the songs in the original game, so the fix makes the new modified songs also have priority 50. If the songs' priority were higher than 50, the save sound wouldn't be heard when entering the room.

### 9. Duplicate songs
Songs 15, 16 and 17 correspond to boss-battle loops. In the original game each loop is different, but in REharmonized all three tracks are the same, with the 3 loops combined into one. The script detects that the songs are identical and avoids duplicating them. Thanks to this space savings, song 23, successor of fate (Juste Belmont's theme) - variation (electric guitar by TristanMachinima), made it into the catalog.

### 10. Credits
Final script that adds a credits screen at the start of the game.

```sh
python3 add_credits_screen.py rom-reharmonized-test6.gba rom-reharmonized-test6-final.gba
```

### 11. Final test
After several rounds of testing with the patch applied, I got it to a state with no errors. All tests were carried out in an emulator:
- I fully completed the game
- I got the bad ending
- I got the good ending
- I died
- I loaded a saved game
- I paused and resumed the game
