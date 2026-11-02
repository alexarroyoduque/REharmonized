.syntax unified
.cpu arm7tdmi
.thumb
.text
.balign 4
.global collection_pause_stub, collection_resume_stub

.thumb_func
collection_pause_stub:
    push {r4, r5, lr}
    ldr r5, player_table_effects
    movs r4, #3
pause_stop_effects:
    ldr r0, [r5]
    bl 0x080BCAE4
    adds r5, #12
    subs r4, #1
    bne pause_stop_effects
    ldr r0, bgm_player
    movs r1, #0x7F
    movs r2, #0
    bl 0x080BD274
    pop {r4, r5, pc}

.thumb_func
collection_resume_stub:
    push {r0, r1, r4, lr}
    ldr r0, bgm_player
    movs r1, #0x7F
    movs r2, #1
    lsls r2, r2, #8
    bl 0x080BD274
    pop {r0, r1}
    bl 0x080BC480
    pop {r4, pc}

.balign 4
player_table_effects: .word 0x081A6B38
bgm_player:          .word 0x03004FC0
 