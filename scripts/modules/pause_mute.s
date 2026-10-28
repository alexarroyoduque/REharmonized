.syntax unified
.cpu arm7tdmi
.thumb
.text
.balign 4
.global pause_stub, resume_stub, volume_stub

.thumb_func
pause_stub:
    push {lr}
    cmp r4, #4
    bne stop_effect
    ldr r0, [r5]
    bl dirty_bgm_tracks
    pop {pc}
stop_effect:
    ldr r0, [r5]
    bl original_stop
    pop {pc}

.thumb_func
resume_stub:
    push {lr}
    cmp r4, #4
    bne continue_player
    ldr r0, [r5]
    bl dirty_bgm_tracks
continue_player:
    ldr r0, [r5]
    bl original_continue
    pop {pc}

.thumb_func
dirty_bgm_tracks:
    ldrb r1, [r0, #8]
    ldr r2, [r0, #44]
    cmp r1, #0
    beq dirty_done
dirty_next:
    ldrb r3, [r2]
    movs r0, #128
    tst r3, r0
    beq dirty_skip
    movs r0, #3
    orrs r3, r0
    strb r3, [r2]
dirty_skip:
    adds r2, #80
    subs r1, #1
    bne dirty_next
dirty_done:
    bx lr

.thumb_func
volume_stub:
    ldr r0, paused_flag
    ldrh r0, [r0]
    cmp r0, #0
    beq original_volume
    ldr r0, bgm_tracks
    cmp r5, r0
    blo original_volume
    ldr r0, bgm_tracks_end
    cmp r5, r0
    bhs original_volume
    movs r0, #0
    strb r0, [r4, #2]
    strb r0, [r4, #3]
    bx lr
original_volume:
    ldrb r1, [r4, #18]
    movs r0, #20
    ldrsb r2, [r4, r0]
    movs r3, #128
    ldr r0, volume_return
    bx r0

.thumb_func
original_stop:
    ldr r3, stop_address
    bx r3
.thumb_func
original_continue:
    ldr r3, continue_address
    bx r3

.balign 4
paused_flag:       .word 0x030021A8
bgm_tracks:        .word 0x030021D0
bgm_tracks_end:    .word 0x03002400
volume_return:    .word 0x080BBF35
stop_address:     .word 0x080BCAE5
continue_address: .word 0x080BC255
