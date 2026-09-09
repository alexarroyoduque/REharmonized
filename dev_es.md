# Notas de desarrollo

## Herramientas
- python 3: scripting
- agbplay (agbplay-gui / agbplay-nc): identificar los IDs de las canciones, escuchar las canciones de reemplazo antes/después de la inyección
- mGBA: emulador (también usado con `-g` como servidor GDB para depuración en vivo)
- gdb: se conecta al servidor GDB de mGBA (`target remote localhost:2345`) para encontrar/validar los puntos de parcheo (p. ej. la rutina de pausa, la resolución del ID de canción) antes de aplicar un fix definitivo en un script
- Audacity: recortar/ajustar los puntos de bucle de los WAV antes de pasarlos a los scripts de inyección
- Homebrew: instalar las herramientas de abajo (`brew install arm-none-eabi-binutils arm-none-eabi-gcc`)
- arm-none-eabi-as / arm-none-eabi-objcopy: ensamblan el stub ARM de arranque usado por `add_credits_screen.py` (`brew install arm-none-eabi-binutils`)

### Dependencias
- Pillow (`pip install pillow`): única dependencia de terceros usada en el proyecto (renderizado de imágenes + conversión a bitmap Modo 3 en `add_credits_screen.py`). Todo lo demás en los scripts es librería estándar de Python 3 (`argparse`, `struct`, `wave`, `subprocess`, `pathlib`, etc.).
- Instálala una vez para el `python3` que uses para ejecutar los scripts (no hace falta venv, aunque también funciona dentro de uno):
  ```sh
  python3 -m pip install --user --break-system-packages pillow
  ```

## Proceso de desarrollo

Todo el código de los scripts ha sido escrito por una IA bajo mi supervisión.

### 1. Objetivo
Sustituir las canciones de Harmony of Dissonance por melodías que suenen mejor.

### 2. Canciones de Circle of the Moon y Aria of Sorrow portadas a Harmony
Al principio pensé en utilizar las canciones de Aria of Sorrow y de Circle of the Moon para sustituir las canciones de Harmony of Dissonance.

Esto resultó ser un éxito porque los tres juegos de Castlevania en GBA comparten el mismo sistema de audio MP2K (también conocido como M4A / "Sappy"). 
Para conseguirlo primero necesitaba cómo se identificaban en memoria las pistas musicales de cada juego. Para identificar las canciones utilicé agbplay.
./build/src/agbplay-gui/agbplay-gui

Después fue necesario crear un script que sustituyera las canciones de Harmony por las canciones de Aria o Circle.

Esto se puede encontrar en los scripts:
```sh
python3 port_circle_song_to_harmony.py rom-harmony.gba rom-circle.gba rom-output.gba

python3 port_aria_song_to_harmony.py rom-harmony.gba rom-aria.gba rom-output.gba

python3 inject_music_to_harmony_from_aria_circle.py rom-harmony.gba config_from_aria_circle.txt rom-output.gba --aria rom-aria.gba --circle rom-circle.gba
```

```txt
# Harmony of dissonance 0001 <- Aria of sorrow 0004
aria 1 4

# Harmony of dissonance 0002 <- Circle of the moon 0008
circle 2 8
```

### 3. Aria of Sorrow Streamed Audio

Cambiar las canciones de Harmony por las de Aria o Circle estaba bien pero mataba la esencia musical de Harmony of Dissonance. Entonces encontré la guía de Rexius55 en [romhacking.net](https://www.romhacking.net/documents/927).
Rexius55 consiguió que cualquier música pudiera sonar en Aria of Sorrow.

Entonces pensé que, como ya había migrado con éxito canciones de Aria a Harmony, podría usar la guía de Rexius55 para crear canciones para Aria y luego pasarlas a Harmony.

### 4. REharmonized
Yo no tengo nociones musicales para convertir las pistas originales de Harmony en melodías que sonaran con gran calidad. Así que utilicé versiones creadas por la comunidad que ya sonaban bien.

Con Audacity ajusté las melodías para recortar los tramos del bucle que debían repetirse.

A partir de aquí hice un script que convertía las canciones de la comunidad para que sonaran como en Aria y luego las portaba a Harmony.

```sh
python3 wav_to_harmony_pause-not-resume-music.py rom-harmony.gba wav_config.txt rom-output.gba
```

El resultado fue un éxito. Tal y como indica Rexius55 en su guía, hay una variable de TEMPO que hay que ajustar manualmente para que los bucles encajen bien en cada canción, y tuve que trabajar bastante en ello.
El script genera sugerencias de gap negativo para ayudar a ajustar el TEMPO. Detecté que los valores negativos hacían las transiciones de los bucles más suaves.

### 5. Solo 32MB

Algunas composiciones quedaron fuera por motivos de espacio: una ROM de GBA solo puede almacenar 32MB. Quedaron fuera las que consideré que menos afectaban a la experiencia de juego principal.

Canciones descartadas:
  01. title screen part 1
  02. title screen part 2
  19. game over
  23. successor of fate (Juste Belmont's theme) - variation
  24. pitch-dark door
  26. VK2K2 - Vampire Killer 2002
  27. game over Simon

### 6. Problemas con la pausa
En el juego original, al pausar el juego la música se silencia. Pero al aplicar el parche REharmonized la música sigue sonando.

Este cambio fue intencionado por el siguiente motivo: las canciones modificadas suenan en un único hilo. El juego original apaga el audio y, al quitar la pausa, sigue sonando desde donde se quedó, porque en el original hay varios "instrumentos" en diferentes hilos de ejecución sonando a la vez. En el script original que hice, al pausar el juego la música dejaba de sonar, pero al quitar la pausa no se escuchaba de nuevo hasta que terminaba su propio bucle.
Esta parte me llevó bastante tiempo resolverla. Con ayuda de la IA, al principio opté por trocear las canciones, pero cada X segundos se notaba una ligera aspereza que no me gustaba.
Finalmente, con ayuda de la IA y el depurador conectado al emulador mGBA, encontré el punto exacto donde se activa la pausa para alterar ligeramente cómo funciona el audio en ese momento y así poder disfrutar del juego sin problemas. La única diferencia respecto al original es que la música sigue sonando durante la pausa.
```sh
python3 wav_to_harmony_pause_fix.py rom-harmony.gba wav_config.txt rom-output.gba
```

### 7. Normalización del audio
Las pistas modificadas sonaban con poco volumen, así que el script se encarga de normalizarlas para que suenen más altas.

### 8. Sala de guardado y prioridades
En la sala de guardar partida suena un latido (id 43). El problema es que si sales de la sala mientras el sonido está sonando, este sigue sonando durante la transición y, al terminar, la canción que debería sonar a continuación no suena.

Esto ocurre porque los sonidos tienen prioridad en el juego. El sonido de guardado tiene prioridad 50, igual que las canciones del juego original, así que el ajuste hace que las nuevas canciones modificadas también tengan prioridad 50. Si la prioridad de las canciones fuera superior a 50, el sonido de guardado no se escucharía al entrar en la sala.

### 9. Canciones duplicadas
Las canciones 15, 16 y 17 corresponden a bucles de batallas contra jefes. En el juego original cada bucle es diferente, pero en REharmonized las tres pistas son iguales, con los 3 bucles combinados en una sola. El script detecta que las canciones son iguales y evita duplicarlas. Gracias a este ahorro de espacio entró en el catálogo la canción 23, successor of fate (Juste Belmont's theme) - variation (a guitarra eléctrica de TristanMachinima).

### 10. Créditos
Script final que coloca una pantalla de créditos al inicio del juego.

```sh
python3 add_credits_screen.py rom-reharmonized-test6.gba rom-reharmonized-test6-final.gba
```

### 11. Test final
Tras varias pruebas con el parche aplicado, he conseguido que no contenga errores. Todas las pruebas se han realizado con emulador:
- He completado el juego entero
- He conseguido el final malo
- He conseguido el final bueno
- He muerto
- He cargado partida
- He pausado el juego y reanudado la partida

### 12. Compatibilidad con "Visual Improvement" (1.0.1)
A petición de la comunidad REharmonized se hace compatible con "Visual Improvement 1.2.7" de Pemburu Vampir con un parche extra.
Primero se aplica "Visual Improvement" y después REharmonized. 

### 13. Compatibilidad con "Visual Improvement" (1.1.0)
Al hacer algunas pruebas detecto que si se aplica primero el parche estándar de REharmonized y después "Visual Improvement" el juego funciona correctamente por lo que se elimina el parche secundario de la 1.0.1.

### 14. Normalizado manual de música (1.1.0)
Algunas composiciones suenan un poco saturadas con la normalización automática del audio modificado por lo que se agrega la posibilidad en el archivo config de controlar dicho aumento del volumen.

```
4   "../music/04 prologue edit.wav" 100 0.2
```
